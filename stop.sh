#!/usr/bin/env bash
# AccessGuard Stop Script for Linux & macOS
echo "Stopping AccessGuard ecosystem services on ports 8000, 8001, 8002, 5173..."
for PORT in 8000 8001 8002 5173; do
    PID=$(lsof -ti :$PORT || true)
    if [ -n "$PID" ]; then
        echo "Killing process on port $PORT (PID: $PID)..."
        kill -9 $PID 2>/dev/null || true
    fi
done
echo "All services stopped."

