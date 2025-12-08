#!/bin/bash
# iOS Memory Leak Detector - Web UI Launcher
# Usage: ./run_web.sh [port]

PORT=${1:-5050}

echo "=============================================="
echo "  iOS Memory Leak Detector - Web UI"
echo "=============================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

# Check Flask
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing Flask..."
    pip install flask
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Starting web server on port $PORT..."
echo "Open http://localhost:$PORT in your browser"
echo ""

python3 web_app.py --port $PORT
