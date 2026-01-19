"""
Flame UI Styles - CSS styles for Qt widgets

Styles inspired by the Autodesk Flame interface.
"""

# =============================================================================
# FLAME COLORS
# =============================================================================

COLORS = {
    'bg_dark': '#313131',
    'bg_medium': '#2a2a2a',
    'bg_light': '#424142',
    'bg_hover': '#4a4a4a',
    'bg_pressed': '#3a3a3a',
    
    'text_normal': '#9a9a9a',
    'text_light': '#d9d9d9',
    'text_dark': '#666666',
    
    'border_dark': '#1a1a1a',
    'border_medium': '#3a3a3a',
    
    'accent_blue': '#4a6fa5',
    'accent_green': '#5a8a5a',
    'accent_red': '#8b4049',
    'accent_yellow': '#b5a642',
    'accent_orange': '#ff6b35',
    
    'success': '#5cb85c',
    'warning': '#f0ad4e',
    'error': '#d9534f',
}


# =============================================================================
# MAIN STYLE
# =============================================================================

FLAME_STYLE = """
/* ========================================
   BASE WIDGETS
   ======================================== */

QWidget {
    background-color: #313131;
    color: #9a9a9a;
    font-family: "Discreet", "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #313131;
}

QDialog {
    background-color: #313131;
}

/* ========================================
   BUTTONS
   ======================================== */

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

QPushButton:disabled {
    background-color: #353535;
    color: #666666;
}

QPushButton#primary {
    background-color: #4a6fa5;
    color: white;
    font-weight: bold;
}

QPushButton#primary:hover {
    background-color: #5a7fb5;
}

QPushButton#success {
    background-color: #5a8a5a;
    color: white;
    font-weight: bold;
}

QPushButton#success:hover {
    background-color: #6a9a6a;
}

QPushButton#danger {
    background-color: #8b4049;
    color: white;
}

QPushButton#danger:hover {
    background-color: #9b5059;
}

/* ========================================
   INPUTS
   ======================================== */

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 5px;
    color: #d9d9d9;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #4a6fa5;
}

QLineEdit:disabled {
    background-color: #252525;
    color: #666666;
}

/* ========================================
   COMBOBOX
   ======================================== */

QComboBox {
    background-color: #424142;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 5px 10px;
    color: #d9d9d9;
    min-width: 80px;
}

QComboBox:hover {
    background-color: #4a4a4a;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #9a9a9a;
    margin-right: 5px;
}

QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    selection-background-color: #4a6fa5;
    selection-color: white;
}

/* ========================================
   TABLES
   ======================================== */

QTableWidget {
    background-color: #2a2a2a;
    alternate-background-color: #2d2d2d;
    gridline-color: #3a3a3a;
    border: 1px solid #1a1a1a;
    selection-background-color: #474747;
}

QTableWidget::item {
    padding: 4px;
}

QTableWidget::item:selected {
    background-color: #474747;
}

/* ComboBox dentro de tabela */
QTableWidget QComboBox {
    background-color: #424142;
    border: 1px solid #3a3a3a;
    border-radius: 2px;
    padding: 2px 6px;
    color: #d9d9d9;
    min-height: 20px;
}

QTableWidget QComboBox:hover {
    background-color: #4a4a4a;
    border-color: #4a6fa5;
}

QTableWidget QComboBox::drop-down {
    border: none;
    width: 18px;
}

QTableWidget QComboBox::down-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #9a9a9a;
}

QTableWidget QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    selection-background-color: #4a6fa5;
    selection-color: white;
}

QHeaderView::section {
    background-color: #393939;
    color: #9a9a9a;
    padding: 5px;
    border: none;
    border-right: 1px solid #2a2a2a;
    border-bottom: 1px solid #2a2a2a;
}

/* ========================================
   TREE WIDGET
   ======================================== */

QTreeWidget {
    background-color: #2a2a2a;
    alternate-background-color: #2d2d2d;
    border: 1px solid #1a1a1a;
    border-radius: 3px;
}

QTreeWidget::item {
    padding: 4px;
    min-height: 22px;
}

QTreeWidget::item:selected {
    color: #d9d9d9;
    background-color: #474747;
}

QTreeWidget::item:hover {
    background-color: #3a3a3a;
}

/* ========================================
   SCROLLBARS
   ======================================== */

QScrollBar:vertical {
    background-color: #2a2a2a;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #555555;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #666666;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #2a2a2a;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background-color: #555555;
    border-radius: 5px;
    min-width: 20px;
}

/* ========================================
   PROGRESS BAR
   ======================================== */

QProgressBar {
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    text-align: center;
    background-color: #2a2a2a;
    color: #d9d9d9;
}

QProgressBar::chunk {
    background-color: #4a6fa5;
    border-radius: 2px;
}

/* ========================================
   CHECKBOX
   ======================================== */

QCheckBox {
    spacing: 5px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #3a3a3a;
    background-color: #2a2a2a;
}

QCheckBox::indicator:checked {
    background-color: #4a6fa5;
    border-color: #4a6fa5;
}

QCheckBox::indicator:hover {
    border-color: #4a6fa5;
}

/* ========================================
   GROUP BOX
   ======================================== */

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

/* ========================================
   TABS
   ======================================== */

QTabWidget::pane {
    border: 1px solid #3a3a3a;
    background-color: #313131;
}

QTabBar::tab {
    background-color: #2a2a2a;
    color: #9a9a9a;
    padding: 8px 16px;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #424142;
    color: #d9d9d9;
}

QTabBar::tab:hover:!selected {
    background-color: #353535;
}

/* ========================================
   SPLITTER
   ======================================== */

QSplitter::handle {
    background-color: #3a3a3a;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

/* ========================================
   MESSAGE BOX
   ======================================== */

QMessageBox {
    background-color: #313131;
}

QMessageBox QPushButton {
    min-width: 80px;
}

QMessageBox QLabel {
    color: #d9d9d9;
}

/* ========================================
   STATUS BAR
   ======================================== */

QStatusBar {
    background-color: #2a2a2a;
    border-top: 1px solid #1a1a1a;
    padding: 3px;
}

/* ========================================
   TOOLTIPS
   ======================================== */

QToolTip {
    background-color: #2a2a2a;
    color: #d9d9d9;
    border: 1px solid #3a3a3a;
    padding: 4px;
}
"""


# =============================================================================
# SPECIFIC STYLES
# =============================================================================

STEP_INDICATOR_STYLE = """
QWidget#step_indicator {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    padding: 10px;
}

QLabel#step_title {
    font-size: 14px;
    font-weight: bold;
    color: #d9d9d9;
}

QLabel#step_current {
    color: #4a6fa5;
}

QLabel#step_complete {
    color: #5cb85c;
}

QLabel#step_pending {
    color: #666666;
}
"""


INFO_BOX_STYLE = """
QWidget#info_box {
    background-color: #2a3a4a;
    border: 1px solid #3a4a5a;
    border-radius: 5px;
    padding: 10px;
}

QLabel#info_text {
    color: #9ac;
}
"""


SUCCESS_BOX_STYLE = """
QWidget#success_box {
    background-color: #2a4a2a;
    border: 1px solid #3a6a3a;
    border-radius: 5px;
    padding: 10px;
}

QLabel#success_text {
    color: #8c8;
}
"""


ERROR_BOX_STYLE = """
QWidget#error_box {
    background-color: #4a2a2a;
    border: 1px solid #6a3a3a;
    border-radius: 5px;
    padding: 10px;
}

QLabel#error_text {
    color: #c88;
}
"""


# =============================================================================
# HTML COLORS
# =============================================================================

def html_color(text: str, color: str) -> str:
    """Return text with HTML color"""
    return f'<span style="color: {color};">{text}</span>'


def html_icon(icon: str, color: str = None) -> str:
    """Return icon with optional color"""
    if color:
        return f'<span style="color: {color};">{icon}</span>'
    return icon


# Ready colored icons
ICON_FLAME = html_icon("🔥", "#ff6b35")
ICON_FTRACK = html_icon("📊", "#4a6fa5")
ICON_SUCCESS = html_icon("✅", "#5cb85c")
ICON_WARNING = html_icon("⚠️", "#f0ad4e")
ICON_ERROR = html_icon("❌", "#d9534f")
ICON_CONNECTED = html_icon("🟢", "#5cb85c")
ICON_DISCONNECTED = html_icon("🔴", "#d9534f")
ICON_MOCK = html_icon("🟡", "#f0ad4e")
