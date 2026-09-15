import unittest
import pandas as pd
from src.build_labels import build_labels
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PREDICTION_HORIZON_DAYS

class TestLabels(unittest.TestCase):
    def test_build_labels(self):
        # We need PREDICTION_HORIZON_DAYS + 1 rows
        n_rows = PREDICTION_HORIZON_DAYS + 5
        dates = pd.date_range(start="2023-01-01", periods=n_rows)
        
        df = pd.DataFrame({
            "date": dates,
            "security_id": [1] * n_rows,
            "close": [100.0] * n_rows,
            "benchmark_close": [1000.0] * n_rows
        })
        
        # Make the future return for stock at index 0 be 10%, benchmark 5% -> label 1
        df.loc[PREDICTION_HORIZON_DAYS, "close"] = 110.0
        df.loc[PREDICTION_HORIZON_DAYS, "benchmark_close"] = 1050.0
        
        # Make the future return for stock at index 1 be 5%, benchmark 10% -> label 0
        df.loc[PREDICTION_HORIZON_DAYS + 1, "close"] = 105.0
        df.loc[PREDICTION_HORIZON_DAYS + 1, "benchmark_close"] = 1100.0
        
        labels_df = build_labels(df)
        
        # Length should be n_rows - PREDICTION_HORIZON_DAYS because the last rows don't have future values
        self.assertEqual(len(labels_df), n_rows - PREDICTION_HORIZON_DAYS)
        
        # Check first row label
        self.assertEqual(labels_df.iloc[0]["label"], 1)
        
        # Check second row label
        self.assertEqual(labels_df.iloc[1]["label"], 0)

if __name__ == '__main__':
    unittest.main()
