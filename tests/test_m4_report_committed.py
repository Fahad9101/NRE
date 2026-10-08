"""The committed Milestone 4 report (reports/m4-report-2026-10-07.json) is what nre/m4_report.py assembles from the committed artifacts, and says what the evidence says. It is evidence,
not a decision: the acceptance decision is the owner's."""
import json
import unittest
from pathlib import Path

from nre import m4_report as rep
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "reports" / "m4-report-2026-10-07.json"


class CommittedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.committed = json.loads(PATH.read_text(encoding="utf-8"))

    def test_it_is_what_the_code_assembles_from_the_committed_artifacts(self):
        self.assertEqual(digest(canonical(rep.assemble(ROOT, "2026-10-07"))), digest(canonical(self.committed)))

    def test_it_states_the_development_statuses_the_holdout_states_and_the_directions(self):
        report = self.committed
        self.assertEqual(report["summary"]["development_statuses"], {"gap_ge_3pct": "NOT_DISTINGUISHABLE", "gap_ge_5pct": "NOT_DISTINGUISHABLE", "day1_close_return": "NOT_DISTINGUISHABLE",
                                                                    "extension_after_open_ge_5pct": "NOT_DISTINGUISHABLE", "loses_half_of_gap": "INSUFFICIENT_DATA"})
        self.assertEqual(sorted(map(tuple, report["estimable"]["holdout"]["evaluated"])), sorted([("extension_after_open_ge_5pct", v) for v in ("all_event", "clean_window")]
                                                                                              + [("day1_close_return", v) for v in ("all_event", "clean_window")]))
        self.assertEqual(len(report["estimable"]["holdout"]["counts_only"]), 6)
        self.assertEqual(len(report["estimable"]["not_modelled"]), 14)
        self.assertEqual({k: v["same_sign"] for k, v in report["summary"]["holdout_direction_checks"].items()}, {k: False for k in report["summary"]["holdout_direction_checks"]})
        self.assertEqual(len(report["summary"]["holdout_direction_checks"]), 4)
        self.assertEqual((report["summary"]["pooled_development_contrasts"]["excluding_zero_at_95"], report["summary"]["holdout_contrasts"]["excluding_zero_at_95"]), (0, 1))

    def test_every_acceptance_criterion_has_its_evidence_and_the_decision_is_left_to_the_owner(self):
        criteria = self.committed["acceptance_criteria"]
        self.assertEqual(len(criteria["criteria"]), 8)
        self.assertTrue(all(c["evidence"] for c in criteria["criteria"]))
        others = [c for c in criteria["criteria"] if c["criterion"] != "the holdout was looked at once"]
        self.assertTrue(all(c["met_by_the_evidence"] is True for c in others))
        looked_once = next(c for c in criteria["criteria"] if c["criterion"] == "the holdout was looked at once")
        self.assertEqual(looked_once["met_by_the_evidence"], rep.JUDGMENT)  # one look in the chain; the replays the owner counted as accesses make it a judgment, which is theirs
        self.assertIn("nothing here declares Milestone 4 accepted", criteria["decision"])
        self.assertEqual(self.committed["integrity"]["protocol"]["amendments"], [])

    def test_it_states_every_access_the_look_in_the_chain_and_the_replays_the_owner_counted(self):
        accounting = json.loads((ROOT / "reports" / "m4-phase4-replay-accesses-2026-10-07.json").read_text(encoding="utf-8"))
        logs = self.committed["integrity"]["logs"]
        self.assertEqual(logs["holdout_accesses_after_genesis"], 1)  # the chained log holds the look only; the replays are in the accounting record
        self.assertEqual(logs["holdout_accesses"], {"logged_in_the_chain": 1, "replays_counted": accounting["totals"]["replay_accesses"], "in_total": accounting["totals"]["accesses"],
                                                    "accounting_record": "reports/m4-phase4-replay-accesses-2026-10-07.json", "owner_decision": accounting["owner_decision"]["owner_message"]})
        self.assertEqual(self.committed["summary"]["holdout_accesses_in_total"], accounting["totals"]["accesses"])
        self.assertEqual(logs["holdout_accesses"]["owner_decision"]["text"], "Count the replays as accesses.")

    def test_the_open_review_items_are_there_for_the_owner(self):
        owner = self.committed["open_for_the_owner"]
        self.assertIn("has not answered", owner["status"])
        self.assertEqual(len(owner["from_the_protocol_to_review"]), 4)
        self.assertEqual(len(owner["protocol_silent_details_that_could_move_a_result"]), 5)
        self.assertIsNone(owner["replay_tests"]["open"])                              # the owner decided: the replay tests are opt-in
        self.assertEqual((owner["replay_tests"]["opt_in"]["decided_by"]["text"], owner["replay_tests"]["opt_in"]["switch"]), ("make the replay tests opt-in", "M4_REPLAY_HOLDOUT=1"))


if __name__ == "__main__":
    unittest.main()
