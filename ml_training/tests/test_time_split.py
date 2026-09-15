import unittest
import pandas as pd
from src.train import time_split
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TRAIN_RATIO, VAL_RATIO

class TestTimeSplit(unittest.TestCase):
    def test_chronological_split(self):
        dates = pd.date_range(start="2023-01-01", periods=100)
        df = pd.DataFrame({
            "date": dates,
            "val": range(100)
        })
        
        train_df, val_df, test_df = time_split(df)
        
        # Check no overlap
        self.assertTrue(train_df["date"].max() < val_df["date"].min())
        self.assertTrue(val_df["date"].max() < test_df["date"].min())
        
        # Check lengths approximately
        self.assertEqual(len(train_df), int(100 * TRAIN_RATIO))
        self.assertEqual(len(val_df), int(100 * VAL_RATIO))
        
if __name__ == '__main__':
    unittest.main()
