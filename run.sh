#!/bin/bash

# RL Gym Harness Startup Script
# This script starts both the backend and frontend services

set -e

echo "🚀 Starting RL Gym Harness Application"

# Check if we're in the right directory
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "   Expected structure:"
    echo "   - backend/ (FastAPI application)"
    echo "   - frontend/ (React application)"
    exit 1
fi

# Function to start backend
start_backend() {
    echo "🔧 Starting Backend Services..."
    cd backend
    
    # Check if .env file exists
    if [ ! -f .env ]; then
        echo "⚠️  .env file not found in backend/. Creating from template..."
        cat > .env << EOF
# API Keys
ANTHROPIC_API_KEY=sk-ant-api03-Your-API-Key-Here
OPENAI_API_KEY=sk-Your-OpenAI-API-Key-Here

# Database
DATABASE_URL=${DATABASE_URL:-postgresql://app_user:password@localhost:5432/harness_main_aws}

# Redis
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
CELERY_BROKER_URL=${CELERY_BROKER_URL:-redis://localhost:6379/0}
CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-redis://localhost:6379/0}

# Application Settings
DEBUG=true
HOST=0.0.0.0
PORT=8000

# Task Execution Settings
CUA_URL=http://localhost:8080
STREAMLIT_URL=http://localhost:8501
MAX_WAIT_TIME=180
CHECK_INTERVAL=2
MAX_RETRIES=3
RETRY_DELAY=2

# Browser Settings
BROWSER_WIDTH=1920
BROWSER_HEIGHT=1080

# Results Directory
RESULTS_DIR=results

# Task CSV File
TASKS_CSV_PATH=tasks/production_tasks.csv
EOF
        echo "✅ Created backend/.env file. Please update with your actual API keys."
    fi
    
    # Start backend using the existing script
    ./run_fastapi.sh &
    BACKEND_PID=$!
    echo "✅ Backend started with PID: $BACKEND_PID"
    
    cd ..
}

# Function to start frontend
start_frontend() {
    echo "🎨 Starting Frontend Services..."
    cd frontend
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing frontend dependencies..."
        npm install
    fi
    
    # Start frontend
    npm run dev &
    FRONTEND_PID=$!
    echo "✅ Frontend started with PID: $FRONTEND_PID"
    
    cd ..
}

# Function to cleanup on exit
cleanup() {
    echo "🛑 Shutting down services..."
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    echo "✅ Services stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start services
start_backend
sleep 5  # Give backend time to start
start_frontend

echo ""
echo "🎉 RL Gym Harness is now running!"
echo ""
echo "📱 Frontend: http://localhost:8503"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo "❤️  Health Check: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for services
wait
