import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window, min_periods=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window, min_periods=window).mean()
    
    rs = np.zeros_like(gain)
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
    
    df["return_1d"] = close.pct_change(periods=1)
    df["return_5d"] = close.pct_change(periods=5)
    df["return_20d"] = close.pct_change(periods=20)
    
    ma_5 = close.rolling(window=5).mean()
    ma_20 = close.rolling(window=20).mean()
    ma_50 = close.rolling(window=50).mean()
    
    df["close_div_ma5"] = np.where(ma_5 > 0, close / ma_5, np.nan)
    df["close_div_ma20"] = np.where(ma_20 > 0, close / ma_20, np.nan)
    df["close_div_ma50"] = np.where(ma_50 > 0, close / ma_50, np.nan)
    
    df["volatility_20d"] = df["return_1d"].rolling(window=20).std()
    
    df["rsi_14"] = calculate_rsi(close, 14)
    
    vol_ma20 = vol.rolling(window=20).mean()
    df["volume_ma20"] = vol_ma20
    df["vol_div_ma20"] = np.where(vol_ma20 > 0, vol / vol_ma20, np.nan)
    
    return df

def build_features(prices: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    bench_feat = build_benchmark_features(benchmark)
    
    # Avoid groupby warning by setting include_groups=False, but then we must inject security_id back if it gets dropped.
    # We use a loop approach to explicitly avoid deprecation warnings and index confusion.
    # Let's just use a loop or index approach to be 100% safe, or just use apply(include_groups=False) and add it back from the original dataframe's index? No, order might change.
    
    # Safest way to avoid groupby warning and keep columns:
    dfs = []
    for sid, grp in prices.groupby("security_id"):
        res = build_stock_features(grp)
        res["security_id"] = sid
        dfs.append(res)
    stock_feat = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=prices.columns)
    
    df = pd.merge(stock_feat, bench_feat, on="date", how="inner")
    
    df["stock_minus_nifty_20d"] = df["return_20d"] - df["nifty_20d_return"]
    
    # Handle infinite values (replace with NaN)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    
    # Drop rows with NaN (warm-up rows and unsafe infinities)
    df = df.dropna().reset_index(drop=True)
    
    return df
