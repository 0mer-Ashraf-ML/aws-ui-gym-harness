#!/bin/bash

# Script to update iteration step counts from conversation history
# This is a ONE-TIME script to backfill total_steps for existing iterations
# Works with both docker-compose.yml (local) and docker-compose.server.yml (server)

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Update Iteration Steps from Conversation History              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "This script will:"
echo "  1. Read conversation history files from results directory"
echo "  2. Extract step counts (computer_call + tool_use)"
echo "  3. Update total_steps in the database"
echo ""
echo "NOTE: This is a ONE-TIME operation. Run this only once!"
echo ""

# Auto-detect FastAPI container name (works for both local and server setups)
echo "🔍 Detecting FastAPI container..."
CONTAINER_NAME=$(docker ps --format '{{.Names}}' | grep -E '(fastapi-app|fastapi_app)' | head -n 1)

if [ -z "$CONTAINER_NAME" ]; then
    echo "❌ Error: FastAPI container is not running!"
    echo "   Please start the container first:"
    echo "   - Local: docker compose up -d"
    echo "   - Server: docker compose -f docker-compose.server.yml up -d"
    exit 1
fi

echo "✅ Found FastAPI container: $CONTAINER_NAME"
echo ""

# Copy the Python script into the container
echo "📦 Copying script to container..."
docker exec "$CONTAINER_NAME" mkdir -p /app/scripts
docker cp backend/scripts/update_iteration_steps.py "$CONTAINER_NAME":/app/scripts/update_iteration_steps.py

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to copy script to container"
    exit 1
fi

echo "✅ Script copied successfully"
echo ""

# Run the Python script inside the Docker container
echo "Running update script inside Docker container..."
echo ""

docker exec -it "$CONTAINER_NAME" python /app/scripts/update_iteration_steps.py

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Done! Check the summary above for results.                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"

