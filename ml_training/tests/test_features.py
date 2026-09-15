import unittest
import pandas as pd
import numpy as np
from src.build_features import calculate_rsi, build_features

class TestFeatures(unittest.TestCase):
    def test_rsi_calculation(self):
        # Create an upward trending series
        prices = pd.Series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25])
        rsi = calculate_rsi(prices, window=14)
        
        # RSI should be 100 since there are no losses
        self.assertEqual(rsi.iloc[-1], 100.0)
        
        # Create a downward trending series
        prices_down = pd.Series([25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10])
        rsi_down = calculate_rsi(prices_down, window=14)
        
        # RSI should be 0 since there are no gains
        self.assertEqual(rsi_down.iloc[-1], 0.0)
        
    def test_build_features_drops_warmup(self):
        dates = pd.date_range(start="2023-01-01", periods=100)
        prices = pd.DataFrame({
            "date": dates,
            "security_id": [1] * 100,
            "symbol": ["AAPL"] * 100,
            "close": np.linspace(100, 200, 100),
            "volume": [1000] * 100
        })
        benchmark = pd.DataFrame({
            "date": dates,
            "close": np.linspace(1000, 2000, 100)
        })
        
        feat_df = build_features(prices, benchmark)
        
        # Because the longest MA is 50, first 49 elements will be dropped due to NaN
        self.assertEqual(len(feat_df), 100 - 49)
        self.assertFalse(feat_df.isnull().any().any())

if __name__ == '__main__':
    unittest.main()
