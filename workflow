#!/bin/bash
# Workflow CLI - Run tasks through the full agent pipeline
# Usage: ./workflow "Add delete button to todo app"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate" 2>/dev/null

python "$SCRIPT_DIR/scripts/workflow.py" "$@"
