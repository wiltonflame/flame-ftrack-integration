"""
Time Tracker Widget - ftrack time tracking

Features:
- Persistent window (doesn't close when changing project)
- Mini floating window when minimized
- List of user's "In Progress" tasks (auto-detects server status format)
- Timer with start/pause/stop
- Manual time entry
- Auto-pause on inactivity
- Visual alert when paused
- Saves time logs to ftrack
- Task history for quick access
- Confirmation when switching tasks with active timer
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from PySide6 import QtWidgets, QtCore, QtGui

from .styles import FLAME_STYLE

logger = logging.getLogger(__name__)

# Inactivity timeout for auto-pause (in seconds)
INACTIVITY_TIMEOUT = 300  # 5 minutes

# Maximum items in history
MAX_HISTORY_ITEMS = 15


# =============================================================================
# MINI TIMER WIDGET - Floating compact window
# =============================================================================

class MiniTimerWidget(QtWidgets.QWidget):
    """
    Compact floating timer widget shown when main window is minimized.
    
    Features:
    - Always on top, small footprint
    - Shows current time and task
    - Play/Pause and Stop buttons
    - Click to expand back to main window
    """
    
    # Signals
    expand_requested = QtCore.Signal()
    play_pause_clicked = QtCore.Signal()
    stop_clicked = QtCore.Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_position = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup compact UI"""
        self.setWindowTitle("Timer")
        self.setFixedSize(280, 70)
        
        # Frameless, always on top, tool window
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.Tool
        )
        
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main container with rounded corners
        self.container = QtWidgets.QFrame(self)
        self.container.setGeometry(0, 0, 280, 70)
        self.container.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 2px solid #5bc0de;
                border-radius: 10px;
            }
        """)
        
        layout = QtWidgets.QHBoxLayout(self.container)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        
        # Timer and task info (left side)
        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setSpacing(2)
        
        # Timer display
        self.timer_label = QtWidgets.QLabel("00:00:00")
        self.timer_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #5cb85c;
            font-family: 'Consolas', 'Monaco', monospace;
        """)
        info_layout.addWidget(self.timer_label)
        
        # Task name
        self.task_label = QtWidgets.QLabel("No task selected")
        self.task_label.setStyleSheet("font-size: 10px; color: #888;")
        self.task_label.setMaximumWidth(150)
        info_layout.addWidget(self.task_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Buttons (right side)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(4)
        
        # Play/Pause button
        self.play_pause_btn = QtWidgets.QPushButton("⏸")
        self.play_pause_btn.setFixedSize(32, 32)
        self.play_pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                color: white;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
        """)
        self.play_pause_btn.clicked.connect(self.play_pause_clicked.emit)
        btn_layout.addWidget(self.play_pause_btn)
        
        # Stop button
        self.stop_btn = QtWidgets.QPushButton("⏹")
        self.stop_btn.setFixedSize(32, 32)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                color: white;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        btn_layout.addWidget(self.stop_btn)
        
        # Expand button
        self.expand_btn = QtWidgets.QPushButton("⬆")
        self.expand_btn.setFixedSize(32, 32)
        self.expand_btn.setToolTip("Expand to full window")
        self.expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #5bc0de;
                border: none;
                border-radius: 16px;
                font-size: 14px;
                color: white;
            }
            QPushButton:hover {
                background-color: #46b8da;
            }
        """)
        self.expand_btn.clicked.connect(self.expand_requested.emit)
        btn_layout.addWidget(self.expand_btn)
        
        layout.addLayout(btn_layout)
    
    def update_display(self, time_str: str, task_name: str, is_paused: bool, is_tracking: bool):
        """Update the mini timer display"""
        self.timer_label.setText(time_str)
        
        # Truncate task name if too long
        display_name = task_name if len(task_name) <= 20 else task_name[:17] + "..."
        self.task_label.setText(display_name)
        
        # Update timer color based on state
        if is_paused:
            self.timer_label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #f0ad4e;
                font-family: 'Consolas', 'Monaco', monospace;
            """)
            self.play_pause_btn.setText("▶")
            self.play_pause_btn.setStyleSheet("""
                QPushButton {
                    background-color: #5cb85c;
                    border: none;
                    border-radius: 16px;
                    font-size: 14px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #4cae4c;
                }
            """)
        elif is_tracking:
            self.timer_label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #5cb85c;
                font-family: 'Consolas', 'Monaco', monospace;
            """)
            self.play_pause_btn.setText("⏸")
            self.play_pause_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f0ad4e;
                    border: none;
                    border-radius: 16px;
                    font-size: 14px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #ec971f;
                }
            """)
        else:
            self.timer_label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #888;
                font-family: 'Consolas', 'Monaco', monospace;
            """)
            self.play_pause_btn.setText("▶")
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if event.buttons() == QtCore.Qt.MouseButton.LeftButton and self._drag_position:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()
    
    def mouseDoubleClickEvent(self, event):
        """Double click to expand"""
        self.expand_requested.emit()


# =============================================================================
# HISTORY MANAGER
# =============================================================================

class TaskHistoryManager:
    """Manages history of accessed tasks/projects"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.history_file = self.config_dir / "time_tracker_history.json"
        self._history: List[Dict] = []
        self._load()
    
    def _load(self):
        """Load history from file"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self._history = data.get('history', [])
                    logger.info(f"Loaded {len(self._history)} history items")
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
            self._history = []
    
    def _save(self):
        """Save history to file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump({'history': self._history}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def add(self, task: Dict) -> bool:
        """Add task to history"""
        if not task or not task.get('id'):
            return False
        
        # Remove if already exists (to move to top)
        self._history = [h for h in self._history if h.get('id') != task.get('id')]
        
        # Create history entry
        history_entry = {
            'id': task.get('id'),
            'name': task.get('name'),
            'project': task.get('project'),
            'parent': task.get('parent'),
            'accessed_at': datetime.now().isoformat(),
            'access_count': 1
        }
        
        # Look for existing entry to increment counter
        for h in self._history:
            if h.get('id') == task.get('id'):
                history_entry['access_count'] = h.get('access_count', 0) + 1
                break
        
        # Add at beginning
        self._history.insert(0, history_entry)
        
        # Limit size
        if len(self._history) > MAX_HISTORY_ITEMS:
            self._history = self._history[:MAX_HISTORY_ITEMS]
        
        self._save()
        return True
    
    def get_all(self) -> List[Dict]:
        """Return all history"""
        return self._history.copy()
    
    def clear(self):
        """Clear history"""
        self._history = []
        self._save()
    
    def remove(self, task_id: str):
        """Remove item from history"""
        self._history = [h for h in self._history if h.get('id') != task_id]
        self._save()


# =============================================================================
# INACTIVITY DETECTOR
# =============================================================================

class InactivityDetector(QtCore.QObject):
    """Detects user inactivity"""
    
    inactivity_detected = QtCore.Signal()
    activity_detected = QtCore.Signal()
    
    def __init__(self, timeout_seconds: int = INACTIVITY_TIMEOUT, parent=None):
        super().__init__(parent)
        self.timeout = timeout_seconds
        self.last_activity = time.time()
        self.is_inactive = False
        
        self._check_timer = QtCore.QTimer(self)
        self._check_timer.timeout.connect(self._check_inactivity)
        self._check_timer.start(10000)
    
    def register_activity(self):
        """Register user activity"""
        self.last_activity = time.time()
        if self.is_inactive:
            self.is_inactive = False
            self.activity_detected.emit()
    
    def _check_inactivity(self):
        """Check if there was inactivity"""
        elapsed = time.time() - self.last_activity
        if elapsed >= self.timeout and not self.is_inactive:
            self.is_inactive = True
            self.inactivity_detected.emit()
    
    def get_idle_time(self) -> int:
        """Return idle time in seconds"""
        return int(time.time() - self.last_activity)


# =============================================================================
# TIME TRACKER WINDOW
# =============================================================================

class TimeTrackerWindow(QtWidgets.QWidget):
    """
    Persistent Time Tracking Window
    
    Features:
    - Doesn't close when changing Flame project
    - Mini floating window when minimized
    - Manual time entry
    - Auto-pause on inactivity
    - Alert when paused
    - Task/project history for quick access
    - Confirmation when switching tasks with active timer
    """
    
    def __init__(self, ftrack_manager=None, parent=None):
        super().__init__(parent)
        
        self.ftrack = ftrack_manager
        self.current_task = None
        self.is_tracking = False
        self.is_paused = False
        self.start_time = None
        self.elapsed_seconds = 0
        self.pause_start = None
        self._all_tasks = []
        
        # History manager
        self.history_manager = TaskHistoryManager()
        
        # Mini timer widget
        self.mini_timer = MiniTimerWidget()
        self.mini_timer.expand_requested.connect(self._expand_from_mini)
        self.mini_timer.play_pause_clicked.connect(self._toggle_pause)
        self.mini_timer.stop_clicked.connect(self._stop_tracking)
        
        # Inactivity detector
        self.inactivity_detector = InactivityDetector(INACTIVITY_TIMEOUT, self)
        self.inactivity_detector.inactivity_detected.connect(self._on_inactivity)
        self.inactivity_detector.activity_detected.connect(self._on_activity_resumed)
        
        self._setup_ui()
        self._setup_timers()
        
        # Event filter to detect activity
        QtWidgets.QApplication.instance().installEventFilter(self)
        
        # Load tasks on startup
        QtCore.QTimer.singleShot(500, self._load_my_tasks)
    
    def changeEvent(self, event):
        """Handle window state changes - show mini timer when minimized"""
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                # Window was minimized - show mini timer
                self._show_mini_timer()
        super().changeEvent(event)
    
    def _show_mini_timer(self):
        """Show the mini timer widget"""
        # Position mini timer at bottom-right of screen
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        x = screen.width() - self.mini_timer.width() - 20
        y = screen.height() - self.mini_timer.height() - 80
        self.mini_timer.move(x, y)
        
        # Update mini timer display
        task_name = self.current_task['name'] if self.current_task else "No task"
        time_str = self._format_time(self.elapsed_seconds)
        self.mini_timer.update_display(time_str, task_name, self.is_paused, self.is_tracking)
        
        self.mini_timer.show()
        logger.info("Mini timer shown")
    
    def _expand_from_mini(self):
        """Expand back to main window from mini timer"""
        self.mini_timer.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        logger.info("Expanded from mini timer")
    
    def _setup_ui(self):
        """Setup user interface"""
        self.setWindowTitle("⏱️ ftrack Time Tracker")
        self.setMinimumSize(450, 650)
        self.setStyleSheet(FLAME_STYLE)
        
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window |
            QtCore.Qt.WindowType.WindowMinimizeButtonHint |
            QtCore.Qt.WindowType.WindowCloseButtonHint
        )
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header with options
        header_layout = QtWidgets.QHBoxLayout()
        
        header = QtWidgets.QLabel()
        header.setTextFormat(QtCore.Qt.TextFormat.RichText)
        header.setText(
            '<span style="font-size: 16px; font-weight: bold; color: #5bc0de;">'
            '⏱️ Time Tracker</span>'
        )
        header_layout.addWidget(header)
        
        header_layout.addStretch()
        
        # Always on top checkbox
        self.always_on_top_cb = QtWidgets.QCheckBox("📌 Always on top")
        self.always_on_top_cb.setStyleSheet("color: #888; font-size: 11px;")
        self.always_on_top_cb.toggled.connect(self._toggle_always_on_top)
        header_layout.addWidget(self.always_on_top_cb)
        
        layout.addLayout(header_layout)
        
        # Timer display
        self._create_timer_display(layout)
        
        # Task info
        self._create_task_info(layout)
        
        # Controls
        self._create_controls(layout)
        
        # Tab widget for Tasks and History
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #888;
                padding: 8px 16px;
                border: 1px solid #3a3a3a;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                color: #5bc0de;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3a3a3a;
            }
        """)
        
        # Tab 1: My Tasks
        tasks_tab = QtWidgets.QWidget()
        self._create_tasks_list(tasks_tab)
        self.tabs.addTab(tasks_tab, "📋 My Tasks")
        
        # Tab 2: History
        history_tab = QtWidgets.QWidget()
        self._create_history_list(history_tab)
        self.tabs.addTab(history_tab, "🕐 History")
        
        # Tab 3: Manual Entry
        manual_tab = QtWidgets.QWidget()
        self._create_manual_entry_tab(manual_tab)
        self.tabs.addTab(manual_tab, "✏️ Manual")
        
        layout.addWidget(self.tabs)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Select a task to start tracking")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)
    
    def _create_timer_display(self, layout):
        """Create timer display"""
        timer_frame = QtWidgets.QFrame()
        timer_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        timer_layout = QtWidgets.QVBoxLayout(timer_frame)
        
        self.time_display = QtWidgets.QLabel("00:00:00")
        self.time_display.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: #00ff00;
            font-family: monospace;
        """)
        self.time_display.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        timer_layout.addWidget(self.time_display)
        
        self.timer_status = QtWidgets.QLabel("STOPPED")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #888;
            font-weight: bold;
        """)
        self.timer_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        timer_layout.addWidget(self.timer_status)
        
        layout.addWidget(timer_frame)
    
    def _create_task_info(self, layout):
        """Create selected task info area"""
        self.task_info_frame = QtWidgets.QFrame()
        self.task_info_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        info_layout = QtWidgets.QVBoxLayout(self.task_info_frame)
        
        self.task_name_label = QtWidgets.QLabel("No task selected")
        self.task_name_label.setStyleSheet("color: #f0ad4e; font-weight: bold; font-size: 13px;")
        info_layout.addWidget(self.task_name_label)
        
        self.task_project_label = QtWidgets.QLabel("")
        self.task_project_label.setStyleSheet("color: #888; font-size: 11px;")
        info_layout.addWidget(self.task_project_label)
        
        layout.addWidget(self.task_info_frame)
    
    def _create_controls(self, layout):
        """Create control buttons"""
        controls = QtWidgets.QHBoxLayout()
        
        self.start_btn = QtWidgets.QPushButton("▶️ Start")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #4cae4c; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.start_btn.setEnabled(False)
        controls.addWidget(self.start_btn)
        
        self.pause_btn = QtWidgets.QPushButton("⏸️ Pause")
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #eea236; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        self.pause_btn.setEnabled(False)
        controls.addWidget(self.pause_btn)
        
        self.stop_btn = QtWidgets.QPushButton("⏹️ Stop & Save")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #c9302c; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.stop_btn)
        
        layout.addLayout(controls)
    
    def _create_tasks_list(self, parent):
        """Create active tasks list (tasks with 'In Progress' status)"""
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(5, 10, 5, 5)
        
        # Header
        header_layout = QtWidgets.QHBoxLayout()
        
        tasks_label = QtWidgets.QLabel()
        tasks_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        tasks_label.setText(
            '<span style="color: #5bc0de; font-weight: bold;">'
            'My Tasks (In Progress)</span>'
        )
        header_layout.addWidget(tasks_label)
        
        header_layout.addStretch()
        
        refresh_btn = QtWidgets.QPushButton("🔄")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.setToolTip("Refresh tasks")
        refresh_btn.clicked.connect(self._load_my_tasks)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Search/Filter field
        filter_layout = QtWidgets.QHBoxLayout()
        
        filter_label = QtWidgets.QLabel("🔍")
        filter_layout.addWidget(filter_label)
        
        self.filter_input = QtWidgets.QLineEdit()
        self.filter_input.setPlaceholderText("Filter by project name...")
        self.filter_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 5px 10px;
                color: #d9d9d9;
            }
            QLineEdit:focus {
                border-color: #5bc0de;
            }
        """)
        self.filter_input.textChanged.connect(self._filter_tasks)
        filter_layout.addWidget(self.filter_input)
        
        clear_btn = QtWidgets.QPushButton("✕")
        clear_btn.setFixedSize(25, 25)
        clear_btn.setToolTip("Clear filter")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #888;
            }
            QPushButton:hover {
                color: #fff;
            }
        """)
        clear_btn.clicked.connect(self._clear_filter)
        filter_layout.addWidget(clear_btn)
        
        layout.addLayout(filter_layout)
        
        # Tasks list
        self.tasks_list = QtWidgets.QListWidget()
        self.tasks_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #4a6fa5;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
        """)
        self.tasks_list.itemClicked.connect(self._on_task_selected)
        self.tasks_list.setMinimumHeight(100)
        layout.addWidget(self.tasks_list)
    
    def _create_history_list(self, parent):
        """Create history list"""
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(5, 10, 5, 5)
        
        # Header
        header_layout = QtWidgets.QHBoxLayout()
        
        history_label = QtWidgets.QLabel()
        history_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        history_label.setText(
            '<span style="color: #f0ad4e; font-weight: bold;">'
            'Recent Tasks & Projects</span>'
        )
        header_layout.addWidget(history_label)
        
        header_layout.addStretch()
        
        clear_history_btn = QtWidgets.QPushButton("🗑️ Clear")
        clear_history_btn.setFixedSize(60, 25)
        clear_history_btn.setToolTip("Clear history")
        clear_history_btn.clicked.connect(self._clear_history)
        header_layout.addWidget(clear_history_btn)
        
        layout.addLayout(header_layout)
        
        # Info label
        info_label = QtWidgets.QLabel()
        info_label.setText('<span style="color: #666; font-size: 10px;">Double-click to select a recent task</span>')
        layout.addWidget(info_label)
        
        # History list
        self.history_list = QtWidgets.QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2a2a2a;
            }
            QListWidget::item:selected {
                background-color: #5a6a5a;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
        """)
        self.history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        self.history_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_history_context_menu)
        layout.addWidget(self.history_list)
        
        # Load history
        self._refresh_history_list()
    
    def _refresh_history_list(self):
        """Update history list"""
        self.history_list.clear()
        
        history = self.history_manager.get_all()
        
        if not history:
            item = QtWidgets.QListWidgetItem("No recent tasks")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(QtGui.QColor("#666"))
            self.history_list.addItem(item)
            return
        
        for h in history:
            item = QtWidgets.QListWidgetItem()
            
            # Format text
            accessed_at = h.get('accessed_at', '')
            try:
                dt = datetime.fromisoformat(accessed_at)
                time_str = dt.strftime("%d/%m %H:%M")
            except:
                time_str = ""
            
            display_text = f"🎯 {h.get('name', 'Unknown')}"
            if h.get('project'):
                display_text += f"\n   📁 {h['project']}"
            if time_str:
                display_text += f"\n   🕐 {time_str}"
            
            item.setText(display_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, h)
            item.setToolTip(f"Access count: {h.get('access_count', 1)}")
            self.history_list.addItem(item)
    
    def _on_history_item_double_clicked(self, item):
        """Double-click on history selects the task"""
        task_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if task_data:
            self._select_task_with_confirmation(task_data)
    
    def _show_history_context_menu(self, position):
        """Context menu for history"""
        item = self.history_list.itemAt(position)
        if not item:
            return
        
        task_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not task_data:
            return
        
        menu = QtWidgets.QMenu(self)
        
        select_action = menu.addAction("▶️ Select")
        select_action.triggered.connect(lambda: self._select_task_with_confirmation(task_data))
        
        menu.addSeparator()
        
        remove_action = menu.addAction("🗑️ Remove from history")
        remove_action.triggered.connect(lambda: self._remove_from_history(task_data))
        
        menu.exec(self.history_list.mapToGlobal(position))
    
    def _remove_from_history(self, task_data: Dict):
        """Remove item from history"""
        self.history_manager.remove(task_data.get('id'))
        self._refresh_history_list()
    
    def _clear_history(self):
        """Clear all history"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear History",
            "Clear all task history?",
            QtWidgets.QMessageBox.StandardButton.Yes |
            QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self._refresh_history_list()
    
    # =========================================================================
    # MANUAL ENTRY TAB
    # =========================================================================
    
    def _create_manual_entry_tab(self, parent):
        """Create manual time entry tab"""
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Header
        header = QtWidgets.QLabel()
        header.setTextFormat(QtCore.Qt.TextFormat.RichText)
        header.setText(
            '<span style="color: #5bc0de; font-size: 13px; font-weight: bold;">'
            '✏️ Add Manual Time Entry</span>'
        )
        layout.addWidget(header)
        
        # Description
        desc = QtWidgets.QLabel("Log hours manually to any of your in-progress tasks.")
        desc.setStyleSheet("color: #888; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        
        # Task selector
        self.manual_task_combo = QtWidgets.QComboBox()
        self.manual_task_combo.setMinimumWidth(200)
        self.manual_task_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                color: #e0e0e0;
            }
            QComboBox:hover {
                border-color: #5bc0de;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                selection-background-color: #5bc0de;
                color: #e0e0e0;
            }
        """)
        form.addRow("Task:", self.manual_task_combo)
        
        # Time input row
        time_layout = QtWidgets.QHBoxLayout()
        
        # Hours
        self.manual_hours = QtWidgets.QSpinBox()
        self.manual_hours.setRange(0, 24)
        self.manual_hours.setValue(0)
        self.manual_hours.setSuffix(" h")
        self.manual_hours.setStyleSheet("""
            QSpinBox {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                color: #e0e0e0;
                min-width: 70px;
            }
            QSpinBox:hover {
                border-color: #5bc0de;
            }
        """)
        time_layout.addWidget(self.manual_hours)
        
        # Minutes
        self.manual_minutes = QtWidgets.QSpinBox()
        self.manual_minutes.setRange(0, 59)
        self.manual_minutes.setValue(0)
        self.manual_minutes.setSuffix(" min")
        self.manual_minutes.setSingleStep(15)
        self.manual_minutes.setStyleSheet("""
            QSpinBox {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                color: #e0e0e0;
                min-width: 80px;
            }
            QSpinBox:hover {
                border-color: #5bc0de;
            }
        """)
        time_layout.addWidget(self.manual_minutes)
        
        time_layout.addStretch()
        
        time_widget = QtWidgets.QWidget()
        time_widget.setLayout(time_layout)
        form.addRow("Duration:", time_widget)
        
        # Date selector
        self.manual_date = QtWidgets.QDateEdit()
        self.manual_date.setDate(QtCore.QDate.currentDate())
        self.manual_date.setCalendarPopup(True)
        self.manual_date.setStyleSheet("""
            QDateEdit {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                color: #e0e0e0;
                min-width: 120px;
            }
            QDateEdit:hover {
                border-color: #5bc0de;
            }
            QDateEdit::drop-down {
                border: none;
                padding-right: 10px;
            }
        """)
        form.addRow("Date:", self.manual_date)
        
        # Comment
        self.manual_comment = QtWidgets.QLineEdit()
        self.manual_comment.setPlaceholderText("Optional comment...")
        self.manual_comment.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                color: #e0e0e0;
            }
            QLineEdit:hover {
                border-color: #5bc0de;
            }
            QLineEdit:focus {
                border-color: #5bc0de;
            }
        """)
        form.addRow("Comment:", self.manual_comment)
        
        layout.addLayout(form)
        
        # Quick time buttons
        quick_layout = QtWidgets.QHBoxLayout()
        quick_label = QtWidgets.QLabel("Quick:")
        quick_label.setStyleSheet("color: #888; font-size: 11px;")
        quick_layout.addWidget(quick_label)
        
        for hours, label in [(0.25, "15m"), (0.5, "30m"), (1, "1h"), (2, "2h"), (4, "4h"), (8, "8h")]:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedSize(45, 28)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #4a4a4a;
                    border-radius: 4px;
                    color: #e0e0e0;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #5bc0de;
                }
            """)
            btn.clicked.connect(lambda checked, h=hours: self._set_manual_time(h))
            quick_layout.addWidget(btn)
        
        quick_layout.addStretch()
        layout.addLayout(quick_layout)
        
        layout.addStretch()
        
        # Submit button
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        self.manual_submit_btn = QtWidgets.QPushButton("📤 Submit Time Log")
        self.manual_submit_btn.setFixedHeight(40)
        self.manual_submit_btn.setMinimumWidth(180)
        self.manual_submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
            QPushButton:pressed {
                background-color: #449d44;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #666;
            }
        """)
        self.manual_submit_btn.clicked.connect(self._submit_manual_entry)
        btn_layout.addWidget(self.manual_submit_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Status label for manual entry
        self.manual_status = QtWidgets.QLabel("")
        self.manual_status.setStyleSheet("color: #888; font-size: 11px;")
        self.manual_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.manual_status)
    
    def _set_manual_time(self, hours: float):
        """Set manual time from quick button"""
        h = int(hours)
        m = int((hours - h) * 60)
        self.manual_hours.setValue(h)
        self.manual_minutes.setValue(m)
    
    def _update_manual_task_combo(self):
        """Update manual entry task combobox with available tasks"""
        self.manual_task_combo.clear()
        
        for task in self._all_tasks:
            display = f"{task['project']} / {task.get('parent', '')} / {task['name']}"
            self.manual_task_combo.addItem(display, task)
        
        # Select current task if any
        if self.current_task:
            for i in range(self.manual_task_combo.count()):
                task_data = self.manual_task_combo.itemData(i)
                if task_data and task_data.get('id') == self.current_task.get('id'):
                    self.manual_task_combo.setCurrentIndex(i)
                    break
    
    def _submit_manual_entry(self):
        """Submit manual time entry to ftrack"""
        # Get selected task
        task_data = self.manual_task_combo.currentData()
        if not task_data:
            self.manual_status.setText("⚠️ Please select a task")
            self.manual_status.setStyleSheet("color: #f0ad4e; font-size: 11px;")
            return
        
        # Get time
        hours = self.manual_hours.value()
        minutes = self.manual_minutes.value()
        total_hours = hours + (minutes / 60.0)
        
        if total_hours <= 0:
            self.manual_status.setText("⚠️ Please enter time duration")
            self.manual_status.setStyleSheet("color: #f0ad4e; font-size: 11px;")
            return
        
        # Get date
        selected_date = self.manual_date.date().toPython()
        
        # Get comment
        comment = self.manual_comment.text().strip()
        if not comment:
            comment = f"Manual entry from Flame Time Tracker"
        
        # Submit to ftrack
        try:
            if self.ftrack and not self.ftrack.is_mock:
                success = self.ftrack.create_timelog(
                    task_id=task_data['id'],
                    hours=total_hours,
                    comment=comment,
                    date=selected_date
                )
                
                if success:
                    self.manual_status.setText(f"✅ Logged {hours}h {minutes}m to {task_data['name']}")
                    self.manual_status.setStyleSheet("color: #5cb85c; font-size: 11px;")
                    
                    # Reset form
                    self.manual_hours.setValue(0)
                    self.manual_minutes.setValue(0)
                    self.manual_comment.clear()
                    
                    logger.info(f"Manual time entry: {total_hours:.2f}h to task {task_data['name']}")
                else:
                    self.manual_status.setText("❌ Failed to submit time log")
                    self.manual_status.setStyleSheet("color: #d9534f; font-size: 11px;")
            else:
                # Mock mode
                self.manual_status.setText(f"✅ [MOCK] Logged {hours}h {minutes}m to {task_data['name']}")
                self.manual_status.setStyleSheet("color: #5cb85c; font-size: 11px;")
                logger.info(f"[MOCK] Manual time entry: {total_hours:.2f}h to task {task_data['name']}")
                
        except Exception as e:
            self.manual_status.setText(f"❌ Error: {str(e)[:50]}")
            self.manual_status.setStyleSheet("color: #d9534f; font-size: 11px;")
            logger.error(f"Manual entry error: {e}")
    
    def _setup_timers(self):
        """Setup internal timers"""
        self._display_timer = QtCore.QTimer(self)
        self._display_timer.timeout.connect(self._update_display)
        self._display_timer.start(1000)
    
    # =========================================================================
    # EVENT FILTER - Detect activity
    # =========================================================================
    
    def eventFilter(self, obj, event):
        """Detect user activity events"""
        if event.type() in (
            QtCore.QEvent.Type.MouseMove,
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.KeyPress,
            QtCore.QEvent.Type.Wheel
        ):
            self.inactivity_detector.register_activity()
        return super().eventFilter(obj, event)
    
    # =========================================================================
    # INACTIVITY HANDLERS
    # =========================================================================
    
    def _on_inactivity(self):
        """Chamado quando detecta inatividade"""
        if self.is_tracking and not self.is_paused:
            logger.info("Inactivity detected - auto-pausing timer")
            self._pause_timer()
            self._show_inactivity_alert()
    
    def _on_activity_resumed(self):
        """Called when activity is resumed after inactivity"""
        logger.info("Activity resumed")
    
    def _show_inactivity_alert(self):
        """Show inactivity alert"""
        self.raise_()
        self.activateWindow()
        self.showNormal()
        
        self.timer_status.setText("⚠️ PAUSED (Inactivity)")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #f0ad4e;
            font-weight: bold;
            background-color: #3a3a1a;
            padding: 5px;
            border-radius: 3px;
        """)
        
        idle_time = self.inactivity_detector.get_idle_time()
        idle_minutes = idle_time // 60
        self.status_label.setText(
            f"⚠️ Timer paused after {idle_minutes} min of inactivity. "
            "Click Resume to continue."
        )
    
    # =========================================================================
    # TASK LOADING
    # =========================================================================
    
    def _load_my_tasks(self):
        """Load current user's tasks with 'In Progress' status"""
        self.tasks_list.clear()
        self._all_tasks = []
        
        if not self.ftrack or not self.ftrack.session:
            item = QtWidgets.QListWidgetItem("⚠️ Not connected to ftrack")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.tasks_list.addItem(item)
            self.status_label.setText("Click refresh after connecting to ftrack")
            return
        
        loading_item = QtWidgets.QListWidgetItem("⏳ Loading tasks...")
        self.tasks_list.addItem(loading_item)
        self.status_label.setText("🔄 Loading your active tasks...")
        QtWidgets.QApplication.processEvents()
        
        try:
            tasks = self.ftrack.get_my_tasks_in_progress()
            
            self.tasks_list.clear()
            
            if not tasks:
                item = QtWidgets.QListWidgetItem("No tasks in progress found")
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
                self.tasks_list.addItem(item)
                self.status_label.setText("No active tasks found for your user")
                return
            
            self._all_tasks = tasks
            self._populate_tasks_list(tasks)
            
            # Update manual entry combo
            self._update_manual_task_combo()
            
            self.status_label.setText(f"✅ {len(tasks)} tasks loaded")
            logger.info(f"Loaded {len(tasks)} tasks in progress")
            
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            self.tasks_list.clear()
            item = QtWidgets.QListWidgetItem(f"❌ Error: {str(e)[:50]}")
            self.tasks_list.addItem(item)
            self.status_label.setText(f"❌ Error loading tasks")
    
    def _populate_tasks_list(self, tasks: list):
        """Populate task list with provided tasks"""
        self.tasks_list.clear()
        
        for task in tasks:
            item = QtWidgets.QListWidgetItem()
            display_text = f"🎯 {task['name']}"
            if task.get('project'):
                display_text += f"\n   📁 {task['project']}"
            if task.get('parent'):
                display_text += f" > {task['parent']}"
            
            item.setText(display_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, task)
            self.tasks_list.addItem(item)
    
    def _filter_tasks(self, text: str):
        """Filter tasks by search text"""
        if not self._all_tasks:
            return
        
        filter_text = text.strip().lower()
        
        if not filter_text:
            self._populate_tasks_list(self._all_tasks)
            self.status_label.setText(f"✅ Showing all {len(self._all_tasks)} tasks")
            return
        
        filtered = [
            task for task in self._all_tasks
            if filter_text in task.get('project', '').lower() or
               filter_text in task.get('name', '').lower() or
               filter_text in task.get('parent', '').lower()
        ]
        
        self._populate_tasks_list(filtered)
        self.status_label.setText(f"🔍 Found {len(filtered)} of {len(self._all_tasks)} tasks")
    
    def _clear_filter(self):
        """Clear the filter"""
        self.filter_input.clear()
        if self._all_tasks:
            self._populate_tasks_list(self._all_tasks)
            self.status_label.setText(f"✅ Showing all {len(self._all_tasks)} tasks")
    
    def _on_task_selected(self, item: QtWidgets.QListWidgetItem):
        """Called when a task is selected"""
        task_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not task_data:
            return
        
        self._select_task_with_confirmation(task_data)
    
    def _select_task_with_confirmation(self, task_data: Dict):
        """Select task with confirmation if timer is active"""
        
        # If already tracking, show confirmation dialog
        if self.is_tracking:
            reply = self._show_project_change_dialog(task_data)
            
            if reply == "save_and_switch":
                self._stop_and_save()
            elif reply == "discard_and_switch":
                self._reset_timer()
            elif reply == "close_app":
                # Close application
                self.close()
                return
            else:  # cancel
                return
        
        # Seleciona a nova task
        self.current_task = task_data
        self._update_task_info()
        self.start_btn.setEnabled(True)
        self.status_label.setText(f"Selected: {task_data['name']} - Click Start to begin")
        
        # Add to history
        self.history_manager.add(task_data)
        self._refresh_history_list()
    
    def _show_project_change_dialog(self, new_task: Dict) -> str:
        """
        Show confirmation dialog when changing task/project
        
        Returns:
            'save_and_switch' - Save time and switch
            'discard_and_switch' - Discard time and switch
            'close_app' - Close application
            'cancel' - Cancel
        """
        current_time = self._format_time(self.elapsed_seconds)
        
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("⏱️ Timer Running")
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setText(
            f"<b>Timer is currently running!</b><br><br>"
            f"Current task: <b>{self.current_task['name']}</b><br>"
            f"Time tracked: <b>{current_time}</b><br><br>"
            f"New task: <b>{new_task['name']}</b><br><br>"
            "What would you like to do?"
        )
        
        # Custom buttons
        save_btn = msg_box.addButton("💾 Save && Switch", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg_box.addButton("🗑️ Discard && Switch", QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        close_btn = msg_box.addButton("🚪 Close App", QtWidgets.QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg_box.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(cancel_btn)
        msg_box.setStyleSheet(FLAME_STYLE)
        
        msg_box.exec()
        
        clicked = msg_box.clickedButton()
        
        if clicked == save_btn:
            return "save_and_switch"
        elif clicked == discard_btn:
            return "discard_and_switch"
        elif clicked == close_btn:
            return "close_app"
        else:
            return "cancel"
    
    def _update_task_info(self):
        """Update selected task info"""
        if self.current_task:
            self.task_name_label.setText(f"🎯 {self.current_task['name']}")
            project_text = self.current_task.get('project', '')
            if self.current_task.get('parent'):
                project_text += f" > {self.current_task['parent']}"
            self.task_project_label.setText(project_text)
        else:
            self.task_name_label.setText("No task selected")
            self.task_project_label.setText("")
    
    # =========================================================================
    # TIMER CONTROLS
    # =========================================================================
    
    def _on_start_clicked(self):
        """Start ou resume timer"""
        if self.is_paused:
            self._resume_timer()
        else:
            self._start_timer()
    
    def _on_pause_clicked(self):
        """Pause timer"""
        self._pause_timer()
    
    def _on_stop_clicked(self):
        """Stop e salvar"""
        self._stop_and_save()
    
    def _start_timer(self):
        """Inicia o timer"""
        if not self.current_task:
            return
        
        self.is_tracking = True
        self.is_paused = False
        self.start_time = datetime.now()
        self.elapsed_seconds = 0
        
        self.start_btn.setText("▶️ Resume")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        
        self.timer_status.setText("🔴 TRACKING")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #00ff00;
            font-weight: bold;
        """)
        
        self.time_display.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: #00ff00;
            font-family: monospace;
        """)
        
        self.status_label.setText(f"⏱️ Tracking time on: {self.current_task['name']}")
        logger.info(f"Started timer for task: {self.current_task['name']}")
    
    def _pause_timer(self):
        """Pausa o timer"""
        if not self.is_tracking:
            return
        
        self.is_paused = True
        self.pause_start = datetime.now()
        
        self.start_btn.setText("▶️ Resume")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        
        self.timer_status.setText("⏸️ PAUSED")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #f0ad4e;
            font-weight: bold;
        """)
        
        self.time_display.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: #f0ad4e;
            font-family: monospace;
        """)
        
        self.status_label.setText("⏸️ Timer paused - Click Resume to continue")
        logger.info("Timer paused")
    
    def _resume_timer(self):
        """Resume timer after pause"""
        if not self.is_tracking:
            return
        
        self.is_paused = False
        self.pause_start = None
        
        self.start_btn.setText("▶️ Resume")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        
        self.timer_status.setText("🔴 TRACKING")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #00ff00;
            font-weight: bold;
        """)
        
        self.time_display.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: #00ff00;
            font-family: monospace;
        """)
        
        self.status_label.setText(f"⏱️ Resumed tracking: {self.current_task['name']}")
        logger.info("Timer resumed")
    
    def _toggle_pause(self):
        """Alterna entre pausar e retomar o timer"""
        if not self.is_tracking:
            return
        
        if self.is_paused:
            self._resume_timer()
        else:
            self._pause_timer()
    
    def _stop_tracking(self):
        """Para o tracking e salva o tempo"""
        self._stop_and_save()
    
    def _stop_and_save(self):
        """Para o timer e salva no ftrack"""
        if not self.is_tracking:
            return
        
        total_seconds = self.elapsed_seconds
        hours = total_seconds / 3600
        
        time_str = self._format_time(total_seconds)
        reply = QtWidgets.QMessageBox.question(
            self,
            "Save Time Log?",
            f"Save {time_str} ({hours:.2f} hours) to:\n\n"
            f"Task: {self.current_task['name']}\n"
            f"Project: {self.current_task.get('project', 'N/A')}\n\n"
            "Save this time log?",
            QtWidgets.QMessageBox.StandardButton.Yes | 
            QtWidgets.QMessageBox.StandardButton.No |
            QtWidgets.QMessageBox.StandardButton.Cancel
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            return
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            success = self._save_time_log(total_seconds)
            if success:
                self.status_label.setText(f"✅ Saved {time_str} to ftrack")
            else:
                self.status_label.setText("❌ Error saving time log")
        else:
            self.status_label.setText("⚠️ Time log discarded")
        
        self._reset_timer()
    
    def _save_time_log(self, total_seconds: int) -> bool:
        """Salva time log no ftrack"""
        if not self.ftrack or not self.current_task:
            return False
        
        try:
            hours = total_seconds / 3600
            success = self.ftrack.create_timelog(
                task_id=self.current_task['id'],
                hours=hours,
                comment=f"Logged from Flame Time Tracker"
            )
            if success:
                logger.info(f"Time log saved: {hours:.2f} hours")
            return success
        except Exception as e:
            logger.error(f"Error saving time log: {e}")
            return False
    
    def _reset_timer(self):
        """Reseta o timer para estado inicial"""
        self.is_tracking = False
        self.is_paused = False
        self.start_time = None
        self.elapsed_seconds = 0
        self.pause_start = None
        
        self.time_display.setText("00:00:00")
        self.time_display.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: #00ff00;
            font-family: monospace;
        """)
        
        self.timer_status.setText("STOPPED")
        self.timer_status.setStyleSheet("""
            font-size: 14px;
            color: #888;
            font-weight: bold;
        """)
        
        self.start_btn.setText("▶️ Start")
        self.start_btn.setEnabled(self.current_task is not None)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
    
    def _update_display(self):
        """Update timer display and sync with mini timer"""
        if self.is_tracking and not self.is_paused:
            self.elapsed_seconds += 1
        
        time_str = self._format_time(self.elapsed_seconds)
        self.time_display.setText(time_str)
        
        # Update mini timer if visible
        if self.mini_timer.isVisible():
            task_name = self.current_task['name'] if self.current_task else "No task"
            self.mini_timer.update_display(time_str, task_name, self.is_paused, self.is_tracking)
    
    def _format_time(self, seconds: int) -> str:
        """Format seconds to HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    # =========================================================================
    # WINDOW EVENTS
    # =========================================================================
    
    def _toggle_always_on_top(self, checked: bool):
        """Toggle always on top window flag"""
        flags = self.windowFlags()
        if checked:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
        
        self.setWindowFlags(flags)
        self.show()
    
    def closeEvent(self, event):
        """Prevent accidental closing if timer is running, also close mini timer"""
        if self.is_tracking:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Timer Running",
                "Timer is still running!\n\n"
                "• Yes - Stop timer and close (time will be lost)\n"
                "• No - Keep window open",
                QtWidgets.QMessageBox.StandardButton.Yes | 
                QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                event.ignore()
                return
        
        # Close mini timer
        self.mini_timer.close()
        
        QtWidgets.QApplication.instance().removeEventFilter(self)
        event.accept()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

_time_tracker_window = None


def show_time_tracker(ftrack_manager=None):
    """
    Show or create the Time Tracker window.
    
    The window is kept as singleton to persist between calls.
    """
    global _time_tracker_window
    
    if _time_tracker_window is None:
        _time_tracker_window = TimeTrackerWindow(ftrack_manager=ftrack_manager)
    elif ftrack_manager and _time_tracker_window.ftrack != ftrack_manager:
        _time_tracker_window.ftrack = ftrack_manager
        _time_tracker_window._load_my_tasks()
    
    _time_tracker_window.show()
    _time_tracker_window.raise_()
    _time_tracker_window.activateWindow()
    
    return _time_tracker_window


def get_time_tracker_window():
    """Return the existing Time Tracker window or None"""
    return _time_tracker_window
