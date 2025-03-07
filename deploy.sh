#!/bin/bash

# Configuration variables
SERVICE_NAME="audio-converter"  # Matches docker-compose.yml

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to log messages
log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

# Function to handle errors
error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker and try again."
fi

# Check if Docker Compose plugin is available
if ! docker compose version &> /dev/null; then
    error "Docker Compose plugin is not installed. Please install the Docker Compose plugin and try again."
fi

if ! docker info &> /dev/null; then
    error "Docker daemon is not running. Please start Docker and try again."
fi

# Step 1: Stop and remove all containers, images, volumes, and orphans
log "Stopping and cleaning up all Docker resources"
docker compose down --rmi all --volumes --remove-orphans || log "No resources found to clean up"

# Step 2: Build the updated image
log "Building updated Docker image for: $SERVICE_NAME"
docker compose build --no-cache "$SERVICE_NAME" || error "Failed to build Docker image"

# Step 3: Start the service
log "Starting service: $SERVICE_NAME"
docker compose up -d "$SERVICE_NAME" || error "Failed to start service"

# Step 4: Verify the service is running
log "Verifying service status"
sleep 2 # Give it a moment to start
if docker compose ps --services --filter "status=running" | grep -q "^${SERVICE_NAME}$"; then
    log "Service $SERVICE_NAME is running successfully"
else
    error "Service $SERVICE_NAME failed to start. Check logs with 'docker compose logs $SERVICE_NAME'"
fi

# Step 5: Test the application (optional)
log "Testing application at http://localhost:9001"
if curl -s "http://localhost:9001" > /dev/null; then
    log "Application is responding"
else
    log "Warning: Application might not be responding yet. Check with 'docker compose logs $SERVICE_NAME'"
fi

# Step 6: Clean up unused images (optional)
log "Cleaning up unused Docker images"
docker image prune -f

log "Deployment completed successfully!"