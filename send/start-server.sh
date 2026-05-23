#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

: "${POWERSTREAM_API_TOKEN:?Set POWERSTREAM_API_TOKEN}"
: "${POWERSTREAM_DEVICE_SN:?Set POWERSTREAM_DEVICE_SN}"

UVICORN_HOST="${UVICORN_HOST:-0.0.0.0}"
UVICORN_PORT="${UVICORN_PORT:-3600}"

python3 -m uvicorn server:app --host "$UVICORN_HOST" --port "$UVICORN_PORT"
