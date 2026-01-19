#!/usr/bin/env python3
"""
Flame-ftrack Integration - Interface Demo

Run this script to view the interface without needing Flame.
Uses MOCK mode (no real ftrack connection).

Usage:
    cd ~/flame_ftrack_integration
    source .venv/bin/activate
    python run_demo.py
"""

import sys
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Adiciona src ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6 import QtWidgets, QtCore, QtGui

# Importa componentes
from src.ftrack_api.ftrack_wrapper import FtrackConnectionMock, FtrackShot
from src.gui.advanced_features import NotesPanel, TimeTrackingWidget
from src.gui.shot_table import ShotTableWidget
from src.config.credentials_manager import FtrackCredentialsDialog, credentials_are_configured


# =============================================================================
# ESTILO FLAME
# =============================================================================

FLAME_STYLE = """
QWidget {
    background-color: #313131;
    color: #9a9a9a;
    font-family: "Segoe UI", "SF Pro Display", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #313131;
}

QTreeWidget {
    background-color: #2a2a2a;
    alternate-background-color: #2d2d2d;
    border: 1px solid #1a1a1a;
    border-radius: 3px;
}

QTreeWidget::item:selected {
    color: #d9d9d9;
    background-color: #474747;
}

QTreeWidget::item:hover {
    background-color: #3a3a3a;
}

QHeaderView::section {
    background-color: #393939;
    color: #9a9a9a;
    padding: 5px;
    border: none;
    border-right: 1px solid #2a2a2a;
}

QPushButton {
    color: #d9d9d9;
    background-color: #424142;
    border: none;
    border-radius: 3px;
    padding: 6px 12px;
    min-width: 60px;
}

QPushButton:hover {
    background-color: #4a4a4a;
}

QPushButton:pressed {
    background-color: #3a3a3a;
}

QLineEdit, QTextEdit {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 5px;
    color: #d9d9d9;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #4a6fa5;
}

QComboBox {
    background-color: #424142;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 5px 10px;
    color: #d9d9d9;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    selection-background-color: #4a6fa5;
}

QTableWidget {
    background-color: #2a2a2a;
    alternate-background-color: #2d2d2d;
    gridline-color: #3a3a3a;
    border: 1px solid #1a1a1a;
}

QTableWidget::item:selected {
    background-color: #474747;
}

QScrollBar:vertical {
    background-color: #2a2a2a;
    width: 10px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #555555;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #666666;
}

QSplitter::handle {
    background-color: #3a3a3a;
}

QTabWidget::pane {
    border: 1px solid #3a3a3a;
    border-radius: 3px;
}

QTabBar::tab {
    background-color: #353535;
    color: #9a9a9a;
    padding: 8px 16px;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
}

QTabBar::tab:selected {
    background-color: #424142;
    color: #d9d9d9;
}

QGroupBox {
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #9a9a9a;
}

QMessageBox {
    background-color: #313131;
}

QMessageBox QPushButton {
    min-width: 80px;
}
"""


# =============================================================================
# JANELA PRINCIPAL DE DEMO
# =============================================================================

class DemoWindow(QtWidgets.QMainWindow):
    """Demo window for Flame-ftrack integration"""
    
    def __init__(self):
        super().__init__()
        
        self.ftrack = FtrackConnectionMock()
        self.ftrack.connect()
        
        self._setup_ui()
        self._connect_signals()
        self._load_demo_data()
    
    def _setup_ui(self):
        """Setup interface"""
        self.setWindowTitle("Flame → ftrack Integration (DEMO MODE)")
        self.setMinimumSize(1400, 800)
        self.setStyleSheet(FLAME_STYLE)
        
        # Widget central
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        # Layout principal
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header = self._create_header()
        main_layout.addLayout(header)
        
        # Main content with splitter
        content_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # === LEFT PANEL: Projects ===
        left_panel = self._create_projects_panel()
        content_splitter.addWidget(left_panel)
        
        # === CENTER PANEL: Shots ===
        center_panel = self._create_shots_panel()
        content_splitter.addWidget(center_panel)
        
        # === RIGHT PANEL: Notes + Time ===
        right_panel = self._create_tools_panel()
        content_splitter.addWidget(right_panel)
        
        # Splitter proportions
        content_splitter.setSizes([300, 600, 350])
        
        main_layout.addWidget(content_splitter)
        
        # Barra de status
        self.statusBar().showMessage("🟢 DEMO MODE - Conectado ao ftrack (mock)")
        self.statusBar().setStyleSheet("background-color: #2a2a2a; padding: 5px;")
    
    def _create_header(self) -> QtWidgets.QHBoxLayout:
        """Create window header"""
        layout = QtWidgets.QHBoxLayout()
        
        # Title
        title = QtWidgets.QLabel("🔥 Flame → ftrack Integration")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #d9d9d9;")
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Configuration button
        config_btn = QtWidgets.QPushButton("⚙️ Configure ftrack")
        config_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        config_btn.clicked.connect(self._open_config)
        config_btn.setStyleSheet("""
            QPushButton {
                background-color: #424142;
                color: #d9d9d9;
                border: none;
                border-radius: 3px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        layout.addWidget(config_btn)
        
        # Connection status indicator
        self.connection_indicator = QtWidgets.QLabel("⚪ Not Configured")
        self.connection_indicator.setStyleSheet("color: #7a7a7a; margin-left: 10px;")
        layout.addWidget(self.connection_indicator)
        
        # Update indicator
        self._update_connection_status()
        
        # Mode indicator
        mode_label = QtWidgets.QLabel("⚠️ DEMO MODE")
        mode_label.setStyleSheet("""
            background-color: #a57a4a;
            color: white;
            padding: 5px 10px;
            border-radius: 3px;
            font-weight: bold;
            margin-left: 10px;
        """)
        layout.addWidget(mode_label)
        
        return layout
    
    def _open_config(self):
        """Open configuration dialog"""
        dialog = FtrackCredentialsDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._update_connection_status()
    
    def _update_connection_status(self):
        """Update connection status indicator"""
        if credentials_are_configured():
            self.connection_indicator.setText("🟢 Configured")
            self.connection_indicator.setStyleSheet("color: #8c8; margin-left: 10px;")
        else:
            self.connection_indicator.setText("⚪ Not Configured")
            self.connection_indicator.setStyleSheet("color: #7a7a7a; margin-left: 10px;")
    
    def _create_projects_panel(self) -> QtWidgets.QWidget:
        """Create projects panel"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 5, 0)
        
        # Title
        title = QtWidgets.QLabel("📁 Projects")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #d9d9d9;")
        layout.addWidget(title)
        
        # Filtro
        self.project_filter = QtWidgets.QLineEdit()
        self.project_filter.setPlaceholderText("🔍 Filter projects...")
        self.project_filter.textChanged.connect(self._filter_projects)
        layout.addWidget(self.project_filter)
        
        # Tree de projetos
        self.projects_tree = QtWidgets.QTreeWidget()
        self.projects_tree.setHeaderLabels(["Name", "Status"])
        self.projects_tree.setAlternatingRowColors(True)
        self.projects_tree.itemClicked.connect(self._on_project_selected)
        self.projects_tree.itemExpanded.connect(self._on_project_expanded)
        layout.addWidget(self.projects_tree)
        
        return panel
    
    def _create_shots_panel(self) -> QtWidgets.QWidget:
        """Create shots panel"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(5, 0, 5, 0)
        
        # Title + destination
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("🎬 Shots")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #d9d9d9;")
        header.addWidget(title)
        
        header.addWidget(QtWidgets.QLabel("→"))
        
        self.destination_label = QtWidgets.QLabel("Select a project/sequence")
        self.destination_label.setStyleSheet("color: #4a6fa5; font-weight: bold;")
        header.addWidget(self.destination_label)
        
        header.addStretch()
        layout.addLayout(header)
        
        # Shot Table Widget (new!)
        self.shot_table = ShotTableWidget()
        layout.addWidget(self.shot_table)
        
        # Action buttons
        actions = QtWidgets.QHBoxLayout()
        
        load_demo_btn = QtWidgets.QPushButton("📋 Load Demo Shots")
        load_demo_btn.clicked.connect(self._load_demo_shots)
        actions.addWidget(load_demo_btn)
        
        actions.addStretch()
        
        create_btn = QtWidgets.QPushButton("🚀 Create in ftrack")
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a8a5a;
                color: white;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a9a6a;
            }
        """)
        create_btn.clicked.connect(self._create_shots)
        actions.addWidget(create_btn)
        
        layout.addLayout(actions)
        
        return panel
    
    def _create_tools_panel(self) -> QtWidgets.QWidget:
        """Create tools panel (Notes + Time)"""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(5, 0, 0, 0)
        
        # Notes Panel
        self.notes_panel = NotesPanel()
        layout.addWidget(self.notes_panel)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3a3a3a;")
        layout.addWidget(line)
        
        # Time Tracking
        self.time_widget = TimeTrackingWidget()
        layout.addWidget(self.time_widget)
        
        return panel
    
    def _connect_signals(self):
        """Connect widget signals"""
        # Notes
        self.notes_panel.note_added.connect(self._on_note_added)
        
        # Time
        self.time_widget.time_logged.connect(self._on_time_logged)
    
    def _load_demo_data(self):
        """Load demo data"""
        # Projects
        projects = self.ftrack.get_projects()
        
        for proj in projects:
            item = QtWidgets.QTreeWidgetItem([proj['name'], proj['status']])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, proj)
            
            # Placeholder for children
            placeholder = QtWidgets.QTreeWidgetItem(["Loading..."])
            item.addChild(placeholder)
            
            self.projects_tree.addTopLevelItem(item)
        
        self.statusBar().showMessage(f"🟢 Loaded {len(projects)} projects (mock data)")
    
    def _filter_projects(self, text: str):
        """Filter projects"""
        for i in range(self.projects_tree.topLevelItemCount()):
            item = self.projects_tree.topLevelItem(i)
            match = text.lower() in item.text(0).lower()
            item.setHidden(not match)
    
    def _on_project_expanded(self, item: QtWidgets.QTreeWidgetItem):
        """Load sequences when project is expanded"""
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.takeChildren()
            
            proj_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if proj_data:
                sequences = self.ftrack.get_sequences(proj_data['id'])
                
                for seq in sequences:
                    seq_item = QtWidgets.QTreeWidgetItem([seq['name'], "Sequence"])
                    seq_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, seq)
                    item.addChild(seq_item)
                
                if not sequences:
                    empty = QtWidgets.QTreeWidgetItem(["(empty)", ""])
                    empty.setDisabled(True)
                    item.addChild(empty)
    
    def _on_project_selected(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handler for project/sequence selection"""
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data:
            # Build path
            path_parts = []
            current = item
            while current:
                path_parts.insert(0, current.text(0))
                current = current.parent()
            
            self.destination_label.setText(" → ".join(path_parts))
            self.selected_parent = data
            
            # Update Notes and Time
            self.notes_panel.set_entity(data['id'], data['name'])
            self.time_widget.set_task(data['id'], data['name'])
            
            # Load mock data
            self.notes_panel.load_notes([
                {'content': 'Initial setup complete', 'author': 'john.doe', 'date': '2025-01-15 10:30', 'category': 'Internal'},
                {'content': 'Client approved concept', 'author': 'jane.smith', 'date': '2025-01-14 15:45', 'category': 'Client'},
            ])
            
            self.time_widget.load_timelogs([
                {'duration_hours': 2.5, 'comment': 'Roto cleanup', 'user': 'john.doe'},
                {'duration_hours': 1.0, 'comment': 'Review notes', 'user': 'jane.smith'},
            ])
            
            self.statusBar().showMessage(f"Selected: {data['name']}")
    
    def _load_demo_shots(self):
        """Load demo shots"""
        self.shot_table.load_demo_data()
        self.statusBar().showMessage("Loaded demo shots")
    
    def _create_shots(self):
        """Simulate shot creation"""
        shots = self.shot_table.get_checked_shots()
        
        if not shots:
            QtWidgets.QMessageBox.warning(self, "Warning", "No shots checked")
            return
        
        # Group by sequence
        sequences = {}
        for shot in shots:
            seq = shot.get("Sequence", "Unknown")
            if seq not in sequences:
                sequences[seq] = []
            sequences[seq].append(shot)
        
        # Show summary
        summary = f"**{len(sequences)} Sequence(s) to create:**\n\n"
        for seq, seq_shots in sequences.items():
            summary += f"📁 **{seq}**\n"
            for shot in seq_shots[:3]:  # Show first 3
                tasks = shot.get("Task Types", [])
                if isinstance(tasks, list):
                    tasks = ", ".join(tasks)
                summary += f"   • {shot.get('Shot Name', '?')} → {tasks}\n"
            if len(seq_shots) > 3:
                summary += f"   ... and {len(seq_shots) - 3} more shots\n"
            summary += "\n"
        
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm",
            f"{summary}\nCreate {len(shots)} shot(s) in ftrack?\n\n(This is a demo - no actual creation)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # Count total tasks
            total_tasks = sum(
                len(s.get("Task Types", [])) if isinstance(s.get("Task Types"), list) else 1
                for s in shots
            )
            
            QtWidgets.QMessageBox.information(
                self, "Demo",
                f"✅ Would create:\n\n"
                f"• {len(sequences)} Sequences\n"
                f"• {len(shots)} Shots\n"
                f"• {total_tasks} Tasks\n\n"
                "In real mode, this would:\n"
                "• Create Sequence entities (if they don't exist)\n"
                "• Create Shot entities inside each Sequence\n"
                "• Create Tasks for each Shot\n"
                "• Upload thumbnails (if available)"
            )
            self.statusBar().showMessage(f"[DEMO] Would create {len(sequences)} sequences, {len(shots)} shots, {total_tasks} tasks")
    
    def _on_note_added(self, note_data: dict):
        """Handler when note is added"""
        logger.info(f"[DEMO] Note added: {note_data}")
        
        # In real mode, would call:
        # self.ftrack.create_note(note_data['entity_id'], note_data['content'], ...)
        
        self.statusBar().showMessage(f"[DEMO] Note added to {note_data['entity_id']}")
    
    def _on_time_logged(self, log_data: dict):
        """Handler when time is logged"""
        logger.info(f"[DEMO] Time logged: {log_data}")
        
        # In real mode, would call:
        # self.ftrack.create_timelog(log_data['task_id'], log_data['duration_hours'] * 3600, ...)
        
        self.statusBar().showMessage(
            f"[DEMO] Logged {log_data['duration_hours']:.2f}h to {log_data['task_id']}"
        )
    
    def closeEvent(self, event):
        """Handler for window close"""
        self.ftrack.disconnect()
        event.accept()


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("  Flame-ftrack Integration - DEMO MODE")
    print("=" * 60)
    print()
    print("This runs in MOCK mode without real ftrack connection.")
    print("Use this to preview the interface and test functionality.")
    print()
    
    app = QtWidgets.QApplication(sys.argv)
    
    # Configure default font
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    
    window = DemoWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
