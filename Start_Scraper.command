#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Social Media Scraper Server..."

# Ensure port 8000 is free (kill existing process if any)
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start the server in the background
python3 server.py &
SERVER_PID=$!

# Wait a moment for the server to initialize
sleep 2

# Open the UI in the default browser
open http://localhost:8000

echo "=================================================="
echo "Server is running at http://localhost:8000"
echo "DO NOT close this terminal window until you are done scraping!"
echo "Press Ctrl+C to stop the server."
echo "=================================================="

# Wait for the server process to keep the terminal open
wait $SERVER_PID
