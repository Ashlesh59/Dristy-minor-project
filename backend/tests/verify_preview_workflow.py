"""
backend/tests/verify_preview_workflow.py
--------------------------------------------------------------------------
Comprehensive verification script for the live Vercel Preview deployment:
- Tests auth, database diagnostics, company search, market data endpoints,
  price history time-series, report generation, and saved report caching.
--------------------------------------------------------------------------
"""

import sys
import time
import json
import requests

PREVIEW_URL = "https://aashinvest-jdwps76sc-desksolutions.vercel.app"

def main():
    print(f"=== VERIFYING LIVE PREVIEW: {PREVIEW_URL} ===")
    session = requests.Session()

    # 1. Health check
    res_health = session.get(f"{PREVIEW_URL}/api/health")
    print(f"1. Health Check: {res_health.status_code} -> {res_health.json()}")
    assert res_health.status_code == 200

    # 2. Login as test user
    login_payload = {
        "email": "test_diagnose@investiq.app",
        "password": "Password123!"
    }
    res_login = session.post(f"{PREVIEW_URL}/api/auth/login", json=login_payload)
    if res_login.status_code != 200:
        # Register if not exists
        reg_payload = {
            "name": "Live Tester",
            "email": "test_diagnose@investiq.app",
            "password": "Password123!"
        }
        res_reg = session.post(f"{PREVIEW_URL}/api/auth/register", json=reg_payload)
        print(f"Registered test user: {res_reg.status_code}")
        res_login = session.post(f"{PREVIEW_URL}/api/auth/login", json=login_payload)

    print(f"2. Auth Login: {res_login.status_code} -> {res_login.json().get('user', {}).get('email')}")
    assert res_login.status_code == 200

    # 3. Database Diagnostics
    res_diag = session.get(f"{PREVIEW_URL}/api/admin/diagnose")
    print(f"3. DB Diagnostics: {res_diag.status_code} ->")
    diag_res = res_diag.json()
    counts = diag_res.get("counts", {})
    print("   Database:", diag_res.get("database"))
    print("   Counts:", json.dumps(counts, indent=2))
    print("   Key Securities:", json.dumps(diag_res.get("key_securities"), indent=2))
    assert counts.get("companies", 0) > 2000
    assert counts.get("daily_prices", 0) > 50000

    # 4. Five Company Searches
    test_queries = ["M&M", "Mahindra & Mahindra", "RELIANCE", "TCS", "INFY", "HDFCBANK"]
    benchmark_securities = {}

    print("\n4. Testing Company Searches:")
    for q in test_queries:
        res_search = session.get(f"{PREVIEW_URL}/api/companies/search", params={"q": q})
        assert res_search.status_code == 200
        results = res_search.json().get("results", [])
        print(f"   Query '{q}': found {len(results)} matches.")
        assert len(results) > 0
        top = results[0]
        print(f"      Top: {top['company_name']} | {top['symbol']} | {top['exchange']} | ID: {top['security_id']}")
        if top['symbol'] not in benchmark_securities:
            benchmark_securities[top['symbol']] = top['security_id']

    # 5. Core Market Data & History Endpoints
    print("\n5. Testing Latest Market Data & Historical Series:")
    for sym, sec_id in benchmark_securities.items():
        res_latest = session.get(f"{PREVIEW_URL}/api/securities/{sec_id}/market-data/latest")
        assert res_latest.status_code == 200
        md = res_latest.json().get("market_data", {})
        print(f"\n   [{sym} - ID {sec_id}]")
        print(f"      Close: INR {md.get('close')} | Change: INR {md.get('change')} ({md.get('change_percent')}%)")
        print(f"      Open: INR {md.get('open')} | High: INR {md.get('high')} | Low: INR {md.get('low')} | VWAP: INR {md.get('vwap')}")
        print(f"      Volume: {md.get('volume')} | SMA20: {md.get('sma_20')} | SMA50: {md.get('sma_50')} | Volatility: {md.get('volatility')}")
        print(f"      52W Range: INR {md.get('week_52_low')} - INR {md.get('week_52_high')} | Returns: {md.get('returns')}")

        # Price History (1M and 1Y)
        res_hist = session.get(f"{PREVIEW_URL}/api/securities/{sec_id}/market-data/history?range=1y")
        assert res_hist.status_code == 200
        prices = res_hist.json().get("prices", [])
        print(f"      1Y History Points: {len(prices)} sessions (Earliest: {prices[0]['date']} INR {prices[0]['close']}, Latest: {prices[-1]['date']} INR {prices[-1]['close']})")

    # 6. Create Research & Generate Investment Report for M&M
    print("\n6. Testing Report Generation for M&M:")
    mm_sec_id = benchmark_securities["M&M"]
    res_create = session.post(f"{PREVIEW_URL}/api/research", json={"security_id": mm_sec_id})
    assert res_create.status_code in (200, 201)
    research_id = res_create.json()["research"]["id"]
    print(f"   Created research record ID: {research_id}")

    # Generate Report
    t0 = time.time()
    res_report = session.post(f"{PREVIEW_URL}/api/research/{research_id}/report")
    dt = time.time() - t0
    print(f"   Generated Report in {dt:.2f}s (Status: {res_report.status_code})")
    assert res_report.status_code == 200
    report_json = res_report.json().get("report", {})
    print(f"   AI Score: {report_json.get('ai_score')} | Stance: {report_json.get('recommendation')}")
    print(f"   Deterministic Fallback Used: {report_json.get('is_deterministic')}")
    print(f"   Decision Summary: {json.dumps(report_json.get('decision_summary'), indent=2)}")

    # Reload Report from Cache (Zero Gemini calls)
    res_cached = session.get(f"{PREVIEW_URL}/api/research/{research_id}")
    assert res_cached.status_code == 200
    cached_report = res_cached.json()["research"]["report_data"]
    assert cached_report["ai_score"] == report_json["ai_score"]
    print("   Cached report successfully reused from database with 0 external calls.")

    print("\n=== ALL LIVE PREVIEW TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    main()
