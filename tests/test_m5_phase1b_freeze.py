"""The Milestone 5 Phase 1b rules, pre-registered before any run (config/m5-phase1b-protocol.json and config/m5-phase1b-cohort-spec.json), bound to the records and code they rely on, and the freeze run end to end on a fake SEC
client over the real spec: the same 23 issuers, a window that starts after Milestone 1's and ends where the calendar says, an outcome-blind Item 2.02 screen, and a seal rule that the label engine's own reasons make necessary."""
import json
import tempfile
import unittest
from pathlib import Path

from nre import depth_cohort as dc
from nre import event_acquire
from nre.calendar import Calendar
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL = ROOT / "config" / "m5-phase1b-protocol.json"
SPEC = ROOT / "config" / "m5-phase1b-cohort-spec.json"
AUTHORIZATION = ROOT / "reports" / "m5-phase1b-authorization-2026-10-09.json"
LATEST_SESSION = "2026-10-08"      # the latest completed session when the window was fixed


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pairs(spec):
    return sorted((i["ticker"], i["cik"]) for i in spec["issuers"])


class PreRegisteredRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol, cls.spec, cls.authorization = load(PROTOCOL), load(SPEC), load(AUTHORIZATION)

    def test_the_spec_validates_against_the_protocol_it_carries_the_hash_of(self):
        dc.validate_spec(self.spec, self.protocol)                         # no exception
        self.assertEqual(self.spec["protocol_sha256"], digest(canonical(self.protocol)))
        self.assertEqual((self.spec["schema_version"], self.spec["selection_mode"], self.spec["window_relation_to_milestone_1"]), (1, "fixed_issuer_set", "after"))
        self.assertEqual(self.spec["allowed_forms"], ["8-K", "8-K/A"])
        self.assertEqual((self.spec["event_window_start"], self.spec["event_window_end"]), (self.protocol["event_window_start"], self.protocol["event_window_end"]))
        self.assertEqual((self.spec["filing_screen_start"], self.spec["filing_screen_end"]), (self.spec["event_window_start"], self.spec["event_window_end"]))

    def test_the_issuers_are_the_same_23_as_every_earlier_step(self):
        self.assertEqual(len(self.spec["issuers"]), 23)
        self.assertEqual(len({i["cik"] for i in self.spec["issuers"]}), 23)
        for name in ("m2-step2-cohort-spec.json", "m2-step3-cohort-spec.json"):
            self.assertEqual(pairs(self.spec), pairs(load(ROOT / "config" / name)), name)
        frozen = load(ROOT / "config" / "m2-step3-frozen-issuer-cohort.json")
        self.assertEqual(pairs(self.spec), sorted((i["ticker"], i["cik"]) for i in frozen["issuers"]))
        self.assertEqual(sorted(self.protocol["candidate_universe"]["ciks"]), sorted(i["cik"] for i in self.spec["issuers"]))

    def test_the_window_starts_the_day_after_milestone_1s_and_ends_where_the_calendar_says(self):
        pilot = load(ROOT / "config" / "pilot.json")
        self.assertEqual(pilot["event_window_end"], "2026-03-31")
        self.assertEqual((self.protocol["event_window_start"], self.protocol["event_window_end"], self.protocol["price_window_end"]), ("2026-04-01", "2026-09-10", "2026-10-31"))
        calendar = Calendar()
        last = event_acquire.event_window({"published_at": "2026-09-10T16:30:00-04:00"}, calendar)                 # an after-hours release on the last date: the worst case for completeness
        self.assertEqual((last["release_timing"], last["reaction_session"], last["required_sessions"][-1]), ("after_hours", "2026-09-11", LATEST_SESSION))
        self.assertEqual(last["end"], self.protocol["price_window_end"])
        self.assertEqual(len(last["required_sessions"]), event_acquire.REACTION_SESSIONS + 1)
        later = event_acquire.event_window({"published_at": "2026-09-11T16:30:00-04:00"}, calendar)                # one date later the window would not be complete
        self.assertGreater(later["required_sessions"][-1], LATEST_SESSION)
        first = event_acquire.event_window({"published_at": "2026-04-01T16:30:00-04:00"}, calendar)
        self.assertEqual((first["anchor_session"], first["reaction_session"]), ("2026-04-01", "2026-04-02"))
        self.assertEqual(self.protocol["window_rule"]["later_releases"], "Releases after the end date are not enumerated by this step.")

    def test_no_candidate_of_the_23_in_an_earlier_ledger_is_dated_in_the_window(self):
        ciks = {i["cik"] for i in self.spec["issuers"]}
        start, end = self.spec["filing_screen_start"], self.spec["filing_screen_end"]
        latest = {}
        for name in ("m1-frozen-candidate-ledger.json", "m2-step2-frozen-candidate-ledger.json", "m2-step3-frozen-candidate-ledger.json"):
            ledger = load(ROOT / "config" / name)["candidates"]
            mine = [c["filing_date"] for c in ledger if c["cik"] in ciks]
            self.assertTrue(mine, name)
            latest[name] = max(mine)
            self.assertFalse([d for d in mine if start <= d <= end], name)
        self.assertLess(latest["m1-frozen-candidate-ledger.json"], start)
        m1_all = [c for c in load(ROOT / "config" / "m1-frozen-candidate-ledger.json")["candidates"] if c["filing_date"] >= start]
        self.assertTrue(m1_all)                                            # the check is not vacuous: Milestone 1's pool does hold later filings, but of other issuers
        self.assertFalse([c for c in m1_all if c["cik"] in ciks])

    def test_the_seal_rule_is_preregistered_and_is_the_owners_choice(self):
        seal = self.protocol["seal"]
        self.assertEqual(seal["method"], "hash_only")
        answers = {a["header"]: a for a in self.authorization["owner_answers"]}
        self.assertEqual(answers["Seal"]["owner_selected"], "Hash-only seal (Recommended)")
        self.assertEqual(answers["Rights"]["owner_selected"], "Yes, provider rights fine")
        self.assertIn("'%s'" % answers["Seal"]["owner_selected"], seal["chosen_by"])
        self.assertIn("reports/m5-phase1b-authorization-2026-10-09.json", seal["chosen_by"])
        never = " ".join(seal["a_sealed_run_never_reports"])
        for needle in ("a label value, a price, a return or a ratio", "whether any day-1 label, gap threshold or gap label is true or false", "NOT_POSITIVE_GAP_GE_0_5PCT",
                       "the times at which labels became available", "other than the zero-volume test"):
            self.assertIn(needle, never)
        allowed = seal["a_sealed_run_may_report"]
        for name in ("session_2_close_return", "session_5_close_return", "session_10_close_return", "session_20_close_return"):
            self.assertIn(name, " ".join(allowed))
            self.assertIn(name, event_acquire.LABEL_NAMES)
        self.assertEqual(event_acquire.REACTION_SESSIONS, 20)
        self.assertIn("recorded_result.labels_sha256", seal["commitment"])
        self.assertIn("is the only look", seal["opening"])

    def test_the_label_engines_own_reason_for_a_non_positive_gap_really_reveals_the_gaps_sign(self):
        source = (ROOT / "nre" / "dataset.py").read_text(encoding="utf-8")
        self.assertIn('label(None, window, "NOT_POSITIVE_GAP_GE_0_5PCT")', source)
        self.assertIn('Decimal(str(current["open"])) >= Decimal(str(p)) * Decimal("1.005")', source)               # the reason is given exactly when the gap is below +0.5%
        self.assertTrue(hasattr(event_acquire, "labels_digest"))

    def test_the_protocol_names_the_owners_words_and_the_record_and_touches_no_earlier_file(self):
        authorization = self.protocol["authorization"]
        self.assertEqual(authorization["words"], "authorize phase 1b")
        self.assertEqual([m["text"] for m in self.authorization["owner_messages"]], [authorization["words"]])
        self.assertEqual((authorization["authorized_on"], authorization["authorized_by"]), ("2026-10-09", "Fahad9101 (project owner)"))
        self.assertTrue((ROOT / authorization["record"]).is_file())
        self.assertIn("It does not amend, extend or touch", self.protocol["relationship_to_earlier_steps"])
        self.assertTrue(self.protocol["protocol_version"].startswith("m5-phase1b-"))
        self.assertEqual((self.protocol["availability_mode"], self.protocol["selection"]), ("historical_reconstruction", "Enumerate before reading returns; no performance-based sampling"))
        self.assertIn("No price, return or label is read by this step.", " ".join(self.spec["limitations"]))


def submissions(cik, accessions):
    """A minimal SEC submissions document: one 8-K per (accession, filing_date, items) triple."""
    return {"cik": cik, "filings": {"recent": {
        "accessionNumber": [a for a, _, _ in accessions], "form": ["8-K"] * len(accessions), "filingDate": [d for _, d, _ in accessions],
        "items": [i for _, _, i in accessions], "primaryDocument": ["ex99.htm"] * len(accessions),
        "acceptanceDateTime": ["%sT21:00:00.000Z" % d for _, d, _ in accessions]}, "files": []}}


class FakeClient:
    def __init__(self, documents, retrieved_at):
        self.documents, self.retrieved_at, self.calls = documents, retrieved_at, []

    def fetch(self, url, output):
        self.calls.append(url)
        body = canonical(self.documents[url])
        return body, {"url": url, "sha256": digest(body), "size": len(body), "retrieved_at": self.retrieved_at, "raw_file": digest(body) + ".raw"}


class SimulatedFreezeTests(unittest.TestCase):
    """The real freeze function, the real spec and protocol, and invented submissions: one filing on each side of each window edge and one that is not an earnings item."""

    @classmethod
    def setUpClass(cls):
        cls.protocol, cls.spec = load(PROTOCOL), load(SPEC)
        cls.documents = {}
        for number, issuer in enumerate(sorted(cls.spec["issuers"], key=lambda i: i["cik"]), 1):
            cik = issuer["cik"]
            sequence = "%06d" % number
            cls.documents["https://data.sec.gov/submissions/CIK%s.json" % cik] = submissions(cik, [
                (cik + "-26-" + sequence[:6], "2026-03-31", "2.02,9.01"),            # the last day of Milestone 1's window: outside
                (cik + "-26-%06d" % (number + 100), "2026-04-01", "2.02"),             # the first day of this window: inside
                (cik + "-26-%06d" % (number + 200), "2026-05-12", "5.02"),             # not an earnings item: outside
                (cik + "-26-%06d" % (number + 300), "2026-09-10", "2.02,9.01"),       # the last day of this window: inside
                (cik + "-26-%06d" % (number + 400), "2026-09-11", "2.02"),             # the day after: outside
            ])
        cls.expected = sorted(a for doc in cls.documents.values() for a, d, i in zip(doc["filings"]["recent"]["accessionNumber"], doc["filings"]["recent"]["filingDate"], doc["filings"]["recent"]["items"])
                              if d in ("2026-04-01", "2026-09-10"))

    def freeze(self):
        client = FakeClient(self.documents, "2026-10-10T12:00:00Z")
        with tempfile.TemporaryDirectory() as tmp:
            cohort, ledger, report = dc.freeze_targeted_candidates(self.spec, self.protocol, tmp, "NRE test contact test@example.test", client=client)
            written = {name: (Path(tmp) / name).read_bytes() for name in ("issuer-cohort.json", "candidate-ledger.json", "discovery-report.json")}
        return cohort, ledger, report, written, client

    def test_only_earnings_items_filed_inside_the_window_are_frozen_for_all_23_issuers(self):
        cohort, ledger, report, written, client = self.freeze()
        self.assertEqual(report["state"], "FROZEN_CANDIDATE_MEMBERSHIP")
        self.assertEqual((report["processed_issuers"], report["issuers_with_item_2_02_candidates"], report["candidate_count"]), (23, 23, 46))
        self.assertEqual([c["candidate_id"] for c in ledger["candidates"]], self.expected)
        self.assertTrue(all(self.spec["filing_screen_start"] <= c["filing_date"] <= self.spec["filing_screen_end"] for c in ledger["candidates"]))
        self.assertEqual({c["filing_date"] for c in ledger["candidates"]}, {"2026-04-01", "2026-09-10"})
        self.assertEqual(len(client.calls), 23)                                  # one submissions file per issuer; none of these filings needs a continuation file
        self.assertEqual(report["filing_screen"], ["2026-04-01", "2026-09-10"])
        self.assertEqual(report["event_window"], ["2026-04-01", "2026-09-10"])
        self.assertEqual(cohort["protocol_sha256"], ledger["protocol_sha256"])
        self.assertEqual(cohort["protocol_sha256"], digest(canonical(self.protocol)))

    def test_the_freeze_reads_no_price_and_is_reproducible(self):
        _, ledger, report, written, _ = self.freeze()
        self.assertIs(report["price_data_accessed_by_this_workflow"], False)
        self.assertIn("No clean-cohort market prices were accessed by this step.", report["limitations"])
        _, ledger2, report2, written2, _ = self.freeze()
        self.assertEqual(ledger["membership_sha256"], ledger2["membership_sha256"])
        self.assertEqual(report["membership_sha256"], report2["membership_sha256"])
        for name in ("candidate-ledger.json",):
            self.assertEqual(json.loads(written[name])["membership_sha256"], ledger["membership_sha256"])
        forbidden = {"open", "high", "low", "close", "volume", "price", "return", "label", "labels"}

        def keys(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from keys(value)
            elif isinstance(node, list):
                for item in node:
                    yield from keys(item)
        for name, body in written.items():
            self.assertEqual(forbidden & set(keys(json.loads(body))), set(), name)

    def test_every_candidate_still_needs_its_primary_review_after_the_freeze(self):
        _, ledger, *_ = self.freeze()
        for candidate in ledger["candidates"]:
            self.assertEqual(candidate["primary_review_state"], "REQUIRED_POST_FREEZE")
            self.assertIsNone(candidate["primary_source_sha256"])


if __name__ == "__main__":
    unittest.main()
