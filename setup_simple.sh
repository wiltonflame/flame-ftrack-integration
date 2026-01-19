#!/bin/bash
# =============================================================================
# Flame-ftrack Integration - Simple System-wide Setup
# =============================================================================
# 
# This script installs ftrack-python-api directly to Flame's shared Python
# directory (/opt/Autodesk/shared/python).
#
# IMPORTANT: PySide6 is NOT installed because Flame 2025+ already includes it.
#            Only ftrack-python-api is installed.
#
# This method (system-wide) is useful for:
#   - Production deployments
#   - Shared installations across multiple users
#   - Simpler setup without virtual environments
#
# Usage:
#   chmod +x setup_simple.sh
#   ./setup_simple.sh
#
# Note: May require sudo permissions to write to /opt/Autodesk/shared/python
#
# Alternative: Use setup_environment.sh for virtual environment (recommended)
# =============================================================================

set -e

echo "=================================================="
echo "  Flame-ftrack Integration - Simple Setup"
echo "=================================================="
echo ""

# Detect Flame Python
FLAME_PYTHON=""
for version in "2026" "2025.2.2" "2025.2.1" "2025.2" "2025.1" "2025" "2024.2"; do
    if [ -f "/opt/Autodesk/python/${version}/bin/python3" ]; then
        FLAME_PYTHON="/opt/Autodesk/python/${version}/bin/python3"
        break
    fi
done

if [ -z "$FLAME_PYTHON" ]; then
    echo "❌ ERROR: Flame Python not found!"
    echo "   Please ensure Flame 2025+ is installed."
    exit 1
fi

echo "✓ Found Flame Python: $FLAME_PYTHON"
$FLAME_PYTHON --version
echo ""

# Install ftrack-python-api to shared location
SHARED_PYTHON="/opt/Autodesk/shared/python"
echo "Installing ftrack-python-api to: $SHARED_PYTHON"
echo ""

# Check if we have write permission
if [ ! -w "$SHARED_PYTHON" ]; then
    echo "⚠️  Need sudo to write to $SHARED_PYTHON"
    sudo $FLAME_PYTHON -m pip install ftrack-python-api --target "$SHARED_PYTHON" --upgrade
else
    $FLAME_PYTHON -m pip install ftrack-python-api --target "$SHARED_PYTHON" --upgrade
fi

echo ""
echo "=================================================="
echo "  ✅ Setup Complete!"
echo "=================================================="
echo ""
echo "ftrack-python-api installed to: $SHARED_PYTHON"
echo ""
echo "Next steps:"
echo "  1. Copy flame_ftrack_hook.py to /opt/Autodesk/shared/python/"
echo "  2. Copy presets/*.xml to /opt/Autodesk/shared/export/presets/sequence_publish/"
echo "  3. Restart Flame"
echo ""
