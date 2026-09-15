import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window, min_periods=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window, min_periods=window).mean()
    
    rs = np.zeros_like(gain)
    # Safe division
    mask = loss != 0
    rs[mask] = gain[mask] / loss[mask]
    
    rsi = np.zeros_like(gain)
    rsi[mask] = 100 - (100 / (1 + rs[mask]))
    rsi[~mask & (gain != 0)] = 100
    
    return pd.Series(rsi, index=series.index)

def build_benchmark_features(bench_df: pd.DataFrame) -> pd.DataFrame:
    df = bench_df.copy()
    df = df.sort_values("date")
    
    df["nifty_20d_return"] = df["close"].pct_change(periods=20)
    df = df.rename(columns={"close": "benchmark_close"})
    return df[["date", "benchmark_close", "nifty_20d_return"]]

def build_stock_features(group: pd.DataFrame) -> pd.DataFrame:
    df = group.copy().sort_values("date")
    close = df["close"]
    vol = df["volume"]
    
    # Returns
    df["return_1d"] = close.pct_change(periods=1)
    df["return_5d"] = close.pct_change(periods=5)
    df["return_20d"] = close.pct_change(periods=20)
    
    # Moving averages
    ma_5 = close.rolling(window=5).mean()
    ma_20 = close.rolling(window=20).mean()
    ma_50 = close.rolling(window=50).mean()
    
    df["close_div_ma5"] = np.where(ma_5 > 0, close / ma_5, np.nan)
    df["close_div_ma20"] = np.where(ma_20 > 0, close / ma_20, np.nan)
    df["close_div_ma50"] = np.where(ma_50 > 0, close / ma_50, np.nan)
    
    # Volatility
    df["volatility_20d"] = df["return_1d"].rolling(window=20).std()
    
    # RSI
    df["rsi_14"] = calculate_rsi(close, 14)
    
    # Volume
    vol_ma20 = vol.rolling(window=20).mean()
    df["volume_ma20"] = vol_ma20
    df["vol_div_ma20"] = np.where(vol_ma20 > 0, vol / vol_ma20, np.nan)
    
    return df

def build_features(prices: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    bench_feat = build_benchmark_features(benchmark)
    
    # Group by security and build features
    stock_feat = prices.groupby("security_id", group_keys=False).apply(build_stock_features)
    
    # Merge with benchmark features
    df = pd.merge(stock_feat, bench_feat, on="date", how="inner")
    
    # Combined feature
    df["stock_minus_nifty_20d"] = df["return_20d"] - df["nifty_20d_return"]
    
    # Drop warm-up rows (NaNs)
    # The longest lookback is 50 days (ma_50), so we drop any rows containing NaN
    df = df.dropna().reset_index(drop=True)
    
    return df
