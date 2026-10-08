"""The Milestone 4 acceptance declaration (reports/m4-acceptance-declaration-2026-10-08.json): bound to the owner's exact word, the frozen protocol, the pinned evidence and the report's criteria. It reads
no outcome and no label, and needs no git history (a CI checkout has none)."""
import hashlib
import json
import unittest
from pathlib import Path

from nre import m4_protocol as pr

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "reports" / "m4-acceptance-declaration-2026-10-08.json"


def norm_sha256(relative):
    """sha256 of a file's bytes with Windows line endings turned into LF, so a checkout with CRLF and one with LF agree."""
    return hashlib.sha256((ROOT / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class AcceptanceDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.declaration = json.loads(PATH.read_text(encoding="utf-8"))

    def test_it_carries_the_owners_exact_word_and_the_message_it_answers(self):
        d = self.declaration
        self.assertEqual((d["exact_words"], d["exact_words_at"]), ("accepted", "2026-10-08T07:31:38.407Z"))
        self.assertEqual((d["declared_by"], d["declared_on"]), ("Fahad9101 (project owner)", "2026-10-08"))
        self.assertEqual(d["status"], "MILESTONE_4_DECLARED_ACCEPTED_BY_THE_PROJECT_OWNER")
        self.assertIn("line 33368", d["exact_words_source"])
        replied = d["assistant_message_replied_to"]
        self.assertTrue(replied.startswith("CI run #235 for `80a3848` passed on attempt 1"))
        self.assertIn("Whether Milestone 4 is accepted", replied)
        self.assertIn("Recommended next step", replied)

    def test_it_reads_the_word_narrowly_and_says_what_it_does_not_answer(self):
        text = " ".join(self.declaration["how_the_words_were_read"])
        for phrase in ("Milestone 4 (Baseline Predictive Models) is accepted", "criterion 7", "does not put words in the owner's mouth", "four review items", "five protocol-silent details",
                       "does not authorize Milestone 5"):
            self.assertIn(phrase, text)

    def test_it_is_bound_to_the_frozen_protocol_and_to_a_pushed_commit_whose_ci_passed(self):
        d = self.declaration
        protocol = pr.load_json(pr.PROTOCOL_PATH)
        self.assertEqual(d["governing_protocol"]["protocol_sha256"], pr.protocol_sha256(protocol))
        self.assertEqual((d["governing_protocol"]["frozen_at"], d["governing_protocol"]["amendments"]), ("2026-10-06T14:45:11Z", []))
        state = d["state_declared"]
        self.assertRegex(state["repository_head_at_declaration"], r"^80a3848[0-9a-f]{33}$")
        self.assertTrue(state["working_tree_clean_at_declaration"] and state["pushed"])
        self.assertEqual((state["ci_run"]["number"], state["ci_run"]["attempt"], state["ci_run"]["conclusion"]), (235, 1, "success"))
        self.assertEqual(d["acceptance_criterion"]["protocol_statement"], protocol["acceptance_of_the_m4_report"]["meaning"])

    def test_the_pinned_evidence_is_unchanged_since_it_was_accepted(self):
        pinned = self.declaration["basis"]["pinned_evidence_sha256_lf_normalized"]
        self.assertEqual(len(pinned), 18)
        for name, sha in pinned.items():
            self.assertEqual(norm_sha256(name), sha, name)
        lines = [x for x in (ROOT / "reports" / "m4-experiment-log.jsonl").read_bytes().replace(b"\r\n", b"\n").split(b"\n") if x.strip()]
        self.assertGreaterEqual(len(lines), 233)       # the log may grow in later work; the 233 records accepted may not change
        self.assertEqual(hashlib.sha256(b"\n".join(lines[:233]) + b"\n").hexdigest(), self.declaration["basis"]["experiment_log_first_233_records_sha256_lf_normalized"])
        for name in self.declaration["basis"]["as_accepted_not_asserted_by_the_binding_test"]:
            self.assertTrue((ROOT / name).is_file(), name)

    def test_the_report_the_owner_decided_on_has_the_criteria_it_had_and_the_access_count_only_grows(self):
        d = self.declaration
        report = json.loads((ROOT / "reports" / "m4-report-2026-10-07.json").read_text(encoding="utf-8"))
        current = {c["criterion"]: c["met_by_the_evidence"] for c in report["acceptance_criteria"]["criteria"]}
        self.assertEqual(current, d["acceptance_criterion"]["evidence_per_criterion_as_reported"])
        self.assertEqual(current["the holdout was looked at once"], "for the owner to judge")
        self.assertEqual(sum(1 for v in current.values() if v is True), 7)
        self.assertEqual(report["summary"]["development_statuses"], d["basis"]["report"]["development_statuses"])
        accounting = json.loads((ROOT / "reports" / "m4-phase4-replay-accesses-2026-10-07.json").read_text(encoding="utf-8"))
        self.assertEqual(d["basis"]["holdout_accesses"]["in_total"], 25)
        self.assertGreaterEqual(accounting["totals"]["accesses"], 25)      # a run of the opt-in replay tests adds to the record; it does not undo the acceptance

    def test_nothing_further_is_authorized_or_claimed_and_the_limits_are_carried(self):
        d = self.declaration
        text = " ".join(d["not_authorized_or_claimed"])
        for phrase in ("Milestone 5", "No second look", "No amendment", "No claim of a predictive edge", "changes no committed result"):
            self.assertIn(phrase, text)
        limits = " ".join(d["accepted_with_these_stated_limits"])
        for phrase in ("No predictor was distinguishable", "convenience sample", "25 times", "never recomputed independently", "unanswered", "The holdout is spent", "PYTHONTZPATH"):
            self.assertIn(phrase, limits)


if __name__ == "__main__":
    unittest.main()
