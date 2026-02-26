#!/bin/bash
set -euo pipefail

# Start the bgutil provider HTTP server on port 4416
node /opt/provider/server/build/main.js --port 4416 &
# Give it a moment to start
sleep 5

export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"

MODE="${BOT_RUNTIME_MODE:-polling}"
if [ "$MODE" = "webhook" ]; then
  python src/webhook.py
else
  python src/main.py
fi
