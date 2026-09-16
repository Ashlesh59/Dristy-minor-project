import sqlite3
import argparse
import sys
import os
import tempfile
import shutil

def export_db(db_path, output_path, allow_unadjusted, min_history=252):
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as e:
        print(f"Error opening database: {e}")
        sys.exit(1)
        
    cursor = conn.cursor()
    
    # Check if adjusted prices exist
    cursor.execute("SELECT COUNT(*) FROM adjusted_daily_prices")
    adj_count = cursor.fetchone()[0]
    
    if adj_count == 0 and not allow_unadjusted:
        print("Error: Adjusted price coverage is incomplete or missing.")
        print("Run with --allow-unadjusted to export raw prices, but be aware this may create false split/bonus returns.")
        sys.exit(1)
        
    if adj_count == 0:
        print("WARNING: Exporting unadjusted data. This may create false split/bonus returns.")
        query = """
            SELECT date, security_id, s.ticker as symbol, close_price as close, volume
            FROM daily_prices dp
            JOIN securities s ON dp.security_id = s.id
            WHERE s.security_type = 'EQ' AND dp.close_price > 0
            GROUP BY date, security_id
            ORDER BY security_id, date
        """
    else:
        query = """
            SELECT date, security_id, s.ticker as symbol, close_price as close, volume
            FROM adjusted_daily_prices adp
            JOIN securities s ON adp.security_id = s.id
            WHERE s.security_type = 'EQ' AND adp.close_price > 0
            GROUP BY date, security_id
            ORDER BY security_id, date
        """
        
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print("Error: No valid records found.")
        sys.exit(1)
        
    # Process rows and filter by min_history
    security_counts = {}
    for row in rows:
        security_counts[row[1]] = security_counts.get(row[1], 0) + 1
        
    valid_securities = {sid for sid, count in security_counts.items() if count >= min_history}
    
    final_rows = [row for row in rows if row[1] in valid_securities]
    
    if not final_rows:
        print(f"Error: No securities met the minimum history requirement of {min_history} days.")
        sys.exit(1)
        
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(output_path) or ".", text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write("date,security_id,symbol,close,volume\n")
            for row in final_rows:
                f.write(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")
                
        shutil.move(temp_path, output_path)
    except Exception as e:
        print(f"Failed to write output: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        sys.exit(1)
        
    dates = [row[0] for row in final_rows]
    print(f"Export successful. Output saved to {os.path.basename(output_path)}")
    print(f"Rows exported: {len(final_rows)}")
    print(f"Securities exported: {len(valid_securities)}")
    print(f"Date range: {min(dates)} to {max(dates)}")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-unadjusted", action="store_true")
    args = parser.parse_args()
    
    export_db(args.database, args.output, args.allow_unadjusted)
