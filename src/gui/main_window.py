"""
Main Window - Flame to ftrack Integration

Main interface that uses separate modules:
- core.ftrack_manager: ftrack business logic
- core.flame_exporter: Flame export operations
- gui.styles: CSS styles for Flame UI
- gui.dialogs: Auxiliary dialogs
- gui.shot_table: Shot table widget

Features:
- Project navigation with search and bookmarks
- Shot table with batch editing
- Thumbnail and video export
- ftrack shot/task creation
- Time tracking integration
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtWidgets, QtCore, QtGui

from .styles import FLAME_STYLE
from .shot_table import ShotTableWidget
from .dialogs import StepProgressDialog, SettingsDialog
from ..core.ftrack_manager import FtrackManager
from ..core.flame_exporter import (
    FlameExporter, 
    DEFAULT_THUMB_PRESET_PATH, 
    DEFAULT_VIDEO_PRESET_PATH,
    DEFAULT_THUMB_DIR,
    DEFAULT_VIDEO_DIR
)

logger = logging.getLogger(__name__)


# =============================================================================
# BOOKMARKS MANAGER - Persistent favorites system
# =============================================================================

class BookmarksManager:
    """Manages project bookmarks for quick access"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.bookmarks_file = self.config_dir / "project_bookmarks.json"
        self._bookmarks: List[Dict] = []
        self._load()
    
    def _load(self):
        """Load bookmarks from file"""
        try:
            if self.bookmarks_file.exists():
                with open(self.bookmarks_file, 'r') as f:
                    data = json.load(f)
                    self._bookmarks = data.get('bookmarks', [])
                    logger.info(f"Loaded {len(self._bookmarks)} bookmarks")
        except Exception as e:
            logger.warning(f"Failed to load bookmarks: {e}")
            self._bookmarks = []
    
    def _save(self):
        """Save bookmarks to file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.bookmarks_file, 'w') as f:
                json.dump({'bookmarks': self._bookmarks}, f, indent=2)
            logger.info(f"Saved {len(self._bookmarks)} bookmarks")
        except Exception as e:
            logger.error(f"Failed to save bookmarks: {e}")
    
    def add(self, project: Dict) -> bool:
        """Add project to bookmarks"""
        for bm in self._bookmarks:
            if bm.get('id') == project.get('id'):
                return False
        
        bookmark = {
            'id': project.get('id'),
            'name': project.get('name'),
            'type': project.get('type', 'Project'),
            'project_id': project.get('project_id', project.get('id'))
        }
        self._bookmarks.insert(0, bookmark)
        
        if len(self._bookmarks) > 20:
            self._bookmarks = self._bookmarks[:20]
        
        self._save()
        return True
    
    def remove(self, project_id: str) -> bool:
        """Remove project from bookmarks"""
        initial_len = len(self._bookmarks)
        self._bookmarks = [bm for bm in self._bookmarks if bm.get('id') != project_id]
        
        if len(self._bookmarks) < initial_len:
            self._save()
            return True
        return False
    
    def get_all(self) -> List[Dict]:
        """Return all bookmarks"""
        return self._bookmarks.copy()
    
    def is_bookmarked(self, project_id: str) -> bool:
        """Check if project is bookmarked"""
        return any(bm.get('id') == project_id for bm in self._bookmarks)


# =============================================================================
# LOG WINDOW - Separate window for application logs
# =============================================================================

class LogWindow(QtWidgets.QWidget):
    """Separate window to display application logs"""
    
    # Signal for thread-safe log appending
    log_signal = QtCore.Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 ftrack Integration - Log")
        self.setMinimumSize(700, 500)
        self.setStyleSheet(FLAME_STYLE)
        
        # Window flags - independent window
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window |
            QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header = QtWidgets.QLabel("📋 Application Log")
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #5bc0de; padding: 5px;")
        layout.addWidget(header)
        
        # Log text area
        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1000)  # Limit lines for performance
        self.log_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #00ff00;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.log_text)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        
        clear_btn = QtWidgets.QPushButton("🗑️ Clear")
        clear_btn.clicked.connect(self.log_text.clear)
        btn_layout.addWidget(clear_btn)
        
        copy_btn = QtWidgets.QPushButton("📋 Copy All")
        copy_btn.clicked.connect(self._copy_all)
        btn_layout.addWidget(copy_btn)
        
        btn_layout.addStretch()
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.hide)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # Connect signal to slot (thread-safe method)
        self.log_signal.connect(self._append_log_internal)
    
    def _copy_all(self):
        """Copy all log content to clipboard"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
    
    def _append_log_internal(self, message: str):
        """Internal slot to append message (thread-safe)"""
        self.log_text.appendPlainText(message)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def append_log(self, message: str):
        """Append message to log (can be called from any thread)"""
        self.log_signal.emit(message)


class QtLogHandler(logging.Handler):
    """Logging handler that sends to LogWindow"""
    
    def __init__(self, log_window: LogWindow):
        super().__init__()
        self.log_window = log_window
        self.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S'))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            # Use append_log which emits signal (thread-safe)
            self.log_window.append_log(msg)
        except Exception:
            pass


# =============================================================================
# MAIN WINDOW
# =============================================================================

class FlameFtrackWindow(QtWidgets.QMainWindow):
    """
    Main Flame-ftrack integration window
    
    Features:
    - ftrack project navigation with search
    - Project bookmarks for quick access
    - Shot table with batch editing
    - Thumbnail export (Step 1)
    - Video export (Step 2)
    - ftrack shot/task creation (Step 3)
    - Dry-run mode for testing
    """
    
    def __init__(self, flame_selection=None, use_mock: bool = False, parent=None):
        super().__init__(parent)
        
        self.flame_selection = flame_selection
        self.use_mock = use_mock
        self.selected_project = None
        
        # Bookmarks manager
        self.bookmarks = BookmarksManager()
        
        # Log window
        self.log_window = LogWindow()
        self._setup_logging()
        
        # Managers
        self.ftrack = FtrackManager()
        self.exporter = FlameExporter()
        
        # Settings
        self.settings = {
            'preset_path': DEFAULT_THUMB_PRESET_PATH,
            'video_preset_path': DEFAULT_VIDEO_PRESET_PATH,
            'output_dir': DEFAULT_THUMB_DIR,
            'video_dir': DEFAULT_VIDEO_DIR,
            'export_thumbs': True,
            'upload_thumbs': True,
            'export_videos': False,
            'upload_versions': False,
        }
        
        self._setup_ui()
        
        # Start connection after UI is visible (100ms delay)
        QtCore.QTimer.singleShot(100, self._connect_ftrack)
        
        if flame_selection:
            self._load_from_timeline()
    
    def _setup_logging(self):
        """Setup logging to the log window"""
        # Add handler to root logger
        root_logger = logging.getLogger()
        
        # Remove duplicate handlers if any
        for handler in root_logger.handlers[:]:
            if isinstance(handler, QtLogHandler):
                root_logger.removeHandler(handler)
        
        # Add new handler
        qt_handler = QtLogHandler(self.log_window)
        qt_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(qt_handler)
        
        # Ensure root logger has DEBUG level
        root_logger.setLevel(logging.DEBUG)
        
        # Initial log
        logger.info("=" * 50)
        logger.info("ftrack Integration started")
        logger.info("=" * 50)
    
    def _show_log_window(self):
        """Show/hide the log window"""
        if self.log_window.isVisible():
            self.log_window.hide()
        else:
            self.log_window.show()
            self.log_window.raise_()
    
    def _show_about(self):
        """Show about dialog with application info and features"""
        about_text = """
        <h2>🔥 Flame → ftrack Integration</h2>
        <p><b>Version:</b> 1.0.0</p>
        <p><b>Author:</b> Wilton Matos</p>
        
        <h3>Features:</h3>
        <ul>
            <li><b>Create Shot:</b> Create shots and tasks in ftrack from Flame timeline</li>
            <li><b>Project Bookmarks:</b> Quick access to favorite projects</li>
            <li><b>Thumbnail Export:</b> Export and upload thumbnails to ftrack</li>
            <li><b>Video Export:</b> Export and upload video versions to ftrack</li>
            <li><b>Batch Operations:</b> Process multiple shots at once</li>
            <li><b>Time Tracker:</b> Track time spent on tasks with ftrack integration</li>
            <li><b>Task History:</b> Quick access to recently used tasks</li>
        </ul>
        
        <h3>Workflow:</h3>
        <ol>
            <li>Load shots from Flame timeline</li>
            <li>Select destination project/sequence in ftrack</li>
            <li>Configure shot properties and tasks</li>
            <li>Execute to create shots in ftrack</li>
        </ol>
        
        <p style="color: #888; margin-top: 20px;">
        Built for Flame 2025+ with PySide6<br>
        Requires ftrack Python API
        </p>
        """
        
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("About")
        msg.setTextFormat(QtCore.Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.setStyleSheet(FLAME_STYLE)
        msg.exec()
    
    # =========================================================================
    # UI SETUP
    # =========================================================================
    
    def _setup_ui(self):
        """Setup user interface"""
        self.setWindowTitle("🔥 Flame → ftrack Integration")
        self.setMinimumSize(1300, 800)
        self.setStyleSheet(FLAME_STYLE)
        
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window |
            QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header = self._create_header()
        main_layout.addLayout(header)
        
        # Splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        left_panel = self._create_projects_panel()
        splitter.addWidget(left_panel)
        
        right_panel = self._create_shots_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([280, 1000])
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Initializing...")
        self.statusBar().setStyleSheet("background-color: #2a2a2a; padding: 5px;")
    
    def _create_header(self) -> QtWidgets.QHBoxLayout:
        """Create header with title and buttons"""
        layout = QtWidgets.QHBoxLayout()
        
        # Title with HTML formatting
        title = QtWidgets.QLabel()
        title.setTextFormat(QtCore.Qt.TextFormat.RichText)
        title.setText('<span style="font-size: 18px; font-weight: bold;">'
                      '<span style="color: #ff6b35;">🔥</span> '
                      '<span style="color: #d9d9d9;">Flame → ftrack Integration</span>'
                      '</span>')
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Status indicator
        self.connection_status = QtWidgets.QLabel()
        self.connection_status.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._update_connection_status(False)
        layout.addWidget(self.connection_status)
        
        # Refresh
        refresh_btn = QtWidgets.QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_projects)
        layout.addWidget(refresh_btn)
        
        # Settings
        settings_btn = QtWidgets.QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)
        
        # Config (credentials)
        config_btn = QtWidgets.QPushButton("🔑 Credentials")
        config_btn.clicked.connect(self._open_credentials)
        layout.addWidget(config_btn)
        
        # Show Log button
        log_btn = QtWidgets.QPushButton("📋 Log")
        log_btn.setToolTip("Show application log window")
        log_btn.clicked.connect(self._show_log_window)
        layout.addWidget(log_btn)
        
        # About button
        about_btn = QtWidgets.QPushButton("ℹ️ About")
        about_btn.setToolTip("About this application")
        about_btn.clicked.connect(self._show_about)
        layout.addWidget(about_btn)
        
        return layout
    
    def _update_connection_status(self, connected: bool):
        """Update connection indicator"""
        if connected:
            if self.ftrack.is_mock:
                self.connection_status.setText(
                    f'<span style="color: #f0ad4e;">🟡 MOCK MODE</span>'
                )
            else:
                self.connection_status.setText(
                    f'<span style="color: #5cb85c;">🟢 Connected</span>'
                )
        else:
            self.connection_status.setText(
                f'<span style="color: #d9534f;">🔴 Disconnected</span>'
            )
    
    def _create_projects_panel(self) -> QtWidgets.QWidget:
        """Create projects panel with search and bookmarks"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 5, 0)
        
        # =====================================================================
        # BOOKMARKS SECTION
        # =====================================================================
        bookmarks_header = QtWidgets.QHBoxLayout()
        
        bm_label = QtWidgets.QLabel()
        bm_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        bm_label.setText('<span style="color: #f0ad4e; font-size: 12px; font-weight: bold;">⭐ Bookmarks</span>')
        bookmarks_header.addWidget(bm_label)
        
        bookmarks_header.addStretch()
        
        # Button to add current project to bookmarks
        self.add_bookmark_btn = QtWidgets.QPushButton("➕")
        self.add_bookmark_btn.setFixedSize(24, 24)
        self.add_bookmark_btn.setToolTip("Add selected project to bookmarks")
        self.add_bookmark_btn.clicked.connect(self._add_current_to_bookmarks)
        self.add_bookmark_btn.setEnabled(False)
        bookmarks_header.addWidget(self.add_bookmark_btn)
        
        layout.addLayout(bookmarks_header)
        
        # Lista de bookmarks
        self.bookmarks_list = QtWidgets.QListWidget()
        self.bookmarks_list.setMaximumHeight(100)
        self.bookmarks_list.setStyleSheet("""
            QListWidget {
                background-color: #252525;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #4a6fa5;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
        """)
        self.bookmarks_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.bookmarks_list.customContextMenuRequested.connect(self._show_bookmark_context_menu)
        self.bookmarks_list.itemDoubleClicked.connect(self._on_bookmark_double_clicked)
        layout.addWidget(self.bookmarks_list)
        
        # Load bookmarks
        self._refresh_bookmarks_list()
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #3a3a3a;")
        layout.addWidget(separator)
        
        # =====================================================================
        # PROJECTS SECTION
        # =====================================================================
        
        # Header
        header = QtWidgets.QLabel()
        header.setTextFormat(QtCore.Qt.TextFormat.RichText)
        header.setText('<span style="color: #5bc0de; font-size: 14px; font-weight: bold;">📁 Projects</span>')
        header.setStyleSheet("padding: 5px;")
        layout.addWidget(header)
        
        # Dynamic search
        search_layout = QtWidgets.QHBoxLayout()
        
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("🔍 Type project name to search...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._search_projects)
        search_layout.addWidget(self.search_input)
        
        self.search_btn = QtWidgets.QPushButton("Search")
        self.search_btn.clicked.connect(self._search_projects)
        self.search_btn.setFixedWidth(70)
        search_layout.addWidget(self.search_btn)
        
        layout.addLayout(search_layout)
        
        # Hint for the user
        hint_label = QtWidgets.QLabel()
        hint_label.setText('<span style="color: #888; font-size: 11px;">Type at least 2 characters and press Enter or click Search</span>')
        hint_label.setStyleSheet("padding: 2px;")
        layout.addWidget(hint_label)
        
        # Tree Widget
        self.projects_tree = QtWidgets.QTreeWidget()
        self.projects_tree.setHeaderLabels(["Name", "Type"])
        self.projects_tree.setColumnWidth(0, 250)
        self.projects_tree.setAlternatingRowColors(True)
        self.projects_tree.setRootIsDecorated(True)
        self.projects_tree.setItemsExpandable(True)
        self.projects_tree.setExpandsOnDoubleClick(False)
        self.projects_tree.setIndentation(20)
        
        # Connect signals
        self.projects_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.projects_tree.itemExpanded.connect(self._on_project_expanded)
        self.projects_tree.itemCollapsed.connect(self._on_project_collapsed)
        
        layout.addWidget(self.projects_tree)
        
        # Timer para debounce da busca
        self._search_timer = QtCore.QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._search_projects)
        
        return panel
    
    # =========================================================================
    # BOOKMARKS METHODS
    # =========================================================================
    
    def _refresh_bookmarks_list(self):
        """Refresh bookmarks list in UI"""
        self.bookmarks_list.clear()
        
        bookmarks = self.bookmarks.get_all()
        
        if not bookmarks:
            item = QtWidgets.QListWidgetItem("No bookmarks yet")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QtGui.QColor("#666"))
            self.bookmarks_list.addItem(item)
            return
        
        for bm in bookmarks:
            item = QtWidgets.QListWidgetItem()
            type_icon = "📁" if bm.get('type') == 'Project' else "📂"
            item.setText(f"{type_icon} {bm.get('name', 'Unknown')}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, bm)
            item.setToolTip(f"Double-click to select\nType: {bm.get('type', 'Project')}")
            self.bookmarks_list.addItem(item)
    
    def _add_current_to_bookmarks(self):
        """Add selected project to bookmarks"""
        if not self.selected_project:
            return
        
        if self.bookmarks.add(self.selected_project):
            self._refresh_bookmarks_list()
            self.statusBar().showMessage(f"⭐ Added '{self.selected_project['name']}' to bookmarks")
            logger.info(f"Added project to bookmarks: {self.selected_project['name']}")
        else:
            self.statusBar().showMessage(f"Project already in bookmarks")
    
    def _show_bookmark_context_menu(self, position):
        """Menu de contexto para bookmarks"""
        item = self.bookmarks_list.itemAt(position)
        if not item:
            return
        
        bm_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not bm_data:
            return
        
        menu = QtWidgets.QMenu(self)
        
        select_action = menu.addAction("📌 Select")
        select_action.triggered.connect(lambda: self._select_bookmarked_project(bm_data))
        
        menu.addSeparator()
        
        remove_action = menu.addAction("🗑️ Remove from bookmarks")
        remove_action.triggered.connect(lambda: self._remove_bookmark(bm_data))
        
        menu.exec(self.bookmarks_list.mapToGlobal(position))
    
    def _on_bookmark_double_clicked(self, item):
        """Double-click on bookmark selects the project"""
        bm_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if bm_data:
            self._select_bookmarked_project(bm_data)
    
    def _select_bookmarked_project(self, bm_data: Dict):
        """Select project from bookmark and search automatically"""
        logger.info(f"Loading bookmarked project: {bm_data['name']}")
        
        # Preenche o campo de busca com o nome do projeto
        project_name = bm_data.get('name', '')
        self.search_input.setText(project_name)
        
        # Execute search automatically
        self._search_projects()
        
        # Wait a moment for search to load
        QtWidgets.QApplication.processEvents()
        
        # Try to find and select item in tree
        QtCore.QTimer.singleShot(500, lambda: self._find_and_select_item(bm_data))
    
    def _find_and_select_item(self, bm_data: Dict):
        """Find and select item in tree by ID"""
        target_id = bm_data.get('id')
        target_name = bm_data.get('name')
        
        if not target_id:
            logger.warning("Bookmark has no ID, cannot select item")
            return
        
        # Search at first level (projects)
        for i in range(self.projects_tree.topLevelItemCount()):
            item = self.projects_tree.topLevelItem(i)
            item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            
            if item_data and item_data.get('id') == target_id:
                # Found exact item
                self.projects_tree.setCurrentItem(item)
                self.projects_tree.scrollToItem(item)
                self._on_project_selected(item, 0)
                
                # Expand item if it's a project
                if item_data.get('type') == 'Project' and not item_data.get('_loaded'):
                    self._on_project_expanded(item)
                
                self.statusBar().showMessage(f"✅ Selected: {target_name}")
                logger.info(f"Found and selected bookmarked item: {target_name}")
                return
        
        # If not found, name might not be exact in search
        # Try by name
        for i in range(self.projects_tree.topLevelItemCount()):
            item = self.projects_tree.topLevelItem(i)
            item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            
            if item_data and target_name.lower() in item_data.get('name', '').lower():
                self.projects_tree.setCurrentItem(item)
                self.projects_tree.scrollToItem(item)
                self._on_project_selected(item, 0)
                
                # Expand item
                if item_data.get('type') == 'Project' and not item_data.get('_loaded'):
                    self._on_project_expanded(item)
                
                self.statusBar().showMessage(f"✅ Selected: {item_data.get('name')}")
                logger.info(f"Found and selected similar item: {item_data.get('name')}")
                return
        
        logger.warning(f"Could not find bookmarked item: {target_name}")
        self.statusBar().showMessage(f"⚠️ Bookmark loaded but item not found in search results")
    
    def _update_destination_label(self):
        """Update destination label with selected project info"""
        if not self.selected_project:
            self.destination_label.setText('<span style="color: #f0ad4e;">Select a project first</span>')
            return
        
        name = self.selected_project.get('name', 'Unknown')
        item_type = self.selected_project.get('type', 'Project')
        
        self.destination_label.setText(
            f'<span style="color: #5cb85c; font-weight: bold;">{name}</span>'
            f'<span style="color: #888;"> ({item_type})</span>'
        )
    
    def _update_buttons(self):
        """Update button states based on selection"""
        has_selection = self.selected_project is not None
        self.dry_run_btn.setEnabled(has_selection)
        self.create_btn.setEnabled(has_selection)
    
    def _remove_bookmark(self, bm_data: Dict):
        """Remove bookmark"""
        if self.bookmarks.remove(bm_data.get('id')):
            self._refresh_bookmarks_list()
            self.statusBar().showMessage(f"Removed '{bm_data['name']}' from bookmarks")
            logger.info(f"Removed project from bookmarks: {bm_data['name']}")
    
    def _create_shots_panel(self) -> QtWidgets.QWidget:
        """Create shots panel"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(5, 0, 0, 0)
        
        # Header
        header = QtWidgets.QHBoxLayout()
        
        shots_label = QtWidgets.QLabel()
        shots_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        shots_label.setText('<span style="color: #5cb85c; font-size: 14px; font-weight: bold;">📋 Shots to Create</span>')
        header.addWidget(shots_label)
        
        arrow_label = QtWidgets.QLabel("→")
        arrow_label.setStyleSheet("color: #d9d9d9; font-size: 16px;")
        header.addWidget(arrow_label)
        
        self.destination_label = QtWidgets.QLabel()
        self.destination_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.destination_label.setText('<span style="color: #f0ad4e;">Select a project first</span>')
        header.addWidget(self.destination_label)
        
        header.addStretch()
        
        # Load buttons
        load_timeline_btn = QtWidgets.QPushButton("📥 Load from Timeline")
        load_timeline_btn.setStyleSheet("background-color: #5a5a8a;")
        load_timeline_btn.clicked.connect(self._load_from_timeline)
        header.addWidget(load_timeline_btn)
        
        demo_btn = QtWidgets.QPushButton("📋 Demo Data")
        demo_btn.clicked.connect(lambda: self.shot_table.load_demo_data())
        header.addWidget(demo_btn)
        
        layout.addLayout(header)
        
        # Shot Table
        self.shot_table = ShotTableWidget()
        layout.addWidget(self.shot_table)
        
        # Settings panel
        settings_panel = self._create_settings_panel()
        layout.addWidget(settings_panel)
        
        # Action buttons
        actions = self._create_action_buttons()
        layout.addLayout(actions)
        
        return panel
    
    def _create_settings_panel(self) -> QtWidgets.QWidget:
        """Create export settings panel"""
        group = QtWidgets.QGroupBox("Export Settings")
        layout = QtWidgets.QGridLayout(group)
        
        # Preset path
        layout.addWidget(QtWidgets.QLabel("Flame Export Preset:"), 0, 0)
        self.preset_edit = QtWidgets.QLineEdit(self.settings['preset_path'])
        layout.addWidget(self.preset_edit, 0, 1)
        preset_browse = QtWidgets.QPushButton("...")
        preset_browse.setMaximumWidth(30)
        preset_browse.clicked.connect(self._browse_preset)
        layout.addWidget(preset_browse, 0, 2)
        
        # Thumbnail output dir
        layout.addWidget(QtWidgets.QLabel("Thumbnail Output:"), 1, 0)
        self.output_edit = QtWidgets.QLineEdit(self.settings['output_dir'])
        layout.addWidget(self.output_edit, 1, 1)
        output_browse = QtWidgets.QPushButton("...")
        output_browse.setMaximumWidth(30)
        output_browse.clicked.connect(self._browse_output)
        layout.addWidget(output_browse, 1, 2)
        
        # Video output dir
        layout.addWidget(QtWidgets.QLabel("Video Output:"), 2, 0)
        self.video_output_edit = QtWidgets.QLineEdit(self.settings.get('video_dir', os.path.expanduser("~/flame_videos")))
        layout.addWidget(self.video_output_edit, 2, 1)
        video_browse = QtWidgets.QPushButton("...")
        video_browse.setMaximumWidth(30)
        video_browse.clicked.connect(self._browse_video_output)
        layout.addWidget(video_browse, 2, 2)
        
        # Checkboxes - Thumbnails
        self.export_check = QtWidgets.QCheckBox("Export thumbnails from Flame")
        self.export_check.setChecked(self.settings['export_thumbs'])
        layout.addWidget(self.export_check, 3, 0, 1, 2)
        
        self.upload_check = QtWidgets.QCheckBox("Upload thumbnails to ftrack")
        self.upload_check.setChecked(self.settings['upload_thumbs'])
        layout.addWidget(self.upload_check, 3, 2, 1, 1)
        
        # Checkboxes - Videos
        self.export_video_check = QtWidgets.QCheckBox("Export videos (H.264/MP4)")
        self.export_video_check.setChecked(self.settings.get('export_videos', False))
        layout.addWidget(self.export_video_check, 4, 0, 1, 2)
        
        self.upload_version_check = QtWidgets.QCheckBox("Upload as versions to ftrack")
        self.upload_version_check.setChecked(self.settings.get('upload_versions', False))
        layout.addWidget(self.upload_version_check, 4, 2, 1, 1)
        
        return group
    
    def _create_action_buttons(self) -> QtWidgets.QHBoxLayout:
        """Create action buttons"""
        layout = QtWidgets.QHBoxLayout()
        
        layout.addStretch()
        
        # Dry Run
        self.dry_run_btn = QtWidgets.QPushButton("🔍 Dry Run (Preview)")
        self.dry_run_btn.clicked.connect(lambda: self._execute(dry_run=True))
        self.dry_run_btn.setEnabled(False)
        layout.addWidget(self.dry_run_btn)
        
        # Create
        self.create_btn = QtWidgets.QPushButton("🚀 Create in ftrack")
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a8a5a;
                color: white;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #6a9a6a; }
            QPushButton:disabled { background-color: #3a5a3a; color: #888888; }
        """)
        self.create_btn.clicked.connect(lambda: self._execute(dry_run=False))
        self.create_btn.setEnabled(False)
        layout.addWidget(self.create_btn)
        
        return layout
    
    # =========================================================================
    # BROWSE HANDLERS
    # =========================================================================
    
    def _browse_preset(self):
        """Select export preset"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Export Preset",
            "/opt/Autodesk/shared/export/presets",
            "XML Files (*.xml);;All Files (*)"
        )
        if path:
            self.preset_edit.setText(path)
            self.settings['preset_path'] = path
    
    def _browse_output(self):
        """Select thumbnail output directory"""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Thumbnail Output Directory",
            self.output_edit.text() or os.path.expanduser("~")
        )
        if path:
            self.output_edit.setText(path)
            self.settings['output_dir'] = path
    
    def _browse_video_output(self):
        """Select video output directory"""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Video Output Directory",
            self.video_output_edit.text() or os.path.expanduser("~")
        )
        if path:
            self.video_output_edit.setText(path)
            self.settings['video_dir'] = path
    
    # =========================================================================
    # FTRACK CONNECTION
    # =========================================================================
    
    def _connect_ftrack(self):
        """Connect to ftrack (without loading projects)"""
        # Check if mock mode was explicitly requested
        if self.use_mock:
            self.ftrack.enable_mock_mode()
            self._update_connection_status(True)
            self._show_search_hint()
            self.statusBar().showMessage("DEMO MODE - Type to search projects")
            return
        
        try:
            from ..config.credentials_manager import get_credentials, credentials_are_configured
            
            if not credentials_are_configured():
                self._update_connection_status(False)
                self.statusBar().showMessage("⚠️ Credentials not configured - click Credentials button")
                return
            
            creds = get_credentials()
            
            # Show connecting state
            self.projects_tree.clear()
            loading_item = QtWidgets.QTreeWidgetItem()
            loading_item.setText(0, "⏳ Connecting to ftrack...")
            loading_item.setText(1, "Please wait")
            self.projects_tree.addTopLevelItem(loading_item)
            self.statusBar().showMessage(f"🔄 Connecting to {creds['server']}...")
            
            # Process events to show the UI
            QtWidgets.QApplication.processEvents()
            
            # Connect to ftrack
            success, msg = self.ftrack.connect(
                server_url=creds['server'],
                api_user=creds['api_user'],
                api_key=creds['api_key']
            )
            
            if not success:
                self._update_connection_status(False)
                self.projects_tree.clear()
                error_item = QtWidgets.QTreeWidgetItem()
                error_item.setText(0, f"❌ {msg}")
                self.projects_tree.addTopLevelItem(error_item)
                self.statusBar().showMessage(f"❌ {msg}")
                return
            
            self._update_connection_status(True)
            
            # Show search hint (doesn't load projects automatically)
            self._show_search_hint()
            self.statusBar().showMessage(f"✅ Connected to {creds['server']} - Type to search projects")
            
        except Exception as e:
            logger.error(f"Error during connection: {e}")
            self._update_connection_status(False)
            self.projects_tree.clear()
            error_item = QtWidgets.QTreeWidgetItem()
            error_item.setText(0, f"❌ Error: {str(e)[:50]}")
            self.projects_tree.addTopLevelItem(error_item)
            self.statusBar().showMessage(f"❌ Connection error: {str(e)[:50]}")
    
    def _show_search_hint(self):
        """Show search hint to user"""
        self.projects_tree.clear()
        hint_item = QtWidgets.QTreeWidgetItem()
        hint_item.setText(0, "🔍 Type project name above to search")
        hint_item.setText(1, "")
        hint_item.setDisabled(True)
        self.projects_tree.addTopLevelItem(hint_item)
    
    def _on_search_text_changed(self, text: str):
        """Handler when search text changes - starts debounce timer"""
        # Cancel previous timer
        self._search_timer.stop()
        
        if len(text) >= 2:
            # Start search after 500ms of inactivity (debounce)
            self._search_timer.start(500)
        elif len(text) == 0:
            self._show_search_hint()
    
    def _search_projects(self):
        """Search projects by typed name"""
        search_text = self.search_input.text().strip()
        
        if len(search_text) < 2:
            self.statusBar().showMessage("⚠️ Type at least 2 characters to search")
            return
        
        logger.info(f"Searching for projects matching: '{search_text}'")
        
        # Show loading
        self.projects_tree.clear()
        loading_item = QtWidgets.QTreeWidgetItem()
        loading_item.setText(0, f"🔍 Searching '{search_text}'...")
        loading_item.setText(1, "")
        self.projects_tree.addTopLevelItem(loading_item)
        self.statusBar().showMessage(f"🔍 Searching projects matching '{search_text}'...")
        QtWidgets.QApplication.processEvents()
        
        try:
            # Search projects by name
            projects = self.ftrack.search_projects(search_text)
            
            if projects:
                logger.info(f"Found {len(projects)} projects matching '{search_text}'")
                self._populate_projects_tree(projects)
                self.statusBar().showMessage(f"✅ Found {len(projects)} projects matching '{search_text}'")
            else:
                logger.warning(f"No projects found matching '{search_text}'")
                self.projects_tree.clear()
                no_result = QtWidgets.QTreeWidgetItem()
                no_result.setText(0, f"No projects found for '{search_text}'")
                no_result.setText(1, "")
                no_result.setDisabled(True)
                self.projects_tree.addTopLevelItem(no_result)
                self.statusBar().showMessage(f"⚠️ No projects found matching '{search_text}'")
                
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.projects_tree.clear()
            error_item = QtWidgets.QTreeWidgetItem()
            error_item.setText(0, f"❌ Error: {str(e)[:40]}")
            self.projects_tree.addTopLevelItem(error_item)
            self.statusBar().showMessage(f"❌ Search error: {str(e)[:50]}")
    
    def _populate_projects_tree(self, projects: list):
        """Populate tree with projects"""
        self.projects_tree.clear()
        
        logger.info(f"Populating tree with {len(projects)} projects")
        
        for proj in projects:
            # Create item with icon indicating it can be expanded
            item = QtWidgets.QTreeWidgetItem()
            item.setText(0, f"📁 {proj['name']}")
            item.setText(1, "Project")
            
            # Store project data
            proj['type'] = 'Project'
            proj['_loaded'] = False
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, proj)
            
            # Add placeholder to enable expansion
            placeholder = QtWidgets.QTreeWidgetItem()
            placeholder.setText(0, "⏳ Loading...")
            placeholder.setText(1, "")
            item.addChild(placeholder)
            
            self.projects_tree.addTopLevelItem(item)
        
        # Adjust column width
        self.projects_tree.resizeColumnToContents(0)
    
    def _load_projects(self):
        """Wrapper to reconnect"""
        self._connect_ftrack()
    
    def _refresh_projects(self):
        """Reconnect and clear search"""
        self.search_input.clear()
        if hasattr(self.ftrack, 'reset_cache'):
            self.ftrack.reset_cache()
        self._connect_ftrack()
    
    def _on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handler for tree item click - expands/collapses and selects"""
        # If has children (or placeholder), toggle expansion
        if item.childCount() > 0:
            if item.isExpanded():
                item.setExpanded(False)
            else:
                item.setExpanded(True)
        
        # Always call selection
        self._on_project_selected(item, column)
    
    def _on_project_expanded(self, item: QtWidgets.QTreeWidgetItem):
        """Load children when item is expanded"""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        # Update icon to indicate expanded
        entity_type = data.get('type', 'Project')
        icon = self._get_type_icon(entity_type, expanded=True)
        item.setText(0, f"{icon} {data['name']}")
        
        # Check if already loaded
        if data.get('_loaded', False):
            logger.debug(f"Item already loaded: {data.get('name', 'unknown')}")
            return
        
        logger.info(f"Expanding: {data.get('name', 'unknown')} ({entity_type})")
        
        # Remover placeholder
        item.takeChildren()
        
        # Fetch children
        parent_id = data['id']
        parent_type = data.get('type', 'Project')
        
        children = self.ftrack.get_project_children(parent_id, parent_type)
        logger.info(f"Got {len(children)} children for {data.get('name', 'unknown')}")
        
        # Determine project_id for propagation
        if parent_type == 'Project':
            root_project_id = parent_id
        else:
            root_project_id = data.get('project_id', parent_id)
        
        # Add children
        for child in children:
            child_item = QtWidgets.QTreeWidgetItem()
            
            # Icon based on type
            child_icon = self._get_type_icon(child['type'], expanded=False)
            child_item.setText(0, f"{child_icon} {child['name']}")
            child_item.setText(1, child['type'])
            
            # Store data
            child['project_id'] = root_project_id
            child['_loaded'] = False
            child_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, child)
            
            # Add placeholder if can have children
            if child.get('has_children', False):
                placeholder = QtWidgets.QTreeWidgetItem()
                placeholder.setText(0, "⏳ Loading...")
                child_item.addChild(placeholder)
            
            item.addChild(child_item)
        
        # If no children, show indication
        if not children:
            empty_item = QtWidgets.QTreeWidgetItem()
            empty_item.setText(0, "(empty)")
            empty_item.setDisabled(True)
            item.addChild(empty_item)
        
        # Mark as loaded
        data['_loaded'] = True
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, data)
        
        # Adjust column width
        self.projects_tree.resizeColumnToContents(0)
    
    def _on_project_collapsed(self, item: QtWidgets.QTreeWidgetItem):
        """Handler when item is collapsed - updates icon"""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data:
            entity_type = data.get('type', 'Project')
            icon = self._get_type_icon(entity_type, expanded=False)
            item.setText(0, f"{icon} {data['name']}")
    
    def _get_type_icon(self, entity_type: str, expanded: bool = False) -> str:
        """Return appropriate icon for each entity type
        
        Args:
            entity_type: Entity type (Project, Folder, etc.)
            expanded: If item is expanded (shows different icon)
        
        Returns:
            Emoji representing the type
        """
        # Icons for collapsed (►) and expanded (▼) states
        if entity_type == 'Project':
            return '📂' if expanded else '📁'
        elif entity_type == 'Folder':
            return '📂' if expanded else '📁'
        
        # Other types don't change with expansion
        icons = {
            'Sequence': '🎬',
            'Shot': '🎯',
            'Task': '✅',
            'Episode': '📺',
            'AssetBuild': '🔧',
            'Milestone': '🏁',
        }
        return icons.get(entity_type, '📄')
    
    def _on_project_selected(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handler for project/folder/sequence selection"""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data:
            # Build path for display
            path_parts = []
            current = item
            while current:
                path_parts.insert(0, current.text(0))
                current = current.parent()
            
            path_str = " → ".join(path_parts)
            item_type = data.get('type', 'Project')
            
            self.destination_label.setText(
                f'<span style="color: #5cb85c; font-weight: bold;">{path_str}</span>'
                f'<span style="color: #888;"> ({item_type})</span>'
            )
            
            # Store selected item (could be Project, Folder, or Sequence)
            self.selected_project = data
            
            # Store the root project ID for API calls
            # Walk up to find the project
            root_item = item
            while root_item.parent():
                root_item = root_item.parent()
            root_data = root_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if root_data:
                self.selected_project['project_id'] = root_data['id']
                self.selected_project['project_name'] = root_data['name']
            
            # Pass ftrack context to shot table for autocomplete features
            project_id = self.selected_project.get('project_id', self.selected_project.get('id'))
            if self.ftrack and self.ftrack.session and project_id:
                self.shot_table.set_ftrack_context(self.ftrack.session, project_id)
            
            self.dry_run_btn.setEnabled(True)
            self.create_btn.setEnabled(True)
            
            # Enable bookmark button
            self.add_bookmark_btn.setEnabled(True)
            
            self.statusBar().showMessage(f"Selected: {data['name']} ({item_type})")
    
    # =========================================================================
    # LOAD DATA
    # =========================================================================
    
    def _load_from_timeline(self):
        """Load shots from timeline"""
        if self.flame_selection:
            count = self.shot_table.load_from_flame_selection(self.flame_selection)
            self.statusBar().showMessage(f"✅ {count} shots loaded from timeline")
        else:
            self.shot_table.load_demo_data()
            self.statusBar().showMessage("📋 Demo data loaded (no Flame selection)")
    
    # =========================================================================
    # SETTINGS / CONFIG
    # =========================================================================
    
    def _show_settings(self):
        """Show settings dialog"""
        # Update settings from fields
        self.settings['preset_path'] = self.preset_edit.text()
        self.settings['output_dir'] = self.output_edit.text()
        self.settings['export_thumbs'] = self.export_check.isChecked()
        self.settings['upload_thumbs'] = self.upload_check.isChecked()
        
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.settings = dialog.get_settings()
            
            # Update fields
            self.preset_edit.setText(self.settings['preset_path'])
            self.output_edit.setText(self.settings['output_dir'])
            self.export_check.setChecked(self.settings['export_thumbs'])
            self.upload_check.setChecked(self.settings['upload_thumbs'])
    
    def _open_credentials(self):
        """Open credentials configuration"""
        try:
            from ..config.credentials_manager import show_credentials_dialog
            if show_credentials_dialog(self):
                self._connect_ftrack()
        except Exception as e:
            logger.error(f"Error opening credentials: {e}")
    
    # =========================================================================
    # EXECUTE
    # =========================================================================
    
    def _execute(self, dry_run: bool = False):
        """
        Execute shot creation
        
        Steps:
        1. Export thumbnails (if enabled)
        2. Export videos (if enabled)
        3. Create shots/tasks in ftrack + upload thumbs/versions
        """
        if not self.selected_project:
            QtWidgets.QMessageBox.warning(self, "Warning", "Select a project first!")
            return
        
        shots = self.shot_table.get_shots_data(checked_only=True)
        
        if not shots:
            QtWidgets.QMessageBox.warning(self, "Warning", "No shots selected!")
            return
        
        # Update settings from UI
        self.settings['preset_path'] = self.preset_edit.text()
        self.settings['output_dir'] = self.output_edit.text()
        self.settings['video_dir'] = self.video_output_edit.text()
        self.settings['export_thumbs'] = self.export_check.isChecked()
        self.settings['upload_thumbs'] = self.upload_check.isChecked()
        self.settings['export_videos'] = self.export_video_check.isChecked()
        self.settings['upload_versions'] = self.upload_version_check.isChecked()
        
        # Group by sequence
        sequences = {}
        for shot in shots:
            seq = shot.get("Sequence", "DEFAULT")
            if seq not in sequences:
                sequences[seq] = []
            sequences[seq].append(shot)
        
        # Count tasks
        total_tasks = sum(
            len(s.get("Task Types", []).split(",")) if isinstance(s.get("Task Types"), str) else 1
            for s in shots
        )
        
        # Summary
        summary = f"{'[DRY RUN] ' if dry_run else ''}Create in: {self.selected_project['name']}\n\n"
        summary += f"📁 {len(sequences)} Sequence(s)\n"
        summary += f"🎬 {len(shots)} Shot(s)\n"
        summary += f"📋 {total_tasks} Task(s)\n"
        
        step_num = 1
        if self.settings['export_thumbs']:
            summary += f"\n🖼️ Step {step_num}: Export thumbnails from Flame"
            summary += f"\n   Output: {self.settings['output_dir']}"
            step_num += 1
        
        if self.settings['export_videos']:
            summary += f"\n🎥 Step {step_num}: Export videos (H.264/MP4)"
            summary += f"\n   Output: {self.settings['video_dir']}"
            step_num += 1
        
        summary += f"\n☁️ Step {step_num}: Create shots in ftrack"
        if self.settings['upload_thumbs']:
            summary += " + upload thumbnails"
        if self.settings['upload_versions']:
            summary += " + upload versions"
        
        if dry_run:
            # Show detailed preview
            details = "\n\n─────────────────────────────────\nDetails:\n"
            for seq_name, seq_shots in sequences.items():
                details += f"\n📁 {seq_name}:\n"
                for shot in seq_shots:
                    tasks = shot.get('Task Types', 'Compositing')
                    if isinstance(tasks, list):
                        tasks = ', '.join(tasks)
                    status = shot.get('Status', 'ready_to_start')
                    details += f"   🎬 {shot['Shot Name']} → {tasks} [{status}]\n"
            
            QtWidgets.QMessageBox.information(
                self, "Dry Run - Preview",
                summary + details + "\n\n✅ Simulation complete!\nNo data was created."
            )
            return
        
        # Confirmation
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Creation",
            summary + "\n\n─────────────────────────────────\nProceed?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        
        # Execute with progress dialog
        self._execute_with_progress(shots)
    
    def _execute_with_progress(self, shots: list):
        """Execute with step progress dialog"""
        
        # Define steps
        steps = []
        if self.settings['export_thumbs']:
            steps.append("Export Thumbnails")
        if self.settings['export_videos']:
            steps.append("Export Videos")
        steps.append("Create Shots & Upload")
        
        # Create dialog
        progress = StepProgressDialog(steps, self)
        progress.show()
        
        results = {
            'exported_thumbs': 0,
            'exported_videos': 0,
            'sequences': 0,
            'shots': 0,
            'tasks': 0,
            'conform_tasks': 0,
            'thumbnails': 0,
            'versions': 0,
            'errors': []
        }
        
        current_step = 0
        
        # =====================================================================
        # STEP 1: Export Thumbnails
        # =====================================================================
        
        if self.settings['export_thumbs']:
            progress.set_step(current_step)
            progress.log("Starting thumbnail export...")
            
            # Configure exporter
            self.exporter.thumb_preset_path = self.settings['preset_path']
            self.exporter.output_dir = self.settings['output_dir']
            
            # Progress callback
            def export_progress(step, current, total, msg):
                progress.set_progress(current, total, msg)
                progress.log(f"  {msg}")
            
            # Export
            if self.exporter.is_flame_available and self.flame_selection:
                export_results = self.exporter.export_thumbnails(
                    self.flame_selection,
                    shots,
                    export_progress
                )
                results['exported_thumbs'] = export_results.get('exported', 0)
                
                progress.log(f"✅ Exported {results['exported_thumbs']} thumbnails")
                
                if export_results.get('errors'):
                    for err in export_results['errors'][:5]:
                        progress.log(f"⚠️ {err}")
            else:
                progress.log("⚠️ Flame not available, skipping thumbnail export")
            
            current_step += 1
        
        # =====================================================================
        # STEP 2: Export Videos (H.264/MP4)
        # =====================================================================
        
        if self.settings['export_videos']:
            progress.set_step(current_step)
            progress.log("Starting video export (H.264/MP4)...")
            
            # Configure exporter
            self.exporter.video_preset_path = self.settings.get('video_preset_path', DEFAULT_VIDEO_PRESET_PATH)
            self.exporter.video_dir = self.settings['video_dir']
            
            # Progress callback
            def video_progress(step, current, total, msg):
                progress.set_progress(current, total, msg)
                progress.log(f"  {msg}")
            
            # Export
            if self.exporter.is_flame_available and self.flame_selection:
                video_results = self.exporter.export_videos(
                    self.flame_selection,
                    shots,
                    video_progress
                )
                results['exported_videos'] = video_results.get('exported', 0)
                
                progress.log(f"✅ Exported {results['exported_videos']} videos")
                
                if video_results.get('errors'):
                    for err in video_results['errors'][:5]:
                        progress.log(f"⚠️ {err}")
            else:
                progress.log("⚠️ Flame not available, skipping video export")
            
            current_step += 1
        
        # =====================================================================
        # STEP 3: Create Shots in ftrack
        # =====================================================================
        
        progress.set_step(current_step)
        progress.log("Creating shots in ftrack...")
        
        # Progress callback
        def ftrack_progress(step, current, total, msg):
            progress.set_progress(current, total, msg)
            if progress.is_canceled():
                return
        
        # Determine project_id and parent info
        # If user selected a Folder/Sequence, we need the root project_id
        project_id = self.selected_project.get('project_id', self.selected_project['id'])
        parent_id = self.selected_project['id']
        parent_type = self.selected_project.get('type', 'Project')
        
        # Create shots
        ftrack_results = self.ftrack.create_shots_batch(
            project_id=project_id,
            shots_data=shots,
            progress_callback=ftrack_progress,
            upload_thumbs=self.settings['upload_thumbs'],
            thumb_dir=self.settings['output_dir'],
            upload_versions=self.settings['upload_versions'],
            video_dir=self.settings['video_dir'],
            parent_id=parent_id,
            parent_type=parent_type
        )
        
        results['sequences'] = ftrack_results.get('sequences', 0)
        results['shots'] = ftrack_results.get('shots', 0)
        results['tasks'] = ftrack_results.get('tasks', 0)
        results['conform_tasks'] = ftrack_results.get('conform_tasks', 0)
        results['thumbnails'] = ftrack_results.get('thumbnails', 0)
        results['versions'] = ftrack_results.get('versions', 0)
        results['errors'].extend(ftrack_results.get('errors', []))
        
        progress.log(f"✅ Created {results['sequences']} sequences")
        progress.log(f"✅ Created {results['shots']} shots")
        progress.log(f"✅ Created {results['conform_tasks']} conform tasks (pending_review)")
        progress.log(f"✅ Created {results['tasks']} tasks")
        if self.settings['upload_thumbs']:
            progress.log(f"✅ Uploaded {results['thumbnails']} thumbnails")
        if self.settings['upload_versions']:
            progress.log(f"✅ Uploaded {results['versions']} versions")
        
        if results['errors']:
            progress.log(f"\n⚠️ Errors ({len(results['errors'])}):")
            for err in results['errors'][:5]:
                progress.log(f"   • {err}")
        
        # Complete
        progress.complete()
        progress.log("\n═══════════════════════════════════")
        progress.log("COMPLETE!")
        progress.log(f"Sequences: {results['sequences']}")
        progress.log(f"Shots: {results['shots']}")
        progress.log(f"Conform Tasks: {results['conform_tasks']}")
        progress.log(f"Tasks: {results['tasks']}")
        progress.log(f"Thumbnails: {results['thumbnails']}")
        progress.log(f"Versions: {results['versions']}")
        if results['errors']:
            progress.log(f"Errors: {len(results['errors'])}")
        
        self.statusBar().showMessage(
            f"✅ Created {results['shots']} shots, {results['conform_tasks']} conform, {results['tasks']} tasks, {results['versions']} versions"
        )
    
    # =========================================================================
    # CLOSE
    # =========================================================================
    
    def closeEvent(self, event):
        """Handler for window close - cleanup resources"""
        # Close log window
        if hasattr(self, 'log_window') and self.log_window:
            self.log_window.close()
        
        # Disconnect ftrack
        self.ftrack.disconnect()
        event.accept()


# =============================================================================
# HOOKS DO FLAME
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


def launch_ftrack_window(selection):
    """Launch the ftrack integration window"""
    global ftrack_window
    ftrack_window = FlameFtrackWindow(flame_selection=selection)
    ftrack_window.show()
    return ftrack_window


def get_media_panel_custom_ui_actions():
    """Hook do Flame para menu de contexto"""
    return [
        {
            "name": "ftrack Integration",
            "actions": [
                {
                    "name": "📤 Create Shots in ftrack",
                    "isVisible": scope_sequence,
                    "execute": launch_ftrack_window,
                    "waitCursor": False
                }
            ]
        }
    ]


# =============================================================================
# STANDALONE
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    app = QtWidgets.QApplication(sys.argv)
    
    window = FlameFtrackWindow(use_mock=True)
    window.show()
    
    sys.exit(app.exec())
