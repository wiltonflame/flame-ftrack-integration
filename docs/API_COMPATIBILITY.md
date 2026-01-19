# ftrack API - Compatibility Reference

This document documents which features use the real ftrack API and which are just GUI placeholders.

## ✅ REAL ftrack API Entities

Based on official documentation: https://ftrack-python-api.rtd.ftrack.com/

| Entity | Description | Usage Example |
|--------|-------------|---------------|
| `Project` | Project | `session.query('Project')` |
| `Sequence` | Sequence | `session.create('Sequence', {'name': 'SEQ_010', 'parent': project})` |
| `Shot` | Shot | `session.create('Shot', {'name': 'SHOT_010', 'parent': sequence})` |
| `Task` | Task | `session.create('Task', {'name': 'comp', 'parent': shot})` |
| `Status` | Status | `session.query('Status')` |
| `Type` | Task type | `session.query('Type where name is "Compositing"')` |
| `User` | User | `session.query('User')` |
| `Timelog` | Time log | `session.create('Timelog', {'duration': 3600})` |
| `Note` | Note/comment | `session.create('Note', {'content': '...', 'parent': entity})` |
| `NoteCategory` | Note category | `session.query('NoteCategory')` |
| `AssetVersion` | Asset version | `session.query('AssetVersion')` |
| `Component` | File/component | `version.create_component(path)` |
| `Location` | Storage location | `session.query('Location where name is "ftrack.server"')` |
| `ReviewSession` | Review session | `session.create('ReviewSession', {...})` |
| `TypedContext` | Base class | Used for generic queries |

## ✅ REAL Methods implemented in `ftrack_wrapper.py`

### Projects and Hierarchy
```python
ftrack.get_projects()                    # ✅ Real
ftrack.get_project_by_name(name)         # ✅ Real
ftrack.get_project_hierarchy(project_id) # ✅ Real
ftrack.get_sequences(project_id)         # ✅ Real
ftrack.get_or_create_sequence(...)       # ✅ Real
```

### Shots and Tasks
```python
ftrack.create_shot(parent_id, shot)      # ✅ Real
ftrack.create_shots_batch(...)           # ✅ Real
ftrack.create_task(parent_id, ...)       # ✅ Real
ftrack.get_task_types()                  # ✅ Real
ftrack.get_task_statuses()               # ✅ Real
```

### Thumbnails
```python
ftrack.upload_thumbnail(entity_id, path) # ✅ Real - uses entity.create_thumbnail()
ftrack.upload_thumbnails_batch(...)      # ✅ Real
ftrack.get_thumbnail_url(entity_id)      # ✅ Real - uses location.get_thumbnail_url()
```

### Notes
```python
ftrack.create_note(entity_id, content)   # ✅ Real - creates Note entity
ftrack.get_notes(entity_id)              # ✅ Real
ftrack.get_note_categories()             # ✅ Real
```

### Timelogs
```python
ftrack.create_timelog(task_id, duration) # ✅ Real - uses task['timelogs'].append()
ftrack.get_timelogs(task_id)             # ✅ Real
```

### Asset Versions
```python
ftrack.get_asset_versions(entity_id)     # ✅ Real
```

### Users
```python
ftrack.get_users()                       # ✅ Real
```

## ⚠️ GUI Placeholders in `advanced_features.py`

The widgets in `advanced_features.py` are **VISUAL INTERFACE ONLY**.
They do NOT make direct API calls - you need to connect them.

| Widget | Status | To work, needs: |
|--------|--------|-----------------|
| `PlaylistWidget` | 🟡 GUI only | Connect signals to ftrack_wrapper methods |
| `NotesPanel` | 🟡 GUI only | Call `ftrack.create_note()` on `note_added` signal |
| `TimeTrackingWidget` | 🟡 GUI only | Call `ftrack.create_timelog()` on `time_logged` signal |
| `VersionCompareWidget` | 🟡 GUI only | Call `ftrack.get_asset_versions()` to populate |
| `BreakdownWidget` | 🟡 GUI only | Concept - ftrack doesn't have "Breakdown" as entity |
| `BatchOperationsWidget` | 🟡 GUI only | Implement batch updates manually |
| `QuickActionsToolbar` | 🟡 GUI only | Connect actions to corresponding functions |

### How to connect GUI to API:

```python
# Example: Connect NotesPanel to ftrack
from src.gui.advanced_features import NotesPanel
from src.ftrack_api import FtrackConnection

notes_panel = NotesPanel()
ftrack = FtrackConnection()
ftrack.connect()

# Connect signal to API
def on_note_added(note_data):
    ftrack.create_note(
        entity_id=note_data['entity_id'],
        content=note_data['content'],
        category=note_data.get('category')
    )

notes_panel.note_added.connect(on_note_added)
```

## 🔴 What does NOT exist in ftrack API

| Concept | Alternative |
|---------|-------------|
| "Breakdown" as entity | Use custom attributes or metadata |
| Native "Playlist" | Use ReviewSession |
| Frame-specific notes | Use metadata in Note or AssetVersion |
| @Mentions in notes | Implement via content parsing |

## 📚 Official References

- **Python API Docs**: https://ftrack-python-api.rtd.ftrack.com/
- **Thumbnails**: https://ftrack-python-api.rtd.ftrack.com/en/stable/example/thumbnail.html
- **Web Review**: https://ftrack-python-api.rtd.ftrack.com/en/stable/example/web_review.html
- **Entities**: https://ftrack-python-api.rtd.ftrack.com/en/stable/working_with_entities.html

## Testing the API

Before using in production, test the methods:

```python
from src.ftrack_api import FtrackConnection

with FtrackConnection() as ftrack:
    # List available types
    print(ftrack.session.types.keys())
    
    # List entity attributes
    task = ftrack.session.query('Task').first()
    print(task.keys())
    
    # Check if method exists
    print(hasattr(task, 'create_thumbnail'))  # True
```
