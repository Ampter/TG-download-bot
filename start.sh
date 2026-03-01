#!/bin/bash
set -euo pipefail

# Start the bgutil provider HTTP server on port 4416
node /opt/provider/server/build/main.js --port 4416 &
# Give it a moment to start
sleep 5

# Install the package in editable mode to handle imports correctly
pip install -e .

MODE="${BOT_RUNTIME_MODE:-polling}"
if [ "$MODE" = "webhook" ]; then
  python -m src.webhook
else
  python -m src.main
fi
