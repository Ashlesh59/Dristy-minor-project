import requests
import json
import sys

PREVIEW_URL = "https://aashinvest-82kxuj416-desksolutions.vercel.app"

def run_comprehensive_check():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 InvestIQ-Comprehensive-Check"})

    print("==================================================")
    print("1. HEALTH & BUILD IDENTIFIER CHECK")
    print("==================================================")
    r_health = session.get(f"{PREVIEW_URL}/api/health", timeout=15)
    print(f"GET /api/health: {r_health.status_code}")
    assert r_health.status_code == 200, f"Health check failed: {r_health.text}"
    h_data = r_health.json()
    assert h_data.get("build_id") == "VERIFIED_SNAPSHOT_V2", f"Invalid build_id: {h_data}"
    assert h_data.get("database") == "connected", f"Database not connected: {h_data}"
    assert h_data.get("status") == "healthy", f"Service status not healthy: {h_data}"
    print(f"-> Verified build_id: {h_data.get('build_id')}")
    print(f"-> Database status: {h_data.get('database')}")
    print(f"-> Environment: {h_data.get('environment')}")

    print("\n==================================================")
    print("2. STATIC PAGES & ASSET INTEGRITY")
    print("==================================================")
    pages = [
        "index.html",
        "login.html",
        "signup.html",
        "dashboard.html",
        "company-research.html",
        "ai-analysis.html",
        "investment-report.html",
        "saved-reports.html",
        "settings.html",
        "help.html",
        "js/ai-analysis.js?v=verified-snapshot-v2",
        "css/ai-analysis.css?v=verified-snapshot-v2"
    ]
    for p in pages:
        r = session.get(f"{PREVIEW_URL}/{p}", timeout=15)
        print(f"GET /{p}: {r.status_code} ({len(r.content)} bytes)")
        assert r.status_code == 200, f"Failed to load /{p}"
    print("-> All static pages and versioned assets loaded with 200 OK.")

    print("\n==================================================")
    print("3. AUTHENTICATION (LOGIN)")
    print("==================================================")
    login_payload = {
        "email": "test_diagnose@investiq.app",
        "password": "Password123!"
    }
    r_login = session.post(f"{PREVIEW_URL}/api/auth/login", json=login_payload, timeout=15)
    print(f"POST /api/auth/login: {r_login.status_code}")
    assert r_login.status_code == 200
    user_info = r_login.json().get("user", {})
    print(f"-> Logged in as: {user_info.get('email')} (ID: {user_info.get('id')})")

    print("\n==================================================")
    print("4. COMPANY SEARCH & MARKET DATA")
    print("==================================================")
    for sym in ["TITAN", "RELIANCE", "TCS", "INFY", "M&M"]:
        r_search = session.get(f"{PREVIEW_URL}/api/companies/search", params={"q": sym}, timeout=15)
        assert r_search.status_code == 200
        results = r_search.json().get("results", [])
        assert len(results) > 0, f"No results for {sym}"
        top = results[0]
        sec_id = top["security_id"]
        print(f"-> Search '{sym}': found {top['company_name']} (Security ID: {sec_id})")

        # Market data latest
        r_mkt = session.get(f"{PREVIEW_URL}/api/securities/{sec_id}/market-data/latest", timeout=15)
        assert r_mkt.status_code == 200
        md = r_mkt.json().get("market_data", {})
        print(f"   EOD Close: INR {md.get('close')} | VWAP: INR {md.get('vwap')} | Source: {md.get('source')}")

        # Market data history
        r_hist = session.get(f"{PREVIEW_URL}/api/securities/{sec_id}/market-data/history?range=1m", timeout=15)
        assert r_hist.status_code == 200
        prices = r_hist.json().get("prices", [])
        print(f"   1M History Points: {len(prices)} days")

    print("\n==================================================")
    print("5. VERIFIED SNAPSHOT & AI ANALYSIS WORKFLOW")
    print("==================================================")
    # Check TITAN Research (ID 22 / 18)
    r_snap = session.get(f"{PREVIEW_URL}/api/research/22/snapshot", timeout=15)
    assert r_snap.status_code == 200
    snap = r_snap.json().get("snapshot", {})
    print(f"-> Snapshot for TITAN:")
    print(f"   Company: {snap.get('company', {}).get('symbol')} ({snap.get('company', {}).get('name')})")
    print(f"   Currency: {snap.get('currency')}")
    print(f"   Market Data Available: {snap.get('market_data', {}).get('is_available')}")
    print(f"   Financial Statements Available: {snap.get('financial_statements', {}).get('is_available')}")
    print(f"   News Articles: {len(snap.get('news_articles', []))} verified stories")
    print(f"   Quality Status: {snap.get('quality_status')}")
    assert snap.get("market_data", {}).get("is_available") is True
    assert snap.get("financial_statements", {}).get("is_available") is False
    assert snap.get("quality_status") == "partial"
    assert len(snap.get("news_articles", [])) > 0

    print("\n==================================================")
    print("6. FULL INVESTMENT REPORT GENERATION")
    print("==================================================")
    r_report = session.post(f"{PREVIEW_URL}/api/research/22/report", timeout=30)
    print(f"POST /api/research/22/report: {r_report.status_code}")
    assert r_report.status_code == 200
    report = r_report.json().get("report", {})
    print(f"-> Generated Report AI Score: {report.get('ai_score')} / 100")
    print(f"-> Stance: {report.get('recommendation')}")
    print(f"-> Decision Summary Available: {'decision_summary' in report}")

    print("\n==================================================")
    print(">>> ALL VERIFICATION CHECKS PASSED WITH 0 ERRORS! <<<")
    print("==================================================")

if __name__ == "__main__":
    run_comprehensive_check()
