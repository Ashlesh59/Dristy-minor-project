import unittest
import pandas as pd
from src.train import time_split
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TRAIN_RATIO, VAL_RATIO, PREDICTION_HORIZON_DAYS

class TestTimeSplit(unittest.TestCase):
    def test_chronological_split(self):
        dates = pd.date_range(start="2023-01-01", periods=300)
        df = pd.DataFrame({
            "date": dates,
            "val": range(300)
        })
        
        train_df, val_df, test_df = time_split(df)
        
        # Check no overlap
        self.assertTrue(train_df["date"].max() < val_df["date"].min())
        self.assertTrue(val_df["date"].max() < test_df["date"].min())
        
        # Check purge window (min val date should be > max train date + purge)
        train_max_idx = list(dates).index(train_df["date"].max())
        val_min_idx = list(dates).index(val_df["date"].min())
        self.assertGreaterEqual(val_min_idx - train_max_idx, PREDICTION_HORIZON_DAYS)
        
        val_max_idx = list(dates).index(val_df["date"].max())
        test_min_idx = list(dates).index(test_df["date"].min())
        self.assertGreaterEqual(test_min_idx - val_max_idx, PREDICTION_HORIZON_DAYS)

if __name__ == '__main__':
    unittest.main()
