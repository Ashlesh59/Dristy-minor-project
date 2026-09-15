# InvestIQ Manual Testing Guide

This guide provides step-by-step instructions for running the InvestIQ development servers, verifying API endpoints, testing user authentication flows, synchronizing exchange equity master datasets, and confirming database safety.

---

## 1. Starting the Servers

### A. Start the Backend Server
From the repository root, open a terminal:
```powershell
cd backend
..\venv\Scripts\python.exe app.py
```
*(On Linux/macOS: `cd backend && ../venv/bin/python app.py`)*

- The backend binds to `0.0.0.0:5000` and is accessible at `http://127.0.0.1:5000` or `http://localhost:5000`.

### B. Start the Frontend Server
Open a second terminal at the repository root:
```powershell
.\venv\Scripts\python.exe -m http.server 3000
```
*(On Linux/macOS: `python3 -m http.server 3000`)*

- The frontend is accessible in your browser at `http://localhost:3000`.

---

## 2. Health & System Monitoring Verification

1. Open your browser and navigate to:
   ```text
   http://localhost:5000/api/health
   ```
2. Verify the JSON response contains:
   ```json
   {
     "database": "connected",
     "environment": "development",
     "services": {
       "alpha_vantage": true,
       "gemini": true
     },
     "status": "healthy",
     "success": true
   }
   ```

---

## 3. Manual Authentication Testing (Signup, Login, Logout)

### Step 1: Open Developer Tools
- In your browser (Chrome/Edge/Firefox), press `F12` or right-click and select **Inspect**.
- Switch to the **Network** and **Application** (or **Storage**) tabs.

### Step 2: Test User Signup
1. Navigate to `http://localhost:3000/signup.html`.
2. Enter:
   - **Full Name**: `Test User`
   - **Email**: `testuser@example.com`
   - **Password**: `Password123!`
3. Click **Create Account**.
4. In DevTools **Network** tab, inspect `POST /api/auth/signup` (Status `201 Created`).

### Step 3: Test User Login
1. Navigate to `http://localhost:3000/login.html`.
2. Enter email and password -> Click **Sign In**.
3. In DevTools: `POST /api/auth/login` returns `200 OK` and a `session` cookie is created.
4. Redirects to `dashboard.html`.

### Step 4: Test User Profile Verification (`/api/auth/me`)
1. Fetch `http://localhost:5000/api/auth/me` -> Returns `200 OK` with user profile.

### Step 5: Test User Logout
1. Click **Log Out** on `dashboard.html`.
2. Inspect `POST /api/auth/logout` (`200 OK`) and confirm session invalidation.

---

## 4. Phase 1A: Exchange Master Data Sync Testing

### Step 1: Dry-Run Import (Synthetic Test Fixture)
From the repository root:
```powershell
.\venv\Scripts\python.exe -m backend.cli.sync_companies --source nse --file backend/tests/fixtures/synthetic_nse_equities.csv --dry-run
```
- Verify: Reports inserted companies/securities without modifying the database.

### Step 2: Live Import (Synthetic Test Fixture)
```powershell
.\venv\Scripts\python.exe -m backend.cli.sync_companies --source nse --file backend/tests/fixtures/synthetic_nse_equities.csv
```
- Verify: Inserts 4 companies and 5 securities, logs 1 skipped row.

### Step 3: Idempotent Re-Import
```powershell
.\venv\Scripts\python.exe -m backend.cli.sync_companies --source nse --file backend/tests/fixtures/synthetic_nse_equities.csv
```
- Verify: `0 inserted`, `0 updated`, `5 unchanged`.

### Step 4: Optional Production Ingestion (Real NSE Dataset)
To ingest the complete downloaded NSE equities file:
```powershell
.\venv\Scripts\python.exe -m backend.cli.sync_companies --source nse --file data/raw/nse/EQUITY_L.csv
```

---

## 5. Phase 2B: Stored Market Data & Historical Charts Testing

### Step 1: Ingest Bhavcopy Fixture or Directory
```powershell
# Ingest single UDiFF ZIP fixture
.\venv\Scripts\python.exe -m backend.cli.sync_market_data --source nse-udiff --file backend/tests/fixtures/synthetic_nse_udiff_bhavcopy.zip

# Or ingest complete Bhavcopy directory
.\venv\Scripts\python.exe -m backend.cli.sync_market_data --source nse-udiff --directory data/raw/nse/bhavcopy
```

### Step 2: Login and Search Company
1. Open `http://localhost:3000/login.html` and sign in.
2. Navigate to `http://localhost:3000/company-research.html`.
3. Type `RELIANCE` into the search box and select **Reliance Industries Limited (RELIANCE · NSE · EQ)** from the dropdown.
4. Click **Start Research**.

### Step 3: Verify EOD Quote Card
1. Inspect the Quote display:
   - **Company Name & Symbol:** "Reliance Industries Limited (RELIANCE · NSE · EQ)".
   - **Badges:** Confirms `End-of-day data`, `Unadjusted prices`, and `NSE CM-UDiFF`.
   - **Latest Close:** Matches stored `close_price`.
   - **Trading Date:** Matches the stored session date (NOT the current system date).
   - **Daily Change:** Confirms calculated absolute change and percentage.

### Step 4: Verify Historical Price Chart & Range Controls
1. Inspect the native SVG price chart rendered below the quote card.
2. Click through range buttons: **1M**, **3M**, **6M**, **1Y**, **3Y**, **5Y**, **MAX**.
3. Verify:
   - Active button styling updates immediately.
   - Chart updates dynamically.
   - Screen-reader data table below the chart reflects the price points.
   - No flickering or out-of-order race conditions when clicking rapidly.

### Step 5: Test Empty and Edge States
1. Search and select a newly added security with no imported Bhavcopy data (e.g. `INFY`).
2. Click **Start Research**.
3. Confirm that the UI displays an honest empty state:
   - *"No end-of-day market data is currently stored for this security."*
   - No fake or fallback prices are shown.
   - Chart displays an honest empty state message.

### Step 6: Verify Network Traffic in DevTools
1. Open DevTools **Network** tab (`F12`).
2. Filter by `Fetch/XHR`.
3. Confirm that ONLY local endpoints (`/api/securities/<id>/market-data/latest`, `/api/securities/<id>/market-data/history`) are called.
4. Confirm **ZERO** requests to `alphavantage.co`, `twelvedata.com`, `googleapis.com`, or external servers.

---

## 6. Phase 2C: Corporate Actions & Split Adjustment Testing

### Step 1: Ingest Corporate Actions CSV
```powershell
# Dry-run
.\venv\Scripts\python.exe -m backend.cli.sync_corporate_actions --source nse --file backend/tests/fixtures/synthetic_nse_corporate_actions.csv --dry-run

# Live Ingestion
.\venv\Scripts\python.exe -m backend.cli.sync_corporate_actions --source nse --file backend/tests/fixtures/synthetic_nse_corporate_actions.csv
```

### Step 2: Rebuild Historical Adjusted Prices
```powershell
# Rebuild all securities
.\venv\Scripts\python.exe -m backend.cli.rebuild_adjusted_prices --all --version split_bonus_v1
```

### Step 3: Verify Price Mode Controls on Company Research
1. Open `http://localhost:3000/company-research.html`.
2. Search and select **Reliance Industries Limited (RELIANCE)**.
3. Click **Start Research**.
4. Click the **Split/Bonus Adjusted** toggle button above the price chart.
5. Verify:
   - Button styling highlights active mode.
   - Historical chart updates immediately to plot split-adjusted prices.
   - Pre-split historical prices do not display artificial crashes.
   - Disclaimer banner states: *"Adjusted for stock splits and bonus issues. Cash dividends and rights issues are excluded. (1 corporate action applied)"*.
6. Switch back to **Raw** mode and verify nominal exchange prices restore.

---

## 7. Verifying Database Integrity & Isolation

Run the automated test launcher from repository root:
```powershell
.\scripts\test_backend.ps1
```
- Verifies SHA-256 hash before and after tests are identical.
- Runs all frontend test suites:
  ```powershell
  node --test tests/*.test.js
  ```
- Confirms `data/raw/**` is ignored by Git:
  ```powershell
  git status
  ```


