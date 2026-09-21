import requests

PREVIEW_URL = "https://aashinvest-pa2ii0pf1-desksolutions.vercel.app"

# Let's test all possible emails or register users
for uid in range(1, 25):
    email = f"user_{uid}@investiq.test"
    s = requests.Session()
    res = s.post(f"{PREVIEW_URL}/api/auth/login", json={"email": email, "password": "Password123!"})
    if res.status_code == 200:
        r_res = s.get(f"{PREVIEW_URL}/api/research")
        print(f"{email}: {r_res.json().get('research')}")

# Also test common users:
for email in ["admin@investiq.app", "test@investiq.app", "user@investiq.app", "investor@investiq.com"]:
    s = requests.Session()
    res = s.post(f"{PREVIEW_URL}/api/auth/login", json={"email": email, "password": "Password123!"})
    if res.status_code == 200:
        print(f"Logged in as {email}")
        r_res = s.get(f"{PREVIEW_URL}/api/research")
        print(f"  {r_res.json().get('research')}")
