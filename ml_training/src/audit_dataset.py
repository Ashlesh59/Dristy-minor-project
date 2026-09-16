import os
import sys
import json
import argparse
import pandas as pd
import numpy as np

from .train import time_split
from .build_features import build_features
from .build_labels import build_labels
from config import TRAIN_RATIO, VAL_RATIO, PREDICTION_HORIZON_DAYS

def audit_dataset(prices_path, benchmark_path, output_json):
    if not os.path.exists(prices_path) or not os.path.exists(benchmark_path):
        print("Error: Input files missing for audit.")
        sys.exit(1)
        
    prices = pd.read_csv(prices_path)
    benchmark = pd.read_csv(benchmark_path)
    
    report = {}
    report["total_rows"] = len(prices)
    report["num_securities"] = int(prices["security_id"].nunique())
    
    dates = pd.to_datetime(prices["date"])
    report["date_range"] = {"min": str(dates.min().date()), "max": str(dates.max().date())}
    report["trading_date_count"] = int(dates.nunique())
    
    obs_per_sec = prices.groupby("security_id").size()
    report["observations_per_security"] = {
        "min": int(obs_per_sec.min()),
        "median": float(obs_per_sec.median()),
        "max": int(obs_per_sec.max())
    }
    
    report["missing_values"] = int(prices.isnull().sum().sum())
    report["duplicate_rows"] = int(prices.duplicated().sum())
    
    bench_dates = set(benchmark["date"])
    stock_dates = set(prices["date"])
    report["stock_benchmark_date_alignment"] = {
        "stock_dates_not_in_benchmark": len(stock_dates - bench_dates),
        "benchmark_dates_not_in_stock": len(bench_dates - stock_dates)
    }
    
    # Calculate extreme returns (e.g. > 20% or < -20% daily)
    prices_sorted = prices.sort_values(["security_id", "date"])
    prices_sorted["ret"] = prices_sorted.groupby("security_id")["close"].pct_change()
    extreme = prices_sorted[(prices_sorted["ret"] > 0.25) | (prices_sorted["ret"] < -0.25)]
    report["extreme_returns_count"] = len(extreme)
    
    report["securities_insufficient_history"] = int((obs_per_sec < 252).sum())
    report["survivorship_bias_warning"] = "WARNING: Data may only include currently active securities, leading to survivorship bias."
    report["unadjusted_price_warning"] = "WARNING: If prices are unadjusted, corporate actions will distort features and labels."
    
    # Build pipeline to get labels and splits
    try:
        from .validate_data import validate_prices, validate_benchmark, align_and_validate
        vp = validate_prices(prices)
        vb = validate_benchmark(benchmark)
        vp, vb = align_and_validate(vp, vb)
        feat = build_features(vp, vb)
        labeled = build_labels(feat)
        
        report["label_distribution"] = labeled["label"].value_counts().to_dict()
        
        train_df, val_df, test_df = time_split(labeled)
        report["partition_boundaries"] = {
            "train": {"min": str(train_df["date"].min()), "max": str(train_df["date"].max())},
            "val": {"min": str(val_df["date"].min()), "max": str(val_df["date"].max())},
            "test": {"min": str(test_df["date"].min()), "max": str(test_df["date"].max())}
        }
        
        report["class_distribution"] = {
            "train": train_df["label"].value_counts().to_dict(),
            "val": val_df["label"].value_counts().to_dict(),
            "test": test_df["label"].value_counts().to_dict()
        }
        
        # Check if any partition has < 2 classes
        for part_name, dist in report["class_distribution"].items():
            if len(dist) < 2:
                print(f"CRITICAL ERROR: Partition '{part_name}' contains only one label class.")
                sys.exit(1)
                
    except Exception as e:
        print(f"CRITICAL ERROR during pipeline execution for audit: {e}")
        sys.exit(1)
        
    with open(output_json, "w") as f:
        json.dump(report, f, indent=2)
        
    print("\n--- DATASET AUDIT REPORT ---")
    for k, v in report.items():
        if isinstance(v, dict):
            print(f"{k}:")
            for sub_k, sub_v in v.items():
                print(f"  {sub_k}: {sub_v}")
        else:
            print(f"{k}: {v}")
    print("----------------------------\n")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    audit_dataset(args.prices, args.benchmark, args.output)
