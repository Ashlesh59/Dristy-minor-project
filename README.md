# 📈 InvestIQ — Equity Research & Analysis Platform

InvestIQ is a full-stack investment research and analysis web application designed for analyzing exchange-listed equities with structured market data, verified end-of-day (EOD) prices, corporate action adjustments, and Google Gemini-assisted equity analysis reports.

---

## 🧭 What InvestIQ Does

* **NSE Listed Company Master & Search:** Fast, local fuzzy search across 2,500+ NSE equity securities without third-party network dependencies.
* **Verified Market Data & Price History:** Ingestion and visualization of NSE UDiFF Common Bhavcopy end-of-day (EOD) pricing data with support for both unadjusted and split-adjusted historical views.
* **Corporate Actions Adjustments:** Idempotent processing of NSE stock splits and bonus issues to calculate reliable adjusted historical time-series.
* **Gemini-Assisted Equity Synthesis:** Structured AI analysis generating executive summaries, risk breakdowns, and investment rationale from verified company and market data.
* **Investment Reports & Persistence:** Printable and exportable equity research dossiers linked to user sessions with full report history.
* **Session-Based Authentication:** Secure user signup, login, session validation, and protected routes.

---

## 💻 Technology Stack

* **Backend:** Python 3.10+, Flask 3.0, Flask-SQLAlchemy 3.1, SQLite, Werkzeug security, Google GenAI SDK.
* **Frontend:** Vanilla HTML5, CSS3 (Custom Design System, Glassmorphism, Responsive), Vanilla ES6+ JavaScript.
* **Testing:** Isolated Python `unittest` suite (102 backend tests) + Node.js test runner (21 frontend tests).

---

## ⚡ Setup & Quick Start

### 1. First-Time Setup

**On Windows:**
Double-click `setup.bat` (or run in CMD / PowerShell):
```cmd
setup.bat
```
This will:
1. Create a Python virtual environment (`.venv`).
2. Install all dependencies from `backend/requirements.txt`.
3. Create `backend/.env` from template if it does not already exist.
4. Automatically import NSE master equities if `data/raw/nse/EQUITY_L.csv` is present.

**On Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
```

---

### 2. Environment Variables Configuration

Edit `backend/.env` to configure your settings:
```env
# Flask Configuration
FLASK_DEBUG=True
SECRET_KEY=generate_a_random_32_char_secret_key

# External Services (Optional / Fallback)
ALPHA_VANTAGE_API_KEY=YOUR_ALPHA_VANTAGE_KEY_HERE
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

* **Google Gemini API Key:** Required for AI-assisted research synthesis. Get a free API key at [Google AI Studio](https://aistudio.google.com/).
* **Alpha Vantage API Key:** Optional fallback provider. Get a free API key at [Alpha Vantage](https://www.alphavantage.co/support/#api-key).

---

### 3. Normal Startup

**On Windows (1-Click Launcher):**
```cmd
run.bat
```
`run.bat` verifies your environment, starts both the Flask backend (port 5000) and frontend static server (port 3000), polls `/api/health` until ready, and launches your browser at `http://localhost:3000`.

**Manual Startup:**
```bash
# Terminal 1 — Backend Server
cd backend
python app.py

# Terminal 2 — Frontend Server (from project root)
python -m http.server 3000
```
Open [http://localhost:3000](http://localhost:3000) in your web browser.

---

## 📊 Data Ingestion & Importers

### 1. NSE Listed Equities Importer
To import or synchronize the official NSE company and security master database:
```bash
python -m backend.cli.sync_companies --source nse --file data/raw/nse/EQUITY_L.csv
```
* Supports `--dry-run` to preview changes without committing.
* 100% idempotent: Re-importing identical files produces zero duplicates.

### 2. Market Data Bhavcopy Importer
To import official NSE CM-UDiFF Bhavcopy daily price files:
```bash
python -m backend.cli.import_market_data --source nse_cm_udiff --file data/raw/nse/bhavcopy/cm_udiff_sample.csv
```

### 3. Corporate Actions Importer & Adjustments
To import corporate actions and calculate split-adjusted historical prices:
```bash
python -m backend.cli.import_corporate_actions --source nse --file data/raw/nse/actions.csv
python -m backend.cli.run_adjustments --security-id <ID>
```

---

## 🧪 Automated Testing

All backend tests enforce **strict database isolation** and never touch the active development database.

**Run Backend Test Suite:**
```powershell
# Windows PowerShell:
.\scripts\test_backend.ps1

# Linux / macOS:
./scripts/test_backend.sh
```

**Run Frontend Unit Tests:**
```bash
node --test tests/*.test.js
```

---

## 📋 Manual Verification Checklist

1. **Authentication:** Register a new user at `/signup.html`, verify session cookie, log in at `/login.html`, check protected routes redirect when logged out.
2. **Local Search:** Navigate to `/company-research.html`, search for `RELIANCE` or `TCS`, select a security, and click create research.
3. **Market Data & Chart:** Verify that price quotes and charts display verified end-of-day data with explicit timestamp labels.
4. **AI Synthesis:** Trigger Gemini analysis and confirm structured JSON summary, risk assessment, and score render without crashing.
5. **Report Generation:** Open the full investment report, verify printer stylesheet (`Ctrl+P`), and check that saved reports reopen at `/saved-reports.html`.

---

## ⚠️ Important Statements & Known Limitations

* **End-of-Day (EOD) Data Only:** InvestIQ operates on verified daily settlement prices and end-of-day data. It does **not** provide sub-second real-time tick streaming or live orderbook feeds.
* **Alpha Vantage Rate Limits:** Free-tier Alpha Vantage keys are subject to strict rate limits (25 requests/day). InvestIQ prioritizes stored local NSE Bhavcopy data.
* **Gemini Model Availability:** AI analysis requires a valid `GEMINI_API_KEY` with internet access. In the event of an API quota limit or connectivity error, the application displays an explicit error message rather than generating hallucinations.
* **Educational Disclaimer:** InvestIQ is an educational and analytical research platform. It does not provide financial advisory services, guaranteed returns, or automated trading execution. All investments carry risk.