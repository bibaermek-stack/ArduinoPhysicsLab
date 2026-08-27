#!/bin/sh
set -eu
PORT="${PORT:-8000}"
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"
echo "Arduino Physics Lab API starting host=0.0.0.0 port=${PORT}"
exec python -m uvicorn server.app.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers --forwarded-allow-ips='*'
