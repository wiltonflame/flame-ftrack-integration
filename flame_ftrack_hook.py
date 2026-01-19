"""
Flame ftrack Integration Hook

This file should be copied to the Flame hooks directory:
  - Linux: /opt/Autodesk/shared/python/ (global)
  - Linux: ~/.flame/python/ (per user)
  
Or add the project path to PYTHONPATH before starting Flame.

Minimum version: Flame 2022
"""

import os
import sys
import glob

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

def _get_project_dir():
    """
    Auto-detect the project directory.
    
    Priority:
    1. FLAME_FTRACK_DIR environment variable
    2. Directory where this hook file is located (if it contains src/)
    3. ~/flame_ftrack_integration (default)
    """
    # Method 1: Environment variable (most explicit)
    env_dir = os.environ.get('FLAME_FTRACK_DIR')
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    
    # Method 2: Same directory as this hook file
    hook_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(os.path.join(hook_dir, 'src')):
        return hook_dir
    
    # Method 3: Default location
    default_dir = os.path.expanduser("~/flame_ftrack_integration")
    return default_dir

# Get project directory
PROJECT_DIR = _get_project_dir()

# Add project directory to path (at the BEGINNING to take priority)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
    print(f"[ftrack] Project dir: {PROJECT_DIR}")

# =============================================================================
# DETECT AND ADD VENV TO PATH
# =============================================================================

def _setup_venv():
    """
    Detect and add virtual environment to sys.path
    
    This is necessary because Flame uses its own internal Python
    and doesn't see packages installed in venv automatically.
    
    CRITICAL: We insert at position 0 to ensure venv packages
    take priority over any system packages.
    """
    venv_paths = [
        os.path.join(PROJECT_DIR, ".venv"),
        os.path.join(PROJECT_DIR, "venv"),
        os.path.join(PROJECT_DIR, "env"),
    ]
    
    for venv_dir in venv_paths:
        if os.path.exists(venv_dir):
            # Find site-packages
            # Linux: .venv/lib/python3.X/site-packages
            site_packages_pattern = os.path.join(venv_dir, "lib", "python*", "site-packages")
            site_packages_dirs = glob.glob(site_packages_pattern)
            
            if site_packages_dirs:
                site_packages = site_packages_dirs[0]
                
                # IMPORTANT: Insert at position 0 to take priority over system packages
                # This ensures we use the venv's ftrack_api, not any global one
                if site_packages in sys.path:
                    sys.path.remove(site_packages)
                sys.path.insert(0, site_packages)
                
                print(f"[ftrack] ✓ Venv loaded: {site_packages}")
                
                # Also add the venv's bin to PATH for any subprocess calls
                venv_bin = os.path.join(venv_dir, "bin")
                if venv_bin not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = venv_bin + ':' + os.environ.get('PATH', '')
                
                return True
            
            # Windows: .venv/Lib/site-packages
            win_site_packages = os.path.join(venv_dir, "Lib", "site-packages")
            if os.path.exists(win_site_packages):
                if win_site_packages in sys.path:
                    sys.path.remove(win_site_packages)
                sys.path.insert(0, win_site_packages)
                print(f"[ftrack] ✓ Venv loaded: {win_site_packages}")
                return True
    
    print(f"[ftrack] ⚠ No venv found in {PROJECT_DIR}")
    return False

# Execute venv setup BEFORE importing ftrack_api
_venv_found = _setup_venv()

# =============================================================================
# VERIFY FTRACK API
# =============================================================================

# Force reimport to ensure we get the venv version
if 'ftrack_api' in sys.modules:
    del sys.modules['ftrack_api']

# Check if ftrack_api is available
try:
    import ftrack_api
    _ftrack_available = True
    
    # Show where ftrack_api is loaded from
    ftrack_location = getattr(ftrack_api, '__file__', 'unknown')
    print(f"[ftrack] ✓ ftrack_api loaded from: {ftrack_location}")
    
except ImportError as e:
    _ftrack_available = False
    print(f"[ftrack] ✗ ftrack_api NOT FOUND: {e}")
    print(f"[ftrack] sys.path[0:3]: {sys.path[:3]}")
    
    if not _venv_found:
        print("[ftrack] ")
        print("[ftrack] To fix, run in terminal:")
        print(f"[ftrack]   cd {PROJECT_DIR}")
        print("[ftrack]   ./setup_environment.sh")
        print("[ftrack] ")


# =============================================================================
# SCOPE FUNCTIONS
# =============================================================================

def scope_sequence(selection):
    """Check if selection contains sequences"""
    try:
        import flame
        for item in selection:
            if isinstance(item, flame.PySequence):
                return True
    except ImportError:
        pass
    return False


def scope_clip(selection):
    """Check if selection contains clips"""
    try:
        import flame
        for item in selection:
            if isinstance(item, (flame.PyClip, flame.PySequence)):
                return True
    except ImportError:
        pass
    return False


def scope_clip_or_sequence(selection):
    """Check if selection contains clips or sequences (for publish review)"""
    try:
        import flame
        for item in selection:
            if isinstance(item, (flame.PyClip, flame.PySequence)):
                return True
    except ImportError:
        pass
    return False


# =============================================================================
# WINDOW MANAGEMENT
# =============================================================================

# Global reference to keep window alive
_ftrack_window = None
_time_tracker_window = None
_publish_review_window = None


def _close_existing_window():
    """Close existing window if open"""
    global _ftrack_window
    if _ftrack_window is not None:
        try:
            _ftrack_window.close()
        except:
            pass
        _ftrack_window = None


# =============================================================================
# MAIN ACTIONS
# =============================================================================

def _launch_ftrack_integration(selection):
    """Launch main ftrack integration window"""
    global _ftrack_window
    
    _close_existing_window()
    
    try:
        from src.gui.main_window import FlameFtrackWindow
        
        _ftrack_window = FlameFtrackWindow(
            flame_selection=selection,
            use_mock=not _ftrack_available
        )
        _ftrack_window.show()
        
    except Exception as e:
        print(f"[ftrack] ERROR launching window: {e}")
        import traceback
        traceback.print_exc()
        
        # Show error dialog
        try:
            from PySide6 import QtWidgets
            QtWidgets.QMessageBox.critical(
                None,
                "ftrack Integration Error",
                f"Could not launch ftrack integration:\n\n{str(e)}\n\n"
                "Check if the integration is correctly installed."
            )
        except:
            pass


def _launch_credentials(selection):
    """Launch credentials configuration dialog"""
    try:
        from src.config.credentials_manager import show_credentials_dialog
        show_credentials_dialog()
    except Exception as e:
        print(f"[ftrack] ERROR opening credentials: {e}")


def _launch_demo(selection):
    """Launch in demo mode without Flame selection"""
    global _ftrack_window
    
    _close_existing_window()
    
    try:
        from src.gui.main_window import FlameFtrackWindow
        
        _ftrack_window = FlameFtrackWindow(
            flame_selection=None,
            use_mock=True
        )
        _ftrack_window.show()
        
        # Load demo data
        _ftrack_window.shot_table.load_demo_data()
        
    except Exception as e:
        print(f"[ftrack] ERROR launching demo: {e}")


def _launch_time_tracker(selection):
    """Launch Time Tracker window"""
    global _time_tracker_window
    
    try:
        from src.gui.time_tracker import TimeTrackerWindow
        from src.core.ftrack_manager import FtrackManager
        
        # Create or get existing ftrack manager
        ftrack = FtrackManager()
        
        # Try to connect with saved credentials
        try:
            from src.config.credentials_manager import get_credentials, credentials_are_configured
            
            if credentials_are_configured():
                creds = get_credentials()
                ftrack.connect(
                    server_url=creds['server'],
                    api_user=creds['api_user'],
                    api_key=creds['api_key']
                )
        except Exception as e:
            print(f"[ftrack] Time tracker: Could not auto-connect: {e}")
        
        # Create or show existing window
        if _time_tracker_window is None:
            _time_tracker_window = TimeTrackerWindow(ftrack_manager=ftrack)
        else:
            # Update ftrack manager if needed
            _time_tracker_window.ftrack = ftrack
            _time_tracker_window._load_my_tasks()
        
        _time_tracker_window.show()
        _time_tracker_window.raise_()
        _time_tracker_window.activateWindow()
        
    except Exception as e:
        print(f"[ftrack] ERROR launching time tracker: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            from PySide6 import QtWidgets
            QtWidgets.QMessageBox.critical(
                None,
                "Time Tracker Error",
                f"Could not launch Time Tracker:\n\n{str(e)}"
            )
        except:
            pass


def _launch_publish_review(selection):
    """Launch publish review dialog for uploading versions to ftrack"""
    global _publish_review_window
    
    # Close existing window if open
    if _publish_review_window is not None:
        try:
            _publish_review_window.close()
        except:
            pass
        _publish_review_window = None
    
    try:
        from src.gui.publish_review import PublishReviewDialog
        from src.core.ftrack_manager import FtrackManager
        from src.config.credentials_manager import get_credentials, credentials_are_configured
        
        # Create and connect ftrack manager
        ftrack = FtrackManager()
        
        if credentials_are_configured():
            creds = get_credentials()
            success, msg = ftrack.connect(
                server_url=creds['server'],
                api_user=creds['api_user'],
                api_key=creds['api_key']
            )
            if success:
                print(f"[ftrack] Publish Review: Connected to ftrack")
            else:
                print(f"[ftrack] Publish Review: Connection warning: {msg}")
        
        # Create dialog with selection
        _publish_review_window = PublishReviewDialog(
            ftrack_manager=ftrack,
            flame_selection=selection
        )
        _publish_review_window.show()
        
    except Exception as e:
        print(f"[ftrack] ERROR launching Publish Review: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            from PySide6 import QtWidgets
            QtWidgets.QMessageBox.critical(
                None,
                "Publish Review Error",
                f"Could not launch Publish Review:\n\n{str(e)}"
            )
        except:
            pass


# =============================================================================
# FLAME MENU - MEDIA PANEL
# =============================================================================

def get_media_panel_custom_ui_actions():
    """
    Define custom UI actions for Media Panel context menu
    
    Appears when right-clicking on sequences in Media Panel.
    """
    return [
        {
            "name": "ftrack Integration",
            "actions": [
                {
                    "name": "🚀 Create Shots in ftrack...",
                    "execute": _launch_ftrack_integration,
                    "isEnabled": scope_sequence,
                    "waitCursor": False,
                },
                {
                    "name": "📤 Publish Review to ftrack...",
                    "execute": _launch_publish_review,
                    "isEnabled": scope_clip_or_sequence,
                    "waitCursor": False,
                },
                {
                    "name": "⏱️ Time Tracker",
                    "execute": _launch_time_tracker,
                    "waitCursor": False,
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "🔑 Configure Credentials...",
                    "execute": _launch_credentials,
                    "waitCursor": False,
                },
                {
                    "name": "📋 Demo Mode",
                    "execute": _launch_demo,
                    "waitCursor": False,
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "ℹ️ About",
                    "execute": _show_about,
                    "waitCursor": False,
                },
            ]
        }
    ]


# =============================================================================
# FLAME MENU - MAIN MENU
# =============================================================================

def get_main_menu_custom_ui_actions():
    """
    Define custom UI actions for main menu
    
    Appears in Flame's main menu bar.
    """
    return [
        {
            "name": "ftrack",
            "actions": [
                {
                    "name": "🚀 Create Shots from Selection...",
                    "execute": _launch_ftrack_integration,
                    "isEnabled": scope_sequence,
                    "waitCursor": False,
                },
                {
                    "name": "📤 Publish Review to ftrack...",
                    "execute": _launch_publish_review,
                    "isEnabled": scope_clip_or_sequence,
                    "waitCursor": False,
                },
                {
                    "name": "⏱️ Time Tracker",
                    "execute": _launch_time_tracker,
                    "waitCursor": False,
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "🔑 Configure Credentials...",
                    "execute": _launch_credentials,
                    "waitCursor": False,
                },
                {
                    "name": "📋 Demo Mode (No Selection)",
                    "execute": _launch_demo,
                    "waitCursor": False,
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "ℹ️ About",
                    "execute": _show_about,
                    "waitCursor": False,
                },
            ]
        }
    ]


def _show_about(selection):
    """Show plugin information"""
    from PySide6 import QtWidgets, QtCore, QtGui
    
    # Create custom dialog
    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle("About Flame → ftrack Integration")
    dialog.setFixedSize(420, 380)
    dialog.setStyleSheet("""
        QDialog {
            background-color: #313131;
        }
        QLabel {
            color: #d9d9d9;
        }
        QPushButton {
            background-color: #4a6fa5;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 20px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #5a8fcf;
        }
    """)
    
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(30, 30, 30, 30)
    layout.setSpacing(15)
    
    # Logo/Title
    title = QtWidgets.QLabel()
    title.setTextFormat(QtCore.Qt.TextFormat.RichText)
    title.setText("""
        <div style="text-align: center;">
            <span style="font-size: 48px;">🔥</span><br>
            <span style="font-size: 22px; font-weight: bold; color: #ff6b35;">Flame → ftrack</span><br>
            <span style="font-size: 16px; color: #9a9a9a;">Integration Tool</span>
        </div>
    """)
    title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    
    # Version
    version = QtWidgets.QLabel()
    version.setTextFormat(QtCore.Qt.TextFormat.RichText)
    version.setText('<p style="text-align: center; color: #7a7a7a;">Version 1.0.0</p>')
    version.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(version)
    
    # Separator
    line1 = QtWidgets.QFrame()
    line1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line1.setStyleSheet("background-color: #4a4a4a;")
    layout.addWidget(line1)
    
    # Description
    desc = QtWidgets.QLabel()
    desc.setTextFormat(QtCore.Qt.TextFormat.RichText)
    desc.setWordWrap(True)
    desc.setText("""
        <p style="color: #b9b9b9; line-height: 1.6; text-align: center;">
        Seamless integration between <b>Autodesk Flame</b> and <b>ftrack</b> 
        for efficient VFX pipeline management.
        </p>
    """)
    layout.addWidget(desc)
    
    layout.addStretch()
    
    # Separator
    line2 = QtWidgets.QFrame()
    line2.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line2.setStyleSheet("background-color: #4a4a4a;")
    layout.addWidget(line2)
    
    # Credits
    credits = QtWidgets.QLabel()
    credits.setTextFormat(QtCore.Qt.TextFormat.RichText)
    credits.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    credits.setText("""
        <p style="color: #9a9a9a; font-size: 12px;">
            Developed by<br>
            <span style="color: #ff6b35; font-size: 14px; font-weight: bold;">Wilton Matos</span><br>
            <span style="color: #7a7a7a; font-size: 11px;">Flame Artist | Pipeline TD</span>
        </p>
        <p style="color: #5a5a5a; font-size: 10px; margin-top: 10px;">
            © 2025
        </p>
    """)
    layout.addWidget(credits)
    
    # OK Button
    btn_layout = QtWidgets.QHBoxLayout()
    btn_layout.addStretch()
    ok_btn = QtWidgets.QPushButton("OK")
    ok_btn.setFixedWidth(100)
    ok_btn.clicked.connect(dialog.accept)
    btn_layout.addWidget(ok_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)
    
    dialog.exec()


# =============================================================================
# FLAME MENU - BATCH
# =============================================================================

def get_batch_custom_ui_actions():
    """
    Define custom UI actions for Batch context menu
    
    Appears when right-clicking on clips/nodes in Batch.
    """
    return [
        {
            "name": "ftrack Integration",
            "actions": [
                {
                    "name": "📤 Publish Review to ftrack...",
                    "execute": _launch_publish_review,
                    "minimumVersion": "2022",
                },
                {
                    "name": "⏱️ Time Tracker",
                    "execute": _launch_time_tracker,
                    "minimumVersion": "2022",
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "🔑 Configure Credentials...",
                    "execute": _launch_credentials,
                    "minimumVersion": "2022",
                },
            ]
        }
    ]


# =============================================================================
# FLAME MENU - TIMELINE (Desktop)
# =============================================================================

def get_timeline_custom_ui_actions():
    """
    Define custom UI actions for Timeline context menu
    
    Appears when right-clicking on segments in Timeline.
    """
    return [
        {
            "name": "ftrack Integration",
            "actions": [
                {
                    "name": "📤 Publish Review to ftrack...",
                    "execute": _launch_publish_review,
                    "minimumVersion": "2022",
                },
                {
                    "name": "⏱️ Time Tracker",
                    "execute": _launch_time_tracker,
                    "minimumVersion": "2022",
                },
                {
                    "name": "---",  # Separator
                },
                {
                    "name": "🔑 Configure Credentials...",
                    "execute": _launch_credentials,
                    "minimumVersion": "2022",
                },
            ]
        }
    ]


# Minimum Flame version
get_media_panel_custom_ui_actions.minimum_version = "2022"
get_batch_custom_ui_actions.minimum_version = "2022"
get_timeline_custom_ui_actions.minimum_version = "2022"
get_main_menu_custom_ui_actions.minimum_version = "2022"
