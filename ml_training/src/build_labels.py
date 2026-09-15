import pandas as pd
import numpy as np
from config import PREDICTION_HORIZON_DAYS

def build_labels(df: pd.DataFrame) -> pd.DataFrame:
    # df is expected to contain 'date', 'security_id', 'close' (stock), and 'nifty_close'
    # Wait, the prompt says benchmark features include nify_20d_return, but we also need benchmark_close for labels
    
    # Let's ensure df is sorted by date within each security
    df = df.sort_values(["security_id", "date"]).copy()
    
    # Calculate stock future return
    # shift(-20) gets the value 20 days in the future
    df["stock_close_future"] = df.groupby("security_id")["close"].shift(-PREDICTION_HORIZON_DAYS)
    df["stock_future_return"] = (df["stock_close_future"] / df["close"]) - 1
    
    # Calculate benchmark future return
    # We can group by date to get unique benchmark closes, or just shift per security if benchmark is merged
    df["benchmark_close_future"] = df.groupby("security_id")["benchmark_close"].shift(-PREDICTION_HORIZON_DAYS)
    df["benchmark_future_return"] = (df["benchmark_close_future"] / df["benchmark_close"]) - 1
    
    # Drop rows where future returns cannot be calculated (the last 20 days)
    df = df.dropna(subset=["stock_future_return", "benchmark_future_return"]).copy()
    
    # Create binary label
    df["label"] = (df["stock_future_return"] > df["benchmark_future_return"]).astype(int)
    
    return df
