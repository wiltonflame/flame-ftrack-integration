"""
Dialogs - Auxiliary dialog windows

Dialogs for:
- Bulk Edit: Batch editing of shots
- Import: CSV/Paste import
- Progress: Progress with steps
"""

import os
import csv
import logging
from typing import List, Dict, Callable

from PySide6 import QtWidgets, QtCore, QtGui

from .styles import FLAME_STYLE

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

from ..core.ftrack_manager import TASK_TYPES, STATUSES


# =============================================================================
# CUSTOM WIDGETS
# =============================================================================

class MultiTaskLineEdit(QtWidgets.QLineEdit):
    """
    Custom QLineEdit with smart autocomplete for multiple comma-separated tasks
    
    How it works:
    - Type task name → autocomplete shows suggestions
    - Select from dropdown → automatically adds comma + space
    - Type next task → autocomplete shows suggestions again
    - Repeat for as many tasks as needed
    
    Example: "Compositing, Rotoscoping, Tracking" (comma-separated)
    """
    
    def __init__(self, task_list, parent=None):
        super().__init__(parent)
        self.task_list = task_list
        self._completing = False  # Flag to prevent popup during completion
        
        # Setup completer
        self.completer = QtWidgets.QCompleter(task_list, self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        
        # Connect completion
        self.completer.activated.connect(self.insert_completion)
        
        # Connect text changed to update completer
        self.textChanged.connect(self.on_text_changed)
        
        # CRITICAL: Set widget on completer, but DON'T set completer on widget
        # This prevents Qt from trying to validate the entire text against the list
        self.completer.setWidget(self)
    
    def keyPressEvent(self, event):
        """
        Intercept keys to manually navigate popup,
        since we removed the default setCompleter() behavior.
        """
        if self.completer.popup().isVisible():
            # If popup is visible, certain keys should go to it
            if event.key() in (QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Return,
                             QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Tab,
                             QtCore.Qt.Key.Key_Backtab):
                event.ignore()
                return
        
        # Process key normally in LineEdit
        super().keyPressEvent(event)
        
        # Shortcut to force completion (Ctrl+Space is common)
        is_shortcut = (event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier and
                      event.key() == QtCore.Qt.Key.Key_Space)
        
        if is_shortcut:
            self.on_text_changed()
    
    def on_text_changed(self):
        """Force completer to update when text changes"""
        # Don't show popup if we're in the middle of inserting a completion
        if self._completing:
            return
        
        # Get current task being typed (after last comma)
        current_word = self.textUnderCursor()
        
        # Only show completer if we have at least 1 character
        if current_word and len(current_word) > 0:
            # Update the completion prefix
            self.completer.setCompletionPrefix(current_word)
            
            # If prefix differs from main suggestion, show popup
            # (avoids showing popup if word is already complete)
            if self.completer.completionCount() > 0:
                # Calculate rectangle position for popup to appear under cursor
                # not at the beginning of the line
                cr = self.cursorRect()
                cr.setWidth(self.completer.popup().sizeHintForColumn(0) +
                          self.completer.popup().verticalScrollBar().sizeHint().width())
                
                # Show popup at cursor position
                self.completer.complete(cr)
        else:
            # Hide popup if no current word
            self.completer.popup().hide()
        
    def textUnderCursor(self):
        """
        Override to return only the current task (after last comma)
        This is what QCompleter uses to determine the prefix for suggestions
        """
        text = self.text()
        cursor_pos = self.cursorPosition()
        
        # Find the start of current task (after last comma before cursor)
        last_comma = text.rfind(',', 0, cursor_pos)
        start_pos = last_comma + 1 if last_comma != -1 else 0
        
        # Return from start of task to cursor position, stripped of leading whitespace
        return text[start_pos:cursor_pos].lstrip()
    
    def insert_completion(self, completion):
        """Insert the selected completion and add comma + space for next task"""
        # Set flag to prevent on_text_changed from showing popup
        self._completing = True
        
        text = self.text()
        cursor_pos = self.cursorPosition()
        
        # Find the start of current task (last comma before cursor)
        last_comma = text.rfind(',', 0, cursor_pos)
        start_pos = last_comma + 1 if last_comma != -1 else 0
        
        # Find the end of current task (next comma after cursor or end)
        next_comma = text.find(',', cursor_pos)
        end_pos = next_comma if next_comma != -1 else len(text)
        
        # Build new text by replacing current task with completion
        # Keep everything before the task, add completion + comma + space, keep everything after
        prefix = text[:start_pos]
        suffix = text[end_pos:].lstrip(', ')
        
        if suffix:
            new_text = prefix + ' ' + completion + ', ' + suffix
        else:
            new_text = prefix + ' ' + completion + ', '
        
        # Clean up leading space if this is the first task
        new_text = new_text.lstrip()
        
        # Set the new text
        self.setText(new_text)
        
        # Position cursor right after the completion and comma+space
        new_cursor_pos = len(new_text)
        self.setCursorPosition(new_cursor_pos)
        
        # Reset flag after a short delay to allow text to settle
        QtCore.QTimer.singleShot(50, lambda: setattr(self, '_completing', False))


# =============================================================================
# BULK EDIT DIALOG
# =============================================================================

class BulkEditDialog(QtWidgets.QDialog):
    """
    Dialog for batch editing of selected shots
    
    Allows changing Sequence, Tasks, Status and Description
    of multiple shots at once.
    """
    
    def __init__(self, parent=None, session=None, project_id=None, cached_task_types=None):
        super().__init__(parent)
        self.session = session
        self.project_id = project_id
        self._cached_task_types = cached_task_types  # Use pre-loaded cache if available
        self.setWindowTitle("✏️ Bulk Edit Selected Shots")
        self.setMinimumWidth(450)
        self.setStyleSheet(FLAME_STYLE)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Info
        info = QtWidgets.QLabel(
            "Edit multiple selected shots at once.\n"
            "Leave fields empty to keep current values."
        )
        info.setStyleSheet("""
            color: #7a9a7a;
            padding: 10px;
            background-color: #2a3a2a;
            border-radius: 5px;
        """)
        layout.addWidget(info)
        
        # Form
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        
        # Sequence
        self.sequence_edit = QtWidgets.QLineEdit()
        self.sequence_edit.setPlaceholderText("Leave empty to keep current")
        form.addRow("Sequence:", self.sequence_edit)
        
        # Task Types (with autocomplete)
        self.tasks_edit, self.tasks_validation_label = self.setup_task_types_field()
        form.addRow("Task Types:", self.tasks_edit)
        form.addRow("", self.tasks_validation_label)
        
        # Status
        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItem("-- Keep current --", "")
        for status in STATUSES:
            self.status_combo.addItem(status, status)
        form.addRow("Status:", self.status_combo)
        
        # Description
        self.desc_edit = QtWidgets.QLineEdit()
        self.desc_edit.setPlaceholderText("Leave empty to keep current")
        form.addRow("Description:", self.desc_edit)
        
        layout.addLayout(form)
        
        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        apply_btn = QtWidgets.QPushButton("✅ Apply to Selected")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self.accept)
        buttons.addWidget(apply_btn)
        
        layout.addLayout(buttons)
    
    def get_values(self) -> Dict:
        """Return filled values (None for empty fields)"""
        return {
            'sequence': self.sequence_edit.text().strip() or None,
            'tasks': self.tasks_edit.text().strip() or None,
            'status': self.status_combo.currentData() or None,
            'description': self.desc_edit.text().strip() or None,
        }
    
    def get_ftrack_task_types(self) -> List[str]:
        """Get available task types from ftrack project schema or fallback list"""
        
        # Use cached task types if available (instant!)
        if self._cached_task_types:
            print(f"[ftrack] BulkEdit: ✓ Using cached task types ({len(self._cached_task_types)} types)")
            return self._cached_task_types
        
        try:
            # Try to get from ftrack session if available
            if self.session and self.project_id:
                print(f"[ftrack] BulkEdit: Loading task types from project {self.project_id}...")
                project = self.session.query(
                    f'Project where id is "{self.project_id}"'
                ).one()
                
                schema = project['project_schema']
                task_types = []
                
                for task_type in schema.get_types('Task'):
                    task_types.append(task_type['name'])
                
                print(f"[ftrack] BulkEdit: ✓ Loaded {len(task_types)} task types: {', '.join(sorted(task_types)[:5])}...")
                logger.info(f"Loaded {len(task_types)} task types from ftrack")
                return sorted(task_types)
            else:
                print(f"[ftrack] BulkEdit: No session ({self.session is not None}) or project_id ({self.project_id})")
        except Exception as e:
            print(f"[ftrack] BulkEdit: ⚠ Error loading task types: {e}")
            logger.warning(f"Could not fetch task types from ftrack: {e}")
        
        # Fallback to imported TASK_TYPES constant
        print(f"[ftrack] BulkEdit: Using fallback task types list")
        logger.info("Using fallback task types list")
        return sorted(TASK_TYPES)
    
    def setup_task_types_field(self):
        """Setup task types field with autocomplete and validation"""
        # Get available task types
        self.available_task_types = self.get_ftrack_task_types()
        
        # Track if we got task types from ftrack (via cache or direct query)
        self._task_types_from_ftrack = (
            self._cached_task_types is not None or 
            (self.session is not None and self.project_id is not None)
        )
        
        # Create custom field with multi-task autocomplete support
        task_field = MultiTaskLineEdit(self.available_task_types)
        task_field.setPlaceholderText("e.g., Compositing, Rotoscoping (comma separated)")
        
        # Validation label
        validation_label = QtWidgets.QLabel()
        validation_label.setWordWrap(True)
        
        # Show available tasks as hint initially
        if self._task_types_from_ftrack:
            validation_label.setText(
                f"📋 Project types: {', '.join(self.available_task_types[:6])}..."
            )
            validation_label.setStyleSheet("color: #7a9a7a; font-size: 10px;")
        else:
            validation_label.setText(f"Available: {', '.join(self.available_task_types[:6])}...")
            validation_label.setStyleSheet("color: #888888; font-size: 10px;")
        
        # Connect validation
        task_field.textChanged.connect(
            lambda text: self.validate_task_type(text, task_field, validation_label)
        )
        
        return task_field, validation_label
    
    def validate_task_type(self, text: str, field_widget: QtWidgets.QLineEdit, 
                          label_widget: QtWidgets.QLabel):
        """Validate task type as user types - supports multiple comma-separated tasks"""
        if not text or not text.strip():
            # Show hint when empty
            if hasattr(self, '_task_types_from_ftrack') and self._task_types_from_ftrack:
                label_widget.setText(
                    f"📋 Project types: {', '.join(self.available_task_types[:6])}..."
                )
                label_widget.setStyleSheet("color: #7a9a7a; font-size: 10px;")
            else:
                label_widget.setText(f"Available: {', '.join(self.available_task_types[:6])}...")
                label_widget.setStyleSheet("color: #888888; font-size: 10px;")
            field_widget.setStyleSheet("")
            return
        
        # Split by COMMA and clean each task (remove extra commas, spaces)
        # This handles cases like "Compositing," or "Compositing, " 
        raw_tasks = text.split(",")
        tasks = []
        for t in raw_tasks:
            cleaned = t.strip()
            if cleaned:  # Only add non-empty tasks
                tasks.append(cleaned)
        
        # If no valid tasks after cleaning (e.g., just "," or ", ")
        if not tasks:
            label_widget.setText(f"Type a task name...")
            label_widget.setStyleSheet("color: #888888; font-size: 10px;")
            field_widget.setStyleSheet("")
            return
        
        # Validate tasks
        available_normalized = {t.lower(): t for t in self.available_task_types}
        invalid_tasks = []
        valid_tasks = []
        
        for task in tasks:
            task_lower = task.lower()
            if task_lower in available_normalized:
                valid_tasks.append(task)
            else:
                invalid_tasks.append(task)
        
        # Show status
        if not invalid_tasks:
            # All valid
            if len(tasks) == 1:
                label_widget.setText(f"✓ Valid task type")
            else:
                label_widget.setText(f"✓ All {len(tasks)} tasks are valid")
            label_widget.setStyleSheet("color: #4a9a4a; font-size: 10px;")
            field_widget.setStyleSheet("")
        else:
            # Some invalid - show suggestions for the first invalid task
            first_invalid = invalid_tasks[0].lower()
            suggestions = [
                t for t in self.available_task_types 
                if first_invalid in t.lower()
            ]
            
            if suggestions:
                label_widget.setText(
                    f"💡 '{invalid_tasks[0]}' → Did you mean: {', '.join(suggestions[:3])}?"
                )
                label_widget.setStyleSheet("color: #ca8a04; font-size: 10px;")
                field_widget.setStyleSheet("border: 1px solid #ca8a04;")
            else:
                label_widget.setText(
                    f"⚠ '{invalid_tasks[0]}' not found in project schema"
                )
                label_widget.setStyleSheet("color: #da4a4a; font-size: 10px;")
                field_widget.setStyleSheet("border: 1px solid #da4a4a;")


# =============================================================================
# IMPORT DIALOG
# =============================================================================

class ImportDialog(QtWidgets.QDialog):
    """
    Dialog for importing shots from CSV or Copy/Paste
    
    Supports:
    - Paste: Tab or comma separated data
    - CSV: CSV file with headers
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📥 Import Shots")
        self.setMinimumSize(650, 550)
        self.setStyleSheet(FLAME_STYLE)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Tabs
        tabs = QtWidgets.QTabWidget()
        
        # Tab 1: Paste
        paste_tab = QtWidgets.QWidget()
        paste_layout = QtWidgets.QVBoxLayout(paste_tab)
        
        paste_info = QtWidgets.QLabel(
            "Paste tab-separated or comma-separated data.\n"
            "Format: Sequence, Shot Name, Task Types, Status, Description\n\n"
            "Example:\n"
            "SEQ010,SHOT_010,Compositing,ready_to_start,Opening scene\n"
            "SEQ010,SHOT_020,Compositing; Roto,in_progress,City transition"
        )
        paste_info.setStyleSheet("""
            color: #9a9a9a;
            padding: 10px;
            background-color: #2a2a2a;
            border-radius: 5px;
            font-family: monospace;
        """)
        paste_layout.addWidget(paste_info)
        
        self.paste_text = QtWidgets.QPlainTextEdit()
        self.paste_text.setPlaceholderText("Paste your data here...")
        paste_layout.addWidget(self.paste_text)
        
        tabs.addTab(paste_tab, "📋 Paste Data")
        
        # Tab 2: CSV File
        csv_tab = QtWidgets.QWidget()
        csv_layout = QtWidgets.QVBoxLayout(csv_tab)
        
        csv_info = QtWidgets.QLabel(
            "Select a CSV file with columns:\n"
            "Sequence, Shot Name, Task Types, Status, Description\n\n"
            "The first row should be the header."
        )
        csv_info.setStyleSheet("""
            color: #9a9a9a;
            padding: 10px;
            background-color: #2a2a2a;
            border-radius: 5px;
        """)
        csv_layout.addWidget(csv_info)
        
        file_row = QtWidgets.QHBoxLayout()
        self.file_path = QtWidgets.QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("No file selected...")
        file_row.addWidget(self.file_path)
        
        browse_btn = QtWidgets.QPushButton("📂 Browse...")
        browse_btn.clicked.connect(self._browse_csv)
        file_row.addWidget(browse_btn)
        
        csv_layout.addLayout(file_row)
        
        # Preview
        self.preview_label = QtWidgets.QLabel("Preview will appear here after selecting a file")
        self.preview_label.setStyleSheet("color: #666666; padding: 10px;")
        csv_layout.addWidget(self.preview_label)
        
        csv_layout.addStretch()
        
        tabs.addTab(csv_tab, "📄 CSV File")
        
        layout.addWidget(tabs)
        self.tabs = tabs
        
        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        import_btn = QtWidgets.QPushButton("📥 Import")
        import_btn.setObjectName("primary")
        import_btn.clicked.connect(self.accept)
        buttons.addWidget(import_btn)
        
        layout.addLayout(buttons)
    
    def _browse_csv(self):
        """Open dialog to select CSV"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            self.file_path.setText(path)
            self._preview_csv(path)
    
    def _preview_csv(self, path: str):
        """Show CSV preview"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                lines = list(reader)[:5]  # First 5 lines
            
            if lines:
                preview = "Preview (first 5 rows):\n\n"
                for line in lines:
                    preview += " | ".join(line[:5]) + "\n"
                self.preview_label.setText(preview)
                self.preview_label.setStyleSheet("color: #9a9a9a; padding: 10px; font-family: monospace;")
        except Exception as e:
            self.preview_label.setText(f"Error reading file: {e}")
            self.preview_label.setStyleSheet("color: #c88; padding: 10px;")
    
    def get_shots(self) -> List[Dict]:
        """Return list of imported shots"""
        if self.tabs.currentIndex() == 0:
            text = self.paste_text.toPlainText().strip()
            return self._parse_text(text) if text else []
        else:
            path = self.file_path.text()
            return self._parse_csv(path) if path and os.path.exists(path) else []
    
    def _parse_text(self, text: str) -> List[Dict]:
        """Parse pasted text"""
        shots = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect separator
            if '\t' in line:
                parts = line.split('\t')
            else:
                parts = line.split(',')
            
            parts = [p.strip() for p in parts]
            
            if len(parts) >= 2:
                shot = {
                    'Sequence': parts[0] if len(parts) > 0 else 'SEQ010',
                    'Shot Name': parts[1] if len(parts) > 1 else '',
                    'Task Types': parts[2] if len(parts) > 2 else 'Compositing',
                    'Status': parts[3] if len(parts) > 3 else 'ready_to_start',
                    'Description': parts[4] if len(parts) > 4 else '',
                }
                if shot['Shot Name']:
                    shots.append(shot)
        
        return shots
    
    def _parse_csv(self, path: str) -> List[Dict]:
        """Parse CSV file"""
        shots = []
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    shot = {
                        'Sequence': row.get('Sequence', row.get('sequence', 'SEQ010')),
                        'Shot Name': row.get('Shot Name', row.get('shot_name', row.get('Shot', ''))),
                        'Task Types': row.get('Task Types', row.get('tasks', 'Compositing')),
                        'Status': row.get('Status', row.get('status', 'ready_to_start')),
                        'Description': row.get('Description', row.get('description', '')),
                    }
                    if shot['Shot Name']:
                        shots.append(shot)
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
        
        return shots


# =============================================================================
# PROGRESS DIALOG WITH STEPS
# =============================================================================

class StepProgressDialog(QtWidgets.QDialog):
    """
    Progress dialog with visual steps
    
    Shows:
    - Step indicator (Step 1, Step 2, etc)
    - Progress bar
    - Current message
    - Operations log
    """
    
    canceled = QtCore.Signal()
    
    def __init__(self, steps: List[str], parent=None):
        """
        Args:
            steps: Lista de nomes dos steps (ex: ["Export Thumbnails", "Create Shots"])
        """
        super().__init__(parent)
        self.steps = steps
        self.current_step = 0
        self._canceled = False
        
        self.setWindowTitle("⏳ Processing...")
        self.setMinimumSize(550, 400)
        self.setStyleSheet(FLAME_STYLE)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog |
            QtCore.Qt.WindowType.CustomizeWindowHint |
            QtCore.Qt.WindowType.WindowTitleHint
        )
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Steps indicator
        steps_widget = QtWidgets.QWidget()
        steps_widget.setStyleSheet("""
            background-color: #2a2a2a;
            border-radius: 5px;
            padding: 10px;
        """)
        steps_layout = QtWidgets.QHBoxLayout(steps_widget)
        
        self.step_labels = []
        for i, step_name in enumerate(self.steps):
            # Step number
            num_label = QtWidgets.QLabel(f"{i + 1}")
            num_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            num_label.setFixedSize(30, 30)
            num_label.setStyleSheet("""
                background-color: #3a3a3a;
                border-radius: 15px;
                color: #666666;
                font-weight: bold;
            """)
            
            # Step name
            name_label = QtWidgets.QLabel(step_name)
            name_label.setStyleSheet("color: #666666;")
            
            step_container = QtWidgets.QVBoxLayout()
            step_container.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            step_container.addWidget(num_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
            step_container.addWidget(name_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
            
            steps_layout.addLayout(step_container)
            
            # Arrow between steps
            if i < len(self.steps) - 1:
                arrow = QtWidgets.QLabel("→")
                arrow.setStyleSheet("color: #3a3a3a; font-size: 20px;")
                steps_layout.addWidget(arrow)
            
            self.step_labels.append((num_label, name_label))
        
        layout.addWidget(steps_widget)
        
        # Current step title
        self.step_title = QtWidgets.QLabel()
        self.step_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #d9d9d9;")
        layout.addWidget(self.step_title)
        
        # Mensagem
        self.message_label = QtWidgets.QLabel("Initializing...")
        self.message_label.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self.message_label)
        
        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Log
        self.log_text = QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            font-family: monospace;
            font-size: 11px;
            background-color: #1a1a1a;
        """)
        layout.addWidget(self.log_text)
        
        # Cancel button
        cancel_layout = QtWidgets.QHBoxLayout()
        cancel_layout.addStretch()
        
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        cancel_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(cancel_layout)
        
        # Inicializa primeiro step
        self.set_step(0)
    
    def set_step(self, step_index: int):
        """Set current step"""
        self.current_step = step_index
        
        # Update steps visual
        for i, (num_label, name_label) in enumerate(self.step_labels):
            if i < step_index:
                # Complete
                num_label.setStyleSheet("""
                    background-color: #5cb85c;
                    border-radius: 15px;
                    color: white;
                    font-weight: bold;
                """)
                name_label.setStyleSheet("color: #5cb85c;")
            elif i == step_index:
                # Current
                num_label.setStyleSheet("""
                    background-color: #4a6fa5;
                    border-radius: 15px;
                    color: white;
                    font-weight: bold;
                """)
                name_label.setStyleSheet("color: #4a6fa5; font-weight: bold;")
            else:
                # Pending
                num_label.setStyleSheet("""
                    background-color: #3a3a3a;
                    border-radius: 15px;
                    color: #666666;
                    font-weight: bold;
                """)
                name_label.setStyleSheet("color: #666666;")
        
        # Update title
        if step_index < len(self.steps):
            self.step_title.setText(f"Step {step_index + 1}: {self.steps[step_index]}")
        
        self.progress_bar.setValue(0)
    
    def set_progress(self, current: int, total: int, message: str = ""):
        """Update progress"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{current}/{total} ({percent}%)")
        
        if message:
            self.message_label.setText(message)
        
        QtWidgets.QApplication.processEvents()
    
    def log(self, message: str):
        """Add message to log"""
        self.log_text.appendPlainText(message)
        # Scroll to end
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QtWidgets.QApplication.processEvents()
    
    def _on_cancel(self):
        """Cancel handler"""
        self._canceled = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Canceling...")
        self.canceled.emit()
    
    def is_canceled(self) -> bool:
        """Check if was canceled"""
        return self._canceled
    
    def complete(self):
        """Mark as complete"""
        # Mark all steps as complete
        for num_label, name_label in self.step_labels:
            num_label.setStyleSheet("""
                background-color: #5cb85c;
                border-radius: 15px;
                color: white;
                font-weight: bold;
            """)
            name_label.setStyleSheet("color: #5cb85c;")
        
        self.step_title.setText("✅ Complete!")
        self.cancel_btn.setText("Close")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.accept)


# =============================================================================
# SETTINGS DIALOG
# =============================================================================

class SettingsDialog(QtWidgets.QDialog):
    """
    Settings dialog
    
    Allows configuring:
    - Export preset path
    - Thumbnails directory
    - Upload options
    """
    
    def __init__(self, settings: Dict, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.setWindowTitle("⚙️ Settings")
        self.setMinimumWidth(500)
        self.setStyleSheet(FLAME_STYLE)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Thumbnail Export
        thumb_group = QtWidgets.QGroupBox("Thumbnail Export")
        thumb_layout = QtWidgets.QFormLayout(thumb_group)
        
        # Preset path
        preset_row = QtWidgets.QHBoxLayout()
        self.preset_edit = QtWidgets.QLineEdit(self.settings.get('preset_path', ''))
        preset_row.addWidget(self.preset_edit)
        preset_browse = QtWidgets.QPushButton("...")
        preset_browse.setMaximumWidth(30)
        preset_browse.clicked.connect(self._browse_preset)
        preset_row.addWidget(preset_browse)
        thumb_layout.addRow("Export Preset:", preset_row)
        
        # Output dir
        output_row = QtWidgets.QHBoxLayout()
        self.output_edit = QtWidgets.QLineEdit(self.settings.get('output_dir', ''))
        output_row.addWidget(self.output_edit)
        output_browse = QtWidgets.QPushButton("...")
        output_browse.setMaximumWidth(30)
        output_browse.clicked.connect(self._browse_output)
        output_row.addWidget(output_browse)
        thumb_layout.addRow("Output Directory:", output_row)
        
        layout.addWidget(thumb_group)
        
        # Options
        options_group = QtWidgets.QGroupBox("Options")
        options_layout = QtWidgets.QVBoxLayout(options_group)
        
        self.export_check = QtWidgets.QCheckBox("Export thumbnails from Flame")
        self.export_check.setChecked(self.settings.get('export_thumbs', True))
        options_layout.addWidget(self.export_check)
        
        self.upload_check = QtWidgets.QCheckBox("Upload thumbnails to ftrack")
        self.upload_check.setChecked(self.settings.get('upload_thumbs', True))
        options_layout.addWidget(self.upload_check)
        
        layout.addWidget(options_group)
        
        layout.addStretch()
        
        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        save_btn = QtWidgets.QPushButton("💾 Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        
        layout.addLayout(buttons)
    
    def _browse_preset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Export Preset", 
            "/opt/Autodesk/shared/export/presets",
            "XML Files (*.xml);;All Files (*)"
        )
        if path:
            self.preset_edit.setText(path)
    
    def _browse_output(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            self.output_edit.text() or os.path.expanduser("~")
        )
        if path:
            self.output_edit.setText(path)
    
    def _save(self):
        self.settings['preset_path'] = self.preset_edit.text()
        self.settings['output_dir'] = self.output_edit.text()
        self.settings['export_thumbs'] = self.export_check.isChecked()
        self.settings['upload_thumbs'] = self.upload_check.isChecked()
        self.accept()
    
    def get_settings(self) -> Dict:
        return self.settings