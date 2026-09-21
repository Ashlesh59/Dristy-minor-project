import requests

PREVIEW_URL = "https://aashinvest-pa2ii0pf1-desksolutions.vercel.app"

session = requests.Session()
session.post(f"{PREVIEW_URL}/api/auth/login", json={"email": "test_diagnose@investiq.app", "password": "Password123!"})

# Search TITAN
res = session.get(f"{PREVIEW_URL}/api/companies/search?q=TITAN")
titan_sec = res.json()["results"][0]
print("TITAN security:", titan_sec)

# Create research
res_create = session.post(f"{PREVIEW_URL}/api/research", json={"security_id": titan_sec["security_id"]})
print("Create research status:", res_create.status_code, res_create.json())
