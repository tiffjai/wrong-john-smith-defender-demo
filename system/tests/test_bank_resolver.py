import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bank_resolver import Names, age_years, note_check, country, contradicts, agrees, date

class SopTests(unittest.TestCase):
    def test_year_tolerance_is_not_agreement(self):
        self.assertFalse(contradicts((1980,), (1981,)))
        self.assertFalse(agrees((1980,), (1981,)))
        self.assertTrue(contradicts((1980,2), (1980,3)))
        self.assertTrue(agrees((1980,), (1980,3,7)))

    def test_age_parser_ignores_money_and_sentence_length(self):
        self.assertEqual(age_years('According to news; September 23, 2016: The court ordered EUR 1,000,000 in damages.'), [])
        self.assertEqual(age_years('January 2023, he was 46.'), [(1976,), (1977,)])
        self.assertEqual(age_years('May 2019 reports profiled 33 year old Alex Example.'), [(1985,), (1986,)])
        self.assertEqual(age_years('May 2019 court imposed a three-year sentence.'), [])
        self.assertEqual(age_years('October 2025: Police recovered PKR 11,000,000 and SAR 4,000, six motorcycles.'), [])
        self.assertEqual(age_years('October 2025: Alex Example, 45, was arrested.'), [(1979,), (1980,)])

    def test_note_legal_name_preserves_unicode(self):
        n={'text':'On 2024-01-02, Persona successfully validated a passport for Slovenia, identifying the holder as MILAN SETFANOVIĆ, born 09/02/1989.','note_id':'N1','created_at':'2024-01-02'}
        parsed=note_check(n)
        self.assertEqual(parsed['verified_name'],'MILAN SETFANOVIĆ')
        self.assertEqual(date(parsed['verified_dob']),(1989,2,9))
        self.assertIsNone(note_check(dict(n,text='Rejected identity check for MILAN TEST, born 09/02/1989.')))

    def test_names_variants_edits_initials_and_together_apart(self):
        names=Names({'groups':[['tony','anthony']]})
        self.assertTrue(names.match('Tony Hall','Anthony Hall'))
        self.assertTrue(names.match('Abdulsalam Yusuf','Abdul Salam Yusuf'))
        self.assertTrue(names.match('Milan Setfanović','Stefanović, Milan'))
        self.assertFalse(names.match('Robert X. Carter','Samuel Carter'))
        self.assertEqual(names.parts('UNKNOWN 123 N/A'),())
        self.assertTrue(names.match('Example GmbH','Example Ltd',True))

    def test_location_and_dates_normalize_without_filling_gaps(self):
        self.assertEqual(country('Ribeirao Pires, Sao Paulo, Brazil'),country('BR'))
        self.assertEqual(country('GB'),country('British'))
        self.assertNotEqual(country('Hong Kong'),country('China'))
        self.assertEqual(date('February 1980'),(1980,2))
        self.assertEqual(date('17/02/1980'),(1980,2,17))
        self.assertIsNone(date('unknown'))
