import json
import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nre import m6_guidance_warmup_opening as probe
from nre.core import DataError, timestamp
from nre.m5_phase1b_audit import load
from nre.m6_guidance_revision import FREEZE, PROTOCOL, ROOT

DUMMY_PRICE = 918273.125
DUMMY_ID = 987654321001


class GuidanceWarmupOpeningTests(unittest.TestCase):
    def copy_inputs(self, root):
        protocol = load(ROOT / PROTOCOL)
        paths = {PROTOCOL, FREEZE, *protocol["input_canonical_sha256"],
                 *protocol["implementation_sha256_git_lf"], *probe.IMPLEMENTATION_PATHS}
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())

    def official(self, params, *, price=DUMMY_PRICE, trade_id=DUMMY_ID):
        return {"x": "Q", "z": "C", "c": ["Q"], "i": trade_id, "p": price,
                "t": (timestamp(params["start"]) + timedelta(seconds=1)).isoformat()}

    def test_exact_source_union_checks_52_openings_and_never_discloses_prices(self):
        cohort = probe.locked_cohort()
        expected = {(r["symbol"], r["reaction_session"]): r for r in cohort["events"]}
        self.assertEqual(len(expected), 52)
        self.assertEqual(sum(r["clean_window"] for r in expected.values()), 44)
        requested, private = [], []

        def fetch(endpoint, params):
            symbol = endpoint.split("/")[-2]
            event = expected[symbol, params["asof"]]
            probe.validate_trade_request(event, endpoint, params)
            self.assertEqual(params["feed"], "sip")
            self.assertEqual(params["limit"], 5000)
            self.assertEqual(timestamp(params["end"]) - timestamp(params["start"]), timedelta(seconds=60))
            requested.append((symbol, params["asof"]))
            return json.dumps({"symbol": symbol, "trades": [self.official(params)], "next_page_token": None}).encode()

        report = probe.run(ROOT, fetch, consume_opening=lambda event, price, commitment: private.append((event, price, commitment)))
        self.assertCountEqual(requested, expected)
        self.assertEqual((report["screened"], report["matched"], report["clean_matched"], report["requests"]), (52, 52, 44, 52))
        self.assertEqual(report["cohort_sha256"], cohort["cohort_sha256"])
        self.assertEqual(report["protocol_sha256"], probe.PROTOCOL_SHA256)
        self.assertEqual(report["dispositions"], {"verified_open": 52})
        self.assertEqual((report["closing_outcome_requests"], report["model_runs"]), (0, 0))
        self.assertEqual(len(private), 52)
        self.assertTrue(all(price == DUMMY_PRICE for _, price, _ in private))
        for row in report["events"]:
            self.assertRegex(row["opening_commitment_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(row["provider_request_sha256"]), 1)
            self.assertEqual(len(row["provider_response_sha256"]), 1)
        for forbidden in (str(DUMMY_PRICE), str(DUMMY_ID), '"p"', '"i"', '"price"', '"trades"', '"return"', '"bars"'):
            self.assertNotIn(forbidden, json.dumps(report))

    def test_missing_conflicting_and_corrected_openings_have_no_commitment_or_callback(self):
        cohort = probe.locked_cohort()
        keys = [(r["symbol"], r["reaction_session"]) for r in cohort["events"]]
        missing, conflicting, corrected = keys[:3]
        requested, private = Counter(), []

        def fetch(endpoint, params):
            symbol = endpoint.split("/")[-2]
            key = symbol, params["asof"]
            requested[key] += 1
            official, next_page = self.official(params), None
            trades = [official]
            if key == missing:
                trades = [dict(official, x="N"), dict(official, z="A"), dict(official, c=["O"]),
                          dict(official, t=params["end"])]
            elif key == conflicting:
                if "page_token" not in params:
                    next_page = "next-page"
                else:
                    self.assertEqual(params["page_token"], "next-page")
                    trades = [dict(official, i=DUMMY_ID + 1, p=DUMMY_PRICE + 1)]
            elif key == corrected:
                trades = [official, dict(official, u=1)]
            return json.dumps({"symbol": symbol, "trades": trades, "next_page_token": next_page}).encode()

        report = probe.run(ROOT, fetch, consume_opening=lambda *args: private.append(args))
        self.assertEqual(report["matched"], 49)
        self.assertEqual(report["dispositions"], {"no_official_open": 1, "ambiguous_official_open": 2, "verified_open": 49})
        self.assertEqual(requested[conflicting], 2)
        self.assertEqual(report["requests"], 53)
        self.assertEqual(len(private), 49)
        for row in report["events"]:
            self.assertEqual(row["opening_commitment_sha256"] is None, row["status"] != "verified_open")
        self.assertNotIn(str(DUMMY_PRICE), json.dumps(report))
        self.assertNotIn(str(DUMMY_PRICE + 1), json.dumps(report))

    def test_a_changed_frozen_source_fails_before_any_provider_request(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_inputs(root)
            path = root / probe.EARLIER
            source = load(path)
            source["candidate_events"][0]["revision_fraction"] += 0.001
            path.write_text(json.dumps(source), encoding="utf-8")

            def fetch(endpoint, params):
                self.fail("Provider called after a frozen source changed")

            with self.assertRaises(DataError):
                probe.run(root, fetch)

    def test_bounded_transport_rejects_noncohort_dates_feeds_and_endpoints(self):
        event = probe.locked_cohort()["events"][0]
        endpoint = f"https://data.alpaca.markets/v2/stocks/{event['symbol']}/trades"
        original = probe.trade_params(event)
        changes = [{"feed": "iex"}, {"asof": "2026-11-19"}, {"limit": 1000},
                   {"end": (timestamp(original["end"]) + timedelta(seconds=1)).isoformat()},
                   {"start": (timestamp(original["start"]) - timedelta(days=1)).isoformat()},
                   {"adjustment": "raw"}, {"page_token": ""}]
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(DataError, "first-minute opening boundary"):
                probe.validate_trade_request(event, endpoint, original | change)
        for wrong in ("https://data.alpaca.markets/v2/stocks/bars", endpoint.replace(event["symbol"], "UNREGISTERED"), endpoint.replace("https:", "http:")):
            with self.subTest(endpoint=wrong), self.assertRaises(DataError):
                probe.validate_trade_request(event, wrong, original)

    def test_commitment_binds_selected_print_and_normalizes_numeric_price(self):
        cohort = probe.locked_cohort()
        event = cohort["events"][0]
        selected = self.official(probe.trade_params(event), price=100)
        args = cohort["protocol_sha256"], cohort["cohort_sha256"]
        expected = probe.opening_commitment(event, selected, *args)
        self.assertEqual(expected, probe.opening_commitment(event, selected | {"p": 100.0}, *args))
        for change in ({"p": 101}, {"i": DUMMY_ID + 1},
                       {"t": (timestamp(selected["t"]) + timedelta(seconds=1)).isoformat()}):
            self.assertNotEqual(expected, probe.opening_commitment(event, selected | change, *args))
        self.assertNotEqual(expected, probe.opening_commitment(event | {"event_id": "another-event"}, selected, *args))

    def test_cli_failure_never_echoes_provider_messages_or_credentials(self):
        output = StringIO()

        def fetch(endpoint, params):
            raise RuntimeError(f"provider-payload-{DUMMY_PRICE}-synthetic-secret")

        with patch("sys.argv", ["opening"]), patch.dict("os.environ", {
                "APCA_API_KEY_ID": "synthetic-key", "APCA_API_SECRET_KEY": "synthetic-secret"}), \
                patch.object(probe.ea, "make_fetch", return_value=fetch), redirect_stdout(output):
            self.assertEqual(probe.main(), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "warmup_opening_failed", "reason": "RuntimeError"})
