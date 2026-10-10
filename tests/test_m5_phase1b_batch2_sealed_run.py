"""The attested sealed run of Milestone 5 Phase 1b batch 2 (reports/m5-phase1b-batch2-sealed-run-2026-10-10.json): the record is the sealed view and nothing else, it agrees with the events file and the calendar (window facts), batch 1's nine pins matched again, the ten
batch 2 events are mapped with every session-return label present, the facts of the run and of the other run of the push are pinned, and the ten commitments the record holds are the ones config/m5-phase1b-events.json pins."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch2-sealed-run-2026-10-10.json"
BATCH_1_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]
BATCH_2_IDS = ["payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
COMMIT = "71feecc8e50af9c1be36ca53a0f2c1ba7c8d5ee0"


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
    def test_it_is_the_nineteen_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(BATCH_1_IDS + BATCH_2_IDS))
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
        self.assertEqual([(p["part"], p["all_ok"], p["level"], len(p["events"])) for p in parts], [("1/5", True, "notice", 4), ("2/5", True, "notice", 3), ("3/5", True, "notice", 4), ("4/5", True, "notice", 4), ("5/5", True, "notice", 4)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(BATCH_1_IDS + BATCH_2_IDS))

    def test_batch_1s_nine_pins_matched_again_and_nothing_else_about_them_changed(self):
        first = load(ROOT / "reports" / "m5-phase1b-batch1-pin-verification-2026-10-10.json")["sealed_view"]["events"]
        for event_id in BATCH_1_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIs(view["labels_match_recorded"], True)
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
                for key in ("session_labels", "corporate_actions", "window", "state", "reasons"):
                    self.assertEqual(view[key], first[event_id][key], key)

    def test_the_ten_are_mapped_with_a_commitment_each_every_session_label_present_and_no_corporate_action(self):
        all_labels = {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES}
        for event_id in BATCH_2_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIsNone(view["labels_match_recorded"])                                 # nothing of batch 2 was pinned when the run happened
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual((view["session_labels"], view["corporate_actions"]), (all_labels, []))
        self.assertEqual(self.record["summary"], {"events_run": 19, "batch_1_pins_checked": 9, "batch_1_pins_that_matched": 9, "batch_1_pins_that_differed": 0, "batch_2_events": 10, "batch_2_mapped": 10, "errored": {},
                                                  "batch_2_events_with_missing_or_zero_volume_sessions": 0, "batch_2_events_with_a_corporate_action": 0, "batch_2_session_labels_that_do_not_exist": {},
                                                  "required_sessions_per_event": 21, "new_commitments": 10})


class RunAndPinsTests(Base):
    def test_the_run_and_the_other_run_of_the_push_are_pinned(self):
        record, run = self.record, self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 6, 38050803498, 114209368329, COMMIT, "success"))
        self.assertIn("the push of 4d2d216 and 71feecc (cd3faaa..71feecc)", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertIn("the job log was not read", record["how_it_was_read"])
        other = record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 250, "run_id": 38050803526, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 114209363704, "conclusion": "success"}, "validate (3.13)": {"job_id": 114209363814, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        watched = (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("- 'nre/event_acquire.py'", watched)
        self.assertIn("- 'config/m1-events.json'", watched)

    def test_the_ten_commitments_are_the_events_files_pins_and_distinct_from_batch_1s(self):
        commitments = self.record["commitments"]
        self.assertEqual(sorted(commitments), sorted(BATCH_2_IDS))
        self.assertEqual(len(set(commitments.values())), 10)
        earlier = {self.by_id[e]["recorded_result"]["labels_sha256"] for e in BATCH_1_IDS}
        self.assertFalse(set(commitments.values()) & earlier)
        for event_id in BATCH_2_IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.by_id[event_id]["recorded_result"], {"labels_sha256": commitments[event_id], "recorded_in": RECORD_PATH})
                self.assertEqual(commitments[event_id], self.view[event_id]["labels_sha256"])
        self.assertEqual(sum("recorded_result" in e for e in self.spec["events"]), 19)
        ea.validate_spec(self.spec, self.calendar)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch2_sealed_run", "2026-10-10"))
        for phrase in ("config/m5-phase1b-events.json as pushed in 71feecc (all ten batch 2 events attested on the owner's signoff, none pinned yet), on top of 4d2d216.", "No label value, price, return, day-1 or gap label exists in it.",
                       "pinning them in the events file is a separate commit, and nothing of batch 2 was pinned when this run happened (labels_match_recorded is null for the ten)."):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("All ten batch 2 events are MAPPED, now that the owner has attested them", "All four session-return labels (session_2, _5, _10, _20) exist for every one of the ten",
                       "The in-window 8-Ks the owner accepted as caveats do not suppress labels; they travel with them.", "Batch 1's nine pins were checked again and all nine report labels_match_recorded true",
                       "The ten commitments are distinct from one another and from batch 1's nine."):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, which has later batches.", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not a pin: the ten commitments are pinned in config/m5-phase1b-events.json by the commit that follows this record, and take effect only when that is pushed."):
            self.assertIn(phrase, nots)


if __name__ == "__main__":
    unittest.main()
