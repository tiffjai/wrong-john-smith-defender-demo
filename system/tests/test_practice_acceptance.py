"""Local practice UAT; participant records remain outside the repository.

SCREENING_DATA=/path/to/dev python3 -m unittest discover -s system/tests -v
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bank_resolver import BankResolver, contradicts, date


class MissingDateSafetyTests(unittest.TestCase):
    def test_unknown_and_compatible_partial_dates_are_not_contradictions(self):
        for supplied in (None, "unknown", "1965", "1965-03"):
            with self.subTest(supplied=supplied):
                self.assertFalse(contradicts(date("1965-03-28"), date(supplied)))


@unittest.skipUnless(os.environ.get("SCREENING_DATA"), "Set SCREENING_DATA to the official dev folder")
class PracticeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = BankResolver(Path(os.environ["SCREENING_DATA"]))
        cls.rows = {r["hit_id"]: r for r in cls.resolver.run()}

    def assert_case(self, hit, customer, decision, code, evidence):
        row = self.rows[hit]
        self.assertEqual(row["customer_record_id"], customer)
        self.assertEqual((row["decision"], row["reason_code"]), (decision, code))
        self.assertIn(evidence, row["evidence"])

    def test_joint_holder_and_decisive_approved_check(self):
        self.assert_case("H-58A39C", "CUS-604925", "DIFFERENT_ENTITY", "DOB_MISMATCH", "KYC-232AE0")
        row = self.rows["H-58A39C"]
        self.assertEqual(row["alert_id"], "A-2642A1")
        self.assertNotIn("KYC-6BA59F", row["evidence"])
        r = self.resolver
        self.assertNotEqual(r.root("CUS-604925"), r.root("CUS-022310"))
        picture = r.picture(r.root("CUS-604925"))
        self.assertEqual(picture["dob"], (1965, 3, 28))
        self.assertNotIn("KYC-6BA59F", [k["check_id"] for k in r.checks["CUS-604925"]])

    def test_second_clearance_still_clears(self):
        self.assert_case("H-CF5228", "CUS-028455", "DIFFERENT_ENTITY", "DOB_MISMATCH", "KYC-66A040")

    def test_missing_hit_dob_stays_review(self):
        self.assert_case("H-FA9F83", "CUS-783545", "REVIEW", "INSUFFICIENT_DATA", "KYC-80B445")
        hit = next(h for h in self.resolver.data["hits"] if h["hit_id"] == "H-FA9F83")
        self.assertEqual(self.resolver.hit_facts(hit)["dobs"], [])

    def test_verified_same_entity_example(self):
        self.assert_case("H-582410", "CUS-377745", "SAME_ENTITY", "NAME_DOB_LOCATION_MATCH", "NOTE-14E25A")
