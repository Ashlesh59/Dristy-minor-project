"""
Unit tests for CorporateActionParser.
"""
import unittest
from datetime import date
from decimal import Decimal

from services.importer.ca_parser import CorporateActionParser


class TestCorporateActionParser(unittest.TestCase):
    def test_parse_date_formats(self):
        self.assertEqual(CorporateActionParser.parse_date("15-SEP-2026"), date(2026, 9, 15))
        self.assertEqual(CorporateActionParser.parse_date("01-Jan-2026"), date(2026, 1, 1))
        self.assertEqual(CorporateActionParser.parse_date("2026-09-15"), date(2026, 9, 15))
        self.assertEqual(CorporateActionParser.parse_date("15/09/2026"), date(2026, 9, 15))
        self.assertIsNone(CorporateActionParser.parse_date("NA"))
        self.assertIsNone(CorporateActionParser.parse_date(""))
        self.assertIsNone(CorporateActionParser.parse_date(None))

    def test_parse_stock_split_standard(self):
        res = CorporateActionParser.parse_purpose("Face Value Split From Rs 10/- To Rs 2/-")
        self.assertEqual(res["action_type"], "stock_split")
        self.assertEqual(res["processing_status"], "verified")
        self.assertEqual(res["ratio_from"], Decimal("10"))
        self.assertEqual(res["ratio_to"], Decimal("2"))

    def test_parse_stock_split_alternative_text(self):
        res = CorporateActionParser.parse_purpose("Stock Split from Rs.10/- to Rs.1/- per share")
        self.assertEqual(res["action_type"], "stock_split")
        self.assertEqual(res["processing_status"], "verified")
        self.assertEqual(res["ratio_from"], Decimal("10"))
        self.assertEqual(res["ratio_to"], Decimal("1"))

    def test_parse_stock_split_ratio_syntax(self):
        res = CorporateActionParser.parse_purpose("Sub-division 10:2")
        self.assertEqual(res["action_type"], "stock_split")
        self.assertEqual(res["processing_status"], "verified")
        self.assertEqual(res["ratio_from"], Decimal("10"))
        self.assertEqual(res["ratio_to"], Decimal("2"))

    def test_parse_stock_split_invalid_ratio(self):
        res = CorporateActionParser.parse_purpose("Split From Rs 2/- To Rs 10/-")
        self.assertEqual(res["action_type"], "stock_split")
        self.assertEqual(res["processing_status"], "manual_review")
        self.assertIn("Invalid split face values", res["review_reason"])

    def test_parse_bonus_1_to_1(self):
        res = CorporateActionParser.parse_purpose("Bonus 1:1")
        self.assertEqual(res["action_type"], "bonus")
        self.assertEqual(res["processing_status"], "verified")
        # 1 bonus for 1 existing -> existing=1, new total=2
        self.assertEqual(res["ratio_from"], Decimal("1"))
        self.assertEqual(res["ratio_to"], Decimal("2"))

    def test_parse_bonus_1_to_2(self):
        res = CorporateActionParser.parse_purpose("Bonus 1:2")
        self.assertEqual(res["action_type"], "bonus")
        self.assertEqual(res["processing_status"], "verified")
        # 1 bonus for 2 existing -> existing=2, new total=3
        self.assertEqual(res["ratio_from"], Decimal("2"))
        self.assertEqual(res["ratio_to"], Decimal("3"))

    def test_parse_bonus_verbose_text(self):
        res = CorporateActionParser.parse_purpose("Bonus Issue of 1 equity share for every 2 equity shares held")
        self.assertEqual(res["action_type"], "bonus")
        self.assertEqual(res["processing_status"], "verified")
        self.assertEqual(res["ratio_from"], Decimal("2"))
        self.assertEqual(res["ratio_to"], Decimal("3"))

    def test_parse_cash_dividend(self):
        res = CorporateActionParser.parse_purpose("Interim Dividend - Rs 10 Per Share")
        self.assertEqual(res["action_type"], "cash_dividend")
        self.assertEqual(res["processing_status"], "verified")
        self.assertEqual(res["cash_amount"], Decimal("10"))
        self.assertIsNone(res["ratio_from"])
        self.assertIsNone(res["ratio_to"])

    def test_parse_rights_issue_manual_review(self):
        res = CorporateActionParser.parse_purpose("Rights Issue 1:4 @ Rs 150")
        self.assertEqual(res["action_type"], "rights_issue")
        self.assertEqual(res["processing_status"], "manual_review")
        self.assertIn("Rights issues require manual TERP calculation", res["review_reason"])

    def test_parse_ambiguous_manual_review(self):
        res = CorporateActionParser.parse_purpose("Scheme of Arrangement and Amalgamation")
        self.assertIn(res["action_type"], ["merger", "demerger"])
        self.assertEqual(res["processing_status"], "manual_review")


if __name__ == "__main__":
    unittest.main()
