import requests
import json
import sys

PREVIEW_URL = "https://aashinvest-82kxuj416-desksolutions.vercel.app"

def test_deployed_files():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 InvestIQ-Verifier"})

    print("=== Step 5.1: Health Endpoint ===")
    res_health = session.get(f"{PREVIEW_URL}/api/health", timeout=15)
    print(f"Status: {res_health.status_code}")
    data_health = res_health.json()
    print(f"Body: {json.dumps(data_health, indent=2)}")
    assert res_health.status_code == 200, f"Expected 200, got {res_health.status_code}"
    assert data_health.get("build_id") == "VERIFIED_SNAPSHOT_V2", f"Expected build_id VERIFIED_SNAPSHOT_V2, got {data_health.get('build_id')}"
    print("[PASS] /api/health returned build_id = VERIFIED_SNAPSHOT_V2")

    print("\n=== Step 5.2: Served js/ai-analysis.js ===")
    res_js = session.get(f"{PREVIEW_URL}/js/ai-analysis.js?v=verified-snapshot-v2", timeout=15)
    print(f"Status: {res_js.status_code}, Length: {len(res_js.text)}")
    assert res_js.status_code == 200
    assert "VERIFIED_SNAPSHOT_V2" in res_js.text, "VERIFIED_SNAPSHOT_V2 missing in JS"
    assert "snapshot" in res_js.text, "snapshot loading logic missing in JS"
    assert "is_legacy_analysis" in res_js.text or "legacyWarning" in res_js.text, "legacy analysis detection missing in JS"
    assert "aiFinancialCards" in res_js.text and "aiStatementsContainer" in res_js.text, "four card rendering missing in JS"
    print("[PASS] js/ai-analysis.js contains build marker, snapshot loading, legacy detection, and 4-card rendering")

    print("\n=== Step 5.3: Served ai-analysis.html ===")
    res_html = session.get(f"{PREVIEW_URL}/ai-analysis.html", timeout=15)
    print(f"Status: {res_html.status_code}, Length: {len(res_html.text)}")
    assert res_html.status_code == 200
    assert "Verified Market Data" in res_html.text, "Verified Market Data missing"
    assert "Verified Financial Statements" in res_html.text, "Verified Financial Statements missing"
    assert "Verified News" in res_html.text, "Verified News missing"
    assert "AI Investment Decision Summary" in res_html.text or "AI Decision Summary" in res_html.text, "AI Decision Summary missing"
    assert "aiLegacyWarning" in res_html.text, "Legacy warning missing"
    assert "VERIFIED_SNAPSHOT_V2" in res_html.text, "Build marker footer missing"
    print("[PASS] ai-analysis.html contains all 4 verified cards, legacy warning banner, and build footer")

    print("\n=== Step 7: Check for removed misleading strings in served frontend ===")
    for bad_str in ["Financial data hasn't been fetched for this research yet", "visit Company Research first"]:
        assert bad_str not in res_html.text, f"Found '{bad_str}' in html"
        assert bad_str not in res_js.text, f"Found '{bad_str}' in js"
    print("[PASS] Misleading strings are completely removed from deployed frontend")

if __name__ == "__main__":
    test_deployed_files()
