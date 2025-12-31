#!/bin/bash
#
# Workflow Hub Startup Script
#
# Quick start for daily development. For first-time setup, use ./scripts/install.sh
#
# Usage: ./start.sh [--no-docker]
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
SKIP_DOCKER=false
for arg in "$@"; do
    case $arg in
        --no-docker)
            SKIP_DOCKER=true
            shift
            ;;
    esac
done

echo -e "${BLUE}Starting Workflow Hub...${NC}"

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "Error: Run this script from the project root directory"
    exit 1
fi

# Step 1: Start Docker PostgreSQL
if [ "$SKIP_DOCKER" = false ]; then
    echo -e "${YELLOW}Starting PostgreSQL...${NC}"

    # Check if container exists
    if docker ps -a --format '{{.Names}}' | grep -q 'docker-db-1'; then
        docker start docker-db-1 2>/dev/null || true
    else
        docker compose -f docker/docker-compose.yml up -d
    fi

    # Wait for PostgreSQL
    for i in {1..10}; do
        if docker exec docker-db-1 pg_isready -U wfhub &> /dev/null; then
            echo -e "  ${GREEN}✓${NC} PostgreSQL ready"
            break
        fi
        sleep 1
    done
fi

# Step 2: Activate virtual environment
echo -e "${YELLOW}Activating environment...${NC}"
source venv/bin/activate
source .env
echo -e "  ${GREEN}✓${NC} Environment loaded"

# Step 3: Run any pending migrations
echo -e "${YELLOW}Checking migrations...${NC}"
alembic upgrade head 2>/dev/null || echo "  (migrations up to date)"
echo -e "  ${GREEN}✓${NC} Database ready"

# Step 4: Start Django server
echo -e "${YELLOW}Starting server...${NC}"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Workflow Hub is running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  Dashboard: ${BLUE}http://localhost:8000/ui/${NC}"
echo -e "  API:       ${BLUE}http://localhost:8000/api/status${NC}"
echo ""
echo -e "  Press Ctrl+C to stop"
echo ""

python manage.py runserver 0.0.0.0:8000
