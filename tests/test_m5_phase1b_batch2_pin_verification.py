"""The second attested sealed run of Milestone 5 Phase 1b batch 2 (reports/m5-phase1b-batch2-pin-verification-2026-10-10.json), the first after the ten batch 2 pins were pushed: the record is the sealed view and nothing else, it agrees with the events file and the calendar,
all nineteen pins matched with nothing else about the events changed since the earlier runs, the labels that do not exist are exactly those a corporate action's date falls inside, and the facts of the run and of the other run of the push are pinned."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch2-pin-verification-2026-10-10.json"
BATCH_2_RUN_PATH = "reports/m5-phase1b-batch2-sealed-run-2026-10-10.json"
BATCH_1_LAST_PATH = "reports/m5-phase1b-batch1-pin-verification-2026-10-10.json"
BATCH_1_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07"]
BATCH_2_IDS = ["payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
ALL_IDS = BATCH_1_IDS + BATCH_2_IDS
JBSS, NBIX, CXT = "jbss-m5b-2026-04-29", "nbix-m5b-2026-05-05", "cxt-m5b-2026-05-06"
COMMIT = "1734e8bed8d459c06e24aa21115f4156bae3b18c"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar = Calendar()
        cls.record = load(ROOT / RECORD_PATH)
        cls.batch_2_run = load(ROOT / BATCH_2_RUN_PATH)
        cls.batch_1_last = load(ROOT / BATCH_1_LAST_PATH)
        cls.spec = load(ROOT / "config" / "m5-phase1b-events.json")
        cls.by_id = {e["event_id"]: e for e in cls.spec["events"]}
        cls.view = cls.record["sealed_view"]["events"]


class SealedViewTests(Base):
    def test_it_is_the_nineteen_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(ALL_IDS))
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
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(ALL_IDS))

    def test_all_nineteen_pins_matched_and_nothing_else_about_the_events_changed(self):
        self.assertEqual(self.record["verified_pins"], sorted(ALL_IDS))
        earlier = {**{event_id: self.batch_1_last["sealed_view"]["events"][event_id] for event_id in BATCH_1_IDS}, **{event_id: self.batch_2_run["sealed_view"]["events"][event_id] for event_id in BATCH_2_IDS}}
        pins = set()
        for event_id in ALL_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                pin = self.by_id[event_id]["recorded_result"]["labels_sha256"]
                self.assertIs(view["labels_match_recorded"], True)
                self.assertEqual(view["labels_sha256"], pin)
                for key in ("session_labels", "corporate_actions", "window", "state", "reasons", "labels_sha256"):
                    self.assertEqual(view[key], earlier[event_id][key], key)
                pins.add(pin)
        for event_id in BATCH_2_IDS:
            self.assertEqual(self.view[event_id]["labels_sha256"], self.batch_2_run["commitments"][event_id], event_id)
            self.assertIsNone(self.batch_2_run["sealed_view"]["events"][event_id]["labels_match_recorded"], event_id)     # nothing of batch 2 was pinned when its commitments were first printed
        self.assertEqual(len(pins), 19)
        self.assertEqual(self.record["summary"], {"events_run": 19, "mapped": 19, "batch_1_pins_checked": 9, "batch_2_pins_checked": 10, "pins_checked": 19, "pins_that_matched": 19, "pins_that_differed": 0, "errored": {},
                                                  "events_with_missing_or_zero_volume_sessions": 0, "required_sessions_per_event": 21,
                                                  "session_labels_that_do_not_exist": {CXT: {"session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"},
                                                                                       NBIX: {"session_10_close_return": "CORPORATE_ACTION_IN_WINDOW", "session_20_close_return": "CORPORATE_ACTION_IN_WINDOW"}},
                                                  "new_commitments": 0})
        ea.validate_spec(self.spec, self.calendar)
        self.assertEqual(sum("recorded_result" in e for e in self.spec["events"]), 19)

    def test_the_labels_that_do_not_exist_are_exactly_those_a_corporate_action_falls_inside(self):
        listed = sorted(event_id for event_id, view in self.view.items() if view["corporate_actions"])
        self.assertEqual(listed, sorted([JBSS, CXT, NBIX]))
        absent = {}
        for event_id in ALL_IDS:
            view = self.view[event_id]
            window = ea.event_window(self.by_id[event_id], self.calendar)
            session, anchor = window["reaction_session"], window["anchor_session"]
            ends = {"session_%d_close_return" % n: self.calendar.offset(session, n - 1) for n in (2, 5, 10, 20)}
            self.assertEqual(sorted(ends), sorted(ea.SESSION_LABEL_NAMES))
            for name in ea.SESSION_LABEL_NAMES:
                crossed = any(anchor < action["ex_date"] <= ends[name] for action in view["corporate_actions"])
                with self.subTest(event=event_id, label=name):
                    self.assertEqual(view["session_labels"][name], {"exists": not crossed, "reason": "CORPORATE_ACTION_IN_WINDOW" if crossed else None})
                if crossed:
                    absent.setdefault(event_id, {})[name] = "CORPORATE_ACTION_IN_WINDOW"
        self.assertEqual(absent, self.record["summary"]["session_labels_that_do_not_exist"])
        self.assertEqual(self.view[NBIX]["corporate_actions"], [{"date_field": "effective_date", "ex_date": "2026-05-18", "id": "b8d80b2b-b0e2-4be3-b612-9325d12d1646", "type": "cash_mergers"}])
        self.assertEqual(self.view[CXT]["corporate_actions"], [{"ex_date": "2026-05-29", "id": "0a5b1554-acfa-4836-9775-8f007fcba86b", "type": "cash_dividends"}])
        self.assertEqual(self.view[JBSS]["corporate_actions"], [{"ex_date": "2026-04-27", "id": "1b6fa9d4-9120-4ce8-946e-700cfe8d9d2a", "type": "cash_dividends"}])
        for event_id in BATCH_2_IDS:
            self.assertEqual(self.view[event_id]["corporate_actions"], [], event_id)


class RunAndRecordTests(Base):
    def test_the_run_and_the_other_run_of_the_push_are_pinned(self):
        record, run = self.record, self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"]),
                         ("M5 Phase 1b sealed event acquisition", 7, 38051607098, 114211704151, COMMIT, "success"))
        self.assertIn("the push of 1734e8b (71feecc..1734e8b); config/m5-phase1b-events.json changed in it", run["trigger"])
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertEqual(record["how_it_was_read"], "From the check run's public annotations through the GitHub API (five sealed parts); the job log was not read.")
        other = record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 251, "run_id": 38051607118, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 114211704299, "conclusion": "success"}, "validate (3.13)": {"job_id": 114211704513, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        watched = (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("- 'nre/event_acquire.py'", watched)
        self.assertIn("- 'config/m1-events.json'", watched)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["kind"], record["recorded_on"]), ("m5_phase1b_batch2_pin_verification", "2026-10-10"))
        for phrase in ("The second attested sealed run of batch 2, and the first after its pins were pushed: config/m5-phase1b-events.json as pushed in 1734e8b, with the ten commitments of " + BATCH_2_RUN_PATH + " pinned in it, on top of 71feecc.",
                       "for each of the nineteen pinned events (batch 1's nine and batch 2's ten) it recomputes the labels from the provider's answer and reports labels_match_recorded, so a pin is checked, never overwritten.",
                       "No label value, price, return, day-1 or gap label exists in it.", "No commitment is new in it: all nineteen were pinned already."):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("All nineteen pinned events report labels_match_recorded true.", "each commitment equals the one the events file pins",
                       "(batch 1's nine from " + BATCH_1_LAST_PATH + ", batch 2's ten from " + BATCH_2_RUN_PATH + ")",
                       "For batch 2 this is the first time its pins were checked: the earlier run printed the ten commitments while nothing was pinned, so labels_match_recorded was null for them.",
                       "The ten commitments came out the same, event by event, and are distinct from one another and from batch 1's nine (nineteen distinct commitments).",
                       "JBSS's dividend (ex-date 2026-04-27) precedes its anchor session and suppresses no label", "CXT's dividend (ex-date 2026-05-29) suppresses its session_20 label only",
                       "NBIX's merger item (dated 2026-05-18 by its effective_date) suppresses its session_10 and session_20 labels", "the ten events of batch 2 still list none.",
                       "This push changed no code, so the Milestone 1 event acquisition did not start; only the main CI and this sealed run did."):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, which has later batches.", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not the sealed audit of the whole extension and the registry of its events and commitments (S7), which is a later stage."):
            self.assertIn(phrase, nots)


if __name__ == "__main__":
    unittest.main()
