"""The replay-access accounting (reports/m4-phase4-replay-accesses-2026-10-07.json): the owner's decision to count the replays that re-read the block-5 outcomes as accesses, and every access
counted from primary sources. The record is data; these tests pin that it is consistent with itself, with the chained access log and with the protocol and the authorization record it
quotes. They read no outcome and no label."""
import json
import unittest
from pathlib import Path

from nre import m4_protocol as pr
from nre import m4_registry as reg

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "reports" / "m4-phase4-replay-accesses-2026-10-07.json"
AUTHORIZATION = ROOT / "reports" / "m4-phase4-authorization-2026-10-07.json"
WORDS = "Count the replays as accesses."


class AccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(PATH.read_text(encoding="utf-8"))
        cls.protocol = pr.load_json(pr.PROTOCOL_PATH)
        cls.chain = [record for record, _ in reg.read(reg.HOLDOUT_LOG)]

    def test_it_quotes_the_owners_decision_and_the_message_it_answers(self):
        decision = self.record["owner_decision"]
        self.assertEqual(decision["owner_message"]["text"], WORDS)
        self.assertEqual(decision["owner_message"]["at"], "2026-10-07T19:14:34.716Z")
        replied = decision["assistant_message_replied_to"]
        self.assertLess(replied["at"], decision["owner_message"]["at"])
        self.assertIn(WORDS, replied["text"])                                # the option the owner chose is in the message they answered
        self.assertIn("Make them opt-in", replied["text"])                   # and so is the one they did not choose
        self.assertIn("Accept them as uncounted verification", replied["text"])
        self.assertIn("This is a recommendation only", replied["text"])
        self.assertEqual(len(decision["not_decided_by_these_words"]), 3)
        self.assertTrue(any("only on request" in item for item in decision["not_decided_by_these_words"]))

    def test_the_accesses_are_numbered_from_the_look_and_every_replay_run_is_two_of_them(self):
        accesses = self.record["accesses"]
        self.assertEqual([a["access_number"] for a in accesses], list(range(1, len(accesses) + 1)))
        self.assertEqual([a["kind"] for a in accesses], ["the_look"] + ["replay"] * (len(accesses) - 1))
        replay_runs = [r for r in self.record["runs"] if r["kind"] == "replay"]
        self.assertEqual(len(accesses) - 1, 2 * len(replay_runs))
        for run in replay_runs:
            mine = [a for a in accesses if a["run"] == run["id"]]
            self.assertEqual([a["look_in_run"] for a in mine], [1, 2])
            self.assertEqual([a["access_number"] for a in mine], run["accesses"])
            self.assertEqual(run["class_setups"], 1)
        self.assertEqual([r["id"] for r in self.record["runs"]], ["R%d" % i for i in range(len(self.record["runs"]))])
        times = [r.get("started_at") or r["expected_after"] for r in self.record["runs"]]
        self.assertEqual(times, sorted(times))                               # numbered in the order they happened, the runs counted in advance last
        totals = self.record["totals"]
        self.assertEqual((totals["accesses"], totals["the_look"], totals["replay_accesses"], totals["replay_runs"]), (len(accesses), 1, len(accesses) - 1, len(replay_runs)))
        self.assertEqual(totals["replay_runs_local"] + totals["replay_runs_in_ci"], totals["replay_runs"])
        self.assertEqual((totals["loads_per_access"], totals["events_read_per_access"]), (46, 23))
        expected = [r for r in replay_runs if r.get("status") == "expected"]
        self.assertEqual((totals["found_runs"] + totals["expected_runs"], totals["expected_runs"], totals["expected_accesses"]), (len(replay_runs), len(expected), 2 * len(expected)))
        self.assertEqual(totals["found_accesses_with_the_look"], 1 + 2 * totals["found_runs"])

    def test_access_one_is_the_look_in_the_chained_log_and_the_chain_holds_nothing_else(self):
        look = self.record["runs"][0]
        self.assertEqual(len(self.chain), 2)                                 # its genesis and the look: the replays are not in the chain
        self.assertEqual(self.chain[1]["access_number"], 1)
        self.assertEqual(look["started_at"], self.chain[1]["created_at"])
        self.assertTrue(look["tree"].endswith(self.chain[1]["harness_commit"][:7]))
        self.assertEqual(len(self.chain[1]["events_read"]), self.record["totals"]["events_read_per_access"])
        self.assertTrue(self.chain[1]["reason"].startswith("Milestone 4 Phase 4: the one look at the final holdout"))
        self.assertTrue(self.record["accesses"][0]["recorded_in"].startswith("reports/m4-holdout-access-log.jsonl"))
        self.assertTrue(all(a["recorded_in"].startswith("this file only") for a in self.record["accesses"][1:]))

    def test_it_quotes_the_protocols_counting_rules_and_the_replay_design_disclosed_before_the_look_verbatim(self):
        rules = self.record["rules_applied"]
        self.assertEqual(rules["protocol_holdout_sealing"], self.protocol["holdout"]["sealing"])
        self.assertEqual(rules["protocol_holdout_a_technical_rerun"], self.protocol["holdout"]["a_technical_rerun"])
        authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
        p4_11 = next(i for i in authorization["details_settled_before_the_look"]["new_in_phase_4"] if i["id"] == "P4-11")
        self.assertIn(rules["disclosed_before_the_look"]["text"], p4_11["detail"])
        self.assertIn("did not say the replays would be counted", rules["disclosed_before_the_look"]["note"])

    def test_every_run_has_its_source_and_none_ran_before_the_look(self):
        look_at = self.record["runs"][0]["started_at"]
        for run in self.record["runs"]:
            for key in ("id", "kind", "started_at" if run.get("status") != "expected" else "expected_after", "where", "what", "result", "source", "tree"):
                self.assertTrue(run[key], (run["id"], key))
        for run in self.record["runs"][1:]:
            if run.get("status") == "expected":
                self.assertGreater(run["expected_after"], look_at)
                self.assertEqual(run["result"], "expected")
                self.assertTrue(run["source"].startswith("expected: counted in advance"), run["source"])
                continue
            self.assertGreater(run["started_at"], look_at)
            self.assertTrue(run["source"].startswith("session transcript line") or run["source"].startswith("https://api.github.com/repos/Fahad9101/NRE/actions/runs/"), run["source"])

    def test_the_runs_counted_in_advance_are_the_closing_pass_and_the_ci_run_of_the_push_and_name_their_authority(self):
        runs = self.record["runs"]
        expected = [r for r in runs if r.get("status") == "expected"]
        self.assertEqual([r["id"] for r in expected], [r["id"] for r in runs[-2:]])      # they come last
        self.assertTrue(expected[0]["where"].startswith("local") and "whole suite" in expected[0]["what"])
        self.assertTrue(expected[1]["where"].startswith("GitHub Actions") and "push" in expected[1]["what"])
        authority = self.record["closing_runs_authorized_by"]
        self.assertEqual((authority["text"], authority["at"]), ("yes continuewith the closing work and push at the end", "2026-10-08T05:26:44.063Z"))
        for run in expected:
            self.assertIn(authority["text"], run["source"])
        self.assertIn("counted before they happened", " ".join(self.record["limits"]))

    def test_the_rules_for_what_happens_next_and_the_limits_are_stated(self):
        going_forward = " ".join(self.record["going_forward"])
        self.assertIn("two more accesses", going_forward)
        self.assertIn("CI", going_forward)
        self.assertIn("not counted unless they are reported", going_forward)
        self.assertIn("lower bound", " ".join(self.record["limits"]))
        self.assertIn("Not Milestone 4 acceptance", " ".join(self.record["not_a_claim"]))


if __name__ == "__main__":
    unittest.main()
