#!/bin/bash
# =============================================================================
# FLAME-FTRACK INTEGRATION - CLEAN UNINSTALL & REINSTALL
# =============================================================================

echo "=============================================="
echo "  Flame-ftrack Integration - Clean Install"
echo "=============================================="
echo ""

# Default Flame directories
FLAME_PYTHON="/opt/Autodesk/shared/python"
FLAME_HOOKS="/opt/Autodesk/shared/python"
PRESET_DIR="/opt/Autodesk/shared/export/presets/sequence_publish"

# =============================================================================
# STEP 1: STOP FLAME (if running)
# =============================================================================
echo "⚠️  IMPORTANT: Close Flame before continuing!"
echo "   Press ENTER when Flame is closed..."
read

# =============================================================================
# STEP 2: CLEAN OLD INSTALLATION
# =============================================================================
echo ""
echo "🧹 Cleaning previous installation..."

# Remove hook file
if [ -f "$FLAME_HOOKS/flame_ftrack_hook.py" ]; then
    echo "   Removing: $FLAME_HOOKS/flame_ftrack_hook.py"
    sudo rm -f "$FLAME_HOOKS/flame_ftrack_hook.py"
fi

# Remove integration folder
if [ -d "$FLAME_PYTHON/flame_ftrack_integration" ]; then
    echo "   Removing: $FLAME_PYTHON/flame_ftrack_integration"
    sudo rm -rf "$FLAME_PYTHON/flame_ftrack_integration"
fi

# Remove any symlinks
if [ -L "$FLAME_HOOKS/flame_ftrack_hook.py" ]; then
    echo "   Removing symlink: $FLAME_HOOKS/flame_ftrack_hook.py"
    sudo rm -f "$FLAME_HOOKS/flame_ftrack_hook.py"
fi

# =============================================================================
# STEP 3: CLEAN PYTHON CACHE
# =============================================================================
echo ""
echo "🧹 Cleaning Python cache..."

# Remove __pycache__ folders
sudo find "$FLAME_PYTHON" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
sudo find "$FLAME_PYTHON" -type f -name "*.pyc" -delete 2>/dev/null
sudo find "$FLAME_PYTHON" -type f -name "*.pyo" -delete 2>/dev/null

# Clean user cache
rm -rf ~/.cache/flame_ftrack 2>/dev/null
rm -rf /tmp/flame_ftrack* 2>/dev/null

echo "   Cache cleaned!"

# =============================================================================
# STEP 4: VERIFY CLEAN STATE
# =============================================================================
echo ""
echo "🔍 Verifying clean state..."

if [ -f "$FLAME_HOOKS/flame_ftrack_hook.py" ]; then
    echo "   ❌ Hook still exists!"
else
    echo "   ✅ Hook removed"
fi

if [ -d "$FLAME_PYTHON/flame_ftrack_integration" ]; then
    echo "   ❌ Folder still exists!"
else
    echo "   ✅ Folder removed"
fi

# =============================================================================
# STEP 5: INSTALL NEW VERSION
# =============================================================================
echo ""
echo "📦 Installing new version..."

# Check if ZIP exists in current directory
if [ -f "flame_ftrack_integration.zip" ]; then
    ZIP_FILE="flame_ftrack_integration.zip"
elif [ -f "$HOME/Downloads/flame_ftrack_integration.zip" ]; then
    ZIP_FILE="$HOME/Downloads/flame_ftrack_integration.zip"
else
    echo "   ❌ File flame_ftrack_integration.zip not found!"
    echo "   Place the ZIP in this directory or in ~/Downloads"
    exit 1
fi

echo "   Using: $ZIP_FILE"

# Create temp directory
TEMP_DIR=$(mktemp -d)
echo "   Extracting to: $TEMP_DIR"

# Extract
unzip -q "$ZIP_FILE" -d "$TEMP_DIR"

# Copy to Flame directory
echo "   Copying to: $FLAME_PYTHON/flame_ftrack_integration"
sudo mkdir -p "$FLAME_PYTHON/flame_ftrack_integration"
sudo cp -r "$TEMP_DIR"/* "$FLAME_PYTHON/flame_ftrack_integration/"

# Copy hook file
echo "   Copying hook to: $FLAME_HOOKS"
sudo cp "$TEMP_DIR/flame_ftrack_hook.py" "$FLAME_HOOKS/"

# Copy presets
echo "   Copying presets to: $PRESET_DIR"
sudo mkdir -p "$PRESET_DIR"
sudo cp "$TEMP_DIR/presets/"*.xml "$PRESET_DIR/" 2>/dev/null

# Set permissions
echo "   Setting permissions..."
sudo chmod -R 755 "$FLAME_PYTHON/flame_ftrack_integration"
sudo chmod 755 "$FLAME_HOOKS/flame_ftrack_hook.py"

# Cleanup
rm -rf "$TEMP_DIR"

# =============================================================================
# STEP 6: VERIFY INSTALLATION
# =============================================================================
echo ""
echo "🔍 Verifying installation..."

if [ -f "$FLAME_HOOKS/flame_ftrack_hook.py" ]; then
    echo "   ✅ Hook installed"
else
    echo "   ❌ Hook not found!"
fi

if [ -d "$FLAME_PYTHON/flame_ftrack_integration/src" ]; then
    echo "   ✅ Modules installed"
else
    echo "   ❌ Modules not found!"
fi

if [ -f "$PRESET_DIR/thumb_for_ftrack.xml" ]; then
    echo "   ✅ Thumbnail preset installed"
else
    echo "   ⚠️  Thumbnail preset not found"
fi

if [ -f "$PRESET_DIR/ftrack_video__shot_version.xml" ]; then
    echo "   ✅ Video preset installed"
else
    echo "   ⚠️  Video preset not found"
fi

# =============================================================================
# STEP 7: TEST IMPORT
# =============================================================================
echo ""
echo "🧪 Testing import..."

python3 << 'EOF'
import sys
sys.path.insert(0, '/opt/Autodesk/shared/python/flame_ftrack_integration')
sys.path.insert(0, '/opt/Autodesk/shared/python')

try:
    from src.core.ftrack_manager import FtrackManager
    print("   ✅ FtrackManager imported")
except Exception as e:
    print(f"   ❌ Error: {e}")

try:
    from src.gui.main_window import FlameFtrackWindow
    print("   ✅ GUI imported")
except Exception as e:
    print(f"   ❌ Error: {e}")
EOF

# =============================================================================
# DONE
# =============================================================================
echo ""
echo "=============================================="
echo "  ✅ Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Install dependencies:"
echo "   ./setup_environment.sh  (recommended - creates venv)"
echo "   OR"
echo "   ./setup_simple.sh  (system-wide installation)"
echo ""
echo "2. Open Flame"
echo "3. Select a sequence"
echo "4. Right-click → 'ftrack: Create Shots from Timeline'"
echo ""
echo "If you have problems, check Flame console for logs."
echo ""
