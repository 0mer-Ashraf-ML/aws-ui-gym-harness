#!/bin/bash

# RL Gym Harness - Docker Image Preparation Script
# This script builds and exports Docker images for client delivery

set -e

echo "🚀 Preparing Docker images for client delivery..."

# Create images directory if it doesn't exist
mkdir -p images

# Build custom images
echo "📦 Building FastAPI backend image..."
docker build -t rl-gym-harness-fastapi:latest ../backend

echo "📦 Building React frontend image..."
docker build -t rl-gym-harness-frontend:latest ../frontend

# Export custom images to tar files
echo "💾 Exporting custom images..."
docker save rl-gym-harness-fastapi:latest | gzip > images/rl-gym-harness-fastapi.tar.gz
docker save rl-gym-harness-frontend:latest | gzip > images/rl-gym-harness-frontend.tar.gz

echo "✅ All images have been prepared and saved to the images/ directory"
echo ""
echo "📋 Image files created:"
echo "  - rl-gym-harness-fastapi.tar.gz"
echo "  - rl-gym-harness-frontend.tar.gz"
echo ""
echo "🎯 Ready for client delivery!"
