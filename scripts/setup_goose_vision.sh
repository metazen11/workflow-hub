#!/bin/bash
#
# Setup Goose Vision MCP Extension
#
# This script configures Goose to use the vision MCP server for image analysis.
# It handles .goosehints and configures the MCP extension.
#
# Run from the project root directory.
#
# Usage: ./scripts/setup_goose_vision.sh
#

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MCP_SCRIPT="$PROJECT_DIR/scripts/mcp_vision_server.py"

# Goose config location varies by OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    GOOSE_CONFIG="$HOME/.config/goose/config.yaml"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - check XDG first
    if [ -n "$XDG_CONFIG_HOME" ]; then
        GOOSE_CONFIG="$XDG_CONFIG_HOME/goose/config.yaml"
    else
        GOOSE_CONFIG="$HOME/.config/goose/config.yaml"
    fi
else
    # Windows/other
    GOOSE_CONFIG="$HOME/.config/goose/config.yaml"
fi

echo -e "${BLUE}Setting up Goose Vision MCP Extension...${NC}"
echo ""

# Check if Goose is installed
if ! command -v goose &> /dev/null; then
    echo -e "${YELLOW}Warning: Goose CLI not found. Install from: https://github.com/block/goose${NC}"
    echo "The configuration will still be created for when Goose is installed."
    echo ""
fi

# Check if MCP script exists
if [ ! -f "$MCP_SCRIPT" ]; then
    echo -e "${YELLOW}Error: MCP vision server not found at $MCP_SCRIPT${NC}"
    exit 1
fi

# Make MCP script executable
chmod +x "$MCP_SCRIPT"
echo -e "  ${GREEN}✓${NC} Made mcp_vision_server.py executable"

# Create Goose config directory if needed
mkdir -p "$(dirname "$GOOSE_CONFIG")"

# Create or update Goose config
if [ -f "$GOOSE_CONFIG" ]; then
    # Check if vision extension already exists
    if grep -q "vision:" "$GOOSE_CONFIG"; then
        echo -e "  ${GREEN}✓${NC} Vision extension already configured in Goose config"
    else
        # Append vision extension to existing config
        cat >> "$GOOSE_CONFIG" << EOF
  vision:
    enabled: true
    name: vision
    type: stdio
    cmd: python3
    args:
      - $MCP_SCRIPT
      - --mcp
EOF
        echo -e "  ${GREEN}✓${NC} Added vision extension to existing Goose config"
    fi
else
    # Create new config
    cat > "$GOOSE_CONFIG" << EOF
GOOSE_PROVIDER: ollama
OLLAMA_HOST: http://localhost:12434/engines/llama.cpp
GOOSE_MODEL: ai/qwen3-coder:latest
extensions:
  developer:
    enabled: true
    name: developer
    type: builtin
  memory:
    enabled: true
    name: memory
    type: builtin
  vision:
    enabled: true
    name: vision
    type: stdio
    cmd: python3
    args:
      - $MCP_SCRIPT
      - --mcp
EOF
    echo -e "  ${GREEN}✓${NC} Created Goose config with vision extension"
fi

# Test vision server
echo ""
echo -e "${BLUE}Testing vision server...${NC}"

# Simple test: ensure the script runs without errors
if python3 "$MCP_SCRIPT" --help 2>&1 | grep -q "MCP Vision Server"; then
    echo -e "  ${GREEN}✓${NC} Vision server script is functional"
else
    echo -e "  ${GREEN}✓${NC} Vision server loaded (testing import...)"
    python3 -c "from scripts.mcp_vision_server import preprocess_prompt; print('  ✓ Import successful')" 2>/dev/null || \
        echo -e "  ${YELLOW}!${NC} Could not import vision server (run from project root)"
fi

# Test Docker Model Runner
echo ""
echo -e "${BLUE}Checking Docker Model Runner...${NC}"

if curl -s http://localhost:12434/engines/v1/models &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} Docker Model Runner is running"

    # Check for vision model
    if docker model ls 2>/dev/null | grep -q "qwen3-vl"; then
        echo -e "  ${GREEN}✓${NC} Vision model (qwen3-vl) is available"
    else
        echo -e "  ${YELLOW}!${NC} Vision model not found. Pull with: docker model pull ai/qwen3-vl"
    fi
else
    echo -e "  ${YELLOW}!${NC} Docker Model Runner not available at localhost:12434"
    echo "  Enable it in Docker Desktop settings > Features in development > Docker Model Runner"
fi

echo ""

# Step: Verify .goosehints exists in project
echo -e "${BLUE}Checking .goosehints...${NC}"

GOOSEHINTS="$PROJECT_DIR/.goosehints"
if [ -f "$GOOSEHINTS" ]; then
    echo -e "  ${GREEN}✓${NC} .goosehints exists in project"
else
    # Create .goosehints if missing
    cat > "$GOOSEHINTS" << 'EOF'
# Goose Hints for Workflow Hub

## Vision/Image Analysis

When a user message or task description contains file paths to images (.png, .jpg, .jpeg, .gif, .webp):

1. Use the `analyze_image` tool to get a description of the image
2. Or use `preprocess_prompt` tool to automatically augment the prompt with image descriptions

Image paths look like:
- /absolute/path/to/image.png
- ./relative/path/to/screenshot.jpg
- ~/home/path/to/diagram.webp

The vision extension provides these tools:
- `analyze_image`: Analyze a single image file
- `analyze_images_in_text`: Find and analyze all images in text
- `preprocess_prompt`: Augment a prompt with image descriptions (recommended)
- `extract_image_paths`: Just extract paths without analyzing

## Workflow Hub Context

This is an agentic development workflow manager. Key concepts:
- Tasks go through pipeline stages: PM -> DEV -> QA -> SEC -> DOCS -> COMPLETE
- Runs are executions of the pipeline for a task
- Each stage has an agent that processes the handoff

## Project Structure

- `app/` - Django application (models, views, services)
- `scripts/` - Agent runners and utilities
- `tests/` - Test files
- `_spec/` - Specifications and handoffs

## Agent Report Format

When completing work, output a JSON report:
```json
{
  "status": "pass" or "fail",
  "summary": "Brief description of work done",
  "details": { "relevant": "data" }
}
```
EOF
    echo -e "  ${GREEN}✓${NC} Created .goosehints"
fi

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Configuration files:"
echo "  Goose config:  $GOOSE_CONFIG"
echo "  MCP script:    $MCP_SCRIPT"
echo "  Goose hints:   $GOOSEHINTS"
echo ""
echo "To test the vision extension with Goose:"
echo -e "  ${BLUE}cd $PROJECT_DIR${NC}"
echo -e "  ${BLUE}goose session --text 'Analyze /path/to/screenshot.png'${NC}"
echo ""
echo "Note: When running goose from the project directory, it will read"
echo "the .goosehints file automatically for context about the project."
echo ""
