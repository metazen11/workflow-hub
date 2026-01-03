#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Stopping existing Workflow Hub servers...${NC}"
# Kill any process running manage.py runserver
# We use -f to match the command line
pkill -f "manage.py runserver" || echo "No running server found."

# Wait a moment for ports to free up
sleep 2

echo -e "${YELLOW}Restarting Workflow Hub...${NC}"
# Execute the standard start script
./start.sh
