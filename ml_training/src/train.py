import os
import json
import hashlib
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier

from .validate_data import validate_prices, validate_benchmark, align_and_validate
from .build_features import build_features
from .build_labels import build_labels
from .evaluate import evaluate_model, calculate_split_metadata
from config import *

def hash_file(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def time_split(df):
    dates = np.sort(df["date"].unique())
    n = len(dates)
    train_end = int(n * TRAIN_RATIO)
    val_end = train_end + int(n * VAL_RATIO)
    
    train_dates = set(dates[:train_end])
    val_dates = set(dates[train_end:val_end])
    test_dates = set(dates[val_end:])
    
    train_df = df[df["date"].isin(train_dates)].copy()
    val_df = df[df["date"].isin(val_dates)].copy()
    test_df = df[df["date"].isin(test_dates)].copy()
    
    if len(train_df) == 0 or len(val_df) == 0 or len(test_df) == 0:
        raise ValueError("One of the splits is empty. Insufficient data.")
    
    assert train_df["date"].max() < val_df["date"].min(), "Train/Val overlap"
    assert val_df["date"].max() < test_df["date"].min(), "Val/Test overlap"
    
    return train_df, val_df, test_df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--benchmark", required=True)
    args = parser.parse_args()
    
    print("Loading data...")
    try:
        prices = pd.read_csv(args.prices)
        benchmark = pd.read_csv(args.benchmark)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Training was not performed because real data is unavailable.")
        return
        
    prices = validate_prices(prices)
    benchmark = validate_benchmark(benchmark)
    prices, benchmark = align_and_validate(prices, benchmark)
    
    print("Building features...")
    features_df = build_features(prices, benchmark)
    
    print("Building labels...")
    final_df = build_labels(features_df)
    
    print("Splitting data...")
    train_df, val_df, test_df = time_split(final_df)
    
    feature_cols = [c for c in final_df.columns if c not in ["date", "security_id", "symbol", "close", "volume", "benchmark_close", "stock_close_future", "stock_future_return", "benchmark_close_future", "benchmark_future_return", "label"]]
    
    X_train, y_train = train_df[feature_cols], train_df["label"]
    X_val, y_val = val_df[feature_cols], val_df["label"]
    X_test, y_test = test_df[feature_cols], test_df["label"]
    
    print("Training model...")
    model = HistGradientBoostingClassifier(random_state=RANDOM_SEED)
    model.fit(X_train, y_train)
    
    print("Evaluating...")
    train_metrics = evaluate_model(model, X_train, y_train)
    val_metrics = evaluate_model(model, X_val, y_val)
    test_metrics = evaluate_model(model, X_test, y_test)
    
    split_meta = calculate_split_metadata(train_df, val_df, test_df)
    
    import sklearn
    
    metadata = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "training_timestamp_utc": datetime.utcnow().isoformat(),
        "model_type": "HistGradientBoostingClassifier",
        "feature_names": feature_cols,
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "training_date_range": split_meta["train_date_range"],
        "validation_date_range": split_meta["val_date_range"],
        "test_date_range": split_meta["test_date_range"],
        "dataset_row_counts": {
            "train": split_meta["train_records"],
            "val": split_meta["val_records"],
            "test": split_meta["test_records"]
        },
        "symbols_count": int(final_df["security_id"].nunique()),
        "metrics": {
            "train": train_metrics,
            "validation": val_metrics,
            "test": test_metrics
        },
        "environment": {
            "python_version": os.sys.version,
            "sklearn_version": sklearn.__version__,
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__
        },
        "input_hashes": {
            "prices_csv_sha256": hash_file(args.prices),
            "benchmark_csv_sha256": hash_file(args.benchmark)
        },
        "limitations": "Model relies solely on historical price and volume data. Does not incorporate fundamentals or news.",
        "disclaimer": "Not financial advice. Experimental model."
    }
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    model_path = MODELS_DIR / "investiq_alphamodel_v1.joblib"
    meta_path = MODELS_DIR / "investiq_alphamodel_v1.metadata.json"
    eval_path = REPORTS_DIR / "evaluation.json"
    
    joblib.dump(model, model_path)
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    with open(eval_path, "w") as f:
        json.dump(metadata["metrics"], f, indent=2)
        
    print("Training complete. Artifacts saved.")

if __name__ == "__main__":
    main()
