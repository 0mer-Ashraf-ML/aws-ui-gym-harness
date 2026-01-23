#!/bin/bash

# FastAPI RL Gym Harness Startup Script
# This script sets up and starts the FastAPI application with proper database and Redis configuration

set -e

echo "🚀 Starting FastAPI RL Gym Harness Application"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
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
    echo "✅ Created .env file. Please update with your actual API keys."
fi

# Create necessary directories
mkdir -p logs results backups

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "🐳 Running in Docker container"
    
    # Wait for database to be ready
    echo "⏳ Waiting for database to be ready..."
    until pg_isready -h postgres -p 5432 -U postgres; do
        echo "Database is unavailable - sleeping"
        sleep 2
    done
    echo "✅ Database is ready"
    
    # Wait for Redis to be ready
    echo "⏳ Waiting for Redis to be ready..."
    until redis-cli -h redis ping; do
        echo "Redis is unavailable - sleeping"
        sleep 2
    done
    echo "✅ Redis is ready"
    
    # Run database migrations
    echo "🔄 Running database migrations..."
    alembic upgrade head
    
    # Start the application
    echo "🚀 Starting FastAPI application..."
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    
else
    echo "💻 Running locally"
    
    # Check if virtual environment exists
    if [ ! -d "env" ]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv env
    fi
    
    # Activate virtual environment
    echo "🔧 Activating virtual environment..."
    source env/bin/activate
    
    # Install dependencies
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
    
    # Install Playwright browsers
    echo "🌐 Installing Playwright browsers..."
    playwright install chromium
    
    # Check if PostgreSQL is running
    if ! pg_isready -h localhost -p 5432 -U postgres > /dev/null 2>&1; then
        echo "⚠️  PostgreSQL is not running. Please start PostgreSQL first."
        echo "   On macOS: brew services start postgresql"
        echo "   On Ubuntu: sudo systemctl start postgresql"
        exit 1
    fi
    
    # Setup database and user (if not exists)
    echo "🔧 Setting up database and user..."
    psql -U postgres -c "CREATE USER app_user WITH PASSWORD 'password';" 2>/dev/null || echo "User app_user already exists"
    psql -U postgres -c "CREATE DATABASE harness_main_aws OWNER app_user;" 2>/dev/null || echo "Database harness_main_aws already exists"
    psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE harness_main_aws TO app_user;" 2>/dev/null || echo "Privileges already granted"
    
    # Check if Redis is running
    if ! redis-cli ping > /dev/null 2>&1; then
        echo "⚠️  Redis is not running. Please start Redis first."
        echo "   On macOS: brew services start redis"
        echo "   On Ubuntu: sudo systemctl start redis"
        exit 1
    fi
    
    # Run database migrations
    echo "🔄 Running database migrations..."
    alembic upgrade head
    
    # Start the application
    echo "🚀 Starting FastAPI application..."
    echo "📝 Note: To start the Celery worker for background tasks, run:"
    echo "   celery -A app.celery_app worker --loglevel=info --concurrency=2 --queues=celery,task_execution,monitoring,cleanup"
    echo ""
    echo "🌐 API will be available at:"
    echo "   - API Documentation: http://localhost:8000/docs"
    echo "   - Health Check: http://localhost:8000/health"
    echo "   - OpenAPI Schema: http://localhost:8000/openapi.json"
    echo ""
    python -m app.main
fi
