import pandas as pd
import argparse
import sys
import os
import tempfile
import shutil

def prepare_benchmark(input_csv, output_csv):
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        print(f"Error reading {input_csv}: {e}")
        sys.exit(1)
        
    # Column mapping
    df.columns = df.columns.str.strip().str.lower()
    
    date_col = next((c for c in df.columns if c in ["date", "timestamp", "time"]), None)
    close_col = next((c for c in df.columns if c in ["close", "close price", "ltp", "closing price"]), None)
    
    if not date_col or not close_col:
        print("Error: Could not identify Date and Close columns.")
        sys.exit(1)
        
    df = df[[date_col, close_col]].copy()
    df.columns = ["date", "close"]
    
    # Parse dates strictly
    try:
        df["date"] = pd.to_datetime(df["date"], errors="raise").dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Error parsing dates: {e}")
        sys.exit(1)
        
    # Drop duplicates
    initial_len = len(df)
    df = df.drop_duplicates(subset=["date"])
    if len(df) != initial_len:
        print("Warning: Duplicate dates were found and dropped.")
        
    # Reject invalid prices
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    if df["close"].isnull().any() or (df["close"] <= 0).any():
        print("Error: Found zero, negative, or invalid closing prices.")
        sys.exit(1)
        
    # Sort chronologically
    df = df.sort_values("date").reset_index(drop=True)
    
    if df.empty:
        print("Error: Empty dataset after processing.")
        sys.exit(1)
        
    # Atomic write
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(output_csv) or ".", text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            df.to_csv(f, index=False, line_terminator='\n')
        shutil.move(temp_path, output_csv)
    except Exception as e:
        print(f"Failed to write output: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        sys.exit(1)
        
    print(f"Benchmark preparation successful. Output saved to {os.path.basename(output_csv)}")
    print(f"Rows prepared: {len(df)}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    prepare_benchmark(args.input, args.output)
