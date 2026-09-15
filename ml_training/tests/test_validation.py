import unittest
import pandas as pd
import numpy as np
from src.validate_data import validate_prices, validate_benchmark, align_and_validate

class TestValidation(unittest.TestCase):
    def test_required_columns(self):
        df = pd.DataFrame({"date": ["2023-01-01"], "symbol": ["AAPL"]}) # Missing security_id, close, volume
        with self.assertRaises(ValueError):
            validate_prices(df)
            
    def test_duplicate_rows(self):
        df = pd.DataFrame({
            "date": ["2023-01-01", "2023-01-01"],
            "security_id": [1, 1],
            "symbol": ["AAPL", "AAPL"],
            "close": [150.0, 150.0],
            "volume": [1000, 1000]
        })
        with self.assertRaises(ValueError):
            validate_prices(df)
            
    def test_invalid_prices(self):
        df = pd.DataFrame({
            "date": ["2023-01-01"],
            "security_id": [1],
            "symbol": ["AAPL"],
            "close": [-5.0],
            "volume": [1000]
        })
        with self.assertRaises(ValueError):
            validate_prices(df)
            
    def test_invalid_dates(self):
        df = pd.DataFrame({
            "date": ["invalid_date"],
            "security_id": [1],
            "symbol": ["AAPL"],
            "close": [150.0],
            "volume": [1000]
        })
        with self.assertRaises(ValueError):
            validate_prices(df)

if __name__ == '__main__':
    unittest.main()
