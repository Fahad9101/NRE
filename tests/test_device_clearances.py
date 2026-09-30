import unittest

from nre.core import DataError
from nre.device_clearances import (
    CLEARANCE_TYPE_510K, DECISION_CODE_510K, DECISION_CODE_PMA, DEVICE_CLASS,
    classify_510k, classify_pma,
)

# Real, trimmed openFDA device/510k.json record for LNSR's own real applicant "Lensar, Inc.",
# fetched directly 2026-09-30 (api.fda.gov/device/510k.json?search=applicant:LENSAR*).
REAL_LENSAR_510K = {
    "k_number": "K090633", "applicant": "Lensar, Inc.", "device_name": "LENSAR LASER SYSTEM",
    "decision_code": "SESE", "decision_description": "Substantially Equivalent",
    "clearance_type": "Traditional", "date_received": "2009-03-09", "decision_date": "2010-05-13",
    "openfda": {"device_class": "2", "device_name": "Ophthalmic Femtosecond Laser"},
}
# Real, trimmed openFDA device/pma.json records, fetched directly 2026-09-30: Medtronic's own
# P060039/S077 (a real 30-Day Notice supplement, decision_code OK30) and Boston Scientific's own
# P830026/S013 (a real original approval, decision_code APPR).
REAL_MEDTRONIC_PMA_SUPPLEMENT = {
    "pma_number": "P060039", "supplement_number": "S077", "applicant": "Medtronic, Inc.",
    "trade_name": "ATTAIN STARFIX MODEL 4195 LEAD", "decision_code": "OK30",
    "supplement_type": "30-Day Notice", "supplement_reason": "Process Change - Manufacturer/Sterilizer/Packager/Supplier",
    "expedited_review_flag": "N", "date_received": "2017-01-17", "decision_date": "2017-02-14",
    "ao_statement": "Modify the electrical discharge machine used to manufacture sub-components for leads and extensions.",
    "openfda": {"device_class": "3"},
}
REAL_BOSTON_SCIENTIFIC_PMA_APPROVAL = {
    "pma_number": "P830026", "supplement_number": "S013", "applicant": "Boston Scientific",
    "trade_name": "COSMOS(TM) SYSTEM", "decision_code": "APPR", "supplement_type": "",
    "supplement_reason": "", "expedited_review_flag": "N",
    "date_received": "1985-12-17", "decision_date": "1986-02-12", "ao_statement": "",
    "openfda": {"device_class": "3"},
}


class TaxonomyShapeTests(unittest.TestCase):
    def test_every_510k_decision_code_has_cleared_category(self):
        # No "not cleared" value exists in the real 510(k) decision_code enum -- the database only
        # stores devices that were found Substantially Equivalent in some form.
        self.assertTrue(all(row["category"] == "cleared" for row in DECISION_CODE_510K.values()))

    def test_deng_is_deliberately_not_covered(self):
        # Real, live value (489 records) with no verified description anywhere checked -- must stay
        # out of the table rather than being guessed.
        self.assertNotIn("DENG", DECISION_CODE_510K)

    def test_pma_decision_codes_cover_every_documented_category(self):
        categories = {row["category"] for row in DECISION_CODE_PMA.values()}
        self.assertEqual(categories, {"approved", "post_approval_action", "withdrawn"})

    def test_device_class_shared_table_has_all_six_real_values(self):
        self.assertEqual(set(DEVICE_CLASS), {"1", "2", "3", "U", "N", "F"})


class Classify510kTests(unittest.TestCase):
    def test_real_lensar_record_classified(self):
        result = classify_510k(REAL_LENSAR_510K)
        self.assertEqual(result["k_number"], "K090633")
        self.assertEqual(result["applicant"], "Lensar, Inc.")
        self.assertEqual(result["decision_category"], "cleared")
        self.assertEqual(result["decision_note"], "Substantially Equivalent")
        self.assertIn(result["clearance_type"], CLEARANCE_TYPE_510K)
        self.assertEqual(result["device_class_description"], DEVICE_CLASS["2"])

    def test_unrecognized_decision_code_is_unclassified_not_guessed(self):
        result = classify_510k({"k_number": "K999999", "decision_code": "DENG"})
        self.assertEqual(result["decision_category"], "unclassified")
        self.assertIsNone(result["decision_note"])

    def test_missing_k_number_rejected(self):
        with self.assertRaises(DataError):
            classify_510k({"decision_code": "SESE"})

    def test_non_dict_rejected(self):
        with self.assertRaises(DataError):
            classify_510k("SESE")


class ClassifyPmaTests(unittest.TestCase):
    def test_real_medtronic_supplement_classified_with_combined_submission_id(self):
        result = classify_pma(REAL_MEDTRONIC_PMA_SUPPLEMENT)
        self.assertEqual(result["pma_number"], "P060039")
        self.assertEqual(result["supplement_number"], "S077")
        self.assertEqual(result["submission_id"], "P060039/S077")
        self.assertEqual(result["decision_category"], "approved")

    def test_real_boston_scientific_original_approval_classified(self):
        result = classify_pma(REAL_BOSTON_SCIENTIFIC_PMA_APPROVAL)
        self.assertEqual(result["decision_code"], "APPR")
        self.assertEqual(result["decision_category"], "approved")
        self.assertEqual(result["device_class_description"], DEVICE_CLASS["3"])

    def test_missing_pma_number_rejected(self):
        with self.assertRaises(DataError):
            classify_pma({"decision_code": "APPR"})

    def test_non_dict_rejected(self):
        with self.assertRaises(DataError):
            classify_pma(42)


if __name__ == "__main__":
    unittest.main()
