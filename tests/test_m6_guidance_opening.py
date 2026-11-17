import json
import unittest
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from nre import m6_guidance_opening as probe
from nre.core import DataError


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "reports/m6-guidance-pilot-evidence-2026-11-17.json"
DUMMY_PRICE = 918273.125
DUMMY_ID = 987654321001


class GuidanceOpeningTests(unittest.TestCase):
    def test_first_minute_sip_requests_and_dispositions_are_price_free(self):
        manifest = json.loads(PILOT.read_text(encoding="utf-8"))
        candidates = {row["symbol"]: row for row in manifest["guidance_candidates"]}
        missing, conflicting, corrected, *_ = candidates
        fetched = Counter()

        def fetch(endpoint, params):
            symbol = endpoint.split("/")[-2]
            self.assertIn(symbol, candidates)
            self.assertEqual(endpoint, f"https://data.alpaca.markets/v2/stocks/{symbol}/trades")
            candidate = candidates[symbol]
            start = datetime.fromisoformat(candidate["scheduled_open_at"])
            end = start + timedelta(minutes=1)
            self.assertEqual(datetime.fromisoformat(params["start"]), start)
            self.assertEqual(datetime.fromisoformat(params["end"]), end)
            self.assertEqual(params["feed"], "sip")
            self.assertEqual(params["asof"], candidate["reaction_session"])
            self.assertEqual(params["limit"], 5000)
            fetched[symbol] += 1

            official = {"x": "Q", "z": "C", "c": ["Q"], "i": DUMMY_ID,
                        "p": DUMMY_PRICE, "t": (start + timedelta(seconds=1)).isoformat()}
            trades = [official]
            next_page = None
            if symbol == missing:
                trades = [dict(official, x="N"), dict(official, z="A"),
                          dict(official, c=["O"]), dict(official, t=end.isoformat())]
            elif symbol == conflicting:
                if "page_token" in params:
                    self.assertEqual(params["page_token"], "second-page")
                    trades = [dict(official, i=DUMMY_ID + 1, p=DUMMY_PRICE + 1)]
                else:
                    next_page = "second-page"
            elif symbol == corrected:
                trades = [official, dict(official, u=1)]
            return json.dumps({"symbol": symbol, "trades": trades,
                               "next_page_token": next_page}).encode()

        report = probe.run(ROOT, fetch)
        expected_requests = Counter({symbol: 1 for symbol in candidates})
        expected_requests[conflicting] += 1
        self.assertEqual(fetched, expected_requests)

        expected_status = {symbol: "verified_open" for symbol in candidates}
        expected_status[missing] = "no_official_open"
        expected_status[conflicting] = expected_status[corrected] = "ambiguous_official_open"
        self.assertEqual(report["screened"], len(candidates))
        self.assertEqual(report["matched"], len(candidates) - 3)
        self.assertEqual(report["dispositions"], dict(Counter(expected_status.values())))
        self.assertCountEqual(report["events"], [
            {"symbol": symbol, "reaction_session": row["reaction_session"],
             "status": expected_status[symbol]}
            for symbol, row in candidates.items()
        ])
        serialized = json.dumps(report)
        for leaked in (str(DUMMY_PRICE), str(DUMMY_PRICE + 1), str(DUMMY_ID), str(DUMMY_ID + 1),
                       '"p"', '"i"', '"price"', '"trade_id"', '"open_price"', '"trades"'):
            self.assertNotIn(leaked, serialized)

    def test_changed_metadata_fails_before_fetch(self):
        pilot_path = PILOT.relative_to(ROOT)
        pilot = json.loads(PILOT.read_text(encoding="utf-8"))
        frame_path = Path(pilot["frame_path"])
        frame = json.loads((ROOT / frame_path).read_text(encoding="utf-8"))
        calendar_path = Path(frame["calendar"]["path"])
        paths = (pilot_path, frame_path, calendar_path)

        def fetch(endpoint, params):
            self.fail("Trade fetch attempted with changed metadata")

        for changed_path in paths:
            with self.subTest(path=changed_path), TemporaryDirectory() as directory:
                root = Path(directory)
                for path in paths:
                    destination = root / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    contents = json.loads((ROOT / path).read_text(encoding="utf-8"))
                    if path == changed_path:
                        contents["unexpected_test_field"] = True
                    destination.write_text(json.dumps(contents), encoding="utf-8")
                with self.assertRaises(DataError):
                    probe.run(root, fetch)
