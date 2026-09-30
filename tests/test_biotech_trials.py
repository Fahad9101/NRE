import unittest

from nre.biotech_trials import CATEGORIES, PHASES, STATUS_TAXONOMY, classify_phases, classify_status, classify_study
from nre.core import DataError

# Real ClinicalTrials.gov protocolSection records for Neurocrine Biosciences (NBIX) -- one of this
# project's own 23 accepted issuers -- fetched directly from clinicaltrials.gov/api/v2/studies/{id}
# and the v2 search endpoint on 2026-09-30. Trimmed to the fields classify_study() reads.
NBIX_COMPLETED = {
    "identificationModule": {"nctId": "NCT03325010",
                             "briefTitle": "Safety, Tolerability, and Efficacy of NBI-98854 for the Treatment of Pediatric Subjects With Tourette Syndrome"},
    "statusModule": {"overallStatus": "COMPLETED"},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine Biosciences"}},
    "conditionsModule": {"conditions": ["Tourette Syndrome"]},
    "designModule": {"phases": ["PHASE2"]},
}
NBIX_TERMINATED = {
    "identificationModule": {"nctId": "NCT04873869",
                             "briefTitle": "Study to Evaluate NBI-921352 as Adjunctive Therapy in Subjects With SCN8A Developmental and Epileptic Encephalopathy Syndrome (SCN8A-DEE)"},
    "statusModule": {"overallStatus": "TERMINATED"},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine Biosciences"}},
    "conditionsModule": {"conditions": ["SCN8A Developmental and Epileptic Encephalopathy Syndrome"]},
    "designModule": {"phases": ["PHASE2"]},
}
NBIX_WITHDRAWN = {
    "identificationModule": {"nctId": "NCT03532022",
                             "briefTitle": "Open-label Comparison of Chronocort® Versus Standard Glucocorticoid Replacement Therapy"},
    "statusModule": {"overallStatus": "WITHDRAWN"},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Neurocrine UK Limited"}},
    "conditionsModule": {"conditions": ["Congenital Adrenal Hyperplasia"]},
    "designModule": {"phases": ["PHASE3"]},
}

# The complete, real set of values ClinicalTrials.gov's own live stats endpoint reports for these
# two enum fields (clinicaltrials.gov/api/v2/stats/field/values?fields=OverallStatus,Phase, read
# 2026-09-30) -- used to prove the taxonomy table's own coverage is exhaustive, not assumed.
REAL_OVERALL_STATUS_VALUES = {
    "COMPLETED", "UNKNOWN", "RECRUITING", "TERMINATED", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING",
    "WITHDRAWN", "ENROLLING_BY_INVITATION", "SUSPENDED", "WITHHELD", "NO_LONGER_AVAILABLE",
    "AVAILABLE", "APPROVED_FOR_MARKETING", "TEMPORARILY_NOT_AVAILABLE",
}
REAL_PHASE_VALUES = {"NA", "PHASE2", "PHASE1", "PHASE3", "PHASE4", "EARLY_PHASE1"}


class TaxonomyCoverageTests(unittest.TestCase):
    def test_every_real_overall_status_value_is_covered(self):
        self.assertEqual(set(STATUS_TAXONOMY), REAL_OVERALL_STATUS_VALUES)

    def test_every_real_phase_value_is_covered(self):
        self.assertEqual(set(PHASES), REAL_PHASE_VALUES)

    def test_every_entry_has_a_valid_category(self):
        for status, entry in STATUS_TAXONOMY.items():
            self.assertIn(entry["category"], CATEGORIES, status)


class ClassifyStatusTests(unittest.TestCase):
    def test_completed_is_its_own_category_not_success(self):
        row = classify_status("COMPLETED")
        self.assertEqual(row["category"], "completed")
        self.assertIn("results data", row["note"])

    def test_terminated_withdrawn_suspended_are_all_discontinued(self):
        for status in ("TERMINATED", "WITHDRAWN", "SUSPENDED"):
            self.assertEqual(classify_status(status)["category"], "discontinued", status)

    def test_unknown_status_value_is_none_not_guessed(self):
        self.assertIsNone(classify_status("SOME_FUTURE_STATUS"))


class ClassifyPhasesTests(unittest.TestCase):
    def test_valid_phases_pass_through(self):
        self.assertEqual(classify_phases(["PHASE2", "PHASE3"]), ["PHASE2", "PHASE3"])

    def test_empty_phases_is_valid(self):
        self.assertEqual(classify_phases([]), [])

    def test_unrecognized_phase_rejected(self):
        with self.assertRaises(DataError):
            classify_phases(["PHASE99"])

    def test_non_list_rejected(self):
        with self.assertRaises(DataError):
            classify_phases("PHASE2")


class ClassifyStudyRealDataTests(unittest.TestCase):
    """Ground truth: three of NBIX's (Neurocrine Biosciences, one of this project's own 23 accepted
    issuers) own real trials, spanning all three of the taxonomy's most consequential categories."""

    def test_completed_trial(self):
        result = classify_study(NBIX_COMPLETED)
        self.assertEqual(result["nct_id"], "NCT03325010")
        self.assertEqual(result["status_category"], "completed")
        self.assertEqual(result["phases"], ["PHASE2"])
        self.assertEqual(result["conditions"], ["Tourette Syndrome"])
        self.assertEqual(result["sponsor"], "Neurocrine Biosciences")

    def test_terminated_trial_is_discontinued(self):
        result = classify_study(NBIX_TERMINATED)
        self.assertEqual(result["status_category"], "discontinued")
        self.assertEqual(result["phases"], ["PHASE2"])

    def test_withdrawn_trial_is_discontinued(self):
        result = classify_study(NBIX_WITHDRAWN)
        self.assertEqual(result["status_category"], "discontinued")
        self.assertEqual(result["phases"], ["PHASE3"])

    def test_missing_nct_id_rejected(self):
        with self.assertRaises(DataError):
            classify_study({"statusModule": {"overallStatus": "COMPLETED"}})

    def test_non_dict_rejected(self):
        with self.assertRaises(DataError):
            classify_study("NCT03325010")

    def test_missing_optional_modules_default_safely(self):
        # A minimal, otherwise-valid record with none of the optional modules present at all.
        result = classify_study({"identificationModule": {"nctId": "NCT00000001"}})
        self.assertEqual(result["status_category"], "unclassified")
        self.assertEqual(result["phases"], [])
        self.assertEqual(result["conditions"], [])
        self.assertIsNone(result["sponsor"])


if __name__ == "__main__":
    unittest.main()
