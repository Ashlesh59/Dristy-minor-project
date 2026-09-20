import requests
import json

PREVIEW_URL = "https://aashinvest-82kxuj416-desksolutions.vercel.app"

def test_research_endpoints():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 InvestIQ-Verifier"})

    # 1. Login
    login_res = session.post(f"{PREVIEW_URL}/api/auth/login", json={
        "email": "test_diagnose@investiq.app",
        "password": "Password123!"
    }, timeout=15)
    print("Auth Status:", login_res.status_code)
    assert login_res.status_code == 200

    # 2. Test TITAN Research 18 (Legacy analysis = True)
    print("\n--- Testing GET /api/research/18 (TITAN) ---")
    res_18 = session.get(f"{PREVIEW_URL}/api/research/18", timeout=15)
    assert res_18.status_code == 200
    d18 = res_18.json()
    r18 = d18.get("research", {})
    print(f"ID 18 Symbol: {r18.get('ticker_symbol')}")
    print(f"ID 18 is_legacy_analysis: {d18.get('is_legacy_analysis')}")
    print(f"ID 18 legacy_warning: {d18.get('legacy_warning')}")
    assert d18.get("is_legacy_analysis") is True
    assert "without the current verified-data snapshot" in d18.get("legacy_warning")

    print("\n--- Testing GET /api/research/18/snapshot ---")
    res_snap18 = session.get(f"{PREVIEW_URL}/api/research/18/snapshot", timeout=15)
    assert res_snap18.status_code == 200
    snap18 = res_snap18.json().get("snapshot", {})
    print(f"Symbol: {snap18.get('company', {}).get('symbol')}")
    print(f"Currency: {snap18.get('currency')}")
    print(f"Market Data Available: {snap18.get('market_data', {}).get('is_available')}")
    print(f"Financial Statements Available: {snap18.get('financial_statements', {}).get('is_available')}")
    print(f"News Articles Count: {len(snap18.get('news_articles', []))}")
    print(f"Quality Status: {snap18.get('quality_status')}")
    assert snap18.get("company", {}).get("symbol") == "TITAN"
    assert snap18.get("currency") == "INR"
    assert snap18.get("market_data", {}).get("is_available") is True
    assert snap18.get("financial_statements", {}).get("is_available") is False
    assert snap18.get("quality_status") == "partial"
    assert len(snap18.get("news_articles", [])) > 0

    # 3. Test Regeneration on Research 18
    print("\n--- Testing POST /api/research/18/analyze?force_refresh=true ---")
    res_regen = session.post(f"{PREVIEW_URL}/api/research/18/analyze?force_refresh=true", timeout=30)
    print(f"Regenerate Status: {res_regen.status_code}")
    assert res_regen.status_code == 200
    regen_data = res_regen.json()
    print(f"Regen is_legacy_analysis: {regen_data.get('is_legacy_analysis')}")
    assert regen_data.get("is_legacy_analysis") is False

    # 4. Verify subsequent GET /api/research/18 is no longer legacy
    res_18_after = session.get(f"{PREVIEW_URL}/api/research/18", timeout=15)
    assert res_18_after.status_code == 200
    d18_after = res_18_after.json()
    print(f"Post-regen is_legacy_analysis: {d18_after.get('is_legacy_analysis')}")
    print(f"Post-regen legacy_warning: {d18_after.get('legacy_warning')}")
    assert d18_after.get("is_legacy_analysis") is False
    assert d18_after.get("legacy_warning") is None

    # 5. Also test TITAN (ID 22)
    print("\n--- Testing TITAN Research ID 22 ---")
    res_22 = session.get(f"{PREVIEW_URL}/api/research/22", timeout=15)
    assert res_22.status_code == 200
    d22 = res_22.json()
    snap22 = d22.get("snapshot", {})
    print(f"ID 22 Symbol: {snap22.get('company', {}).get('symbol')}")
    print(f"ID 22 Currency: {snap22.get('currency')}")
    print(f"ID 22 Market Data Available: {snap22.get('market_data', {}).get('is_available')}")
    print(f"ID 22 Financial Statements Available: {snap22.get('financial_statements', {}).get('is_available')}")
    print(f"ID 22 News Articles Count: {len(snap22.get('news_articles', []))}")
    print(f"ID 22 Quality Status: {snap22.get('quality_status')}")
    assert snap22.get("company", {}).get("symbol") == "TITAN"
    assert snap22.get("currency") == "INR"
    assert snap22.get("market_data", {}).get("is_available") is True
    assert snap22.get("financial_statements", {}).get("is_available") is False
    assert snap22.get("quality_status") == "partial"
    assert len(snap22.get("news_articles", [])) > 0

    print("\n[ALL LIVE VERIFICATION TESTS PASSED SUCCESSFULLY!]")

if __name__ == "__main__":
    test_research_endpoints()
