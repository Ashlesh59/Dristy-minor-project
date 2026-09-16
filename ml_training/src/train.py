import os
import sys
import json
import hashlib
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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
    
    train_dates = dates[:train_end]
    val_dates = dates[train_end:val_end]
    test_dates = dates[val_end:]
    
    if len(train_dates) == 0 or len(val_dates) == 0 or len(test_dates) == 0:
        raise ValueError("One of the splits is empty. Insufficient data.")
        
    # Apply 20-trading-day purge/embargo
    # This means dropping the first 20 days of val_dates and test_dates
    val_dates = val_dates[PREDICTION_HORIZON_DAYS:]
    test_dates = test_dates[PREDICTION_HORIZON_DAYS:]
    
    if len(val_dates) == 0 or len(test_dates) == 0:
        raise ValueError("Validation or test set empty after purge window. Insufficient data.")
    
    train_dates_set = set(train_dates)
    val_dates_set = set(val_dates)
    test_dates_set = set(test_dates)
    
    train_df = df[df["date"].isin(train_dates_set)].copy()
    val_df = df[df["date"].isin(val_dates_set)].copy()
    test_df = df[df["date"].isin(test_dates_set)].copy()
    
    assert train_df["date"].max() < val_df["date"].min(), "Train/Val overlap"
    assert val_df["date"].max() < test_df["date"].min(), "Val/Test overlap"
    
    return train_df, val_df, test_df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--benchmark", required=True)
    args = parser.parse_args()
    
    if not os.path.exists(args.prices) or not os.path.exists(args.benchmark):
        print("Error: Input files missing.")
        sys.exit(1)
    
    print("Loading data...")
    try:
        prices = pd.read_csv(args.prices)
        benchmark = pd.read_csv(args.benchmark)
    except Exception as e:
        print(f"Error reading data: {e}")
        sys.exit(1)
        
    try:
        prices = validate_prices(prices)
        benchmark = validate_benchmark(benchmark)
        prices, benchmark = align_and_validate(prices, benchmark)
        
        print("Building features...")
        features_df = build_features(prices, benchmark)
        
        print("Building labels...")
        final_df = build_labels(features_df)
        
        print("Splitting data...")
        train_df, val_df, test_df = time_split(final_df)
    except Exception as e:
        print(f"Validation or preprocessing failed: {e}")
        sys.exit(1)
    
    feature_cols = [c for c in final_df.columns if c not in ["date", "security_id", "symbol", "close", "volume", "benchmark_close", "stock_close_future", "stock_future_return", "benchmark_close_future", "benchmark_future_return", "label"]]
    
    X_train, y_train = train_df[feature_cols], train_df["label"]
    X_val, y_val = val_df[feature_cols], val_df["label"]
    X_test, y_test = test_df[feature_cols], test_df["label"]
    
    print("Training candidate models...")
    try:
        # Dummy
        dummy = DummyClassifier(strategy="prior")
        dummy.fit(X_train, y_train)
        
        # Logistic Regression
        lr = Pipeline([("scaler", StandardScaler()), ("lr", LogisticRegression(random_state=RANDOM_SEED, max_iter=1000))])
        lr.fit(X_train, y_train)
        
        # HistGradientBoosting
        hgb = HistGradientBoostingClassifier(random_state=RANDOM_SEED)
        hgb.fit(X_train, y_train)
        
        models = {"Dummy": dummy, "LogisticRegression": lr, "HistGradientBoosting": hgb}
        
        best_model_name = None
        best_score = -float('inf')
        
        for name, m in models.items():
            probs = m.predict_proba(X_val)[:, 1]
            from sklearn.metrics import roc_auc_score
            score = roc_auc_score(y_val, probs)
            if score > best_score:
                best_score = score
                best_model_name = name
                
        print(f"Selected {best_model_name} based on validation ROC-AUC.")
        selected_model = models[best_model_name]
        
    except Exception as e:
        print(f"Training failed: {e}")
        sys.exit(1)
    
    try:
        print("Evaluating...")
        train_metrics = evaluate_model(selected_model, X_train, y_train, y_train=y_train)
        val_metrics = evaluate_model(selected_model, X_val, y_val, y_train=y_train)
        test_metrics = evaluate_model(selected_model, X_test, y_test, y_train=y_train)
    except Exception as e:
        print(f"Evaluation failed: {e}")
        sys.exit(1)
    
    split_meta = calculate_split_metadata(train_df, val_df, test_df)
    import sklearn
    
    metadata = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "training_timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "model_type": best_model_name,
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
            "python_version": os.sys.version.split()[0],
            "sklearn_version": sklearn.__version__,
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__
        },
        "input_hashes": {
            "prices_csv_sha256": hash_file(args.prices),
            "benchmark_csv_sha256": hash_file(args.benchmark)
        },
        "limitations": "Model relies solely on historical price and volume data. Does not incorporate fundamentals or news.",
        "disclaimer": "Experimental model. Not financial advice."
    }
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    model_path = MODELS_DIR / "investiq_alphamodel_v1.joblib"
    meta_path = MODELS_DIR / "investiq_alphamodel_v1.metadata.json"
    eval_path = REPORTS_DIR / "evaluation.json"
    
    from .backtest import run_backtest
    try:
        print("Running backtest...")
        backtest_report = run_backtest(test_df, selected_model, feature_cols)
    except Exception as e:
        print(f"Backtest failed: {e}")
        backtest_report = {"status": "FAILED", "reason": str(e), "metrics": {}}

    try:
        joblib.dump(selected_model, model_path)
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)
        with open(eval_path, "w") as f:
            json.dump(metadata["metrics"], f, indent=2)
        with open(REPORTS_DIR / "backtest.json", "w") as f:
            json.dump(backtest_report, f, indent=2)
    except Exception as e:
        print(f"Artifact saving failed: {e}")
        sys.exit(1)
        
    print("Training complete. Artifacts saved.")

if __name__ == "__main__":
    main()
