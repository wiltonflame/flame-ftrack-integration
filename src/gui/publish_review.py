"""
Publish Review Dialog - Upload shot versions to ftrack

Provides a simple interface for artists to:
1. Select a clip/sequence in Flame
2. Choose a task (from their in-progress tasks)
3. Add a comment/note
4. Export and upload to ftrack as a reviewable version

The workflow is designed to be quick and efficient for daily reviews.
"""

import os
import logging
import tempfile
import time
import glob
from typing import Dict, List, Optional, Callable
from datetime import datetime

from PySide6 import QtWidgets, QtCore, QtGui

from .styles import FLAME_STYLE

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Get project directory (same as flame_ftrack_hook.py)
def _get_project_dir():
    """Get the project directory"""
    import os
    # Try environment variable
    env_dir = os.environ.get('FLAME_FTRACK_DIR')
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    # Try relative to this file
    this_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(this_dir))
    if os.path.isdir(os.path.join(project_dir, 'presets')):
        return project_dir
    # Default
    return os.path.expanduser("~/flame_ftrack_integration")

PROJECT_DIR = _get_project_dir()

# Export settings for review videos
DEFAULT_VIDEO_PRESET = os.path.join(PROJECT_DIR, "presets", "ftrack_video__shot_version.xml")
DEFAULT_EXPORT_DIR = os.path.expanduser("~/flame_review_exports")


# =============================================================================
# PUBLISH REVIEW DIALOG
# =============================================================================

class PublishReviewDialog(QtWidgets.QDialog):
    """
    Dialog for publishing shot reviews to ftrack
    
    Features:
    - Shows only user's in-progress tasks
    - Grouped by project for easy navigation
    - Comment field for version notes
    - Progress feedback during export and upload
    """
    
    # Signals
    publish_complete = QtCore.Signal(bool, str)  # success, message
    
    def __init__(self, ftrack_manager, flame_selection=None, parent=None):
        super().__init__(parent)
        
        self.ftrack = ftrack_manager
        self.flame_selection = flame_selection
        self.selected_task = None
        self._tasks_data = []
        
        self.setWindowTitle("📤 Publish Review to ftrack")
        self.setMinimumSize(550, 600)
        self.setStyleSheet(FLAME_STYLE)
        
        self._setup_ui()
        self._load_tasks()
        self._update_selection_info()
    
    def _setup_ui(self):
        """Build the dialog UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # =====================================================================
        # HEADER
        # =====================================================================
        header = QtWidgets.QLabel()
        header.setTextFormat(QtCore.Qt.TextFormat.RichText)
        header.setText("""
            <div style="text-align: center;">
                <span style="font-size: 18px; font-weight: bold; color: #d9d9d9;">
                    📤 Publish Review
                </span><br>
                <span style="color: #7a7a7a; font-size: 12px;">
                    Export and upload to ftrack for review
                </span>
            </div>
        """)
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # =====================================================================
        # SELECTION INFO
        # =====================================================================
        self.selection_frame = QtWidgets.QFrame()
        self.selection_frame.setStyleSheet("""
            QFrame {
                background-color: #2a3a4a;
                border: 1px solid #3a4a5a;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        selection_layout = QtWidgets.QHBoxLayout(self.selection_frame)
        
        self.selection_icon = QtWidgets.QLabel("🎬")
        self.selection_icon.setStyleSheet("font-size: 24px;")
        selection_layout.addWidget(self.selection_icon)
        
        self.selection_label = QtWidgets.QLabel("No selection")
        self.selection_label.setStyleSheet("color: #9ac; font-size: 13px;")
        selection_layout.addWidget(self.selection_label, 1)
        
        layout.addWidget(self.selection_frame)
        
        # =====================================================================
        # TASK SELECTION
        # =====================================================================
        task_group = QtWidgets.QGroupBox("Select Task (In Progress)")
        task_layout = QtWidgets.QVBoxLayout(task_group)
        
        # Search/Filter
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("🔍"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Filter tasks...")
        self.search_edit.textChanged.connect(self._filter_tasks)
        search_layout.addWidget(self.search_edit)
        task_layout.addLayout(search_layout)
        
        # Task tree (grouped by project)
        self.task_tree = QtWidgets.QTreeWidget()
        self.task_tree.setHeaderLabels(["Task", "Shot/Asset", "Type"])
        self.task_tree.setAlternatingRowColors(True)
        self.task_tree.setRootIsDecorated(True)
        self.task_tree.itemSelectionChanged.connect(self._on_task_selected)
        self.task_tree.setMinimumHeight(180)
        
        # Column widths
        self.task_tree.setColumnWidth(0, 200)
        self.task_tree.setColumnWidth(1, 150)
        self.task_tree.setColumnWidth(2, 100)
        
        task_layout.addWidget(self.task_tree)
        
        # Refresh button
        refresh_btn = QtWidgets.QPushButton("🔄 Refresh Tasks")
        refresh_btn.clicked.connect(self._load_tasks)
        task_layout.addWidget(refresh_btn)
        
        layout.addWidget(task_group)
        
        # =====================================================================
        # COMMENT/NOTES
        # =====================================================================
        comment_group = QtWidgets.QGroupBox("Version Notes")
        comment_layout = QtWidgets.QVBoxLayout(comment_group)
        
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText(
            "Add notes for this version...\n"
            "Example: Fixed color grading, added lens flare effect"
        )
        self.comment_edit.setMaximumHeight(80)
        comment_layout.addWidget(self.comment_edit)
        
        layout.addWidget(comment_group)
        
        # =====================================================================
        # EXPORT SETTINGS (collapsible)
        # =====================================================================
        export_group = QtWidgets.QGroupBox("Export Settings")
        export_layout = QtWidgets.QFormLayout(export_group)
        
        # Export directory
        export_dir_layout = QtWidgets.QHBoxLayout()
        self.export_dir_edit = QtWidgets.QLineEdit()
        self.export_dir_edit.setText(self._load_export_path())
        self.export_dir_edit.setPlaceholderText(DEFAULT_EXPORT_DIR)
        export_dir_layout.addWidget(self.export_dir_edit)
        
        browse_btn = QtWidgets.QPushButton("...")
        browse_btn.setMaximumWidth(30)
        browse_btn.setToolTip("Browse for export directory")
        browse_btn.clicked.connect(self._browse_export_dir)
        export_dir_layout.addWidget(browse_btn)
        
        export_layout.addRow("Export Directory:", export_dir_layout)
        
        # Show current path info
        self.path_info_label = QtWidgets.QLabel()
        self.path_info_label.setStyleSheet("color: #7a7a7a; font-size: 11px;")
        self._update_path_info()
        export_layout.addRow("", self.path_info_label)
        
        # Connect to update info when path changes
        self.export_dir_edit.textChanged.connect(self._update_path_info)
        
        layout.addWidget(export_group)
        
        # =====================================================================
        # PROGRESS SECTION (hidden by default)
        # =====================================================================
        self.progress_frame = QtWidgets.QFrame()
        self.progress_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        progress_layout = QtWidgets.QVBoxLayout(self.progress_frame)
        
        self.progress_label = QtWidgets.QLabel("Ready")
        self.progress_label.setStyleSheet("color: #9a9a9a;")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_frame.hide()
        layout.addWidget(self.progress_frame)
        
        # =====================================================================
        # BUTTONS
        # =====================================================================
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.publish_btn = QtWidgets.QPushButton("📤 Publish Review")
        self.publish_btn.setObjectName("primary")
        self.publish_btn.setEnabled(False)
        self.publish_btn.clicked.connect(self._do_publish)
        button_layout.addWidget(self.publish_btn)
        
        layout.addLayout(button_layout)
    
    # =========================================================================
    # EXPORT PATH SETTINGS
    # =========================================================================
    
    def _get_settings_file(self) -> str:
        """Get path to settings file"""
        return os.path.join(PROJECT_DIR, "config", "publish_review_settings.json")
    
    def _load_export_path(self) -> str:
        """Load saved export path from settings"""
        try:
            settings_file = self._get_settings_file()
            if os.path.exists(settings_file):
                import json
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    return settings.get('export_dir', DEFAULT_EXPORT_DIR)
        except Exception as e:
            print(f"[ftrack] Could not load settings: {e}")
        return DEFAULT_EXPORT_DIR
    
    def _save_export_path(self, path: str):
        """Save export path to settings"""
        try:
            settings_file = self._get_settings_file()
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            
            import json
            settings = {}
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
            
            settings['export_dir'] = path
            
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            print(f"[ftrack] Export path saved: {path}")
        except Exception as e:
            print(f"[ftrack] Could not save settings: {e}")
    
    def _browse_export_dir(self):
        """Open directory browser for export path"""
        current_path = self.export_dir_edit.text() or DEFAULT_EXPORT_DIR
        
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            current_path
        )
        
        if path:
            self.export_dir_edit.setText(path)
            self._save_export_path(path)
    
    def _update_path_info(self):
        """Update the path info label"""
        path = self.export_dir_edit.text() or DEFAULT_EXPORT_DIR
        
        if os.path.exists(path):
            # Count existing files
            try:
                files = [f for f in os.listdir(path) if f.endswith(('.mp4', '.mov', '.m4v'))]
                self.path_info_label.setText(f"✓ Directory exists • {len(files)} video(s)")
                self.path_info_label.setStyleSheet("color: #7a9a7a; font-size: 11px;")
            except:
                self.path_info_label.setText("✓ Directory exists")
                self.path_info_label.setStyleSheet("color: #7a9a7a; font-size: 11px;")
        else:
            self.path_info_label.setText("Directory will be created on export")
            self.path_info_label.setStyleSheet("color: #9a9a7a; font-size: 11px;")
    
    def _get_export_dir(self) -> str:
        """Get the current export directory (from UI or default)"""
        path = self.export_dir_edit.text().strip()
        if path:
            return path
        return DEFAULT_EXPORT_DIR
    
    # =========================================================================
    # DATA LOADING
    # =========================================================================
    
    def _load_tasks(self):
        """Load user's in-progress tasks from ftrack"""
        self.task_tree.clear()
        self._tasks_data = []
        
        if not self.ftrack or not self.ftrack.connected:
            self._show_no_connection()
            return
        
        # Show loading
        loading_item = QtWidgets.QTreeWidgetItem(self.task_tree)
        loading_item.setText(0, "Loading tasks...")
        loading_item.setForeground(0, QtGui.QColor("#7a7a7a"))
        QtWidgets.QApplication.processEvents()
        
        try:
            # Get tasks in progress for current user
            tasks = self.ftrack.get_my_tasks_in_progress()
            self._tasks_data = tasks
            
            self.task_tree.clear()
            
            if not tasks:
                no_tasks_item = QtWidgets.QTreeWidgetItem(self.task_tree)
                no_tasks_item.setText(0, "No tasks in progress")
                no_tasks_item.setForeground(0, QtGui.QColor("#7a7a7a"))
                return
            
            # Group by project
            projects = {}
            for task in tasks:
                project_name = task.get('project', 'Unknown Project')
                if project_name not in projects:
                    projects[project_name] = []
                projects[project_name].append(task)
            
            # Build tree
            for project_name in sorted(projects.keys()):
                project_item = QtWidgets.QTreeWidgetItem(self.task_tree)
                project_item.setText(0, f"📁 {project_name}")
                project_item.setForeground(0, QtGui.QColor("#ff6b35"))
                project_item.setExpanded(True)
                project_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)  # Not selectable
                
                for task in projects[project_name]:
                    task_item = QtWidgets.QTreeWidgetItem(project_item)
                    task_item.setText(0, task.get('name', 'Unknown'))
                    task_item.setText(1, task.get('parent', '-'))
                    task_item.setText(2, task.get('type', '-'))
                    task_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, task)
            
            logger.info(f"Loaded {len(tasks)} in-progress tasks")
            
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            self.task_tree.clear()
            error_item = QtWidgets.QTreeWidgetItem(self.task_tree)
            error_item.setText(0, f"Error: {str(e)}")
            error_item.setForeground(0, QtGui.QColor("#d9534f"))
    
    def _show_no_connection(self):
        """Show message when not connected to ftrack"""
        self.task_tree.clear()
        item = QtWidgets.QTreeWidgetItem(self.task_tree)
        item.setText(0, "⚠️ Not connected to ftrack")
        item.setForeground(0, QtGui.QColor("#f0ad4e"))
        
        help_item = QtWidgets.QTreeWidgetItem(self.task_tree)
        help_item.setText(0, "Configure credentials first")
        help_item.setForeground(0, QtGui.QColor("#7a7a7a"))
    
    def _filter_tasks(self, text: str):
        """Filter tasks by search text"""
        text = text.lower()
        
        for i in range(self.task_tree.topLevelItemCount()):
            project_item = self.task_tree.topLevelItem(i)
            project_visible = False
            
            for j in range(project_item.childCount()):
                task_item = project_item.child(j)
                task_data = task_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                
                if task_data:
                    # Check if any field matches
                    matches = (
                        text in task_data.get('name', '').lower() or
                        text in task_data.get('parent', '').lower() or
                        text in task_data.get('type', '').lower() or
                        text in task_data.get('project', '').lower()
                    )
                    task_item.setHidden(not matches)
                    if matches:
                        project_visible = True
            
            # Show project if any task matches, or if no filter
            project_item.setHidden(not project_visible and bool(text))
    
    def _on_task_selected(self):
        """Handle task selection"""
        items = self.task_tree.selectedItems()
        
        if items:
            task_data = items[0].data(0, QtCore.Qt.ItemDataRole.UserRole)
            if task_data:  # Valid task (not a project header)
                self.selected_task = task_data
                self.publish_btn.setEnabled(True)
                return
        
        self.selected_task = None
        self.publish_btn.setEnabled(False)
    
    # =========================================================================
    # SELECTION INFO
    # =========================================================================
    
    def _update_selection_info(self):
        """Update the selection info panel"""
        if not self.flame_selection:
            self.selection_label.setText("No media selected")
            self.selection_icon.setText("⚠️")
            self.selection_frame.setStyleSheet("""
                QFrame {
                    background-color: #4a3a2a;
                    border: 1px solid #5a4a3a;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
            return
        
        try:
            # Try to get selection info
            selection_info = self._get_selection_info()
            
            if selection_info:
                self.selection_label.setText(
                    f"<b>{selection_info['name']}</b><br>"
                    f"<span style='color: #7a7a7a;'>"
                    f"{selection_info['type']} • {selection_info['duration']}"
                    f"</span>"
                )
                self.selection_icon.setText("🎬")
                self.selection_frame.setStyleSheet("""
                    QFrame {
                        background-color: #2a3a4a;
                        border: 1px solid #3a4a5a;
                        border-radius: 5px;
                        padding: 10px;
                    }
                """)
            else:
                self.selection_label.setText("Selection ready for export")
                self.selection_icon.setText("🎬")
                
        except Exception as e:
            logger.warning(f"Could not get selection info: {e}")
            self.selection_label.setText("Media selected")
    
    def _get_selection_info(self) -> Optional[Dict]:
        """Get information about the Flame selection (Media Panel, Batch, Timeline)"""
        try:
            import flame
            
            for item in self.flame_selection:
                # Sequence (timeline)
                if isinstance(item, flame.PySequence):
                    name = str(item.name.get_value()).strip("'")
                    duration = item.duration if hasattr(item, 'duration') else 0
                    return {
                        'name': name,
                        'type': 'Sequence',
                        'duration': f"{duration} frames"
                    }
                # Clip (media panel, batch)
                elif isinstance(item, flame.PyClip):
                    name = str(item.name.get_value()).strip("'")
                    duration = item.duration if hasattr(item, 'duration') else 0
                    return {
                        'name': name,
                        'type': 'Clip',
                        'duration': f"{duration} frames"
                    }
                # Batch nodes - try to get clip from node
                elif hasattr(item, 'clip'):
                    clip = item.clip
                    if clip and hasattr(clip, 'name'):
                        name = str(clip.name.get_value()).strip("'")
                        duration = clip.duration if hasattr(clip, 'duration') else 0
                        return {
                            'name': name,
                            'type': 'Batch Clip',
                            'duration': f"{duration} frames"
                        }
                # Generic - try to get name attribute
                elif hasattr(item, 'name'):
                    try:
                        if hasattr(item.name, 'get_value'):
                            name = str(item.name.get_value()).strip("'")
                        else:
                            name = str(item.name).strip("'")
                        
                        duration = item.duration if hasattr(item, 'duration') else 0
                        item_type = type(item).__name__.replace('Py', '')
                        
                        return {
                            'name': name,
                            'type': item_type,
                            'duration': f"{duration} frames" if duration else "N/A"
                        }
                    except:
                        pass
            
            # If we have selection but couldn't parse it
            if self.flame_selection:
                print(f"[ftrack] Selection type: {type(self.flame_selection[0])}")
                return {
                    'name': 'Selected Media',
                    'type': 'Unknown',
                    'duration': 'N/A'
                }
            
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Error getting selection info: {e}")
            print(f"[ftrack] Warning: Could not get selection info: {e}")
        
        return None
    
    # =========================================================================
    # PUBLISH WORKFLOW
    # =========================================================================
    
    def _do_publish(self):
        """Execute the publish workflow"""
        if not self.selected_task:
            QtWidgets.QMessageBox.warning(
                self, "No Task Selected",
                "Please select a task to publish to."
            )
            return
        
        if not self.flame_selection:
            QtWidgets.QMessageBox.warning(
                self, "No Selection",
                "Please select a clip or sequence in Flame."
            )
            return
        
        # Disable UI during publish
        self._set_ui_enabled(False)
        self.progress_frame.show()
        
        try:
            # Step 1: Export video from Flame
            self._update_progress("Exporting video from Flame...", 10)
            video_path = self._export_video()
            
            if not video_path:
                # Show more helpful error message
                error_msg = (
                    "Failed to export video from Flame.\n\n"
                    "Possible causes:\n"
                    "• Export preset not found\n"
                    "• Flame export failed\n"
                    "• No write permission to export directory\n\n"
                    "Check the terminal for detailed error messages.\n\n"
                    f"Export directory: {self._get_export_dir()}\n"
                    f"Expected preset: {DEFAULT_VIDEO_PRESET}"
                )
                raise Exception(error_msg)
            
            # Step 2: Get task entity from ftrack
            self._update_progress("Preparing ftrack upload...", 40)
            task_id = self.selected_task.get('id')
            parent_id = self.selected_task.get('parent_id')
            
            print(f"[ftrack] Task ID: {task_id}")
            print(f"[ftrack] Parent ID: {parent_id}")
            print(f"[ftrack] Video path: {video_path}")
            
            # Step 3: Create version and upload
            self._update_progress("Uploading to ftrack...", 60)
            
            comment = self.comment_edit.toPlainText().strip()
            if not comment:
                comment = f"Review from Flame - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            success = self._upload_to_ftrack(task_id, parent_id, video_path, comment)
            
            if success:
                self._update_progress("✅ Published successfully!", 100)
                
                # Show success message
                QtWidgets.QMessageBox.information(
                    self, "Publish Complete",
                    f"Successfully published review to:\n\n"
                    f"Task: {self.selected_task.get('name')}\n"
                    f"Shot: {self.selected_task.get('parent')}\n"
                    f"Project: {self.selected_task.get('project')}"
                )
                
                self.accept()
            else:
                raise Exception("Failed to upload to ftrack. Check terminal for details.")
            
        except Exception as e:
            logger.error(f"Publish failed: {e}")
            self._update_progress(f"❌ Error", 0)
            
            QtWidgets.QMessageBox.critical(
                self, "Publish Failed",
                f"Could not publish review:\n\n{str(e)}"
            )
            
        finally:
            self._set_ui_enabled(True)
    
    def _export_video(self) -> Optional[str]:
        """Export video from Flame selection (Media Panel, Batch, Timeline)"""
        try:
            import flame
            
            # Get export directory from UI (user preference)
            export_dir = self._get_export_dir()
            os.makedirs(export_dir, exist_ok=True)
            print(f"[ftrack] Export directory: {export_dir}")
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Get exportable item from selection
            name = "review"
            selected_item = None
            
            for item in self.flame_selection:
                print(f"[ftrack] Checking item type: {type(item).__name__}")
                
                # Direct clip or sequence
                if isinstance(item, (flame.PyClip, flame.PySequence)):
                    if hasattr(item, 'name') and hasattr(item.name, 'get_value'):
                        name = str(item.name.get_value()).strip("'")
                    selected_item = item
                    print(f"[ftrack] Found direct clip/sequence: {name}")
                    break
                
                # Batch node with clip attribute
                elif hasattr(item, 'clip') and item.clip is not None:
                    clip = item.clip
                    if hasattr(clip, 'name') and hasattr(clip.name, 'get_value'):
                        name = str(clip.name.get_value()).strip("'")
                    selected_item = clip
                    print(f"[ftrack] Found batch clip: {name}")
                    break
                
                # Try generic name attribute
                elif hasattr(item, 'name'):
                    try:
                        if hasattr(item.name, 'get_value'):
                            name = str(item.name.get_value()).strip("'")
                        else:
                            name = str(item.name).strip("'")
                        selected_item = item
                        print(f"[ftrack] Found generic item: {name}")
                        break
                    except Exception as e:
                        print(f"[ftrack] Could not get name: {e}")
            
            # Clean name for filename
            name = "".join(c for c in name if c.isalnum() or c in "._-")
            
            print(f"[ftrack] Exporting item: {name}")
            
            if selected_item is None:
                print("[ftrack] ERROR: No valid item found in selection")
                print(f"[ftrack] Selection contents: {self.flame_selection}")
                return None
            
            # Check for preset - try multiple locations
            preset_path = DEFAULT_VIDEO_PRESET
            preset_locations = [
                # Simple review preset (works with clips) - preferred
                os.path.join(PROJECT_DIR, "presets", "ftrack_review_simple.xml"),
                # Project preset 
                DEFAULT_VIDEO_PRESET,
                os.path.join(PROJECT_DIR, "presets", "ftrack_video__shot_version.xml"),
                # System preset location
                "/opt/Autodesk/shared/export/presets/sequence_publish/ftrack_video__shot_version.xml",
                "/opt/Autodesk/shared/export/presets/sequence_publish/ftrack_review_simple.xml",
                # User home
                os.path.expanduser("~/flame_ftrack_integration/presets/ftrack_review_simple.xml"),
                os.path.expanduser("~/flame_ftrack_integration/presets/ftrack_video__shot_version.xml"),
                # Flame built-in presets (fallbacks)
                "/opt/Autodesk/shared/export/presets/movie_file/Quicktime/Quicktime.xml",
                "/opt/Autodesk/shared/export/presets/movie_file/QuickTime/QuickTime (H.264).xml",
            ]
            
            preset_found = False
            for p in preset_locations:
                if os.path.exists(p):
                    preset_path = p
                    preset_found = True
                    print(f"[ftrack] Using preset: {preset_path}")
                    break
            
            if not preset_found:
                # Try to find any available preset in common directories
                preset_dirs = [
                    "/opt/Autodesk/shared/export/presets/sequence_publish",
                    "/opt/Autodesk/shared/export/presets/movie_file",
                    "/opt/Autodesk/shared/export/presets",
                ]
                
                for preset_dir in preset_dirs:
                    if os.path.exists(preset_dir):
                        print(f"[ftrack] Searching for presets in: {preset_dir}")
                        for root, dirs, files in os.walk(preset_dir):
                            for f in files:
                                if f.endswith('.xml'):
                                    preset_path = os.path.join(root, f)
                                    preset_found = True
                                    print(f"[ftrack] Found fallback preset: {preset_path}")
                                    break
                            if preset_found:
                                break
                    if preset_found:
                        break
            
            if not preset_found:
                print(f"[ftrack] ERROR: No export preset found!")
                print(f"[ftrack] Please install preset at: {DEFAULT_VIDEO_PRESET}")
                return None
            
            # List files before export
            files_before = set()
            for ext in ['*.mov', '*.mp4', '*.m4v']:
                files_before.update(glob.glob(os.path.join(export_dir, '**', ext), recursive=True))
            
            print(f"[ftrack] Files before export: {len(files_before)}")
            
            # Export using Flame
            print(f"[ftrack] Starting export...")
            exporter = flame.PyExporter()
            exporter.foreground = True
            
            try:
                exporter.export(selected_item, preset_path, export_dir)
                print(f"[ftrack] Export command completed")
            except Exception as export_err:
                print(f"[ftrack] Export command error: {export_err}")
                # Continue anyway - sometimes export works but throws an error
            
            # Wait for export to complete (Flame exports can take a moment)
            print(f"[ftrack] Waiting for export to complete...")
            time.sleep(3)
            
            # List files after export
            files_after = set()
            for ext in ['*.mov', '*.mp4', '*.m4v']:
                files_after.update(glob.glob(os.path.join(export_dir, '**', ext), recursive=True))
            
            # Find new files
            new_files = files_after - files_before
            print(f"[ftrack] Files after export: {len(files_after)}")
            print(f"[ftrack] New files: {len(new_files)}")
            
            if new_files:
                # Return the most recently modified new file
                newest = max(new_files, key=os.path.getmtime)
                print(f"[ftrack] ✓ Exported video: {newest}")
                return newest
            
            # Fallback: search for files matching the name
            search_patterns = [
                os.path.join(export_dir, f"{name}*.mov"),
                os.path.join(export_dir, f"{name}*.mp4"),
                os.path.join(export_dir, "**", f"{name}*.mov"),
                os.path.join(export_dir, "**", f"{name}*.mp4"),
                os.path.join(export_dir, "**", "*.mov"),
                os.path.join(export_dir, "**", "*.mp4"),
            ]
            
            for pattern in search_patterns:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    # Get the most recent file
                    matches.sort(key=os.path.getmtime, reverse=True)
                    video_path = matches[0]
                    # Check if it's recent (within last minute)
                    if time.time() - os.path.getmtime(video_path) < 60:
                        print(f"[ftrack] ✓ Found recent video: {video_path}")
                        return video_path
            
            print(f"[ftrack] ERROR: Could not find exported video in {export_dir}")
            print(f"[ftrack] Directory contents:")
            for f in os.listdir(export_dir):
                print(f"[ftrack]   - {f}")
            
            return None
            
        except ImportError as e:
            print(f"[ftrack] ERROR: Flame not available: {e}")
            return None
            
        except Exception as e:
            print(f"[ftrack] ERROR: Export failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _upload_to_ftrack(self, task_id: str, parent_id: str, 
                          video_path: str, comment: str) -> bool:
        """Upload video to ftrack as a new version"""
        try:
            if not self.ftrack or not self.ftrack.session:
                print("[ftrack] ERROR: No ftrack session available")
                return False
            
            session = self.ftrack.session
            
            # Get the task entity
            task = None
            if task_id:
                task = session.query(f'Task where id is "{task_id}"').first()
                if task:
                    print(f"[ftrack] Found task: {task['name']}")
            
            # Get the parent entity (shot or asset)
            parent = None
            if parent_id:
                parent = session.query(
                    f'TypedContext where id is "{parent_id}"'
                ).first()
                if parent:
                    print(f"[ftrack] Found parent: {parent['name']}")
            
            if not parent and task:
                # Fallback: get parent from task
                parent = task.get('parent')
                if parent:
                    print(f"[ftrack] Using parent from task: {parent['name']}")
            
            if not parent:
                print("[ftrack] ERROR: Could not find parent entity for version")
                return False
            
            # Create version using custom logic (more control than manager)
            print(f"[ftrack] Creating version with comment: {comment[:50]}...")
            
            shot_name = parent['name']
            
            # Get or create asset
            asset_type = session.query('AssetType where name is "Upload"').first()
            if not asset_type:
                asset_type = session.query('AssetType where name is "Review"').first()
            
            existing_asset = session.query(
                f'Asset where name is "{shot_name}" and parent.id is "{parent["id"]}"'
            ).first()
            
            if existing_asset:
                asset = existing_asset
                print(f"[ftrack] Using existing asset: {asset['name']}")
            else:
                asset_data = {
                    'name': shot_name,
                    'parent': parent,
                }
                if asset_type:
                    asset_data['type'] = asset_type
                
                asset = session.create('Asset', asset_data)
                session.commit()
                print(f"[ftrack] Created new asset: {asset['name']}")
            
            # Create version with task link
            version_data = {
                'asset': asset,
                'comment': comment,  # This goes to version comment field
            }
            
            # Link to the specific task the user selected
            if task:
                version_data['task'] = task
                print(f"[ftrack] Linking version to task: {task['name']}")
            
            version = session.create('AssetVersion', version_data)
            session.commit()
            print(f"[ftrack] Created version: v{version.get('version', '?')}")
            
            # Also create a Note on the version (more visible in ftrack UI)
            if comment and comment.strip():
                try:
                    # Get current user
                    user = session.query(
                        f'User where username is "{session.api_user}"'
                    ).first()
                    
                    if user:
                        note = session.create('Note', {
                            'content': comment,
                            'author': user,
                        })
                        version['notes'].append(note)
                        session.commit()
                        print(f"[ftrack] Created note on version")
                except Exception as note_err:
                    print(f"[ftrack] Warning: Could not create note: {note_err}")
                    # Continue anyway - the version comment is still there
            
            # Upload video as component
            server_location = session.query(
                'Location where name is "ftrack.server"'
            ).one()
            
            print(f"[ftrack] Uploading video...")
            version.create_component(
                path=video_path,
                data={'name': 'main'},
                location=server_location
            )
            
            # Encode media for web review
            print(f"[ftrack] Encoding for web review...")
            version.encode_media(video_path)
            
            session.commit()
            
            print(f"[ftrack] ✓ Version published successfully!")
            print(f"[ftrack]   Shot: {shot_name}")
            print(f"[ftrack]   Task: {task['name'] if task else 'N/A'}")
            print(f"[ftrack]   Comment: {comment[:30]}...")
            
            return True
            
        except Exception as e:
            print(f"[ftrack] ERROR: Upload failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _update_progress(self, message: str, value: int):
        """Update progress display"""
        self.progress_label.setText(message)
        self.progress_bar.setValue(value)
        QtWidgets.QApplication.processEvents()
    
    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI elements"""
        self.task_tree.setEnabled(enabled)
        self.search_edit.setEnabled(enabled)
        self.comment_edit.setEnabled(enabled)
        self.publish_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)


# =============================================================================
# QUICK PUBLISH FUNCTION
# =============================================================================

def launch_publish_review(selection, ftrack_manager=None):
    """
    Launch the publish review dialog
    
    Args:
        selection: Flame selection
        ftrack_manager: FtrackManager instance (optional, will create if needed)
    
    Returns:
        True if published successfully
    """
    # Create ftrack manager if needed
    if ftrack_manager is None:
        from ..core.ftrack_manager import FtrackManager
        from ..config.credentials_manager import get_credentials, credentials_are_configured
        
        ftrack_manager = FtrackManager()
        
        if credentials_are_configured():
            creds = get_credentials()
            ftrack_manager.connect(
                server_url=creds['server'],
                api_user=creds['api_user'],
                api_key=creds['api_key']
            )
    
    # Create and show dialog
    dialog = PublishReviewDialog(
        ftrack_manager=ftrack_manager,
        flame_selection=selection
    )
    
    result = dialog.exec()
    return result == QtWidgets.QDialog.DialogCode.Accepted


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import sys
    
    app = QtWidgets.QApplication(sys.argv)
    
    # Test with mock data
    class MockFtrack:
        connected = True
        session = None
        
        def get_my_tasks_in_progress(self):
            return [
                {'id': '1', 'name': 'compositing', 'parent': 'SHOT_010', 
                 'parent_id': 'p1', 'project': 'Project Alpha', 'type': 'Compositing'},
                {'id': '2', 'name': 'rotoscoping', 'parent': 'SHOT_010',
                 'parent_id': 'p1', 'project': 'Project Alpha', 'type': 'Rotoscoping'},
                {'id': '3', 'name': 'compositing', 'parent': 'SHOT_020',
                 'parent_id': 'p2', 'project': 'Project Alpha', 'type': 'Compositing'},
                {'id': '4', 'name': 'comp', 'parent': 'VFX_001',
                 'parent_id': 'p3', 'project': 'Project Beta', 'type': 'Compositing'},
            ]
        
        def create_version(self, shot, video_path, version_name, comment):
            print(f"[MOCK] Creating version: {version_name}")
            print(f"  Video: {video_path}")
            print(f"  Comment: {comment}")
            return True
    
    dialog = PublishReviewDialog(
        ftrack_manager=MockFtrack(),
        flame_selection=None
    )
    dialog.show()
    
    sys.exit(app.exec())
