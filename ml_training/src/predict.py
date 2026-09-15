import argparse
import json
import joblib
import pandas as pd
from datetime import datetime
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    
    model_path = Path(args.model)
    meta_path = model_path.with_name(model_path.stem + ".metadata.json")
    
    if not model_path.exists():
        print(json.dumps({"error": f"Model not found at {model_path}"}))
        return
        
    if not meta_path.exists():
        print(json.dumps({"error": f"Metadata not found at {meta_path}"}))
        return
        
    try:
        model = joblib.load(model_path)
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception as e:
        print(json.dumps({"error": f"Failed to load model or metadata: {str(e)}"}))
        return
        
    try:
        input_df = pd.read_csv(args.input)
    except Exception as e:
        print(json.dumps({"error": f"Failed to read input CSV: {str(e)}"}))
        return
        
    feature_cols = meta.get("feature_names", [])
    missing_cols = [c for c in feature_cols if c not in input_df.columns]
    if missing_cols:
        print(json.dumps({"error": f"Input missing required features: {missing_cols}"}))
        return
        
    X = input_df[feature_cols]
    
    try:
        preds = model.predict(X)
        probs = model.predict_proba(X)[:, 1]
    except Exception as e:
        print(json.dumps({"error": f"Prediction failed: {str(e)}"}))
        return
        
    results = []
    for idx, row in input_df.iterrows():
        res = {
            "model": meta.get("model_name", "InvestIQ AlphaModel v1"),
            "model_version": meta.get("model_version", "1.0.0"),
            "security_id": int(row.get("security_id", 0)),
            "symbol": str(row.get("symbol", "UNKNOWN")),
            "prediction_horizon_days": meta.get("prediction_horizon_days", 20),
            "outperformance_probability": float(probs[idx]),
            "predicted_class": int(preds[idx]),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "disclaimer": meta.get("disclaimer", "Experimental model. Not financial advice.")
        }
        results.append(res)
        
    if len(results) == 1:
        print(json.dumps(results[0], indent=2))
    else:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
