"""What Milestone 5 scoping recorded about itself: the owner's go-ahead and how it was read (reports/m5-scoping-authorization-2026-10-08.json), the owner's answer to the proposal's six decisions
(reports/m5-scope-confirmation-2026-10-08.json), and the proposal (docs/M5-ADVANCED-MODELS-SCOPE.md) bound to the evidence and the documents it cites."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORIZATION = ROOT / "reports" / "m5-scoping-authorization-2026-10-08.json"
CONFIRMATION = ROOT / "reports" / "m5-scope-confirmation-2026-10-08.json"
PROPOSAL = ROOT / "docs" / "M5-ADVANCED-MODELS-SCOPE.md"


def decisions_of(text):
    """The six numbered items of the proposal's section 6 as (number, title, recommended default, the rest of the item), in the words written there with line breaks flattened."""
    section = text[text.index("## 6. Decisions needed"):text.index("## 7.")]
    flat = " ".join(section.split())
    flat = flat[flat.index("1. **"):]
    out = []
    for number, title, body in re.findall(r"(\d)\. \*\*([^*]+?)\.\*\* (.+?)(?= \d\. \*\*|$)", flat):
        assert body.startswith("Recommended: "), body
        cut = min(i for i in (body.find(marker) for marker in (" Alternatives:", " Alternative:", " Note that")) if i != -1)
        out.append((int(number), title, body[len("Recommended: "):cut], body[cut + 1:]))
    return out


class AuthorizationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("authorize m5 scoping", "2026-10-08T07:43:52.358Z")])
        self.assertIn("line 33553", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertTrue(replied["text"].startswith("CI run #236 for `fb33eea` passed on attempt 1"))
        self.assertIn('say "authorize m5 scoping"', replied["text"])
        self.assertIn("It is a recommendation only", replied["text"])

    def test_it_reads_the_words_narrowly_and_says_so(self):
        text = " ".join(self.record["how_the_words_were_read"])
        for phrase in ("a scoping proposal, nothing built", "committed", "does not authorize reading any block-5 outcome again", "Milestone 4 stays as accepted", "decisions the proposal lists are the owner's",
                       "has seen the Milestone 4 holdout's results"):
            self.assertIn(phrase, text)

    def test_what_is_authorized_and_what_is_not_is_listed(self):
        record = self.record
        done = " ".join(record["authorized_and_done_under_these_words"])
        for name in ("docs/M5-ADVANCED-MODELS-SCOPE.md", "nre/m5_scoping_evidence.py", "reports/m5-scoping-evidence-2026-10-08.json", "tests/test_m5_scoping_record.py"):
            self.assertIn(name, done)
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Building any Milestone 5", "Pre-registering a Milestone 5 protocol", "Acquiring any data", "Any read of a block-5 outcome", "Declaring Milestone 5 accepted",
                       "Any change to the accepted Milestone 4 work", "Choosing among the decisions"):
            self.assertIn(phrase, not_authorized)
        self.assertIn("Not a start of Milestone 5 building", " ".join(record["not_a_claim"]))


class ConfirmationRecordTests(unittest.TestCase):
    """The owner's answer to the six decisions: his words, the decisions word for word, and that no phase is authorized."""
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(CONFIRMATION.read_text(encoding="utf-8"))
        cls.note = PROPOSAL.read_text(encoding="utf-8")

    def test_it_quotes_the_owners_words_and_the_message_they_answer(self):
        record = self.record
        self.assertEqual(record["status"], "MILESTONE_5_SCOPE_DECISIONS_MADE_BY_THE_PROJECT_OWNER_NO_PHASE_AUTHORIZED")
        self.assertEqual([(m["text"], m["at"]) for m in record["owner_messages"]], [("take your defaults for all six", "2026-10-08T16:07:04.055Z")])
        self.assertIn("line 34796", record["owner_messages"][0]["source"])
        replied = record["assistant_message_replied_to"]
        self.assertLess(replied["at"], record["owner_messages"][0]["at"])
        self.assertTrue(replied["text"].startswith("Both commits are on `origin/main` (`fb33eea..622de37`), and CI is green."))
        for phrase in ('"take your defaults for all six" is a valid answer', "**Recommended next step:** answer decision 1", "each need your separate go-ahead", "This is a recommendation, not an authorization."):
            self.assertIn(phrase, replied["text"])

    def test_the_six_decisions_are_the_proposals_recommended_defaults_word_for_word(self):
        decisions = self.record["decisions"]
        self.assertEqual(decisions_of(self.note), [(d["number"], d["title"], d["recommended_default"], d["alternatives_and_notes_as_written"]) for d in decisions])
        self.assertEqual([d["number"] for d in decisions], [1, 2, 3, 4, 5, 6])
        for decision in decisions:
            self.assertEqual(decision["decided"], "the recommended default")
            self.assertTrue(decision["effect"] and decision["still_needed_before_it_takes_effect"])
        self.assertIn("not authorized by it", decisions[1]["still_needed_before_it_takes_effect"])                      # decision 2 names the probe and the data steps
        self.assertIn("does not answer Milestone 4's review item", decisions[4]["still_needed_before_it_takes_effect"])    # decision 5 sets Milestone 5's structure only
        self.assertIn("not authorized by this decision", decisions[5]["still_needed_before_it_takes_effect"])             # decision 6 names the probe
        proposal = self.record["proposal_as_decided"]
        self.assertEqual((proposal["document"], proposal["pushed"]), ("docs/M5-ADVANCED-MODELS-SCOPE.md", True))
        self.assertTrue(proposal["commit"].startswith("622de37") and len(proposal["commit"]) == 40)
        self.assertEqual(len(proposal["sha256_of_the_document_at_that_commit_line_endings_normalized"]), 64)             # recorded for that commit; the document is a living file

    def test_it_decides_but_authorizes_no_phase_and_keeps_the_change_rule(self):
        record = self.record
        not_authorized = " ".join(record["not_authorized_by_these_words"])
        for phrase in ("Phase 1a, the availability probe", "Phase 1b", "Phase 1c", "Phase 0, pre-registering", "Phase 2", "Phase 3", "Phase 4", "Any read of a block-5 outcome",
                       "Purchasing or licensing any dataset", "Declaring Milestone 5 accepted", "Any change to the accepted Milestone 4 work"):
            self.assertIn(phrase, not_authorized)
        done = " ".join(record["authorized_and_done_under_these_words"])
        self.assertIn("reports/m5-scope-confirmation-2026-10-08.json", done)
        self.assertNotIn("config/m5-protocol.json", done)
        read = " ".join(record["how_the_words_were_read"])
        for phrase in ("It decides; it authorizes no phase", "The probe is Phase 1a", "which stay at their defaults"):
            self.assertIn(phrase, read)
        self.assertIn("does not change a confirmed default on its own", record["change_rule"])
        self.assertIn("Not a start of Milestone 5 building", " ".join(record["not_a_claim"]))
        proposed = record["order_proposed_after_the_decisions"]
        self.assertFalse(proposed["is_a_decision"])
        self.assertEqual([step.split(":")[0] for step in proposed["order"]], ["1a", "1b", "0", "1c", "2", "3", "4"])
        self.assertEqual(proposed["each_step_needs"], "its own explicit go-ahead from the owner")


class ScopeNoteTests(unittest.TestCase):
    """The proposal (docs/M5-ADVANCED-MODELS-SCOPE.md) is bound to the evidence it cites, to the governing text it quotes and to the files it names."""
    NOTE = PROPOSAL
    EVIDENCE = ROOT / "reports" / "m5-scoping-evidence-2026-10-08.json"
    MASTER, CONTRACT, PROTOCOL = "docs/NRE-1.0-MASTER-PROMPT.md", "docs/MILESTONE-0-TECHNICAL-CONTRACT.md", "config/m4-protocol.json"
    # every quotation the proposal takes from a governing document, as the proposal writes it between quotation marks: it must be in that document word for word (case and line breaks aside)
    QUOTES = [(MASTER, "Perform calibration and ablation studies. Promote only improvements that survive out-of-sample testing."), (MASTER, "promote only improvements that survive out-of-sample testing"),
              (PROTOCOL, "a replication check on direction and a single, logged exposure of the frozen pipeline to data it was not developed on; not a source of statistical power"),
              (MASTER, "the production model should win on out-of-sample performance, not complexity"), (MASTER, "calibration matters more than flashy classification accuracy"),
              (MASTER, "repeated tuning against the same holdout period"), (MASTER, "where justified"), (CONTRACT, "only with incremental out-of-sample evidence"),
              (CONTRACT, "Freeze a final chronological holdout before iterative research"), (CONTRACT, "absent historical consensus and market-structure vintages"), (CONTRACT, "for later milestones")]
    # words the proposal puts between quotation marks that are its own: terms and proposed labels or wordings, not quotations of anything
    OWN_WORDS = ["promotion", "no improvement could be shown", "an advanced model beats the strongest baseline", "carried forward as a candidate expected-reaction model for Milestone 6",
                 "validated for use", "Milestone 2 step 4", "Milestone 5 done", "no promotion", "no improvement shown"]
    # files the proposal names as something a later phase would create if it is authorized: they need not exist and are named only in the proposed scope (section 3)
    PROPOSED = {"config/m5-protocol.json"}

    @classmethod
    def setUpClass(cls):
        cls.text = cls.NOTE.read_text(encoding="utf-8")
        cls.evidence = json.loads(cls.EVIDENCE.read_text(encoding="utf-8"))
        cls.confirmation = json.loads(CONFIRMATION.read_text(encoding="utf-8"))

    def test_it_says_nothing_is_built_the_decisions_are_made_and_no_phase_is_authorized(self):
        flat = " ".join(self.text.split())
        for phrase in ("Nothing for Milestone 5 is built and no phase of section 3 is authorized: each needs its own go-ahead", "its six decisions were then made the same day, each at the recommended default",
                       "It fits nothing, predicts nothing, reads no event-level outcome and acquires no data", "it uses no result of the Milestone 4 holdout", "does not decide any of section 6",
                       "it does not start Milestone 5", "does not pre-register anything", "**A disclosure:** the assistant writing this proposal has seen the block-5 results"):
            self.assertIn(phrase, flat)
        self.assertNotIn("Every decision in section 6 is open", flat)
        for name in ("reports/m5-scoping-authorization-2026-10-08.json", "reports/m5-scope-confirmation-2026-10-08.json"):
            self.assertIn(name, self.text)

    def test_the_order_it_proposes_for_the_go_aheads_is_a_proposal_and_is_the_records(self):
        flat = " ".join(self.text.split())
        proposed = self.confirmation["order_proposed_after_the_decisions"]
        self.assertFalse(proposed["is_a_decision"])
        self.assertIn("An order is proposed here after the decisions, and is not itself a decision: %s," % ", ".join(step.split(":")[0] for step in proposed["order"]), flat)
        self.assertIn("Made on 2026-10-08, all six at the recommended default (`reports/m5-scope-confirmation-2026-10-08.json`)", flat)

    def test_its_tables_and_figures_are_the_evidences(self):
        from nre import m5_scoping_evidence as ev
        flat = " ".join(self.text.split())
        self.assertNotIn("{{", self.text)
        for table in ev.tables(self.evidence).values():
            for line in table.splitlines():
                self.assertIn(line, self.text)
        for key, value in ev.figures(self.evidence).items():
            self.assertIn(value, flat, key)
        self.assertIn("about %s such events" % ev.figures(self.evidence)["SUPPLY"], flat)          # and says it is an estimate, not a count
        self.assertIn("an estimate, not a count", flat)

    def test_each_sentence_that_uses_a_figure_uses_the_evidences_figure(self):
        """A figure that is right in the tables but wrong in the prose would pass an 'appears somewhere' check, so each sentence is checked whole."""
        from nre import m5_scoping_evidence as ev
        flat = " ".join(self.text.split())
        values = dict(ev.figures(self.evidence))
        cells = self.evidence["detectability"]
        main = [cell for name, cell in cells.items() if not name.startswith("loses_half_of_gap")]
        calibration = [fold["if_a_fifth_is_held_back_twice"]["held_back_for_calibration"] for fold in self.evidence["fold_sizes"]["extension_after_open_ge_5pct/clean_window"].values()]
        accounting = json.loads((ROOT / "reports" / "m4-phase4-replay-accesses-2026-10-07.json").read_text(encoding="utf-8"))
        values.update(EVENTS_MIN=min(c["events"] for c in main), EVENTS_MAX=max(c["events"] for c in main), LOSES_EVENTS=cells["loses_half_of_gap/all_event"]["events"],
                      EXT_CAL_MIN=min(calibration), EXT_CAL_MAX=max(calibration), ACCESSES=accounting["totals"]["accesses"], DATASET=self.evidence["data_supply"]["events"])
        sentences = [
            "Milestone 4's confirmatory contrasts had 99% half-widths of {SHARE_MIN} to {SHARE_MAX} of the comparator's score on the main targets",
            "would take about {EV5_MIN} to {EV5_MAX} test events, {X_POOLED_MIN} to {X_POOLED_MAX} times the pooled test sets Milestone 4 had and {X_DATASET_MIN} to {X_DATASET_MAX} times the whole dataset of {DATASET}",
            "the dataset's own rate suggests about {SUPPLY} such events exist since the data ended (an estimate, not a count)",
            "At {TRAIN_MIN} to {TRAIN_MAX} training events (the four main targets)",
            "needs a held-out calibration period inside every fold: {CAL_MIN} to {CAL_MAX} events here",
            "on today's pooled development test sets ({EVENTS_MIN} to {EVENTS_MAX} events) an improvement has to be about {SHARE_MIN} to {SHARE_MAX} of the comparator's score",
            "and {LOSES_SHARE} for `loses_half_of_gap`, whose test set is {LOSES_EVENTS} events",
            "Seeing a 5% improvement would take about {EV5_MIN} to {EV5_MAX} test events; a 10% improvement, about {EV10_MIN} to {EV10_MAX}.",
            "would leave half-widths of {SHARE_AT_128_MIN} to {SHARE_AT_128_MAX}",
            "with {EXT_CAL_MIN} to {EXT_CAL_MAX} events to calibrate on",
            "At the dataset's own rate ({SUPPLY_FORMULA}) about {SUPPLY} events would have occurred since",
            "the {ACCESSES} counted accesses"]
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                self.assertIn(sentence.format(**values), flat)

    def test_every_quotation_is_verbatim_the_owners_or_declared_to_be_the_proposals_own_wording(self):
        flat = " ".join(self.text.split())
        self.assertEqual(self.text.count('"') % 2, 0)                              # so that quotation marks pair up
        spans = re.findall(r'"([^"]*)"', flat)
        self.assertGreaterEqual(len(spans), 20)                                    # the extraction found the quotations
        for source, words in self.QUOTES:                                          # a governing quotation is in its document word for word, and the proposal does say it
            with self.subTest(source=source, words=words):
                self.assertIn(words.lower(), " ".join((ROOT / source).read_text(encoding="utf-8").split()).lower())
                self.assertIn('"%s"' % words, flat)
        owners = [m["text"] for path in (AUTHORIZATION, CONFIRMATION) for m in json.loads(path.read_text(encoding="utf-8"))["owner_messages"]]
        self.assertEqual(owners, ["authorize m5 scoping", "take your defaults for all six"])
        known = {words for _, words in self.QUOTES} | set(self.OWN_WORDS) | set(owners)
        for span in spans:                                                         # and nothing else is in quotation marks
            with self.subTest(span=span):
                self.assertIn(span, known)
        for words in self.OWN_WORDS:                                               # the list of its own words holds no stale entry
            with self.subTest(own=words):
                self.assertIn('"%s"' % words, flat)

    def test_what_it_says_led_on_development_is_what_the_evidence_says_led(self):
        flat = " ".join(self.text.split())
        words = {"C4_issuer_history_rate": "the issuer-history rate", "C3_sector_group_quantiles": "the sector-group quantiles", "C1_pooled_rate": "the pooled rate"}
        led = {}
        for name, cell in self.evidence["detectability"].items():
            self.assertEqual(cell["strongest_m4_predictor"], cell["strongest_simple_baseline"], name)          # no logistic or ridge model led in any evaluated cell
            led.setdefault(name.split("/")[0], set()).add(words[cell["strongest_m4_predictor"]])
        self.assertTrue(all(len(v) == 1 for v in led.values()), led)                                         # and the same one led in both versions of a target
        led = {target: next(iter(v)) for target, v in led.items()}
        self.assertEqual(led["gap_ge_3pct"], led["gap_ge_5pct"])
        self.assertEqual(led["gap_ge_3pct"], led["loses_half_of_gap"])
        self.assertIn("the best-scoring Milestone 4 predictor in every evaluated cell was a simple baseline: %s for the 3%% and 5%% gaps and `loses_half_of_gap`, %s for the Day-1 return, %s for the extension target. "
                      "The logistic and ridge models never led." % (led["gap_ge_3pct"], led["day1_close_return"], led["extension_after_open_ge_5pct"]), flat)

    def test_what_it_says_about_the_data_the_project_holds_is_what_its_own_records_say(self):
        flat = " ".join(self.text.split())
        policy = json.loads((ROOT / "config" / "fingerprint-policy.json").read_text(encoding="utf-8"))
        per_issuer = self.evidence["data_supply"]["events_per_issuer_in_the_fingerprint_table_note"]
        self.assertLess(per_issuer["most"], policy["mean_median"]["report_from_n"])
        self.assertIn("%d to %d events per issuer (none has the %d needed for a mean or median, or the %d for quantiles)" % (
            per_issuer["fewest"], per_issuer["most"], policy["mean_median"]["report_from_n"], policy["quantiles"]["report_from_n"]), flat)
        self.assertIn("(at least %d members; the distance has only timing and sector terms)" % policy["analogues"]["min_members"], flat)
        self.assertEqual(sorted(policy["analogues"]["distance"]), ["sector_mismatch", "timing_mismatch"])
        example = " ".join((ROOT / "reports" / "m3-worked-example-jbss-catalyst-features-2026-09-30.json").read_text(encoding="utf-8").split())
        self.assertIn("exists for only a handful of worked examples", example)               # Milestone 3's own statement of how much real surprise data there is
        self.assertIn("NOT_COMPUTED", example)
        self.assertIn("a computed surprise exists only for a handful of worked examples", flat)
        m3 = " ".join((ROOT / "reports" / "m3-acceptance-declaration-2026-09-30.json").read_text(encoding="utf-8").split())
        self.assertIn("vs. consensus are both out of scope by explicit owner decision", m3)    # and of why consensus and guidance surprise are out of scope
        self.assertIn("consensus and guidance surprise are out of scope by decision", flat)

    def test_the_milestones_it_says_are_not_this_ones_are_the_master_prompts(self):
        flat = " ".join(self.text.split())
        master = (ROOT / self.MASTER).read_text(encoding="utf-8")
        for claim, heading in (("rank or select candidates or produce a candidate list (Milestone 7)", "## Milestone 7 — Real-Time Candidate Ranking"),
                               ("compute a reaction gap (Milestone 6)", "## Milestone 6 — Reaction Gap Engine"), ("run a paper-trading validation (Milestone 8)", "## Milestone 8 — Paper-Trading Validation")):
            with self.subTest(claim=claim):
                self.assertIn(claim, flat)
                self.assertIn(heading, master)
        for number in ("22. BACKTESTING", "23. TRANSACTION-COST SENSITIVITY"):          # "backtest or model transaction costs (no execution data exists; master prompt sections 22 and 23)"
            self.assertIn("# " + number, master)
        self.assertIn("master prompt sections 22 and 23", flat)
        self.assertIn("Collect:", master[master.index("## Milestone 8"):])               # Milestone 8 is where the master prompt collects the execution evidence
        self.assertIn("slippage", master[master.index("## Milestone 8"):master.index("## Milestone 9")])

    def test_the_six_decisions_are_there_each_with_a_recommendation(self):
        for number, title in enumerate(("Shape of Milestone 5", "Data", "Holdout", "Implementation", "Claim level and structure", "Market-structure features"), 1):
            self.assertIn("%d. **%s.**" % (number, title), self.text)
        section = self.text[self.text.index("## 6. Decisions needed"):self.text.index("## 7.")]
        self.assertEqual(section.count("Recommended:"), 6)

    def test_every_file_it_names_exists_unless_it_is_a_proposed_one_named_only_in_the_proposed_scope(self):
        names = sorted(set(re.findall(r"`((?:reports|docs|nre|tests|config|scripts)/[A-Za-z0-9_./\-]+\.(?:json|jsonl|md|py))`", self.text)))
        self.assertGreaterEqual(len(names), 7)
        scope = self.text[self.text.index("## 3. Proposed scope"):self.text.index("## 4. ")]
        elsewhere = self.text.replace(scope, "")
        for name in names:
            with self.subTest(name=name):
                if name in self.PROPOSED:
                    self.assertIn(name, scope)
                    self.assertNotIn(name, elsewhere)                              # outside section 3 it would read as something that exists
                else:
                    self.assertTrue((ROOT / name).is_file())
        self.assertLessEqual(self.PROPOSED, set(names))                            # the list holds no stale entry


if __name__ == "__main__":
    unittest.main()
