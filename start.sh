#!/bin/bash
set -euo pipefail

# Start the bgutil provider HTTP server on port 4416
node /opt/provider/server/build/main.js --port 4416 &
# Give it a moment to start
sleep 2

MODE="${BOT_RUNTIME_MODE:-polling}"
if [ "$MODE" = "webhook" ]; then
  python webhook.py
else
  python main.py
fi
