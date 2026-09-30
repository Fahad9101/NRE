import unittest

from nre.core import DataError
from nre.fda_approvals import (
    APPLICATION_PREFIXES, SUBMISSION_CLASS_CODE, SUBMISSION_STATUS, SUBMISSION_TYPE,
    classify_application, classify_application_number, classify_submission,
)

# Real Drugs@FDA data for NDA020793 (CAFCIT / caffeine citrate, sponsor HIKMA), fetched directly
# from api.fda.gov/drug/drugsfda.json?search=application_number:"NDA020793" on 2026-09-30. Trimmed
# to the fields classify_application()/classify_submission() read; all 9 of its real submissions
# happen to be AP (approved) -- ANDA077757 below supplies a real TA (tentative approval) example.
# submission_class_code is each submission's own real value, same fetch.
NDA020793 = {
    "application_number": "NDA020793",
    "sponsor_name": "HIKMA",
    "products": [
        {"brand_name": "CAFCIT"},
        {"brand_name": "CAFCIT"},
    ],
    "submissions": [
        {"submission_type": "SUPPL", "submission_number": "4", "submission_status": "AP", "submission_status_date": "20020208", "submission_class_code": "LABELING"},
        {"submission_type": "SUPPL", "submission_number": "2", "submission_status": "AP", "submission_status_date": "20000414", "submission_class_code": "MANUF (CMC)"},
        {"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP", "submission_status_date": "19990921", "submission_class_code": "TYPE 2"},
        {"submission_type": "SUPPL", "submission_number": "16", "submission_status": "AP", "submission_status_date": "20141223", "submission_class_code": "MANUF (CMC)"},
        {"submission_type": "SUPPL", "submission_number": "9", "submission_status": "AP", "submission_status_date": "20100611", "submission_class_code": "LABELING"},
        {"submission_type": "SUPPL", "submission_number": "5", "submission_status": "AP", "submission_status_date": "20020308", "submission_class_code": "MANUF (CMC)"},
        {"submission_type": "SUPPL", "submission_number": "3", "submission_status": "AP", "submission_status_date": "20020118", "submission_class_code": "LABELING"},
        {"submission_type": "SUPPL", "submission_number": "1", "submission_status": "AP", "submission_status_date": "20000412", "submission_class_code": "EFFICACY"},
        {"submission_type": "SUPPL", "submission_number": "19", "submission_status": "AP", "submission_status_date": "20200302", "submission_class_code": "LABELING"},
    ],
}
ANDA077757 = {
    "application_number": "ANDA077757", "sponsor_name": "CARACO", "products": [],
    "submissions": [{"submission_type": "ORIG", "submission_number": "1", "submission_status": "TA", "submission_status_date": "20071109"}],
}

# The complete, real value sets openFDA's own live count aggregation reports for these fields
# (api.fda.gov/drug/drugsfda.json?count=submissions.<field>, read 2026-09-30) -- used to prove the
# taxonomy tables' own coverage is exhaustive, not assumed.
REAL_SUBMISSION_STATUS_VALUES = {"AP", "TA"}
REAL_SUBMISSION_TYPE_VALUES = {"ORIG", "SUPPL"}
# All 27 real submission_class_code values; UNKNOWN/BIOSIMILAR/TYPE 10- BLA are deliberately absent
# from SUBMISSION_CLASS_CODE (no real record, up to 50 sampled each, ever populates their own
# submission_class_code_description field) -- see nre/fda_approvals.py's own module docstring.
REAL_SUBMISSION_CLASS_CODE_VALUES = {
    "LABELING", "UNKNOWN", "MANUF (CMC)", "EFFICACY", "TYPE 1", "TYPE 3", "TYPE 5", "REMS", "N/A",
    "TYPE 4", "BIOEQUIV", "TYPE 2", "S", "TYPE 6", "MEDGAS", "TYPE 1/4", "TYPE 7", "BIOSIMILAR",
    "TYPE 3/4", "TYPE 8", "TYPE 9", "TYPE 10", "TYPE 2/3", "TYPE 9- BLA", "TYPE 2/4", "TYPE 4/5",
    "TYPE 10- BLA",
}
UNDESCRIBED_SUBMISSION_CLASS_CODES = {"UNKNOWN", "BIOSIMILAR", "TYPE 10- BLA"}


class TaxonomyCoverageTests(unittest.TestCase):
    def test_every_real_submission_status_value_is_covered(self):
        self.assertEqual(set(SUBMISSION_STATUS), REAL_SUBMISSION_STATUS_VALUES)

    def test_every_real_submission_type_value_is_covered(self):
        self.assertEqual(set(SUBMISSION_TYPE), REAL_SUBMISSION_TYPE_VALUES)

    def test_every_described_submission_class_code_value_is_covered(self):
        described = REAL_SUBMISSION_CLASS_CODE_VALUES - UNDESCRIBED_SUBMISSION_CLASS_CODES
        self.assertEqual(set(SUBMISSION_CLASS_CODE), described)

    def test_undescribed_codes_are_deliberately_excluded_not_forgotten(self):
        self.assertTrue(UNDESCRIBED_SUBMISSION_CLASS_CODES.isdisjoint(SUBMISSION_CLASS_CODE))


class ClassifyApplicationNumberTests(unittest.TestCase):
    def test_nda_prefix(self):
        self.assertEqual(classify_application_number("NDA020793"), {"prefix": "NDA", "pathway": "new_drug_application"})

    def test_anda_prefix_is_its_own_pathway_not_nda(self):
        result = classify_application_number("ANDA077757")
        self.assertEqual(result["prefix"], "ANDA")
        self.assertEqual(result["pathway"], "abbreviated_new_drug_application")

    def test_bla_prefix(self):
        self.assertEqual(classify_application_number("BLA125057")["pathway"], "biologics_license_application")

    def test_unrecognized_prefix_is_none_not_guessed(self):
        self.assertIsNone(classify_application_number("IND012345"))

    def test_non_string_rejected(self):
        with self.assertRaises(DataError):
            classify_application_number(20793)


class ClassifySubmissionTests(unittest.TestCase):
    def test_approved_original(self):
        result = classify_submission({"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP"})
        self.assertEqual(result["submission_type_category"], "original_application")
        self.assertEqual(result["submission_status_category"], "approved")

    def test_tentative_approval(self):
        result = classify_submission({"submission_type": "ORIG", "submission_status": "TA"})
        self.assertEqual(result["submission_status_category"], "tentative_approval")

    def test_unrecognized_status_is_unclassified_not_guessed(self):
        result = classify_submission({"submission_type": "ORIG", "submission_status": "SOME_FUTURE_STATUS"})
        self.assertEqual(result["submission_status_category"], "unclassified")

    def test_real_combination_class_code(self):
        result = classify_submission({"submission_type": "SUPPL", "submission_status": "AP",
                                       "submission_class_code": "TYPE 1/4"})
        self.assertEqual(result["submission_class_code_category"], "new_molecular_entity_and_new_combination")

    def test_undescribed_class_code_is_unclassified_not_guessed(self):
        result = classify_submission({"submission_type": "ORIG", "submission_status": "AP",
                                       "submission_class_code": "BIOSIMILAR"})
        self.assertEqual(result["submission_class_code_category"], "unclassified")

    def test_non_dict_rejected(self):
        with self.assertRaises(DataError):
            classify_submission("AP")


class ClassifyApplicationRealDataTests(unittest.TestCase):
    """Ground truth: NDA020793 (CAFCIT) and ANDA077757, two real Drugs@FDA applications spanning
    both real submission_status values and both real submission_type values."""

    def test_cafcit_all_nine_submissions_approved(self):
        result = classify_application(NDA020793)
        self.assertEqual(result["application_number"], "NDA020793")
        self.assertEqual(result["pathway"], "new_drug_application")
        self.assertEqual(result["sponsor_name"], "HIKMA")
        self.assertEqual(result["brand_names"], ["CAFCIT"])
        self.assertEqual(len(result["submissions"]), 9)
        self.assertTrue(all(s["submission_status_category"] == "approved" for s in result["submissions"]))
        origs = [s for s in result["submissions"] if s["submission_type_category"] == "original_application"]
        self.assertEqual(len(origs), 1)
        self.assertEqual(origs[0]["submission_status_date"], "19990921")
        self.assertEqual(origs[0]["submission_class_code_category"], "new_active_ingredient")

    def test_anda_tentative_approval(self):
        result = classify_application(ANDA077757)
        self.assertEqual(result["pathway"], "abbreviated_new_drug_application")
        self.assertEqual(result["submissions"][0]["submission_status_category"], "tentative_approval")

    def test_missing_application_number_rejected(self):
        with self.assertRaises(DataError):
            classify_application({"submissions": []})

    def test_missing_submissions_list_rejected(self):
        with self.assertRaises(DataError):
            classify_application({"application_number": "NDA020793"})

    def test_no_products_defaults_to_empty_brand_names(self):
        result = classify_application({"application_number": "NDA020793", "submissions": []})
        self.assertEqual(result["brand_names"], [])


if __name__ == "__main__":
    unittest.main()
