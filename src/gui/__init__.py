"""
GUI Module - User interface components

Components:
- main_window: Main application window with bookmarks and log viewer
- shot_table: Shot table widget
- dialogs: Auxiliary dialogs (BulkEdit, Import, Progress)
- styles: CSS styles for Flame UI
- time_tracker: Time tracking widget with mini floating timer and manual entry
- publish_review: Dialog for publishing shot reviews to ftrack
"""

from .main_window import FlameFtrackWindow, launch_ftrack_window, scope_sequence, BookmarksManager, LogWindow
from .shot_table import ShotTableWidget
from .dialogs import BulkEditDialog, ImportDialog, StepProgressDialog
from .styles import FLAME_STYLE
from .time_tracker import TimeTrackerWindow, show_time_tracker, get_time_tracker_window, TaskHistoryManager, MiniTimerWidget
from .publish_review import PublishReviewDialog, launch_publish_review

__all__ = [
    'FlameFtrackWindow',
    'launch_ftrack_window',
    'scope_sequence',
    'BookmarksManager',
    'LogWindow',
    'ShotTableWidget',
    'BulkEditDialog',
    'ImportDialog',
    'StepProgressDialog',
    'FLAME_STYLE',
    'TimeTrackerWindow',
    'show_time_tracker',
    'get_time_tracker_window',
    'TaskHistoryManager',
    'MiniTimerWidget',
    'PublishReviewDialog',
    'launch_publish_review',
]
