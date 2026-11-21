"""Invented records exercise bank SOP without practice labels."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bank_resolver import BankResolver

class BankVariationTests(unittest.TestCase):
    def fixture(self):
        return {
            'customers': [{'record_id':'C-NEW','full_name':'ALEX MORGAN','entity_type':'Individual','email':'alex@example.invalid','dob':'1980-03-14','residence_country':'United Kingdom'}],
            'accounts': [{'account_id':'ACC-NEW','customer_id':'C-NEW'}],
            'alerts': [{'alert_id':'A-NEW','account_ref':'ACC-NEW','customer':{'name':'Alex Morgan'},'hit_ids':['H-NEW'],'screened_at':'2026-01-01'}],
            'hits': [{'hit_id':'H-NEW','alert_id':'A-NEW','name':'Alex Morgan','entity_type':'Individual','dobs':['1980-03-14'],'countries':['United Kingdom']}],
            'onboarding': [], 'kyc_checks': [], 'search_results': [],
            'notes': [{'note_id':'N-NEW','requester_email':'alex@example.invalid','created_at':'2025-01-01','text':'Verified passport from United Kingdom: ALEX MORGAN, DOB 14/03/1980.'}],
        }

    def resolve(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'name_variants.json').write_text('{"groups": []}')
            for name, rows in data.items():
                (folder/f'{name}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            return BankResolver(folder).run()[0]

    def test_new_ids_are_not_decision_inputs(self):
        data = self.fixture()
        first = self.resolve(data)
        second = self.resolve(json.loads(json.dumps(data).replace('-NEW','-UNSEEN-77')))
        self.assertEqual(first['decision'],'SAME_ENTITY')
        self.assertEqual((first['decision'],first['reason_code']),(second['decision'],second['reason_code']))
        self.assertEqual(second['customer_record_id'],'C-UNSEEN-77')
        self.assertIn('N-UNSEEN-77',second['evidence'])

    def test_reworded_verified_notes_preserve_identity(self):
        for wording in ('Identity check completed: ALEX MORGAN, date of birth recorded as 14/03/1980. United Kingdom passport.', 'Passport validated for ALEX MORGAN, born March 14, 1980, United Kingdom.'):
            with self.subTest(wording=wording):
                data = self.fixture()
                data['notes'][0]['text'] = wording
                row = self.resolve(data)
                self.assertEqual(row['decision'],'SAME_ENTITY')
                self.assertIn('N-NEW',row['evidence'])

    def test_missing_and_partial_dates_do_not_become_mismatches(self):
        for dates, expected in (([],'REVIEW'),(['1980'],'SAME_ENTITY'),(['1980-03'],'SAME_ENTITY')):
            with self.subTest(dates=dates):
                data = self.fixture()
                data['hits'][0]['dobs'] = dates
                self.assertEqual(self.resolve(data)['decision'],expected)

    def test_rejected_note_cannot_override_identity(self):
        data = self.fixture()
        data['notes'][0]['text'] = 'Rejected passport: ALEX MORGAN, DOB 14/03/1950.'
        row = self.resolve(data)
        self.assertEqual(row['decision'],'SAME_ENTITY')
        self.assertNotIn('N-NEW',row['evidence'])

    def test_rare_policy_exclusions(self):
        for changes, code in (({'entity_type':'Company'},'ENTITY_TYPE_MISMATCH'),({'deceased_date':'2020-01-01'},'DECEASED'),({'profile_notes':'According to Example News; January 01, 1985: A report.'},'TEMPORAL_IMPOSSIBILITY')):
            with self.subTest(code=code):
                data = self.fixture()
                data['hits'][0].update(changes)
                row = self.resolve(data)
                self.assertEqual((row['decision'],row['reason_code']),('DIFFERENT_ENTITY',code))

    def test_unknown_note_with_missing_facts_stays_review(self):
        data = self.fixture()
        data['customers'][0]['dob'] = None
        data['notes'][0]['text'] = 'A reviewer had a conversation. Identity is unresolved.'
        data['hits'][0]['dobs'] = []
        row = self.resolve(data)
        self.assertEqual((row['decision'],row['reason_code']),('REVIEW','INSUFFICIENT_DATA'))
        self.assertNotIn('N-NEW',row['evidence'])
