import requests

PREVIEW_URL = "https://aashinvest-pa2ii0pf1-desksolutions.vercel.app"

def inspect():
    # Let's test known user emails from past runs
    emails = [
        "test_diagnose@investiq.app",
        "ash@gmail.com",
        "mvp_test_user_2026@investiq.test",
        "demo@investiq.com",
        "analyst_v2@investiq.test"
    ]
    for email in emails:
        session = requests.Session()
        res = session.post(f"{PREVIEW_URL}/api/auth/login", json={"email": email, "password": "Password123!"})
        if res.status_code == 200:
            user = res.json().get("user", {})
            print(f"Logged in as {email} (id: {user.get('id')})")
            res_r = session.get(f"{PREVIEW_URL}/api/research")
            if res_r.status_code == 200:
                recs = res_r.json().get("research", [])
                print(f"  Research records for {email}: {[ (r.get('id'), r.get('ticker_symbol')) for r in recs ]}")
                for r in recs:
                    if r.get('id') == 16 or r.get('ticker_symbol') == 'TITAN':
                        print(f"  --> Found TITAN or 16: ID {r.get('id')} ({r.get('ticker_symbol')})")
        else:
            print(f"Failed to log in as {email} ({res.status_code})")

if __name__ == "__main__":
    inspect()
