#!/bin/bash
# Start the bgutil provider HTTP server on port 4416
node /opt/provider/server/build/main.js --port 4416 &
# Give it a moment to start
sleep 2
# Run your bot
python main.py
