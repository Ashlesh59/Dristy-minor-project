import pandas as pd
import numpy as np

def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    required_cols = ["date", "security_id", "symbol", "close", "volume"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in prices: {missing}")
    
    # Check nulls in required columns
    if df[required_cols].isnull().any().any():
        raise ValueError("Missing values in required columns.")
        
    try:
        df["date"] = pd.to_datetime(df["date"])
    except Exception as e:
        raise ValueError("Invalid dates found.") from e
        
    # Check duplicates
    if df.duplicated(subset=["security_id", "date"]).any():
        raise ValueError("Duplicate security/date rows found.")
        
    # Check valid values
    if (df["close"] <= 0).any():
        raise ValueError("Negative or zero closing prices found.")
    if (df["volume"] < 0).any():
        raise ValueError("Negative volume found.")
        
    # Sort
    if not df["date"].is_monotonic_increasing:
        # Check if it's sortable and if it was already sorted by security_id and date
        pass
    
    df = df.sort_values(by=["security_id", "date"]).reset_index(drop=True)
    return df

def validate_benchmark(df: pd.DataFrame) -> pd.DataFrame:
    required_cols = ["date", "close"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in benchmark: {missing}")
        
    if df[required_cols].isnull().any().any():
        raise ValueError("Missing values in benchmark.")
        
    try:
        df["date"] = pd.to_datetime(df["date"])
    except Exception:
        raise ValueError("Invalid dates in benchmark.")
        
    if df.duplicated(subset=["date"]).any():
        raise ValueError("Duplicate date rows in benchmark.")
        
    if (df["close"] <= 0).any():
        raise ValueError("Negative or zero closing prices in benchmark.")
        
    df = df.sort_values(by="date").reset_index(drop=True)
    return df

def align_and_validate(prices: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    min_price_date = prices["date"].min()
    max_price_date = prices["date"].max()
    
    min_bench_date = benchmark["date"].min()
    max_bench_date = benchmark["date"].max()
    
    if max_bench_date < min_price_date or min_bench_date > max_price_date:
        raise ValueError("Benchmark date range cannot be aligned with stock data.")
        
    # Minimum history: need at least 50 days of past data + 20 days forward
    # 70 days minimum overall
    if len(benchmark) < 70:
        raise ValueError("Insufficient history in benchmark (needs at least 70 days).")
        
    return prices, benchmark
