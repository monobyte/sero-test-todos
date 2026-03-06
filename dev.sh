#!/bin/bash

# Market Monitor Development Script
# Runs both backend and frontend in the same terminal using tmux

set -e

echo "🚀 Market Monitor Development Environment"
echo "=========================================="

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux is not installed."
    echo ""
    echo "Please install tmux:"
    echo "  Ubuntu/Debian: sudo apt install tmux"
    echo "  macOS: brew install tmux"
    echo "  Or run backend and frontend manually in separate terminals."
    exit 1
fi

# Check if session already exists
if tmux has-session -t market-monitor 2>/dev/null; then
    echo "⚠️  tmux session 'market-monitor' already exists"
    echo ""
    read -p "Do you want to kill it and start fresh? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        tmux kill-session -t market-monitor
    else
        echo "Attaching to existing session..."
        tmux attach -t market-monitor
        exit 0
    fi
fi

# Create new tmux session
echo "📦 Creating tmux session..."
tmux new-session -d -s market-monitor

# Rename first window and split it
tmux rename-window -t market-monitor:0 'market-monitor'
tmux split-window -h -t market-monitor:0

# Setup backend (left pane)
echo "🐍 Setting up backend (left pane)..."
tmux send-keys -t market-monitor:0.0 'cd backend' C-m
tmux send-keys -t market-monitor:0.0 'echo "🐍 Activating Python virtual environment..."' C-m
tmux send-keys -t market-monitor:0.0 'source venv/bin/activate || python -m venv venv && source venv/bin/activate' C-m
tmux send-keys -t market-monitor:0.0 'echo "📦 Installing dependencies..."' C-m
tmux send-keys -t market-monitor:0.0 'pip install -q -r requirements.txt' C-m
tmux send-keys -t market-monitor:0.0 'echo "✅ Backend ready!"' C-m
tmux send-keys -t market-monitor:0.0 'echo "🚀 Starting FastAPI server..."' C-m
tmux send-keys -t market-monitor:0.0 'uvicorn main:app --host 0.0.0.0 --port 8000 --reload' C-m

# Setup frontend (right pane)
echo "⚛️  Setting up frontend (right pane)..."
tmux send-keys -t market-monitor:0.1 'cd frontend' C-m
tmux send-keys -t market-monitor:0.1 'echo "⚛️  Frontend starting..."' C-m
tmux send-keys -t market-monitor:0.1 'echo "📦 Ensuring dependencies are installed..."' C-m
tmux send-keys -t market-monitor:0.1 'npm install' C-m
tmux send-keys -t market-monitor:0.1 'echo "✅ Frontend ready!"' C-m
tmux send-keys -t market-monitor:0.1 'echo "🚀 Starting Vite dev server..."' C-m
tmux send-keys -t market-monitor:0.1 'npm run dev' C-m

# Attach to the session
echo ""
echo "✅ Development environment ready!"
echo ""
echo "📝 tmux Quick Reference:"
echo "  - Switch panes: Ctrl+B then arrow keys"
echo "  - Detach: Ctrl+B then D"
echo "  - Reattach: tmux attach -t market-monitor"
echo "  - Kill session: tmux kill-session -t market-monitor"
echo ""
echo "🌐 Access Points:"
echo "  - Backend API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Frontend: http://localhost:3000 (or port shown in right pane)"
echo ""
echo "Attaching to session in 2 seconds..."
sleep 2

tmux attach -t market-monitor
