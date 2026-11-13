#!/usr/bin/env bash
# AccessGuard Launcher for Linux & macOS
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================================="
echo "  🛡️  Starting AccessGuard Unified Access Governance Lab...       "
echo "=================================================================="

# 1. Start PostgreSQL
if command -v docker &> /dev/null; then
    docker compose up -d
fi

# 2. Check virtual environment
if [ ! -d "backend/.venv" ]; then
    python3 -m venv backend/.venv
    ./backend/.venv/bin/pip install -r backend/requirements.txt
fi

if [ ! -f "backend/.env" ]; then
    cp backend/.env.example backend/.env
fi

# 3. Database migrations & seed
./backend/.venv/bin/python backend/check_db.py || true
./backend/.venv/bin/python -m alembic -c backend/alembic.ini upgrade head || true
./backend/.venv/bin/python backend/seed_demo.py || true

# 4. Launch services in background
echo "Launching Core Backend API on http://127.0.0.1:8000..."
(cd backend && ./backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload) &

echo "Launching Dialog Final ML Service on http://127.0.0.1:8001..."
(cd backend && ./backend/.venv/bin/uvicorn mock_ml_service:app --host 127.0.0.1 --port 8001 --reload) &

echo "Launching Dialog Access Log API on http://127.0.0.1:8002..."
(cd accesslog-main && ../backend/.venv/bin/python standalone_api.py) &

echo "Launching React Frontend on http://127.0.0.1:5173..."
(cd frontend && npm run dev) &

echo ""
echo "=================================================================="
echo "  All services started! Dashboard: http://127.0.0.1:5173         "
echo "=================================================================="

