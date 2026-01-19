"""
Shot Table Widget - Table for managing shots

Features:
- Multiple sequences (grouping)
- Multiple task types per shot
- Checkbox for selection
- Bulk editing
- CSV/Paste import
"""

import logging
from typing import List, Dict

from PySide6 import QtWidgets, QtCore, QtGui

from ..core.ftrack_manager import TASK_TYPES, STATUSES, DEFAULT_STATUS
from .dialogs import BulkEditDialog, ImportDialog

logger = logging.getLogger(__name__)


# =============================================================================
# SHOT TABLE WIDGET
# =============================================================================

class ShotTableWidget(QtWidgets.QWidget):
    """
    Shot table widget
    
    Signals:
        shots_changed: Emitted when shot list is modified
    """
    
    shots_changed = QtCore.Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # ftrack context for autocomplete
        self._ftrack_session = None
        self._ftrack_project_id = None
        self._cached_task_types = None  # Cache for task types
        self._loading_task_types = False  # Flag to prevent multiple loads
        self._setup_ui()
    
    def set_ftrack_context(self, session, project_id: str):
        """
        Set ftrack context for autocomplete features in dialogs
        
        Args:
            session: ftrack_api.Session instance
            project_id: Current project ID
        """
        self._ftrack_session = session
        self._ftrack_project_id = project_id
        self._cached_task_types = None  # Clear cache when project changes
        print(f"[ftrack] ShotTable: Context set - project_id={project_id}")
        
        # Pre-load task types in background
        self._preload_task_types()
    
    def _preload_task_types(self):
        """Pre-load task types from ftrack in background thread"""
        if self._loading_task_types:
            return
        
        if not self._ftrack_session or not self._ftrack_project_id:
            return
        
        self._loading_task_types = True
        
        # Use QThread for background loading
        from PySide6.QtCore import QThread, Signal
        
        class TaskTypeLoader(QThread):
            finished = Signal(list)
            
            def __init__(self, session, project_id):
                super().__init__()
                self.session = session
                self.project_id = project_id
            
            def run(self):
                try:
                    project = self.session.query(
                        f'Project where id is "{self.project_id}"'
                    ).one()
                    
                    schema = project['project_schema']
                    task_types = []
                    
                    for task_type in schema.get_types('Task'):
                        task_types.append(task_type['name'])
                    
                    self.finished.emit(sorted(task_types))
                except Exception as e:
                    print(f"[ftrack] Error pre-loading task types: {e}")
                    self.finished.emit([])
        
        def on_loaded(task_types):
            self._cached_task_types = task_types
            self._loading_task_types = False
            if task_types:
                print(f"[ftrack] ShotTable: ✓ Pre-loaded {len(task_types)} task types")
        
        self._loader_thread = TaskTypeLoader(self._ftrack_session, self._ftrack_project_id)
        self._loader_thread.finished.connect(on_loaded)
        self._loader_thread.start()
    
    def get_cached_task_types(self):
        """Get cached task types (or None if not loaded yet)"""
        return self._cached_task_types
    
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addLayout(toolbar)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        
        # Columns
        columns = ["✓", "Sequence", "Shot Name", "Task Types", "Status", "Description"]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        
        # Column widths
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 120)
        self.table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(self.table)
        
        # Info label
        self.info_label = QtWidgets.QLabel("0 shots | 0 selected | 0 checked")
        self.info_label.setStyleSheet("color: #666666; padding: 5px;")
        layout.addWidget(self.info_label)
        
        # Connect selection
        self.table.itemSelectionChanged.connect(self._update_info)
    
    def _create_toolbar(self) -> QtWidgets.QHBoxLayout:
        """Create toolbar with buttons"""
        toolbar = QtWidgets.QHBoxLayout()
        
        # Add/Remove
        add_btn = QtWidgets.QPushButton("➕ Add Row")
        add_btn.clicked.connect(lambda: self._add_row())
        toolbar.addWidget(add_btn)
        
        remove_btn = QtWidgets.QPushButton("➖ Remove")
        remove_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(remove_btn)
        
        toolbar.addWidget(self._create_separator())
        
        # Import
        import_btn = QtWidgets.QPushButton("📥 Import...")
        import_btn.clicked.connect(self._show_import_dialog)
        toolbar.addWidget(import_btn)
        
        toolbar.addStretch()
        
        # Bulk edit
        bulk_edit_btn = QtWidgets.QPushButton("✏️ Bulk Edit")
        bulk_edit_btn.setStyleSheet("background-color: #5a5a8a;")
        bulk_edit_btn.clicked.connect(self._show_bulk_edit)
        toolbar.addWidget(bulk_edit_btn)
        
        toolbar.addWidget(self._create_separator())
        
        # Selection
        select_all_btn = QtWidgets.QPushButton("☑️ All")
        select_all_btn.clicked.connect(self._select_all)
        toolbar.addWidget(select_all_btn)
        
        deselect_btn = QtWidgets.QPushButton("☐ None")
        deselect_btn.clicked.connect(self._deselect_all)
        toolbar.addWidget(deselect_btn)
        
        clear_btn = QtWidgets.QPushButton("🗑️ Clear")
        clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(clear_btn)
        
        return toolbar
    
    def _create_separator(self) -> QtWidgets.QFrame:
        """Create vertical separator"""
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        sep.setStyleSheet("color: #3a3a3a;")
        return sep
    
    def _update_info(self):
        """Update count info"""
        total = self.table.rowCount()
        selected = len(self._get_selected_rows())
        checked = len(self._get_checked_rows())
        self.info_label.setText(f"{total} shots | {selected} selected | {checked} checked")
    
    def _get_selected_rows(self) -> List[int]:
        """Return indices of selected rows in table"""
        return list(set(item.row() for item in self.table.selectedItems()))
    
    def _get_checked_rows(self) -> List[int]:
        """Return indices of rows with checkbox checked"""
        rows = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(QtWidgets.QCheckBox)
                if checkbox and checkbox.isChecked():
                    rows.append(row)
        return rows
    
    # -------------------------------------------------------------------------
    # ROW OPERATIONS
    # -------------------------------------------------------------------------
    
    def _add_row(self, data: Dict = None):
        """Add new row"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Checkbox
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(True)
        checkbox.stateChanged.connect(self._update_info)
        widget = QtWidgets.QWidget()
        cb_layout = QtWidgets.QHBoxLayout(widget)
        cb_layout.addWidget(checkbox)
        cb_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 0, widget)
        
        # Sequence (editable)
        seq = data.get("Sequence", "SEQ010") if data else "SEQ010"
        seq_item = QtWidgets.QTableWidgetItem(seq)
        # Store original shot data (including _segment, _sequence) in UserRole
        if data:
            seq_item.setData(QtCore.Qt.ItemDataRole.UserRole, data)
        self.table.setItem(row, 1, seq_item)
        
        # Shot Name (editable)
        shot = data.get("Shot Name", f"SHOT_{(row+1)*10:03d}") if data else f"SHOT_{(row+1)*10:03d}"
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(shot))
        
        # Task Types (editable ComboBox)
        task_combo = QtWidgets.QComboBox()
        task_combo.setEditable(True)
        task_combo.addItems(TASK_TYPES)
        if data and "Task Types" in data:
            tasks = data["Task Types"]
            if isinstance(tasks, list):
                tasks = ", ".join(tasks)
            task_combo.setCurrentText(tasks)
        else:
            task_combo.setCurrentText("Compositing")
        self.table.setCellWidget(row, 3, task_combo)
        
        # Status (ComboBox) - using production ftrack names
        status_combo = QtWidgets.QComboBox()
        status_combo.addItems(STATUSES)
        if data and "Status" in data:
            idx = status_combo.findText(data["Status"])
            if idx >= 0:
                status_combo.setCurrentIndex(idx)
            else:
                # Set default if not found
                idx = status_combo.findText(DEFAULT_STATUS)
                if idx >= 0:
                    status_combo.setCurrentIndex(idx)
        else:
            # Set default status
            idx = status_combo.findText(DEFAULT_STATUS)
            if idx >= 0:
                status_combo.setCurrentIndex(idx)
        self.table.setCellWidget(row, 4, status_combo)
        
        # Description (editable)
        desc = data.get("Description", "") if data else ""
        self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(desc))
        
        self._update_info()
        self.shots_changed.emit()
    
    def _remove_selected(self):
        """Remove selected rows"""
        rows = sorted(self._get_selected_rows(), reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self._update_info()
        self.shots_changed.emit()
    
    def _select_all(self):
        """Check all checkboxes"""
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(QtWidgets.QCheckBox)
                if checkbox:
                    checkbox.setChecked(True)
        self._update_info()
    
    def _deselect_all(self):
        """Uncheck all checkboxes"""
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                checkbox = widget.findChild(QtWidgets.QCheckBox)
                if checkbox:
                    checkbox.setChecked(False)
        self._update_info()
    
    def _clear_all(self):
        """Clear all rows"""
        self.table.setRowCount(0)
        self._update_info()
        self.shots_changed.emit()
    
    # -------------------------------------------------------------------------
    # IMPORT / EXPORT
    # -------------------------------------------------------------------------
    
    def _show_import_dialog(self):
        """Show import dialog"""
        dialog = ImportDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            shots = dialog.get_shots()
            for shot in shots:
                self._add_row(shot)
    
    def _show_bulk_edit(self):
        """Show bulk edit dialog"""
        selected_rows = self._get_selected_rows()
        if not selected_rows:
            selected_rows = self._get_checked_rows()
        
        if not selected_rows:
            QtWidgets.QMessageBox.information(
                self, "Bulk Edit", "Select rows to edit"
            )
            return
        
        # Pass ftrack context and cached task types for instant loading
        dialog = BulkEditDialog(
            parent=self,
            session=self._ftrack_session,
            project_id=self._ftrack_project_id,
            cached_task_types=self._cached_task_types
        )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            changes = dialog.get_values()
            self._apply_bulk_changes(selected_rows, changes)
    
    def _apply_bulk_changes(self, rows: List[int], changes: Dict):
        """Apply changes to multiple rows"""
        for row in rows:
            # Sequence - key is 'sequence' (lowercase)
            if changes.get("sequence"):
                item = self.table.item(row, 1)
                if item:
                    item.setText(changes["sequence"])
            
            # Task Types - key is 'tasks'
            if changes.get("tasks"):
                combo = self.table.cellWidget(row, 3)
                if combo:
                    combo.setCurrentText(changes["tasks"])
            
            # Status - key is 'status'
            if changes.get("status"):
                combo = self.table.cellWidget(row, 4)
                if combo:
                    idx = combo.findText(changes["status"])
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
            
            # Description - key is 'description'
            if changes.get("description"):
                item = self.table.item(row, 5)
                if item:
                    item.setText(changes["description"])
        
        self.shots_changed.emit()
        logger.info(f"Bulk edit applied to {len(rows)} rows")
    
    # -------------------------------------------------------------------------
    # DATA ACCESS
    # -------------------------------------------------------------------------
    
    def get_shots_data(self, checked_only: bool = True) -> List[Dict]:
        """
        Get shot data from table
        
        Args:
            checked_only: If True, return only checked rows
        
        Returns:
            List of dicts with shot data (includes _segment and _sequence if available)
        """
        shots = []
        
        for row in range(self.table.rowCount()):
            # Check checkbox
            if checked_only:
                widget = self.table.cellWidget(row, 0)
                if widget:
                    checkbox = widget.findChild(QtWidgets.QCheckBox)
                    if not checkbox or not checkbox.isChecked():
                        continue
            
            # Get data from table
            sequence_item = self.table.item(row, 1)
            shot_name_item = self.table.item(row, 2)
            task_combo = self.table.cellWidget(row, 3)
            status_combo = self.table.cellWidget(row, 4)
            description_item = self.table.item(row, 5)
            
            # Get original data from UserRole (includes _segment, _sequence)
            original_data = {}
            if sequence_item:
                stored_data = sequence_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if stored_data and isinstance(stored_data, dict):
                    original_data = stored_data
            
            # Build shot data with current table values
            shot_data = {
                "Sequence": sequence_item.text() if sequence_item else "SEQ010",
                "Shot Name": shot_name_item.text() if shot_name_item else "",
                "Task Types": task_combo.currentText() if task_combo else "Compositing",
                "Status": status_combo.currentText() if status_combo else DEFAULT_STATUS,
                "Description": description_item.text() if description_item else "",
                # Include _segment and _sequence from original data
                "_segment": original_data.get("_segment"),
                "_sequence": original_data.get("_sequence"),
            }
            
            if shot_data["Shot Name"]:
                shots.append(shot_data)
        
        return shots
    
    def load_shots_data(self, shots: List[Dict]):
        """
        Load shots into table
        
        Args:
            shots: List of shot dicts
        """
        self._clear_all()
        for shot in shots:
            self._add_row(shot)
    
    def load_from_flame_selection(self, selection) -> int:
        """
        Load shots from Flame selection
        
        Args:
            selection: Flame selection
        
        Returns:
            Number of shots loaded
        """
        from ..core.flame_exporter import FlameExporter
        
        exporter = FlameExporter()
        shots = exporter.extract_shots_from_selection(selection)
        
        self._clear_all()
        for shot in shots:
            self._add_row(shot)
        
        return len(shots)
    
    def load_demo_data(self):
        """Load demo data for testing"""
        demo_shots = [
            {"Sequence": "SEQ010", "Shot Name": "vfx_010", "Task Types": "Compositing", 
             "Status": "ready_to_start", "Description": "Wide shot with CG extension"},
            {"Sequence": "SEQ010", "Shot Name": "vfx_020", "Task Types": "Compositing, Rotoscoping", 
             "Status": "ready_to_start", "Description": "Character close-up"},
            {"Sequence": "SEQ010", "Shot Name": "vfx_030", "Task Types": "Tracking, Compositing", 
             "Status": "ready_to_start", "Description": "Camera tracking required"},
            {"Sequence": "SEQ020", "Shot Name": "vfx_040", "Task Types": "FX, Compositing", 
             "Status": "ready_to_start", "Description": "Explosion effect"},
            {"Sequence": "SEQ020", "Shot Name": "vfx_050", "Task Types": "Compositing", 
             "Status": "ready_to_start", "Description": "Sky replacement"},
            {"Sequence": "SEQ020", "Shot Name": "vfx_060", "Task Types": "Matte Painting", 
             "Status": "ready_to_start", "Description": "Background extension"},
        ]
        
        self._clear_all()
        for shot in demo_shots:
            self._add_row(shot)
