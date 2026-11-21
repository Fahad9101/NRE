import copy
import json
import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from nre import event_acquire as ea
from nre import m6_guidance_price_basis as probe
from nre import m6_guidance_warmup_opening as opening
from nre.calendar import Calendar
from nre.core import DataError, digest, canonical, timestamp
from nre.m5_phase1b_audit import load
from nre.m6_guidance_revision import EARLIER, FREEZE, PROTOCOL, ROOT

DUMMY_PRICE = 918273.125
DUMMY_AMOUNT = 123456.789012
ACTION_ID = "12345678-1234-1234-1234-123456789abc"


class GuidancePriceBasisTests(unittest.TestCase):
    def setUp(self):
        self.cohort = probe.locked_cohort()
        self.calendar = Calendar(load(ROOT / load(ROOT / PROTOCOL)["calendar"]))
        self.by_query = {(r["symbol"], r["reaction_session"]): r for r in self.cohort["events"]}

    def bar(self, params):
        return {"t": timestamp(params["start"]).isoformat(), "o": DUMMY_PRICE,
                "h": DUMMY_PRICE + 1, "l": DUMMY_PRICE - 1, "c": DUMMY_PRICE + 0.25,
                "v": 999888, "n": 100, "vw": DUMMY_PRICE + 0.125}

    def provider(self, *, ca_pages=None, mutate_bar=None, ca_error=None):
        requests = []
        ca_pages = ca_pages or [{"corporate_actions": {}, "next_page_token": None}]

        def fetch(endpoint, params):
            requests.append((endpoint, copy.deepcopy(params)))
            if endpoint == ea.ACTIONS_ENDPOINT:
                if ca_error:
                    raise HTTPError(endpoint, ca_error, "synthetic provider secret", None, None)
                index = 0 if "page_token" not in params else int(params["page_token"])
                return json.dumps(ca_pages[index]).encode()
            self.assertEqual(endpoint, ea.BARS_ENDPOINT)
            event = self.by_query[params["symbols"], params["asof"]]
            self.assertEqual(params, probe.anchor_params(event, self.calendar))
            self.assertLess(timestamp(params["end"]), timestamp(event.get("scheduled_open_at", event["reaction_session"] + "T09:30:00-05:00")))
            row = self.bar(params)
            payload = {"bars": {event["symbol"]: [row]}, "next_page_token": None}
            if mutate_bar:
                payload = mutate_bar(event, payload)
            return json.dumps(payload).encode()

        return fetch, requests

    def action(self, symbol, **changes):
        return {"id": ACTION_ID, "symbol": symbol, "ex_date": "2025-01-13",
                "process_date": "2025-02-01", "rate": DUMMY_AMOUNT, **changes}

    def test_complete_107_event_union_uses_only_raw_prior_anchors_and_seals_values(self):
        self.assertEqual(Counter(r["subset"] for r in self.cohort["events"]), {"warmup": 52, "held": 55})
        self.assertEqual(sum(r["clean_window"] for r in self.cohort["events"]), 97)
        fetch, requests = self.provider()
        result = probe.run(ROOT, fetch)
        self.assertEqual(result["screened"], 107)
        self.assertEqual(result["dispositions"], {"provider_basis_checks_passed": 107})
        self.assertEqual(result["requests"], 108)
        self.assertEqual(requests[0], (ea.ACTIONS_ENDPOINT, probe.action_params(self.cohort)))
        self.assertEqual(requests[0][1]["data_quality"], "all")
        self.assertEqual(requests[0][1]["region"], "all")
        self.assertEqual(requests[0][1]["start"], "2024-01-01")
        self.assertEqual(requests[0][1]["end"], "2026-11-21")
        self.assertCountEqual([(p["symbols"], p["asof"]) for e, p in requests[1:]], self.by_query)
        for event in result["events"]:
            self.assertEqual(event["anchor_status"], "verified_raw_anchor")
            self.assertRegex(event["anchor_commitment_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(event["anchor_receipts"]), 1)
        self.assertEqual((result["reaction_session_bar_requests"], result["closing_outcome_requests"], result["model_runs"]), (0, 0, 0))
        for value in (str(DUMMY_PRICE), str(DUMMY_PRICE + 0.25), '"o"', '"c"', '"price"', '"return"', '"raw_anchor_bar"', '"bars"'):
            self.assertNotIn(value, json.dumps(result))

    def test_action_effective_dates_control_the_bridge_and_process_date_does_not(self):
        event = self.cohort["events"][0]
        anchor, reaction = event["anchor_session"], event["reaction_session"]
        for kind in ("cash_dividends", "forward_splits"):
            with self.subTest(kind=kind):
                row = self.action(event["symbol"], ex_date=reaction, process_date="2026-11-20")
                actions, unresolved = probe.inventory([{"corporate_actions": {kind: [row]}}], {event["symbol"]})
                self.assertEqual(unresolved, set())
                status, hits = probe.bridge_status(event, actions, unresolved)
                self.assertEqual(status, "action_requires_reconciliation")
                self.assertEqual(hits, [digest(canonical(row))])
                row["ex_date"] = anchor
                actions, unresolved = probe.inventory([{"corporate_actions": {kind: [row]}}], {event["symbol"]})
                self.assertEqual(probe.bridge_status(event, actions, unresolved), ("no_observed_action_in_bridge", []))
        row = self.action(event["symbol"], effective_date=anchor)
        row.pop("ex_date")
        actions, unresolved = probe.inventory([{"corporate_actions": {"stock_mergers": [row]}}], {event["symbol"]})
        self.assertEqual(probe.bridge_status(event, actions, unresolved)[0], "action_requires_reconciliation")
        row.pop("effective_date")
        row["process_date"] = reaction
        row["payable_date"] = reaction
        actions, unresolved = probe.inventory([{"corporate_actions": {"stock_mergers": [row]}}], {event["symbol"]})
        self.assertEqual(probe.bridge_status(event, actions, unresolved), ("unresolved_action_inventory", []))

    def test_incomplete_unknown_and_conflicting_actions_fail_closed_without_amounts(self):
        symbols = {"EA", "DDOG"}
        base = self.action("EA")
        cases = [
            ("cash_dividends", {k: v for k, v in base.items() if k != "ex_date"}, {"EA"}),
            ("cash_dividends", base | {"ex_date": "not-a-date"}, {"EA"}),
            ("cash_dividends", base | {"effective_date": "2025-01-14"}, {"EA"}),
            ("cash_dividends", base | {"symbol": "OUTSIDE"}, symbols),
            ("cash_dividends", {k: v for k, v in base.items() if k != "id"}, {"EA"}),
            ("unknown-provider-text-" + str(DUMMY_AMOUNT), base, {"EA"}),
        ]
        for kind, row, expected in cases:
            with self.subTest(kind=kind, row=row):
                actions, unresolved = probe.inventory([{"corporate_actions": {kind: [row]}}], symbols)
                self.assertEqual(unresolved, expected)
                serialized = json.dumps(actions)
                for value in (str(DUMMY_AMOUNT), ACTION_ID, '"rate"'):
                    self.assertNotIn(value, serialized)
        first = {"corporate_actions": {"cash_dividends": [base]}}
        changed = {"corporate_actions": {"cash_dividends": [base | {"symbol": "DDOG"}]}}
        _, unresolved = probe.inventory([first, changed], symbols)
        self.assertEqual(unresolved, symbols)

    def test_paginated_inventory_deduplicates_exact_records_and_rejects_repeated_tokens(self):
        symbol = self.cohort["events"][0]["symbol"]
        row = self.action(symbol, ex_date="2024-01-02")
        pages = [{"corporate_actions": {"cash_dividends": [row]}, "next_page_token": "1"},
                 {"corporate_actions": {"cash_dividends": [row]}, "next_page_token": None}]
        fetch, requests = self.provider(ca_pages=pages)
        result = probe.run(ROOT, fetch)
        self.assertEqual(result["requests"], 109)
        self.assertEqual(len(result["corporate_action_inventory"]["actions"]), 1)
        self.assertEqual(len(result["corporate_action_inventory"]["receipts"]), 2)
        self.assertEqual(requests[1][1]["page_token"], "1")
        self.assertEqual(result["dispositions"], {"provider_basis_checks_passed": 107})
        pages[1]["next_page_token"] = "1"
        fetch, requests = self.provider(ca_pages=pages)
        with self.assertRaisesRegex(DataError, "invalid or repeated pagination token"):
            probe.run(ROOT, fetch)
        self.assertTrue(all(endpoint == ea.ACTIONS_ENDPOINT for endpoint, _ in requests))

    def test_invalid_or_ambiguous_anchors_are_withheld_without_disclosing_prices(self):
        keys = [(r["symbol"], r["reaction_session"]) for r in self.cohort["events"]]

        def mutate(event, payload):
            index = keys.index((event["symbol"], event["reaction_session"]))
            row = payload["bars"][event["symbol"]][0]
            if index == 0:
                payload["bars"][event["symbol"]].append(copy.deepcopy(row))
            elif index == 1:
                row["t"] = (timestamp(row["t"]) + timedelta(minutes=1)).isoformat()
            elif index == 2:
                row["v"] = 0
            elif index == 3:
                row["l"] = row["h"] + 1
            elif index == 4:
                row["c"] = float("nan")
            elif index == 5:
                payload["bars"] = {"OUTSIDE": [row]}
            elif index == 6:
                payload["bars"][event["symbol"]] = []
            return payload

        fetch, _ = self.provider(mutate_bar=mutate)
        result = probe.run(ROOT, fetch)
        self.assertEqual(result["dispositions"], {"basis_unverified": 7, "provider_basis_checks_passed": 100})
        self.assertEqual(Counter(r["anchor_status"] for r in result["events"]), {
            "ambiguous_anchor": 1, "invalid_anchor": 4, "invalid_anchor_response": 1,
            "missing_anchor": 1, "verified_raw_anchor": 100})
        for row in result["events"][:7]:
            self.assertIsNone(row["anchor_commitment_sha256"])
        self.assertNotIn(str(DUMMY_PRICE), json.dumps(result))
        self.assertNotIn("NaN", json.dumps(result))

    def test_denied_action_access_never_clears_basis_even_when_anchors_are_valid(self):
        fetch, requests = self.provider(ca_error=403)
        result = probe.run(ROOT, fetch)
        self.assertEqual(result["corporate_action_inventory"]["http_status"], 403)
        self.assertEqual(result["corporate_action_inventory"]["status"], "corporate_action_provider_error")
        self.assertEqual(result["dispositions"], {"basis_unverified": 107})
        self.assertTrue(all(r["anchor_status"] == "verified_raw_anchor" and r["corporate_action_status"] == "unresolved_action_inventory" for r in result["events"]))
        self.assertEqual(len(requests), 108)
        self.assertNotIn("synthetic provider secret", json.dumps(result))

    def test_transport_rejects_expanded_dates_adjustments_and_nonregistered_endpoints(self):
        event = self.cohort["events"][0]
        expected = probe.anchor_params(event, self.calendar)
        for change in ({"asof": "2026-11-21"}, {"adjustment": "all"}, {"feed": "iex"},
                       {"symbols": "OUTSIDE"}, {"timeframe": "1Min"},
                       {"end": event["reaction_session"] + "T23:59:59-04:00"}, {"page_token": ""}):
            with self.subTest(change=change), self.assertRaises(DataError):
                probe.validate_request(ea.BARS_ENDPOINT, expected | change, expected)
        with self.assertRaises(DataError):
            probe.validate_request("https://data.alpaca.markets/v2/stocks/EA/trades", expected, expected)

    def test_a_changed_frozen_source_fails_before_any_provider_request(self):
        protocol = load(ROOT / PROTOCOL)
        paths = {PROTOCOL, FREEZE, *protocol["input_canonical_sha256"],
                 *protocol["implementation_sha256_git_lf"], *opening.IMPLEMENTATION_PATHS,
                 "nre/m6_guidance_price_basis.py"}
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for path in paths:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / path).read_bytes())
            earlier = load(root / EARLIER)
            earlier["candidate_events"][0]["revision_fraction"] += 0.01
            (root / EARLIER).write_text(json.dumps(earlier), encoding="utf-8")

            def fetch(endpoint, params):
                self.fail("Provider called after frozen source changed")

            with self.assertRaises(DataError):
                probe.run(root, fetch)

    def test_cli_failure_never_echoes_provider_payload_or_credentials(self):
        output = StringIO()

        def fetch(endpoint, params):
            raise RuntimeError(f"provider-{DUMMY_PRICE}-synthetic-secret")

        with patch("sys.argv", ["basis"]), patch.dict("os.environ", {
                "APCA_API_KEY_ID": "synthetic-key", "APCA_API_SECRET_KEY": "synthetic-secret"}), \
                patch.object(probe.ea, "make_fetch", return_value=fetch), redirect_stdout(output):
            self.assertEqual(probe.main(), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "price_basis_failed", "reason": "RuntimeError"})
