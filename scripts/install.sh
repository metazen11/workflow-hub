#!/bin/bash
#
# Workflow Hub Installation Script
#
# This script sets up a local development environment for Workflow Hub.
# Run from the project root directory.
#
# Usage: ./scripts/install.sh [--skip-models] [--skip-docker]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_MODELS=false
SKIP_DOCKER=false

for arg in "$@"; do
    case $arg in
        --skip-models)
            SKIP_MODELS=true
            shift
            ;;
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Workflow Hub Installation Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo -e "${RED}Error: Run this script from the project root directory${NC}"
    echo "Usage: ./scripts/install.sh"
    exit 1
fi

# Step 1: Check prerequisites
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION"
else
    echo -e "  ${RED}✗${NC} Python 3 not found. Please install Python 3.9+"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>&1 | awk '{print $3}' | tr -d ',')
    echo -e "  ${GREEN}✓${NC} Docker $DOCKER_VERSION"
else
    echo -e "  ${RED}✗${NC} Docker not found. Please install Docker Desktop"
    exit 1
fi

# Check Docker Compose
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>&1)
    echo -e "  ${GREEN}✓${NC} Docker Compose $COMPOSE_VERSION"
else
    echo -e "  ${RED}✗${NC} Docker Compose not found"
    exit 1
fi

# Check Goose (optional)
if command -v goose &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Goose CLI found"
else
    echo -e "  ${YELLOW}!${NC} Goose CLI not found (optional - needed for agent execution)"
fi

echo ""

# Step 2: Create virtual environment
echo -e "${YELLOW}Step 2: Setting up Python virtual environment...${NC}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "  ${GREEN}✓${NC} Created virtual environment"
else
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
fi

# Activate venv
source venv/bin/activate
echo -e "  ${GREEN}✓${NC} Activated virtual environment"

# Upgrade pip
pip install --upgrade pip -q
echo -e "  ${GREEN}✓${NC} Upgraded pip"

echo ""

# Step 3: Install Python dependencies
echo -e "${YELLOW}Step 3: Installing Python dependencies...${NC}"

pip install -r requirements.txt -q
echo -e "  ${GREEN}✓${NC} Installed requirements.txt"

# Install Playwright browsers
if python -c "import playwright" 2>/dev/null; then
    playwright install chromium --quiet 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Installed Playwright browsers"
fi

echo ""

# Step 4: Configure environment
echo -e "${YELLOW}Step 4: Configuring environment...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${GREEN}✓${NC} Created .env from .env.example"
        echo -e "  ${YELLOW}!${NC} Please review .env and update settings as needed"
    else
        # Create minimal .env
        cat > .env << 'EOF'
# Database
POSTGRES_USER=wfhub
POSTGRES_PASSWORD=wfhub
POSTGRES_DB=wfhub
DATABASE_URL=postgresql://wfhub:wfhub@localhost:5432/wfhub

# Django
DJANGO_SECRET_KEY=change-me-in-production
DEBUG=True

# Workflow Hub
WORKFLOW_HUB_URL=http://localhost:8000
AUTO_TRIGGER_AGENTS=true

# LLM Configuration (Docker Model Runner)
GOOSE_PROVIDER=ollama
OLLAMA_HOST=http://localhost:12434/engines/llama.cpp
GOOSE_MODEL=ai/qwen3-coder:latest
VISION_MODEL=ai/qwen3-vl

# Timeouts
LLM_TIMEOUT=600
EOF
        echo -e "  ${GREEN}✓${NC} Created default .env file"
        echo -e "  ${YELLOW}!${NC} Please review .env and update settings as needed"
    fi
else
    echo -e "  ${GREEN}✓${NC} .env already exists"
fi

echo ""

# Step 5: Start Docker services
if [ "$SKIP_DOCKER" = false ]; then
    echo -e "${YELLOW}Step 5: Starting Docker services...${NC}"

    # Start PostgreSQL
    docker compose -f docker/docker-compose.yml up -d
    echo -e "  ${GREEN}✓${NC} Started PostgreSQL container"

    # Wait for PostgreSQL to be ready
    echo -e "  Waiting for PostgreSQL to be ready..."
    sleep 3

    # Check if PostgreSQL is accepting connections
    for i in {1..10}; do
        if docker exec docker-db-1 pg_isready -U wfhub &> /dev/null; then
            echo -e "  ${GREEN}✓${NC} PostgreSQL is ready"
            break
        fi
        if [ $i -eq 10 ]; then
            echo -e "  ${YELLOW}!${NC} PostgreSQL may still be starting..."
        fi
        sleep 1
    done
else
    echo -e "${YELLOW}Step 5: Skipping Docker services (--skip-docker)${NC}"
fi

echo ""

# Step 6: Run database migrations
echo -e "${YELLOW}Step 6: Running database migrations...${NC}"

source .env
alembic upgrade head
echo -e "  ${GREEN}✓${NC} Applied Alembic migrations"

echo ""

# Step 7: Seed role configurations
echo -e "${YELLOW}Step 7: Seeding role configurations...${NC}"

python scripts/seed_role_configs.py
echo -e "  ${GREEN}✓${NC} Seeded agent role configs"

echo ""

# Step 8: Pull LLM models
if [ "$SKIP_MODELS" = false ]; then
    echo -e "${YELLOW}Step 8: Pulling LLM models (this may take a while)...${NC}"

    # Check if Docker Model Runner is available
    if curl -s http://localhost:12434/engines/v1/models &> /dev/null; then
        echo -e "  Docker Model Runner detected"

        # Pull qwen3-coder
        echo -e "  Pulling ai/qwen3-coder (code generation)..."
        docker model pull ai/qwen3-coder 2>/dev/null && \
            echo -e "  ${GREEN}✓${NC} Pulled ai/qwen3-coder" || \
            echo -e "  ${YELLOW}!${NC} Could not pull ai/qwen3-coder (pull manually)"

        # Pull qwen3-vl
        echo -e "  Pulling ai/qwen3-vl (vision/screenshots)..."
        docker model pull ai/qwen3-vl 2>/dev/null && \
            echo -e "  ${GREEN}✓${NC} Pulled ai/qwen3-vl" || \
            echo -e "  ${YELLOW}!${NC} Could not pull ai/qwen3-vl (pull manually)"

        # Configure context sizes for large prompts
        echo -e "  Configuring model context sizes..."
        docker model configure --context-size=500000 ai/qwen3-coder 2>/dev/null && \
            echo -e "  ${GREEN}✓${NC} Set ai/qwen3-coder context to 500k tokens" || \
            echo -e "  ${YELLOW}!${NC} Could not configure ai/qwen3-coder context size"
        docker model configure --context-size=30000 ai/qwen3-vl 2>/dev/null && \
            echo -e "  ${GREEN}✓${NC} Set ai/qwen3-vl context to 30k tokens" || \
            echo -e "  ${YELLOW}!${NC} Could not configure ai/qwen3-vl context size"
    else
        echo -e "  ${YELLOW}!${NC} Docker Model Runner not available at localhost:12434"
        echo -e "  ${YELLOW}!${NC} Enable it in Docker Desktop settings or pull models manually:"
        echo -e "      docker model pull ai/qwen3-coder"
        echo -e "      docker model pull ai/qwen3-vl"
    fi
else
    echo -e "${YELLOW}Step 8: Skipping model download (--skip-models)${NC}"
fi

echo ""

# Step 9: Create necessary directories
echo -e "${YELLOW}Step 9: Creating directories...${NC}"

mkdir -p workspaces
mkdir -p .cache/image_descriptions
echo -e "  ${GREEN}✓${NC} Created workspaces/ and .cache/ directories"

echo ""

# Done!
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "To start the server:"
echo -e "  ${BLUE}source venv/bin/activate${NC}"
echo -e "  ${BLUE}source .env${NC}"
echo -e "  ${BLUE}python manage.py runserver 0.0.0.0:8000${NC}"
echo ""
echo -e "Then open: ${BLUE}http://localhost:8000/ui/${NC}"
echo ""
echo -e "For more information, see:"
echo -e "  - README.md"
echo -e "  - docs/DOCKER_MODEL_RUNNER.md"
echo -e "  - docs/OFFLINE_SETUP.md"
echo ""
