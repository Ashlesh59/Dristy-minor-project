#!/bin/bash
echo "===================================================="
echo "              Starting InvestIQ...                 "
echo "===================================================="
echo ""

if ! command -v python3 &> /dev/null
then
    echo "[ERROR] python3 could not be found. Please install Python 3.10+."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
fi

echo "[2/4] Installing dependencies..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r backend/requirements.txt

if [ ! -f "backend/.env" ]; then
    echo "[NOTICE] backend/.env not found. Creating from .env.example..."
    cp backend/.env.example backend/.env
fi

echo "[3/4] Starting backend server on port 5000..."
(cd backend && python3 app.py) &
BACKEND_PID=$!

echo "[4/4] Starting frontend server on port 3000..."
python3 -m http.server 3000 &
FRONTEND_PID=$!

sleep 2
echo "Opening http://localhost:3000 in your browser..."
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000
elif command -v open &> /dev/null; then
    open http://localhost:3000
fi

echo "===================================================="
echo " InvestIQ is running! Press Ctrl+C to stop both servers."
echo "===================================================="

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
