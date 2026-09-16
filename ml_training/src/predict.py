import sys
import os
import json
import joblib
import pandas as pd
import numpy as np
from datetime import datetime

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
MODEL_PATH = os.path.join(MODELS_DIR, "investiq_alphamodel_v1.joblib")
META_PATH = os.path.join(MODELS_DIR, "investiq_alphamodel_v1.metadata.json")

def predict_cli():
    try:
        input_data = json.load(sys.stdin)
    except Exception as e:
        print(f"Error reading JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)
        
    if not os.path.exists(MODEL_PATH) or not os.path.exists(META_PATH):
        print("Error: Model or metadata not found.", file=sys.stderr)
        sys.exit(1)
        
    try:
        model = joblib.load(MODEL_PATH)
        with open(META_PATH, "r") as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"Error loading model artifacts: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Verify model version
    if metadata.get("model_version") != "1.0.0":
        print("Error: Model version mismatch.", file=sys.stderr)
        sys.exit(1)
        
    features = input_data.get("features", {})
    security_id = input_data.get("security_id", -1)
    symbol = input_data.get("symbol", "UNKNOWN")
    
    expected_features = metadata.get("feature_names", [])
    
    # Check exact match of features
    if set(features.keys()) != set(expected_features):
        print("Error: Feature mismatch. Provided features do not exactly match model expected features.", file=sys.stderr)
        sys.exit(1)
        
    # Check for NaN and infinite values
    for v in features.values():
        if v is None or pd.isna(v) or np.isinf(v):
            print("Error: Input contains NaN or infinite values.", file=sys.stderr)
            sys.exit(1)
            
    # Build dataframe in exact order
    try:
        df = pd.DataFrame([{col: features[col] for col in expected_features}])
    except Exception as e:
        print(f"Error preparing features: {e}", file=sys.stderr)
        sys.exit(1)
        
    try:
        probs = model.predict_proba(df)[0]
        prob_1 = probs[1]
        pred_class = 1 if prob_1 > 0.5 else 0
    except Exception as e:
        print(f"Error during prediction: {e}", file=sys.stderr)
        sys.exit(1)
        
    output = {
        "model": metadata.get("model_name", "InvestIQ AlphaModel v1"),
        "model_version": metadata.get("model_version", "1.0.0"),
        "security_id": security_id,
        "symbol": symbol,
        "prediction_horizon_days": metadata.get("prediction_horizon_days", 20),
        "outperformance_probability": float(prob_1),
        "predicted_class": int(pred_class),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "disclaimer": "Experimental model. Not financial advice."
    }
    
    print(json.dumps(output))

if __name__ == "__main__":
    predict_cli()
