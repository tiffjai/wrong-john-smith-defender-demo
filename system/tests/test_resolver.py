import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resolver import date_parts, dates_conflict, execute, load_policy, predict, read_rows, resolve_customer, run

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'

class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.data = {n: read_rows(EXAMPLES, n) for n in ('alerts','hits','customers','accounts','onboarding','kyc_checks')}
        self.policy = load_policy(EXAMPLES)

    def test_partial_dates_never_impute(self):
        self.assertFalse(dates_conflict('1988', '1988-03-14'))
        self.assertTrue(dates_conflict('1988', '1952'))
        self.assertFalse(dates_conflict(None, '1952'))
        self.assertIsNone(date_parts('1988-02-30'))

    def test_three_decisions_and_exact_ids(self):
        rows = run(EXAMPLES)
        self.assertEqual([r['decision'] for r in rows], ['DIFFERENT_ENTITY','REVIEW','SAME_ENTITY','REVIEW'])
        self.assertIn('KYC-01', rows[0]['evidence'])
        self.assertNotIn('KYC-REJECTED', rows[0]['evidence'])
        self.assertIn('ONB-01', rows[0]['evidence'])
        self.assertEqual(len(rows), 4)

    def test_shared_email_is_ambiguous(self):
        self.data['customers'].append({'customer_id':'OTHER','email':'anna@example.invalid'})
        _, cid, _, _ = resolve_customer(self.data['alerts'][2], self.data)
        self.assertEqual(cid, 'AMBIGUOUS')

    def test_passed_conflicts_require_review(self):
        self.data['kyc_checks'].append({'check_id':'CONFLICT','applicant_id':'APP-01','result':'passed','verified_dob':'1952'})
        row = predict(self.data['alerts'][0], self.data['hits'][0], self.data, self.policy)
        self.assertEqual(row['decision'], 'REVIEW')
        self.assertIn('CONFLICT', row['evidence'])

    def test_policy_adapter_required_for_automatic_decisions(self):
        policy = {'review_code':'INSUFFICIENT_EVIDENCE'}
        row = predict(self.data['alerts'][0], self.data['hits'][0], self.data, policy)
        self.assertEqual(row['decision'], 'REVIEW')

    def test_byte_reproducibility_five_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for i in range(5):
                p = Path(tmp) / f'{i}.jsonl'
                execute(EXAMPLES, p)
                outputs.append(p.read_bytes())
            self.assertEqual(len(set(outputs)), 1)

if __name__ == '__main__':
    unittest.main()
