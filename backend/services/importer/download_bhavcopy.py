import os
import urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

DEST_DIR = os.path.abspath("data/raw/nse/bhavcopy")
os.makedirs(DEST_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
}

def fetch_date(date_str):
    dest = os.path.join(DEST_DIR, f"BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip")
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return date_str, True, os.path.getsize(dest), "Cached"

    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
            if len(data) > 1000:
                with open(dest, "wb") as f:
                    f.write(data)
                return date_str, True, len(data), "Downloaded"
    except Exception as e:
        return date_str, False, 0, str(e)
    return date_str, False, 0, "Empty"

def main():
    start_dt = datetime(2026, 9, 16)
    candidate_dates = []
    for i in range(70):
        cur = start_dt - timedelta(days=i)
        if cur.weekday() < 5:  # Mon-Fri
            candidate_dates.append(cur.strftime("%Y%m%d"))

    print(f"Checking {len(candidate_dates)} candidate trading dates...")
    successful = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_date, d): d for d in candidate_dates}
        for future in as_completed(futures):
            d, success, size, msg = future.result()
            if success:
                successful.append((d, size))
                print(f"[OK] {d}: {size} bytes ({msg})")
            else:
                print(f"[SKIP] {d}: {msg}")

    successful.sort(reverse=True)
    print("=" * 50)
    print(f"Total downloaded trading days: {len(successful)}")
    print(f"Date range: {successful[-1][0]} to {successful[0][0]}" if successful else "None")

if __name__ == "__main__":
    main()
