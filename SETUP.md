# InvestIQ — Steps to Run the Backend

## Prerequisites
- Python 3.10+
- A virtual environment tool (`python -m venv`)

## 1. Create & activate virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

## 2. Install dependencies
```bash
pip install -r backend/requirements.txt
```

## 3. Set up environment variables

Copy the template and fill in your own values:
```bash
copy backend\.env.example backend\.env
```

Then edit `backend/.env`:
```
FLASK_DEBUG=True
SECRET_KEY=<generate a random 32-char string>
ALPHA_VANTAGE_API_KEY=<your Alpha Vantage key from https://alphavantage.co>
GEMINI_API_KEY=<your Gemini key from https://aistudio.google.com>
```

**Production only** (set DEBUG=False):
```
SECRET_KEY=<strong random secret — never the dev default>
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

## 4. Start the backend
```bash
cd backend
python app.py
```
Backend runs at: http://127.0.0.1:5000

## 5. Start the frontend
Open a second terminal in the project root:
```bash
python -m http.server 3000
```
Frontend runs at: http://localhost:3000

## 6. Test the connection
```bash
curl http://127.0.0.1:5000/api/health
```
Expected: `{"status": "healthy", "success": true}`
