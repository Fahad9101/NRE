"""The attested sealed run of Milestone 5 Phase 1b batch 5, the last (reports/m5-phase1b-batch5-sealed-run-2026-10-15.json): the record is the sealed view and nothing else, it agrees with the events file and the calendar (window facts), the thirty-eight pins of batches 1 to 4 matched again,
the five batch 5 events are mapped with all four session-return labels (JBSS's two dividends precede its anchor session and suppress none), the facts of the run and of the other run of the push are pinned, and the five commitments the record holds are the ones
config/m5-phase1b-events.json pins."""
import json
import re
import unittest
from pathlib import Path

from nre import event_acquire as ea
from nre.calendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "reports/m5-phase1b-batch5-sealed-run-2026-10-15.json"
BATCH_2_RECORD_PATH = "reports/m5-phase1b-batch2-pin-verification-2026-10-10.json"
BATCH_3_RECORD_PATH = "reports/m5-phase1b-batch3-sealed-run-2026-10-14.json"
BATCH_4_RECORD_PATH = "reports/m5-phase1b-batch4-sealed-run-2026-10-15.json"
BATCHES_1_AND_2_IDS = ["caci-m5b-2026-04-22", "alkt-m5b-2026-04-29", "jbss-m5b-2026-04-29", "hurn-m5b-2026-05-05", "nbix-m5b-2026-05-05", "parr-m5b-2026-05-05", "cxt-m5b-2026-05-06", "aspn-m5b-2026-05-07", "coll-m5b-2026-05-07",
                       "payo-m5b-2026-05-07", "pdfs-m5b-2026-05-07", "real-m5b-2026-05-07", "tecx-m5b-2026-05-07", "lnsr-m5b-2026-05-08", "rekr-m5b-2026-05-11", "achv-m5b-2026-05-12", "slsn-m5b-2026-05-12", "klc-m5b-2026-05-14", "ttwo-m5b-2026-05-21"]
BATCH_3_IDS = ["okta-m5b-2026-05-28", "vsat-m5b-2026-05-28", "love-m5b-2026-06-11", "hurn-m5b-2026-07-28", "alkt-m5b-2026-07-29", "nbix-m5b-2026-07-30", "parr-m5b-2026-08-04", "vsat-m5b-2026-08-04", "caci-m5b-2026-08-05", "cxt-m5b-2026-08-05"]
BATCH_4_IDS = ["aspn-m5b-2026-08-06", "coll-m5b-2026-08-06", "pdfs-m5b-2026-08-06", "real-m5b-2026-08-06", "tecx-m5b-2026-08-06", "ttwo-m5b-2026-08-07", "achv-m5b-2026-08-11", "klc-m5b-2026-08-13", "lnsr-m5b-2026-08-13"]
BATCH_5_IDS = ["rekr-m5b-2026-08-13", "jbss-m5b-2026-08-19", "slsn-m5b-2026-08-19", "okta-m5b-2026-08-26", "love-m5b-2026-09-10"]
JBSS = BATCH_5_IDS[1]
EARLIER_IDS = BATCHES_1_AND_2_IDS + BATCH_3_IDS + BATCH_4_IDS
COMMIT = "89111c5666127fbb50f35ffecfc6c85836dfb48f"
DIVIDENDS = [{"ex_date": "2026-08-17", "id": "b819a028-2051-49fd-bcd4-6505d853d06f", "type": "cash_dividends"}, {"ex_date": "2026-08-17", "id": "ef28820a-6a63-4119-b7eb-0d71f55b7a91", "type": "cash_dividends"}]


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
    def test_it_is_the_forty_three_events_and_holds_only_what_the_seal_allows(self):
        self.assertEqual(sorted(self.view), sorted(EARLIER_IDS + BATCH_5_IDS))
        self.assertEqual(len(self.view), 43)
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
                         [("1/10", True, "notice", 4), ("2/10", True, "notice", 4), ("3/10", True, "notice", 5), ("4/10", True, "notice", 5), ("5/10", True, "notice", 5), ("6/10", True, "notice", 5), ("7/10", True, "notice", 5),
                          ("8/10", True, "notice", 5), ("9/10", True, "notice", 4), ("10/10", True, "notice", 1)])
        self.assertLessEqual(len(parts), 10)                                                     # GitHub keeps only the first ten annotations of a kind per step
        self.assertLess(max(p["message_characters"] for p in parts), 4096)
        self.assertEqual(sorted(sum((p["events"] for p in parts), [])), sorted(EARLIER_IDS + BATCH_5_IDS))

    def test_the_thirty_eight_pins_matched_again_and_nothing_else_about_them_changed(self):
        first = load(ROOT / BATCH_2_RECORD_PATH)["sealed_view"]["events"]                # the nineteen of batches 1 and 2 were last printed by their verification run
        second = load(ROOT / BATCH_3_RECORD_PATH)["sealed_view"]["events"]               # batch 3's ten by their attested run
        third = load(ROOT / BATCH_4_RECORD_PATH)["sealed_view"]["events"]                # batch 4's nine by theirs
        for event_id in EARLIER_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIs(view["labels_match_recorded"], True)
                self.assertEqual(view["labels_sha256"], self.by_id[event_id]["recorded_result"]["labels_sha256"])
                earlier = first[event_id] if event_id in BATCHES_1_AND_2_IDS else second[event_id] if event_id in BATCH_3_IDS else third[event_id]
                for key in ("session_labels", "corporate_actions", "window", "state", "reasons", "labels_sha256"):
                    self.assertEqual(view[key], earlier[key], key)

    def test_the_five_are_mapped_with_a_commitment_each_and_every_label_exists(self):
        for event_id in BATCH_5_IDS:
            with self.subTest(event=event_id):
                view = self.view[event_id]
                self.assertIsNone(view["labels_match_recorded"])                                 # nothing of batch 5 was pinned when the run happened
                self.assertRegex(view["labels_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(view["corporate_actions"], DIVIDENDS if event_id == JBSS else [])
                self.assertEqual(view["session_labels"], {name: {"exists": True, "reason": None} for name in ea.SESSION_LABEL_NAMES})
                self.assertEqual(sorted(view["session_labels"]), ["session_10_close_return", "session_20_close_return", "session_2_close_return", "session_5_close_return"])
        self.assertEqual(self.record["summary"], {"events_run": 43, "pins_checked": 38, "pins_that_matched": 38, "pins_that_differed": 0, "batch_5_events": 5, "batch_5_mapped": 5, "errored": {}, "batch_5_events_with_missing_or_zero_volume_sessions": 0,
                                                  "batch_5_events_with_a_corporate_action": 1, "batch_5_session_labels_that_do_not_exist": {}, "required_sessions_per_event": 21, "new_commitments": 5})

    def test_jbss_dividends_precede_its_anchor_session_so_they_suppress_no_label(self):
        found = self.record["corporate_actions_found"]
        self.assertEqual(found, {JBSS: [{"type": "cash_dividends", "ex_date": "2026-08-17", "id": d["id"], "windows_it_falls_inside": []} for d in DIVIDENDS]})
        window = ea.event_window(self.by_id[JBSS], self.calendar)
        session, anchor = window["reaction_session"], window["anchor_session"]
        self.assertEqual((anchor, session), ("2026-08-19", "2026-08-20"))
        ends = {"day1": session, **{"session_%d_close_return" % n: self.calendar.offset(session, n - 1) for n in (2, 5, 10, 20)}}
        self.assertEqual([name for name, end in ends.items() if anchor < "2026-08-17" <= end], [])      # two days before the anchor session: inside no label's window
        dry = load(ROOT / "reports" / "m5-phase1b-batch5-dry-run-2026-10-15.json")
        self.assertEqual(found, dry["corporate_actions_found"])                                  # the same two dividends the dry run listed, with the same ids
        self.assertEqual(self.view[JBSS]["corporate_actions"], dry["sealed_view"]["events"][JBSS]["corporate_actions"])


class RunAndPinsTests(Base):
    def test_the_run_and_the_other_run_of_the_push_are_pinned(self):
        record, run = self.record, self.record["run"]
        self.assertEqual((run["workflow"], run["run_number"], run["run_id"], run["job_id"], run["commit"], run["conclusion"], run["created_at"]),
                         ("M5 Phase 1b sealed event acquisition", 16, 38771616027, 116548588358, COMMIT, "success", "2026-10-15T16:45:10Z"))
        self.assertEqual(run["trigger"], "the push of 89111c5 (1c590a9..89111c5), which also published 9e2021f; config/m5-phase1b-events.json changed in it")
        self.assertIn("No event returned an error and no pin differed, so the step exited with code 0", run["why"])
        self.assertEqual(record["how_it_was_read"], "From the check run's public annotations through the GitHub API (ten sealed parts, the most GitHub keeps of one kind per step); the job log was not read.")
        other = record["other_runs_of_the_same_push"]
        self.assertEqual(other["ci"], {"workflow": "NRE Milestone 1", "run_number": 262, "run_id": 38771615984, "conclusion": "success",
                                       "jobs": {"validate (3.12)": {"job_id": 116548589054, "conclusion": "success"}, "validate (3.13)": {"job_id": 116548589587, "conclusion": "success"}}})
        self.assertEqual(other["milestone_1_event_acquisition"], "Not started: the workflow watches nre/event_acquire.py and config/m1-events.json, and this push changed neither.")
        self.assertEqual((ROOT / ".github" / "workflows" / "m5-phase1b-event-acquire.yml").read_text(encoding="utf-8").splitlines()[0], "name: " + run["workflow"])
        watched = (ROOT / ".github" / "workflows" / "event-acquire.yml").read_text(encoding="utf-8")
        self.assertIn("- 'nre/event_acquire.py'", watched)
        self.assertIn("- 'config/m1-events.json'", watched)

    def test_the_five_commitments_are_the_events_files_pins_and_distinct_from_the_thirty_eight(self):
        commitments = self.record["commitments"]
        self.assertEqual(sorted(commitments), sorted(BATCH_5_IDS))
        self.assertEqual(len(set(commitments.values())), 5)
        earlier = {self.by_id[e]["recorded_result"]["labels_sha256"] for e in EARLIER_IDS}
        self.assertEqual(len(earlier), 38)
        self.assertFalse(set(commitments.values()) & earlier)
        for event_id in BATCH_5_IDS:
            with self.subTest(event=event_id):
                self.assertEqual(self.by_id[event_id]["recorded_result"], {"labels_sha256": commitments[event_id], "recorded_in": RECORD_PATH})
                self.assertEqual(commitments[event_id], self.view[event_id]["labels_sha256"])
        self.assertEqual(sum("recorded_result" in e for e in self.spec["events"]), 43)                                       # every event of the extension is pinned
        self.assertEqual(len(self.spec["events"]), 43)
        ea.validate_spec(self.spec, self.calendar)

    def test_it_says_what_it_is_and_what_it_is_not(self):
        record = self.record
        self.assertEqual((record["schema_version"], record["kind"], record["recorded_on"]), (1, "m5_phase1b_batch5_sealed_run", "2026-10-15"))
        for phrase in ("The attested sealed run of batch 5, the last: config/m5-phase1b-events.json as pushed in 89111c5 (all five batch 5 events attested on the owner's signoff, none pinned yet), on top of 9e2021f and 1c590a9.",
                       "and the check of the thirty-eight pins of batches 1 to 4. No label value, price, return, day-1 or gap label exists in it.",
                       "The commitments are what the one-time Phase 4 recomputation is checked against; pinning them in the events file is a separate commit, "
                       "and nothing of batch 5 was pinned when this run happened (labels_match_recorded is null for the five)."):
            self.assertIn(phrase, record["what_this_is"])
        text = " ".join(record["findings"])
        for phrase in ("All five batch 5 events are MAPPED, now that the owner has attested them: the provider answered for each, all 21 required sessions are present, none has zero volume, and each has a commitment.",
                       "All five have all four session-return labels (session_2, _5, _10, _20). JBSS 2026-08-19 lists two cash dividends (ids b819a028-2051-49fd-bcd4-6505d853d06f and ef28820a-6a63-4119-b7eb-0d71f55b7a91), the two the dry run listed, both with ex-date 2026-08-17, "
                       "two days before its anchor session 2026-08-19: they fall inside no label's window (recomputed from the calendar), so no label is suppressed. The other four list no corporate action.",
                       "The filings the owner accepted as caveats (REKR's Item 3.01 filing and pre-announcement, and the in-window 8-Ks of JBSS, SLSN and OKTA) do not suppress labels; they travel with them.",
                       "The thirty-eight pins of batches 1 to 4 were checked again and all thirty-eight report labels_match_recorded true with the commitments of the earlier runs; nothing about them changed.",
                       "The five commitments are distinct from one another and from the thirty-eight pinned ones.",
                       "No event errored. JBSS, SLSN, OKTA and LOVE, the four events the first dry run's annotation limit hid, all computed, LOVE's window (which ends 2026-10-31) included: that fits the best guess recorded in the dry-run record about the first failure, "
                       "but it does not confirm it, and what failed in the first run remains unknown.",
                       "The view took ten annotation parts for forty-three events, the most GitHub keeps of one kind per step, and all ten are present; the last holds a single event, so a few events' worth of room is left under the limit."):
            self.assertIn(phrase, text)
        nots = " ".join(record["not_a_claim"])
        for phrase in ("Not an acceptance of Phase 1b or of the extension, which still has its sealed audit (S7).", "Not a label, a price or a return: the sealed view holds none, and none was read.",
                       "Not a pin: the five commitments are pinned in config/m5-phase1b-events.json by the commit that follows this record, and take effect only when that is pushed."):
            self.assertIn(phrase, nots)
        dry = load(ROOT / "reports" / "m5-phase1b-batch5-dry-run-2026-10-15.json")
        self.assertIn("Part 11/11, which would have held JBSS, SLSN, OKTA and LOVE.", dry["first_dry_run"]["what_was_not"])      # the four events the finding says the first dry run hid


if __name__ == "__main__":
    unittest.main()
