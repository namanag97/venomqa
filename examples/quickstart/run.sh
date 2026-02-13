#!/bin/bash
# VenomQA Quickstart - One Command Runner
#
# This script starts the sample API and runs VenomQA tests.
# Usage: ./run.sh [options]
#
# Options:
#   --build     Force rebuild of Docker images
#   --clean     Clean up after tests
#   --debug     Run tests in debug mode
#   --watch     Run tests in watch mode
#   -h, --help  Show this help message

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default options
BUILD=false
CLEAN=false
DEBUG=false
WATCH=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --watch)
            WATCH=true
            shift
            ;;
        -h|--help)
            echo "VenomQA Quickstart Runner"
            echo ""
            echo "Usage: ./run.sh [options]"
            echo ""
            echo "Options:"
            echo "  --build     Force rebuild of Docker images"
            echo "  --clean     Clean up after tests"
            echo "  --debug     Run tests in debug mode"
            echo "  --watch     Run tests in watch mode"
            echo "  -h, --help  Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  VenomQA Quickstart${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found. Please install Docker.${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Docker daemon not running. Please start Docker.${NC}"
    exit 1
fi

if ! command -v venomqa &> /dev/null; then
    echo -e "${YELLOW}VenomQA not found. Installing...${NC}"
    pip install venomqa || {
        echo -e "${RED}Failed to install VenomQA${NC}"
        exit 1
    }
fi

echo -e "${GREEN}Prerequisites OK${NC}"
echo ""

# Start services
echo -e "${YELLOW}Starting services...${NC}"

if [ "$BUILD" = true ]; then
    docker compose up -d --build
else
    docker compose up -d
fi

# Wait for API to be healthy
echo -e "${YELLOW}Waiting for API to be ready...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}API is ready!${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}API failed to start. Check logs with: docker compose logs api${NC}"
    exit 1
fi

echo ""

# Run VenomQA tests
echo -e "${YELLOW}Running VenomQA tests...${NC}"
echo ""

cd qa

VENOMQA_ARGS=""
if [ "$DEBUG" = true ]; then
    VENOMQA_ARGS="--debug"
fi

if [ "$WATCH" = true ]; then
    venomqa watch $VENOMQA_ARGS
else
    venomqa run $VENOMQA_ARGS
fi

EXIT_CODE=$?

cd ..

# Cleanup if requested
if [ "$CLEAN" = true ]; then
    echo ""
    echo -e "${YELLOW}Cleaning up...${NC}"
    docker compose down -v
    echo -e "${GREEN}Cleanup complete${NC}"
fi

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Some tests failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE
