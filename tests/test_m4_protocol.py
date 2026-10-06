"""Guards the frozen Milestone 4 protocol (config/m4-protocol.json, version 1): its hash, the inputs it pins, the counts it states and the decisions it encodes.

This checks a document. It implements no Milestone 4 logic: no model, no harness, no evaluation.
"""
import json
import unittest
from pathlib import Path

from nre import caveat_sensitivity as cs
from nre import fingerprints as fp
from nre import m4_scoping_evidence as ev
from nre.core import canonical, digest

ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_REL = "config/m4-protocol.json"
FREEZE_REL = "reports/m4-protocol-freeze-2026-10-06.json"
THRESHOLD = 10


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def file_digest(rel):
    return digest(canonical(load(rel)))


PROTOCOL = load(PROTOCOL_REL)
FREEZE = load(FREEZE_REL)
SPEC = load(PROTOCOL["inputs"]["events_spec"]["path"])
INPUTS = fp.load_inputs(spec_path=ROOT / PROTOCOL["inputs"]["events_spec"]["path"], calendar_path=ROOT / PROTOCOL["inputs"]["calendar"]["path"])
BLOCKS = ev.assign_blocks(INPUTS["events"])
FUNCTIONS = {t[0]: t[3] for t in ev.TARGETS}
CLEAN = cs.variant_inputs(INPUTS, cs.caveated_pairs(SPEC, with_derived=True), "with_derived")
VERSIONS = {"all_event": INPUTS, "clean_window": CLEAN}
FOLDS = {"dev_test_block_3": ([1, 2], 3), "dev_test_block_4": ([1, 2, 3], 4), "holdout_test_block_5": ([1, 2, 3, 4], 5)}


def count(values):
    return {"defined": sum(v is not None for v in values), "pos": sum(1 for v in values if v), "neg": sum(1 for v in values if v is False)}


def fold_counts(version, target, fold):
    train_blocks, test_block = FOLDS[fold]
    fn = FUNCTIONS[target]
    events = VERSIONS[version]["events"]
    return (count([fn(e["labels"]) for e in events if BLOCKS[e["event_id"]] in train_blocks]),
            count([fn(e["labels"]) for e in events if BLOCKS[e["event_id"]] == test_block]))


def meets(c):
    return c["pos"] >= THRESHOLD and c["neg"] >= THRESHOLD


class IntegrityTests(unittest.TestCase):
    def test_the_frozen_protocol_matches_its_recorded_hash(self):
        self.assertEqual(digest(canonical(PROTOCOL)), FREEZE["protocol"]["canonical_sha256"])

    def test_version_1_has_no_amendments(self):
        self.assertEqual((PROTOCOL["protocol_version"], PROTOCOL["amendments"]["history"]), ("1", []))
        self.assertEqual(FREEZE["protocol"]["protocol_version"], "1")

    def test_the_pinned_files_are_unchanged(self):
        pins = PROTOCOL["inputs"]
        for key in ("events_spec", "calendar", "fingerprint_policy", "sector_map", "scoping_evidence", "caveat_check"):
            self.assertEqual(file_digest(pins[key]["path"]), pins[key]["canonical_sha256"], key)

    def test_the_pinned_derived_inputs_are_unchanged(self):
        pins = PROTOCOL["inputs"]
        provenance = fp.provenance(INPUTS, "m4_protocol_guard")
        self.assertEqual(provenance["inputs"]["event_table_sha256"], pins["event_table_sha256"])
        self.assertEqual(digest(canonical({e["event_id"]: e["labels_sha256"] for e in INPUTS["events"]})), pins["event_labels_sha256"])
        self.assertEqual(digest(canonical(BLOCKS)), pins["block_assignment_sha256"])
        self.assertEqual(digest(canonical({k: sorted(v) for k, v in sorted(cs.caveated_pairs(SPEC).items())})), pins["caveated_labels"]["as_recorded_sha256"])
        derived = cs.caveated_pairs(SPEC, with_derived=True)
        self.assertEqual(digest(canonical({k: sorted(v) for k, v in sorted(derived.items())})), pins["caveated_labels"]["with_derived_labels_sha256"])
        self.assertEqual(len(derived), pins["caveated_labels"]["events_with_caveats"])

    def test_the_freeze_record_pins_the_same_inputs(self):
        self.assertEqual(FREEZE["inputs_pinned"], PROTOCOL["inputs"])

    def test_the_freeze_says_nothing_was_evaluated(self):
        state = FREEZE["state_at_freeze"]
        self.assertFalse(any(state[k] for k in ("a_baseline_model_or_harness_exists", "any_predictor_fitted_scored_or_evaluated", "any_development_fold_evaluated",
                                                "any_holdout_access")))


class StructureTests(unittest.TestCase):
    def test_the_yardsticks_are_the_ones_the_scoping_evidence_declared(self):
        self.assertEqual(ev.BLOCK_GAP_DAYS, 28)
        self.assertEqual(ev.MIN_TRAIN_EVENTS, PROTOCOL["blocks_and_folds"]["minimum_training_events_to_fit"])
        self.assertEqual((ev.BUCKETS["estimable_at_or_above"], ev.BUCKETS["thin_at_or_above"]), (30, THRESHOLD))
        self.assertIn("more than 28 calendar days", PROTOCOL["blocks_and_folds"]["block_rule"])

    def test_blocks_and_folds_follow_the_rule_and_need_no_purge(self):
        sizes = [sum(1 for b in BLOCKS.values() if b == n) for n in range(1, 6)]
        self.assertEqual(sizes, PROTOCOL["blocks_and_folds"]["expected_blocks"]["sizes"])
        self.assertEqual([f["test_block"] for f in PROTOCOL["blocks_and_folds"]["development_folds"]], [3, 4])
        self.assertEqual(PROTOCOL["blocks_and_folds"]["final_holdout_fold"]["test_block"], 5)
        for boundary in load("reports/m4-scoping-evidence-2026-10-03.json")["time_structure"]["boundaries"]:
            self.assertGreater(boundary["slack_days"], 0)

    def test_primary_targets_are_few_and_cover_the_four_families(self):
        primary = PROTOCOL["targets"]["primary"]
        self.assertLessEqual(len(primary), 6)
        self.assertEqual({t["master_prompt_family"] for t in primary}, {"opening gap", "Day-1 move", "gap retention", "continuation/fade"})
        self.assertEqual({t["clock"] for t in primary}, {"B", "C0"})

    def test_every_target_is_classified_by_the_rule_and_agrees_with_the_evidence(self):
        evidence = {t["target"]: t for t in load("reports/m4-scoping-evidence-2026-10-03.json")["targets"]}
        groups = PROTOCOL["targets"]
        listed = [t["id"] for t in groups["primary"] if t["kind"] == "binary"] + [t["id"] for t in groups["descriptive_only"]] \
            + [t["id"] for t in groups["insufficient_data_by_rule"]]
        self.assertEqual(sorted(listed), sorted(evidence))
        for t in groups["primary"]:
            if t["kind"] == "binary":
                self.assertEqual(t["counts_at_freeze_all_event"], {k: evidence[t["id"]][k] for k in ("n_defined", "positives", "negatives")})
        for t in groups["descriptive_only"] + groups["insufficient_data_by_rule"]:
            row, counts = evidence[t["id"]], t["counts_at_freeze_all_event"]
            self.assertEqual(counts, {k: row[k] for k in ("n_defined", "positives", "negatives")})
            self.assertEqual(t["role"] == "insufficient_data_by_rule", min(row["positives"], row["negatives"]) < THRESHOLD, t["id"])
        self.assertEqual(PROTOCOL["insufficient_data"]["target_level"]["applies_to"], [t["id"] for t in groups["insufficient_data_by_rule"]])

    def test_the_owner_decisions_are_encoded(self):
        decisions = load("reports/m4-scope-decisions-2026-10-03.json")["decisions"]
        self.assertTrue(decisions["shape_of_milestone_4"]["owner_answer"].startswith("All four families"))
        self.assertTrue(decisions["final_holdout"]["owner_answer"].startswith("Block 5"))
        self.assertTrue(decisions["caveats"]["owner_answer"].startswith("Report both; clean-window drives"))
        self.assertTrue(decisions["data"]["owner_answer"].startswith("Existing events, labels only"))
        encoded = PROTOCOL["owner_decisions_encoded"]
        self.assertIn("All four families", encoded["shape"])
        self.assertIn("Block 5", encoded["holdout"])
        self.assertIn("clean-window version drives", encoded["caveats"])
        self.assertIn("labels only", encoded["data"])
        self.assertEqual(PROTOCOL["holdout"]["block"], 5)
        self.assertEqual(PROTOCOL["intervals"]["headline_interval_for_the_primary_contrast"]["levels"], {"reporting": 0.95, "claims": 0.99})


class StatedCountsTests(unittest.TestCase):
    """The consequences the protocol states in advance must be what the counts imply, in both caveat versions."""

    def test_loses_half_of_gap_cannot_be_fitted_in_the_clean_window_development_fold_3(self):
        train, _ = fold_counts("clean_window", "loses_half_of_gap", "dev_test_block_3")
        self.assertEqual(train["pos"], 9)
        self.assertFalse(meets(train))
        self.assertTrue(meets(fold_counts("all_event", "loses_half_of_gap", "dev_test_block_3")[0]))
        _, fold4_test = fold_counts("clean_window", "loses_half_of_gap", "dev_test_block_4")
        self.assertEqual(fold4_test["defined"], 10)
        self.assertFalse(meets(fold4_test))  # the pooled development test set is fold 4 alone

    def test_gap_ge_5pct_has_exactly_the_minimum_pooled_development_positives(self):
        for version in VERSIONS:
            pooled = [fold_counts(version, "gap_ge_5pct", f)[1] for f in ("dev_test_block_3", "dev_test_block_4")]
            self.assertEqual(sum(c["pos"] for c in pooled), THRESHOLD, version)

    def test_the_holdout_is_counts_only_for_three_primaries_and_evaluable_for_two(self):
        for version in VERSIONS:
            for target in ("gap_ge_3pct", "gap_ge_5pct", "loses_half_of_gap"):
                train, test = fold_counts(version, target, "holdout_test_block_5")
                self.assertFalse(meets(test), (version, target))
                self.assertTrue(3 <= test["pos"] <= 5, (version, target))
            _, ext = fold_counts(version, "extension_after_open_ge_5pct", "holdout_test_block_5")
            self.assertTrue(meets(ext), version)
            values = [e["labels"]["day1_close_return"]["value"] for e in VERSIONS[version]["events"] if BLOCKS[e["event_id"]] == 5]
            self.assertGreaterEqual(sum(v is not None for v in values), 20, version)

    def test_the_freeze_records_the_same_resulting_statuses(self):
        recorded = FREEZE["pre_freeze_count_check"]["resulting_status"]
        for version in VERSIONS:
            for target in ("gap_ge_3pct", "gap_ge_5pct", "extension_after_open_ge_5pct"):
                pooled = [fold_counts(version, target, f) for f in ("dev_test_block_3", "dev_test_block_4")]
                included = [te for tr, te in pooled if meets(tr)]
                total = {k: sum(c[k] for c in included) for k in ("pos", "neg")}
                self.assertEqual(recorded[version][target]["development"], "EVALUABLE" if meets(total) else "INSUFFICIENT_DATA", (version, target))
        self.assertEqual(recorded["clean_window"]["loses_half_of_gap"]["development"], "INSUFFICIENT_DATA")
        self.assertEqual(recorded["all_event"]["loses_half_of_gap"]["development"], "EVALUABLE")


class DocumentTests(unittest.TestCase):
    def test_the_readable_note_states_what_is_frozen(self):
        doc = (ROOT / "docs" / "M4-PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn(FREEZE["protocol"]["canonical_sha256"], doc)
        self.assertIn("Nothing has been fitted, scored or evaluated", doc)
        self.assertIn("most targets are expected to be NOT_DISTINGUISHABLE", " ".join(doc.split()))
        self.assertIn("the JSON governs", doc)
        for target in PROTOCOL["targets"]["primary"]:
            self.assertIn("`%s`" % target["id"], doc)

    def test_the_authorization_record_quotes_the_owner_and_bounds_what_it_covers(self):
        record = load("reports/m4-phase0-authorization-2026-10-03.json")
        self.assertEqual(record["owner_message"]["text"], FREEZE["authorization"]["owner_words"])
        self.assertEqual(record["owner_message"]["at"], FREEZE["authorization"]["at"])
        self.assertTrue(any("tests/test_m4_protocol.py" in line for line in record["authorized_and_done_under_these_words"]))
        self.assertTrue(any(line.startswith("Phase 1") for line in record["not_authorized_by_these_words"]))
        self.assertTrue(any("holdout" in line for line in record["not_authorized_by_these_words"]))

    def test_the_protocol_names_the_files_that_exist(self):
        for key in ("scope_proposal", "scope_authorization", "scope_decisions", "phase_0_authorization"):
            self.assertTrue((ROOT / PROTOCOL["authority"][key]).is_file(), key)
        self.assertTrue((ROOT / PROTOCOL["integrity"]["freeze_record"]).is_file())
        self.assertTrue((ROOT / PROTOCOL["integrity"]["human_readable_note"].split(" ")[0]).is_file())


if __name__ == "__main__":
    unittest.main()
