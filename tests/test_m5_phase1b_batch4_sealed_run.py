"""The attested sealed run of Milestone 5 Phase 1b batch 4 (reports/m5-phase1b-batch4-sealed-run-2026-10-15.json): the record is the sealed view and nothing else, it agrees with the events file and the calendar (window facts), the twenty-nine pins of batches 1 to 3 matched again,
the nine batch 4 events are mapped with all four session-return labels (Alpaca lists no corporate action over any of their windows), the facts of the run and of the other run of the push are pinned, and the nine commitments the record holds are the ones
config/m5-phase1b-events.json pins."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch4-sealed-run-2026-10-15.json"
BATCH_2_RECORD_PATH = "reports/m5-phase1b-batch2-pin-verification-2026-10-10.json"
BATCH_3_RECORD_PATH = "reports/m5-phase1b-batch3-sealed-run-2026-10-14.json"
BATCHES_1_AND_2_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
                       "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
BATCH_3_IDS = ["okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
EARLIER_IDS = BATCHES_1_AND_2_IDS + BATCH_3_IDS
BATCH_4_IDS = ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "ttwo-m5b-2026-08-07", "achv-m5b-2026-08-11", "klc-m5b-2026-08-13", "lnsr-m5b-2026-08-13"]
COMMIT = "49fe41113d15f627c57d1b641839bc3960b1229f"


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
    def test_it_is_the_thirty_eight_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(EARLIER_IDS + BATCH_4_IDS))
        text = json.dumps(self.view, sort_keys=True)
        self.assertIsNone(re.search(r"\d\.\d", text))
        self.assertNotIn("NOT_POSITIVE", text)
        for event_id, view in self.view.items():
            with self.subTest(event=event_id):
                self.assertLessEqual(set(view), ea.SEALED_REPORT_KEYS)
                self.assertEqual((view["event_id"], view["sealed"], view["state"], view["reasons"], view["access_check_passed"], view["missing_sessions"], view["zero_volume_sessions"]), (event_id, True, "MAPPED", [], True, [], []))
                self.assertNotIn("error", view)
                window = ea.event_window(self.by_id[event_id], self.calendar)
                self.assertEqual(view["window"], {"anchor_session": window["anchor_session"], "asof": window["asof"], "end": window["end"], "reaction_session": window["reaction_session"],
                                                  "release_timing": window["release_timing"], "required_sessions": 21, "start": window["start"]})
        parts = self.record["annotation_parts"]
        self.assertEqual([(p["part"], p["all_ok"], p["level"], len(p["events"])) for p in parts],
                         [("1/10", True, "notice", 4), ("2/10", True, "notice", 3), ("3/10", True, "notice", 4), ("4/10", True, "notice", 4), ("5/10", True, "notice", 4), ("6/10", True, "notice", 4), ("7/10", True, "notice", 4),
                          ("8/10", True, "notice", 4), ("9/10", True, "notice", 4), ("10/10", True, "notice", 3)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + BATCH_4_IDS))

    def test_the_twenty_nine_pins_matched_again_and_nothing_else_about_them_changed(self):
        first = load(ROOT / BATCH_2_RECORD_PATH)["sealed_view"]["events"]                # the nineteen of batches 1 and 2 were last printed by their verification run
        second = load(ROOT / BATCH_3_RECORD_PATH)["sealed_view"]["events"]               # batch 3's ten by their attested run
        for event_id in EARLIER_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIs(view["labels_match_recorded"], True)
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
                earlier = first[event_id] if event_id in BATCHES_1_AND_2_IDS else second[event_id]
                for key in ("session_labels", "corporate_actions", "window", "state", "reasons", "labels_sha256"):
                    self.assertEqual(view[key], earlier[key], key)

    def test_the_nine_are_mapped_with_a_commitment_each_and_every_label_exists(self):
        for event_id in BATCH_4_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIsNone(view["labels_match_recorded"])                                 # nothing of batch 4 was pinned when the run happened
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(view["corporate_actions"], [])
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertEqual(sorted(view["session_labels"]), ["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"])
        self.assertEqual(self.record["summary"], {"events_run": 38, "pins_checked": 29, "pins_that_matched": 29, "pins_that_differed": 0, "batch_4_events": 9, "batch_4_mapped": 9, "errored": {}, "batch_4_events_with_missing_or_zero_volume_sessions": 0,
                                                  "batch_4_events_with_a_corporate_action": 0, "batch_4_session_labels_that_do_not_exist": {}, "required_sessions_per_event": 21, "new_commitments": 9})
        self.assertEqual(self.record["corporate_actions_found"], {})


class RunAndPinsTests(Base):
    def test_the_run_and_the_other_run_of_the_push_are_pinned(self):
        record, run = self.record, self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"], run["created_at"]),
                         ("M5 Phase 1b sealed event acquisition", 12, 38677568928, 116234549402, COMMIT, "success", "2026-10-15T03:41:27Z"))
        self.assertEqual(run["trigger"], "the push of 49fe411 (d14220d..49fe411); config/m5-phase1b-events.json changed in it")
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertEqual(record["how_it_was_read"], "From the check run's public annotations through the GitHub API (ten sealed parts); the job log was not read.")
        other = record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 258, "run_id": 38677568948, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 116234549604, "conclusion": "success"}, "validate (3.13)": {"job_id": 116234549877, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        watched = (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("- 'nre/event_acquire.py'", watched)
        self.assertIn("- 'config/m1-events.json'", watched)

    def test_the_nine_commitments_are_the_events_files_pins_and_distinct_from_the_twenty_nine(self):
        commitments = self.record["commitments"]
        self.assertEqual(sorted(commitments), sorted(BATCH_4_IDS))
        self.assertEqual(len(set(commitments.values())), 9)
        earlier = {self.by_id[e]["recorded_result"]["labels_sha256"] for e in EARLIER_IDS}
        self.assertEqual(len(earlier), 29)
        self.assertFalse(set(commitments.values()) & earlier)
        for event_id in BATCH_4_IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.by_id[event_id]["recorded_result"], {"labels_sha256": commitments[event_id], "recorded_in": RECORD_PATH})
                self.assertEqual(commitments[event_id], self.view[event_id]["labels_sha256"])
        self.assertEqual(sum("recorded_result" in e for e in self.spec["events"][:38]), 38)                                  # batch 5's events, when built, are pinned from their own record
        ea.validate_spec(self.spec, self.calendar)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["schema_version"], record["kind"], record["recorded_on"]), (1, "m5_phase1b_batch4_sealed_run", "2026-10-15"))
        for phrase in ("config/m5-phase1b-events.json as pushed in 49fe411 (all nine batch 4 events attested on the owner's signoff, none pinned yet), on top of d14220d and a0ce7ac.",
                       "and the check of the twenty-nine pins of batches 1 to 3. No label value, price, return, day-1 or gap label exists in it.",
                       "pinning them in the events file is a separate commit, and nothing of batch 4 was pinned when this run happened (labels_match_recorded is null for the nine)."):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("All nine batch 4 events are MAPPED, now that the owner has attested them: the provider answered for each, all 21 required sessions are present, none has zero volume, and each has a commitment.",
                       "All nine have all four session-return labels (session_2, _5, _10, _20): Alpaca lists no corporate action over any of their windows, so no label is suppressed.",
                       "The filings the owner accepted as caveats (ACHV's Item 5.03 filing and the in-window 8-Ks of COLL, ACHV and KLC) do not suppress labels; they travel with them.",
                       "The twenty-nine pins of batches 1 to 3 were checked again and all twenty-nine report labels_match_recorded true with the commitments of the earlier runs; nothing about them changed.",
                       "The nine commitments are distinct from one another and from the twenty-nine pinned ones."):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, which has later batches.", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not a pin: the nine commitments are pinned in config/m5-phase1b-events.json by the commit that follows this record, and take effect only when that is pushed."):
            self.assertIn(phrase, nots)


if __name__ == "__main__":
    unittest.main()
