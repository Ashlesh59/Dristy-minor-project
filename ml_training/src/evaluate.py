import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, log_loss

def evaluate_model(model, X, y) -> dict:
    if len(y.unique()) < 2:
        raise ValueError("Only one class exists in this partition. Evaluation cannot proceed.")
        
    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]
    
    # Majority class baseline
    majority_class = y.mode()[0]
    baseline_preds = np.full_like(y, majority_class)
    baseline_probs = np.full_like(y, y.mean()) # Baseline probability is the mean of positive class
    
    metrics = {
        "accuracy": float(accuracy_score(y, preds)),
        "precision": float(precision_score(y, preds, zero_division=0)),
        "recall": float(recall_score(y, preds, zero_division=0)),
        "f1_score": float(f1_score(y, preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, probs)),
        "log_loss": float(log_loss(y, probs)),
        "positive_label_percentage": float(y.mean() * 100),
        
        "baseline_accuracy": float(accuracy_score(y, baseline_preds)),
        "baseline_precision": float(precision_score(y, baseline_preds, zero_division=0)),
        "baseline_recall": float(recall_score(y, baseline_preds, zero_division=0)),
        "baseline_f1_score": float(f1_score(y, baseline_preds, zero_division=0)),
        "baseline_roc_auc": float(roc_auc_score(y, baseline_probs)),
        "baseline_log_loss": float(log_loss(y, baseline_probs))
    }
    return metrics

def calculate_split_metadata(df_train, df_val, df_test) -> dict:
    return {
        "train_records": len(df_train),
        "val_records": len(df_val),
        "test_records": len(df_test),
        "train_date_range": [str(df_train["date"].min()), str(df_train["date"].max())],
        "val_date_range": [str(df_val["date"].min()), str(df_val["date"].max())],
        "test_date_range": [str(df_test["date"].min()), str(df_test["date"].max())]
    }
