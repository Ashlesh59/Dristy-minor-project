import requests
import json

PREVIEW_URL = "https://aashinvest-jxc0fahop-desksolutions.vercel.app"

def test_research_16_workflow():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 InvestIQ-Verifier"})

    # 1. Login with analyst_v2 account
    login_res = session.post(f"{PREVIEW_URL}/api/auth/login", json={
        "email": "analyst_v2@investiq.test",
        "password": "Password123!"
    }, timeout=15)
    
    if login_res.status_code != 200:
        # Try registering or testuser
        signup_res = session.post(f"{PREVIEW_URL}/api/auth/signup", json={
            "name": "Lead Analyst",
            "email": "analyst_v2@investiq.test",
            "password": "Password123!"
        }, timeout=15)
        print("Signup result:", signup_res.status_code, signup_res.text)
        login_res = session.post(f"{PREVIEW_URL}/api/auth/login", json={
            "email": "analyst_v2@investiq.test",
            "password": "Password123!"
        }, timeout=15)

    print(f"Auth Status: {login_res.status_code}")
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"

    # 2. Check GET /api/research/16
    res_16 = session.get(f"{PREVIEW_URL}/api/research/16", timeout=15)
    print(f"\nGET /api/research/16: {res_16.status_code}")
    if res_16.status_code != 200:
        print(f"Response: {res_16.text}")
    assert res_16.status_code == 200
    data_16 = res_16.json()
    r = data_16.get("research", {})
    print(f"Security: {r.get('ticker_symbol')}")
    print(f"is_legacy_analysis: {r.get('is_legacy_analysis')}")
    print(f"snapshot present: {'snapshot' in r}")

    # 3. Check GET /api/research/16/snapshot
    res_snap = session.get(f"{PREVIEW_URL}/api/research/16/snapshot", timeout=15)
    print(f"\nGET /api/research/16/snapshot: {res_snap.status_code}")
    assert res_snap.status_code == 200
    snap = res_snap.json().get("snapshot", {})
    print("Snapshot details:")
    print("  company.symbol:", snap.get("company", {}).get("symbol"))
    print("  currency:", snap.get("currency"))
    print("  market_data.is_available:", snap.get("market_data", {}).get("is_available"))
    print("  financial_statements.is_available:", snap.get("financial_statements", {}).get("is_available"))
    print("  news_articles count:", len(snap.get("news_articles", [])))
    print("  quality_status:", snap.get("quality_status"))

    assert snap.get("company", {}).get("symbol") == "TITAN", f"Expected TITAN, got {snap.get('company', {}).get('symbol')}"
    assert snap.get("currency") == "INR", f"Expected INR, got {snap.get('currency')}"
    assert snap.get("market_data", {}).get("is_available") is True, "Market data is not available"
    assert snap.get("financial_statements", {}).get("is_available") is False, "Financial statements should be false (partial)"
    assert snap.get("quality_status") == "partial", f"Expected quality_status partial, got {snap.get('quality_status')}"
    assert len(snap.get("news_articles", [])) > 0, "No news articles found"

    # 4. Trigger Regeneration: POST /api/research/16/analyze?force_refresh=true
    print("\nTriggering POST /api/research/16/analyze?force_refresh=true ...")
    res_analyze = session.post(f"{PREVIEW_URL}/api/research/16/analyze?force_refresh=true", timeout=30)
    print(f"Analyze status: {res_analyze.status_code}")
    assert res_analyze.status_code == 200
    analyze_data = res_analyze.json()
    print("Regeneration result:")
    print("  success:", analyze_data.get("success"))
    print("  is_legacy_analysis:", analyze_data.get("is_legacy_analysis"))
    print("  score:", analyze_data.get("analysis", {}).get("score"))
    print("  recommendation:", analyze_data.get("analysis", {}).get("recommendation"))
    print("  summary:", analyze_data.get("analysis", {}).get("summary")[:100] + "...")

    assert analyze_data.get("is_legacy_analysis") is False, "Analysis should no longer be legacy after regeneration!"

    # 5. Verify subsequent GET /api/research/16 reflects the regenerated analysis
    res_16_updated = session.get(f"{PREVIEW_URL}/api/research/16", timeout=15)
    assert res_16_updated.status_code == 200
    r_up = res_16_updated.json().get("research", {})
    assert r_up.get("is_legacy_analysis") is False, "Saved research must have is_legacy_analysis = False"
    print("\n[ALL PASS] Research 16 API workflow successfully verified against live Vercel Preview!")

if __name__ == "__main__":
    test_research_16_workflow()
