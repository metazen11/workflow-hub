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
SKIP_FRONTEND=false
for arg in "$@"; do
    case $arg in
        --no-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --no-frontend)
            SKIP_FRONTEND=true
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

    # Start only db + postgrest (app container would conflict with local Django)
    docker compose -f docker/docker-compose.yml up -d db postgrest

    # Wait for PostgreSQL
    for i in {1..10}; do
        if docker exec wfhub-db pg_isready -U wfhub &> /dev/null; then
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
echo -e "  Dashboard:  ${BLUE}http://localhost:8000/ui/${NC}"
echo -e "  API:        ${BLUE}http://localhost:8000/api/status${NC}"
echo -e "  Queue:      ${BLUE}http://localhost:8000/api/queue/status${NC}"
echo ""
echo -e "  ${YELLOW}Note:${NC} Director daemon auto-starts if enabled in database"
echo -e "        Check director_settings.enabled or /ui/settings/"
echo ""
echo -e "  Press Ctrl+C to stop"
echo ""

# Step 5: Start pipeline editor (Next.js)
if [ "$SKIP_FRONTEND" = false ]; then
    if command -v npm &> /dev/null; then
        echo -e "${YELLOW}Starting Pipeline Editor (Next.js)...${NC}"
        rm -rf pipeline-editor/.next
        HOST=127.0.0.1 npm --prefix pipeline-editor run dev -- -H 127.0.0.1 -p 3001 > /tmp/pipeline-editor.log 2>&1 &
        FRONTEND_PID=$!
        echo -e "  ${GREEN}✓${NC} Pipeline Editor running (PID ${FRONTEND_PID})"
        echo -e "  Editor:   ${BLUE}http://localhost:3001/${NC}"
        echo -e "  Logs:     /tmp/pipeline-editor.log"
        trap "kill ${FRONTEND_PID} 2>/dev/null || true" EXIT
    else
        echo -e "${YELLOW}Warning:${NC} npm not found; skipping Pipeline Editor"
    fi
fi

python manage.py runserver 0.0.0.0:8000
