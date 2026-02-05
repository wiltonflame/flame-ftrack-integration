#!/bin/bash
# =============================================================================
# Flame-ftrack Integration - Virtual Environment Setup
# =============================================================================
#
# This script creates a virtual environment using Flame's Python and installs
# only the required dependencies (ftrack-python-api).
#
# IMPORTANT: PySide6 is NOT installed because Flame 2025+ already includes it.
#            Only ftrack-python-api is installed.
#
# This method (virtual environment) is RECOMMENDED because:
#   - Provides isolation from system Python
#   - Easier to manage and update dependencies
#   - Better for development and testing
#
# Usage:
#   chmod +x setup_environment.sh
#   ./setup_environment.sh
#
# Alternative: Use setup_simple.sh for system-wide installation
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo -e "${CYAN}=================================================="
echo "  Flame-ftrack Integration - Environment Setup"
echo -e "==================================================${NC}"
echo ""

# Step 1: Detect Flame Python
echo -e "${GREEN}[1/4] Detecting Flame Python...${NC}"
FLAME_PYTHON=""

for version in "2026" "2025.2.2" "2025.2.1" "2025.2" "2025.1" "2025" "2024.2"; do
    if [ -f "/opt/Autodesk/python/${version}/bin/python3" ]; then
        FLAME_PYTHON="/opt/Autodesk/python/${version}/bin/python3"
        echo -e "   ${GREEN}✓${NC} Found Flame Python: $FLAME_PYTHON"
        break
    fi
done

if [ -z "$FLAME_PYTHON" ]; then
    echo -e "   ${RED}✗ ERROR: Flame Python not found!${NC}"
    echo "   Please ensure Autodesk Flame 2025+ is installed."
    
    if [ -d "/opt/Autodesk/python" ]; then
        echo ""
        echo "   Available in /opt/Autodesk/python/:"
        ls /opt/Autodesk/python/ 2>/dev/null || echo "   (none)"
    fi
    exit 1
fi

echo -e "   Version: $($FLAME_PYTHON --version)"

# Step 2: Create virtual environment
echo -e "\n${GREEN}[2/4] Creating virtual environment...${NC}"

if [ -d "$VENV_DIR" ]; then
    echo -e "   ${YELLOW}⚠${NC} Existing venv found, removing..."
    rm -rf "$VENV_DIR"
fi

$FLAME_PYTHON -m venv "$VENV_DIR"
echo -e "   ${GREEN}✓${NC} Virtual environment created: $VENV_DIR"

# Step 3: Activate and upgrade pip
echo -e "\n${GREEN}[3/4] Activating environment...${NC}"
source "$VENV_DIR/bin/activate"
echo -e "   ${GREEN}✓${NC} Environment activated"

echo "   Upgrading pip..."
pip install --upgrade pip --quiet

# Step 4: Install only ftrack-python-api
echo -e "\n${GREEN}[4/4] Installing ftrack-python-api...${NC}"
pip install ftrack-python-api --quiet

if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✓${NC} ftrack-python-api installed successfully"
else
    echo -e "   ${RED}✗${NC} Installation failed!"
    exit 1
fi

# Show what's installed
echo ""
echo -e "${CYAN}Installed packages:${NC}"
pip list | grep -E "ftrack|arrow|requests"

echo ""
echo -e "${CYAN}=================================================="
echo "  ✅ Setup Complete!"
echo -e "==================================================${NC}"
echo ""
echo -e "${YELLOW}Note: PySide6 is NOT installed because Flame 2025+ already has it.${NC}"
echo ""
echo "To activate manually:"
echo -e "  ${CYAN}source $VENV_DIR/bin/activate${NC}"
echo ""
echo "Next steps:"
echo "  1. Copy presets to Flame:"
echo -e "     ${CYAN}cp presets/*.xml /opt/Autodesk/shared/export/presets/sequence_publish/${NC}"
echo ""
echo "  2. Run the demo (optional):"
echo -e "     ${CYAN}python run_demo.py${NC}"
echo ""
