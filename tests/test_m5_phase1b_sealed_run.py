"""The attested sealed run of Milestone 5 Phase 1b batch 1 (reports/m5-phase1b-batch1-sealed-run-2026-10-10.json): the record is the sealed view and nothing else, it agrees with the events file and the calendar (window facts, the windows each corporate action falls
inside), the facts of the run and of the other runs of the same push are pinned, and the eight commitments it holds are the ones config/m5-phase1b-events.json pins."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch1-sealed-run-2026-10-10.json"
RAW = ROOT / "archive" / "m5-phase1b-sec-freeze" / "raw"
IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]
NBIX, CXT, JBSS = "nbix-m5b-2026-05-05", "cxt-m5b-2026-05-06", "jbss-m5b-2026-04-29"
COMMIT = "92e65baa3a78e30dd5dabdcbca16b128dee4164a"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar = Calendar()
        cls.record = load(ROOT / RECORD_PATH)
        cls.spec = load(ROOT / "config" / "m5-phase1b-events.json")
        cls.by_id = {e["event_id"]: e for e in cls.spec["events"]}
        cls.view = cls.record["sealed_view"]["events"]


class SealedViewTests(Base):
    def test_it_is_the_nine_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(IDS))
        text = json.dumps(self.view, sort_keys=True)
        self.assertIsNone(re.search(r"\d\.\d", text))
        self.assertNotIn("NOT_POSITIVE", text)
        for event_id, view in self.view.items():
            with self.subTest(event=event_id):
                self.assertLessEqual(set(view), ea.SEALED_REPORT_KEYS)
                self.assertEqual((view["event_id"], view["sealed"], view["access_check_passed"], view["missing_sessions"], view["zero_volume_sessions"]), (event_id, True, True, [], []))
                window = ea.event_window(self.by_id[event_id], self.calendar)
                self.assertEqual(view["window"], {"anchor_session": window["anchor_session"], "asof": window["asof"], "end": window["end"], "reaction_session": window["reaction_session"],
                                                  "release_timing": window["release_timing"], "required_sessions": 21, "start": window["start"]})
                self.assertIsNone(view["labels_match_recorded"])                      # nothing was pinned when the run happened
                self.assertNotIn("error", view)
        parts = self.record["annotation_parts"]
        self.assertEqual([(p["part"], p["all_ok"], p["level"]) for p in parts], [("1/3", True, "notice"), ("2/3", True, "notice"), ("3/3", True, "notice")])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(IDS))
        self.assertEqual([len(p["events"]) for p in parts], [4, 4, 1])

    def test_eight_events_map_with_commitments_and_nbix_is_quarantined_unattested(self):
        for event_id, view in self.view.items():
            with self.subTest(event=event_id):
                if event_id == NBIX:
                    # Unattested when the run happened; the owner attested it afterwards (reports/m5-phase1b-nbix-signoff-2026-10-10.json), so the view shows no commitment and no session labels.
                    self.assertEqual((view["state"], view["reasons"], view["labels_sha256"], view["session_labels"]), ("QUARANTINED", ["FIRST_PUBLIC_TIME_UNVERIFIED"], None, None))
                    continue
                self.assertEqual((view["state"], view["reasons"]), ("MAPPED", []))
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                expected = {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES}
                if event_id == CXT:
                    expected["session_20_close_return"] = {"exists": False, "reason": "CORPORATE_ACTION_IN_WINDOW"}
                self.assertEqual(view["session_labels"], expected)
        self.assertEqual(self.record["summary"], {"events_run": 9, "mapped": 8, "quarantined": {NBIX: ["FIRST_PUBLIC_TIME_UNVERIFIED"]}, "errored": {}, "events_with_missing_or_zero_volume_sessions": 0, "required_sessions_per_event": 21,
                                                  "session_labels_that_do_not_exist": {CXT: {"session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}}, "commitments": 8})

    def test_the_corporate_actions_and_the_windows_they_fall_inside_are_recomputed_from_the_calendar(self):
        found = self.record["corporate_actions_found"]
        self.assertEqual(sorted(found), sorted([NBIX, CXT, JBSS]))
        self.assertEqual({k: v["corporate_actions"] for k, v in self.view.items() if v["corporate_actions"]},
                         {CXT: [{"ex_date": "2026-05-29", "id": "0a5b1554-acfa-4836-9775-8f007fcba86b", "type": "cash_dividends"}],
                          JBSS: [{"ex_date": "2026-04-27", "id": "1b6fa9d4-9120-4ce8-946e-700cfe8d9d2a", "type": "cash_dividends"}],
                          NBIX: [{"date_field": "effective_date", "ex_date": "2026-05-18", "id": "b8d80b2b-b0e2-4be3-b612-9325d12d1646", "type": "cash_mergers"}]})
        for event_id, listed in found.items():
            window = ea.event_window(self.by_id[event_id], self.calendar)
            session, anchor = window["reaction_session"], window["anchor_session"]
            sessions = {"day1": [anchor, session], **{"session_%d_close_return" % n: [anchor, self.calendar.offset(session, n - 1)] for n in (2, 5, 10, 20)}}
            self.assertEqual(len(listed), 1)
            self.assertEqual(sorted(listed[0]["windows_it_falls_inside"]), sorted(name for name, w in sessions.items() if w[0] < listed[0]["ex_date"] <= w[1]), event_id)
            self.assertEqual({k: v for k, v in listed[0].items() if k != "windows_it_falls_inside"}, self.view[event_id]["corporate_actions"][0])
        self.assertEqual(found[NBIX][0]["windows_it_falls_inside"], ["session_10_close_return", "session_20_close_return"])
        self.assertEqual(found[CXT][0]["windows_it_falls_inside"], ["session_20_close_return"])
        self.assertEqual(found[JBSS][0]["windows_it_falls_inside"], [])

    def test_the_nbix_item_is_dated_like_the_filing_that_completed_its_acquisition(self):
        issuer = next(i for i in load(ROOT / "config" / "m5-phase1b-frozen-issuer-cohort.json")["issuers"] if i["ticker"] == "NBIX")
        metas = {meta["url"]: meta for meta in (load(path) for path in sorted(RAW.glob("*.json")))}
        recent = json.loads((RAW / metas[issuer["submissions_url"]]["raw_file"]).read_bytes())["filings"]["recent"]
        rows = [(recent["filingDate"][i], recent["form"][i], recent["items"][i]) for i in range(len(recent["accessionNumber"]))]
        self.assertIn(("2026-05-18", "8-K", "1.01,2.01,2.03,7.01,9.01"), rows)
        self.assertEqual(self.view[NBIX]["corporate_actions"][0]["ex_date"], "2026-05-18")
        text = " ".join(self.record["findings"])
        self.assertIn("the reading that the item is the Soleno acquisition remains an inference, because the sealed view carries no company names", text)
        self.assertIn("it cannot show whether the item lists NBIX as acquirer or acquiree", text)


class RunAndPinsTests(Base):
    def test_the_run_and_the_other_runs_of_the_push_are_pinned(self):
        run = self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 2, 38029982756, 114148695104, COMMIT, "success"))
        self.assertIn("the push of 4cc381c, ac370f9 and 92e65ba (22c9838..92e65ba)", run["trigger"])
        self.assertIn("No event returned an error, so the step exited with code 0", run["why"])
        self.assertIn("the job log was not read", self.record["how_it_was_read"])
        other = self.record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 246, "run_id": 38029982820, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 114148695185, "conclusion": "success"}, "validate (3.13)": {"job_id": 114148695341, "conclusion": "success"}}})
        m1 = other["milestone_1_event_acquisition"]
        self.assertEqual((m1["workflow"], m1["run_number"], m1["run_id"], m1["job_id"], m1["conclusion"]), ("Attested event acquisition", 16, 38029982856, 114148695567, "success"))
        self.assertIn("26 events: 23 MAPPED with labels_match_recorded true, 3 QUARANTINED as before; no label values in the annotations.", m1["result"])
        self.assertIn("the real-data check that ac370f9 leaves the unsealed path, and so every result already computed, unchanged", m1["result"])
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        self.assertEqual((ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + m1["workflow"])

    def test_the_eight_commitments_are_the_events_files_pins_and_nbix_has_none(self):
        commitments = self.record["commitments"]
        self.assertEqual(sorted(commitments), sorted(i for i in IDS if i != NBIX))
        self.assertEqual(len(set(commitments.values())), 8)
        for event_id in IDS:
            with self.subTest(event=event_id):
                event = self.by_id[event_id]
                if event_id == NBIX:
                    self.assertNotIn("recorded_result", event)
                    continue
                self.assertEqual(event["recorded_result"], {"labels_sha256": commitments[event_id], "recorded_in": RECORD_PATH})
                self.assertEqual(commitments[event_id], self.view[event_id]["labels_sha256"])
        ea.validate_spec(self.spec, self.calendar)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch1_sealed_run", "2026-10-10"))
        for phrase in ("config/m5-phase1b-events.json as pushed in 92e65ba (the eight events the owner signed off are attested, NBIX is not)", "No label value, price, return, day-1 or gap label exists in it.",
                       "pinning them in the events file is a separate commit, and nothing was pinned when this run happened (labels_match_recorded is null throughout)"):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("For seven of them all four session-return labels (session_2, _5, _10, _20) exist.", "CXT's session_20_close_return does not exist, with the reason CORPORATE_ACTION_IN_WINDOW",
                       "NBIX 2026-05-05 no longer errors.", "so the engine would suppress those two labels, and not the others, if NBIX is attested",
                       "This is the first run in which the change of ac370f9 (a merger dated by its effective date) did anything on real data"):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, and not an attestation of NBIX 2026-05-05, which stays unattested.", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not a pin: the commitments are pinned in config/m5-phase1b-events.json by the commit that follows this record, and take effect only when that is pushed.",
                       "Not a finding about the Soleno acquisition or about whether NBIX is the acquirer of the item it lists."):
            self.assertIn(phrase, nots)


if __name__ == "__main__":
    unittest.main()
