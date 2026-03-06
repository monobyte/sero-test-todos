#!/bin/bash
# Startup script for Market Monitor Backend

# Exit on error
set -e

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env and add your API keys before running the server."
    exit 1
fi

# Start server
echo "Starting FastAPI server..."
echo "API: http://0.0.0.0:8000"
echo "Docs: http://0.0.0.0:8000/docs"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
