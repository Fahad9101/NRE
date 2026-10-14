"""The attested sealed run of Milestone 5 Phase 1b batch 3 (reports/m5-phase1b-batch3-sealed-run-2026-10-14.json): the record is the sealed view and nothing else, it agrees with the events file and the calendar (window facts), the nineteen pins of batches 1 and 2 matched again, the ten
batch 3 events are mapped with their session-return labels (CXT's session_20 label does not exist, because of its dividend, recomputed from the calendar), the facts of the run and of the other run of the push are pinned, and the ten commitments the record holds are the ones
config/m5-phase1b-events.json pins."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch3-sealed-run-2026-10-14.json"
EARLIER_RECORD_PATH = "reports/m5-phase1b-batch2-pin-verification-2026-10-10.json"
EARLIER_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
               "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
BATCH_3_IDS = ["okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
CXT = "cxt-m5b-2026-08-05"
COMMIT = "90f34cb3c79d9956d259bd1b16bf069ef23e5513"


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
    def test_it_is_the_twenty_nine_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(EARLIER_IDS + BATCH_3_IDS))
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
                         [("1/8", True, "notice", 4), ("2/8", True, "notice", 3), ("3/8", True, "notice", 4), ("4/8", True, "notice", 4), ("5/8", True, "notice", 4), ("6/8", True, "notice", 4), ("7/8", True, "notice", 4), ("8/8", True, "notice", 2)])
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + BATCH_3_IDS))

    def test_the_nineteen_pins_matched_again_and_nothing_else_about_them_changed(self):
        first = load(ROOT / EARLIER_RECORD_PATH)["sealed_view"]["events"]
        for event_id in EARLIER_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIs(view["labels_match_recorded"], True)
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
                for key in ("session_labels", "corporate_actions", "window", "state", "reasons", "labels_sha256"):
                    self.assertEqual(view[key], first[event_id][key], key)

    def test_the_ten_are_mapped_with_a_commitment_each_and_only_the_label_the_dividend_crosses_is_absent(self):
        absent = {}
        for event_id in BATCH_3_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIsNone(view["labels_match_recorded"])                                 # nothing of batch 3 was pinned when the run happened
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                window = ea.event_window(self.by_id[event_id], self.calendar)
                session, anchor = window["reaction_session"], window["anchor_session"]
                for name in ea.SESSION_LABEL_NAMES:
                    n = int(name.split("_")[1])
                    crossed = any(anchor < action["ex_date"] <= self.calendar.offset(session, n - 1) for action in view["corporate_actions"])
                    self.assertEqual(view["session_labels"][name], {"exists": not crossed, "reason": "CORPORATE_ACTION_IN_WINDOW" if crossed else None}, name)
                    if crossed:
                        absent.setdefault(event_id, {})[name] = "CORPORATE_ACTION_IN_WINDOW"
                self.assertEqual(view["corporate_actions"], [{"ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "type": "cash_dividends"}] if event_id == CXT else [])
        self.assertEqual(absent, {CXT: {"session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}})
        self.assertEqual(self.record["summary"], {"events_run": 29, "pins_checked": 19, "pins_that_matched": 19, "pins_that_differed": 0, "batch_3_events": 10, "batch_3_mapped": 10, "errored": {}, "batch_3_events_with_missing_or_zero_volume_sessions": 0,
                                                  "batch_3_events_with_a_corporate_action": 1, "batch_3_session_labels_that_do_not_exist": absent, "required_sessions_per_event": 21, "new_commitments": 10})
        found = self.record["corporate_actions_found"]
        self.assertEqual(found, {CXT: [{"type": "cash_dividends", "ex_date": "2026-08-31", "id": "6c4c5bfd-242f-42e0-8f31-61d12a1783ad", "windows_it_falls_inside": ["session_20_close_return"]}]})


class RunAndPinsTests(Base):
    def test_the_run_and_the_other_run_of_the_push_are_pinned(self):
        record, run = self.record, self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 9, 38512544114, 115684098762, COMMIT, "success"))
        self.assertIn("the push of 30b4a3f and 90f34cb (b00783e..90f34cb); config/m5-phase1b-events.json changed in 90f34cb", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertEqual(record["how_it_was_read"], "From the check run's public annotations through the GitHub API (eight sealed parts); the job log was not read.")
        other = record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 254, "run_id": 38512544125, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 115684098974, "conclusion": "success"}, "validate (3.13)": {"job_id": 115684099178, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        watched = (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("- 'nre/event_acquire.py'", watched)
        self.assertIn("- 'config/m1-events.json'", watched)

    def test_the_ten_commitments_are_the_events_files_pins_and_distinct_from_the_nineteen(self):
        commitments = self.record["commitments"]
        self.assertEqual(sorted(commitments), sorted(BATCH_3_IDS))
        self.assertEqual(len(set(commitments.values())), 10)
        earlier = {self.by_id[e]["recorded_result"]["labels_sha256"] for e in EARLIER_IDS}
        self.assertEqual(len(earlier), 19)
        self.assertFalse(set(commitments.values()) & earlier)
        for event_id in BATCH_3_IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.by_id[event_id]["recorded_result"], {"labels_sha256": commitments[event_id], "recorded_in": RECORD_PATH})
                self.assertEqual(commitments[event_id], self.view[event_id]["labels_sha256"])
        self.assertEqual(sum("recorded_result" in e for e in self.spec["events"]), 29)
        ea.validate_spec(self.spec, self.calendar)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch3_sealed_run", "2026-10-14"))
        for phrase in ("config/m5-phase1b-events.json as pushed in 90f34cb (all ten batch 3 events attested on the owner's signoff, none pinned yet), on top of 30b4a3f and b00783e.", "and the check of the nineteen pins of batches 1 and 2. No label value, price, return, day-1 or gap label exists in it.",
                       "pinning them in the events file is a separate commit, and nothing of batch 3 was pinned when this run happened (labels_match_recorded is null for the ten)."):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("All ten batch 3 events are MAPPED, now that the owner has attested them", "Nine of the ten have all four session-return labels (session_2, _5, _10, _20).",
                       "CXT 2026-08-05's session_20 label does not exist, with the reason CORPORATE_ACTION_IN_WINDOW, because its one cash dividend (ex-date 2026-08-31) falls inside that window only (recomputed from the calendar); its other three labels exist.",
                       "The in-window 8-Ks the owner accepted as caveats do not suppress labels; they travel with them.", "The nineteen pins of batches 1 and 2 were checked again and all nineteen report labels_match_recorded true",
                       "The ten commitments are distinct from one another and from the nineteen pinned ones."):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, which has later batches.", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not a pin: the ten commitments are pinned in config/m5-phase1b-events.json by the commit that follows this record, and take effect only when that is pushed."):
            self.assertIn(phrase, nots)


if __name__ == "__main__":
    unittest.main()
