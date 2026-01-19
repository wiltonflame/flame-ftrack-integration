# Flame-ftrack Integration

A comprehensive integration between Autodesk Flame and ftrack Studio for streamlined VFX pipeline management. Create shots, manage tasks, export thumbnails, upload video versions, publish reviews, and track time directly from within Flame.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Flame](https://img.shields.io/badge/Flame-2025+-orange.svg)
![ftrack](https://img.shields.io/badge/ftrack-4.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

### 🎬 Shot Management
- **Batch shot creation** from Flame timeline segments
- **Automatic sequence detection** and creation in ftrack
- **Multi-task assignment** per shot (Compositing, Rotoscoping, Tracking, etc.)
- **Status management** with customizable statuses
- **Project bookmarks** for quick access to frequently used projects
- **Shot table with batch editing** for efficient shot management

### 🖼️ Thumbnail Export
- **Automatic thumbnail generation** from timeline using custom XML presets
- **Direct upload to ftrack** as shot thumbnails
- **Configurable output directory** and format (JPEG)

### 🎥 Video Version Upload
- **H.264/MP4 video export** from Flame timeline
- **Automatic version creation** in ftrack with web playback support
- **ftrack encoding integration** for streaming playback

### 📤 Publish Review
- **Quick review publishing** directly from Flame timeline/clips
- **Task selection** from user's in-progress tasks (grouped by project)
- **Comment/note support** for version descriptions
- **Progress feedback** during export and upload
- **One-click workflow** for daily reviews

### ⏱️ Time Tracker
- **Persistent tracking window** (stays open when changing Flame projects)
- **Mini floating timer** when window is minimized (always on top)
- **Automatic task list** showing user's in-progress tasks
- **Timer controls** with start, pause, and stop
- **Manual time entry** for logging time after the fact
- **Auto-pause on inactivity** (5-minute timeout)
- **Visual alerts** when timer is paused
- **Task history** for quick access to recently tracked tasks
- **Confirmation dialogs** when switching tasks with active timer
- **Direct ftrack integration** - saves time logs directly to ftrack

### 🔧 Pipeline Integration
- **Native Flame hook** integration with context menus in multiple locations:
  - **Media Panel** (right-click on sequences)
  - **Main Menu** (ftrack menu in menu bar)
  - **Batch** (right-click on clips/nodes)
  - **Timeline** (right-click on segments)
- **Standalone demo mode** for testing without Flame
- **GUI-based credential management** (no manual file editing)
- **Dry-run mode** for previewing operations before execution

## Requirements

- **Autodesk Flame** 2025 or later (Python 3.11)
- **ftrack Studio** account with API access
- **ftrack-python-api** >= 2.0
- **PySide6** >= 6.5.0 (included with Flame 2025+, no installation needed)

> **Note:** PySide6 is already included with Flame 2025+, so only `ftrack-python-api` needs to be installed.

## Installation

### 1. Clone the Repository

```bash
cd ~
git clone https://github.com/wiltonflame/flame-ftrack-integration.git
cd flame-ftrack-integration
```

### 2. Install Dependencies

Choose one of the installation methods below:

#### Option A: Virtual Environment (Recommended)

Creates an isolated virtual environment using Flame's Python and installs only `ftrack-python-api`:

```bash
chmod +x setup_environment.sh
./setup_environment.sh
```

This script:
- Detects Flame Python automatically (2025, 2025.1, 2025.2, 2026, etc.)
- Creates a virtual environment (`.venv`) in the project directory
- Installs `ftrack-python-api` in the venv
- **Note:** PySide6 is NOT installed because Flame already includes it

#### Option B: Simple Installation (System-wide)

Installs `ftrack-python-api` directly to Flame's shared Python directory:

```bash
chmod +x setup_simple.sh
./setup_simple.sh
```

This script:
- Detects Flame Python automatically
- Installs `ftrack-python-api` to `/opt/Autodesk/shared/python`
- Requires write permissions (may need `sudo`)

> **Which method to choose?**
> - **Virtual Environment (Option A)**: Better isolation, easier to manage, recommended for development
> - **Simple Installation (Option B)**: System-wide, simpler setup, good for production deployments

### 3. Install Flame Hook

Copy or symlink the hook to Flame's Python hooks directory:

```bash
# Option 1: Symlink (recommended)
ln -s ~/flame_ftrack_integration/flame_ftrack_hook.py \
      /opt/Autodesk/shared/python/flame_ftrack_hook.py

# Option 2: Copy
cp ~/flame_ftrack_integration/flame_ftrack_hook.py \
   /opt/Autodesk/shared/python/flame_ftrack_hook.py
```

> **Note:** If using symlink, you may need `sudo` depending on permissions.

### 4. Install Export Presets

Copy the XML presets to Flame's shared presets directory:

```bash
sudo cp presets/*.xml /opt/Autodesk/shared/export/presets/sequence_publish/
```

### 5. Configure Credentials

On first launch, the integration will prompt for ftrack credentials:
- **Server URL**: Your ftrack server (e.g., `https://yourcompany.ftrackapp.com`)
- **API Key**: Your personal API key from ftrack
- **Username**: Your ftrack username

Credentials are stored securely in `~/.config/flame_ftrack/credentials.json`

## Usage

The integration provides multiple entry points through Flame's interface. Access the ftrack integration via:

### 📍 Menu Locations

#### Media Panel (Right-click on Sequences)
- **🚀 Create Shots in ftrack...** - Main shot creation window
- **📤 Publish Review to ftrack...** - Quick review publishing
- **⏱️ Time Tracker** - Open time tracking window
- **🔑 Configure Credentials...** - Manage ftrack credentials
- **📋 Demo Mode** - Test without Flame selection
- **ℹ️ About** - Plugin information

#### Main Menu Bar (ftrack menu)
- **🚀 Create Shots from Selection...** - Main shot creation window
- **📤 Publish Review to ftrack...** - Quick review publishing
- **⏱️ Time Tracker** - Open time tracking window
- **🔑 Configure Credentials...** - Manage ftrack credentials
- **📋 Demo Mode (No Selection)** - Test without Flame selection
- **ℹ️ About** - Plugin information

#### Batch Panel (Right-click on Clips/Nodes)
- **📤 Publish Review to ftrack...** - Quick review publishing
- **⏱️ Time Tracker** - Open time tracking window
- **🔑 Configure Credentials...** - Manage ftrack credentials

#### Timeline (Right-click on Segments)
- **📤 Publish Review to ftrack...** - Quick review publishing
- **⏱️ Time Tracker** - Open time tracking window
- **🔑 Configure Credentials...** - Manage ftrack credentials

### 🎬 Creating Shots from Timeline

1. Select a sequence in the Media Panel
2. Right-click → **"🚀 Create Shots in ftrack..."** (or use Main Menu → ftrack)
3. Select target ftrack project (use search or bookmarks)
4. Configure options:
   - Enable/disable thumbnail export
   - Enable/disable video export
   - Select task types to create per shot
   - Set default task status
5. Review shots in the table (edit names, tasks, statuses)
6. Click **"Create Shots"** or **"Dry Run"** to preview

### 📤 Publishing Reviews

Quick workflow for uploading review versions:

1. Select a clip or sequence in Flame (Media Panel, Batch, or Timeline)
2. Right-click → **"📤 Publish Review to ftrack..."**
3. Select a task from your in-progress tasks (grouped by project)
4. Add an optional comment/note for the version
5. Click **"Publish"**
6. The integration will:
   - Export video from Flame using the review preset
   - Create a version in ftrack
   - Upload the video with encoding for web playback
   - Show progress feedback throughout

### ⏱️ Time Tracking

Track time spent on ftrack tasks directly from Flame:

1. Open Time Tracker: Right-click → **"⏱️ Time Tracker"** (available from any menu)
2. The window shows your in-progress tasks
3. Select a task and click **"Start"** to begin tracking
4. Use **"Pause"** to pause the timer (auto-pauses after 5 minutes of inactivity)
5. Click **"Stop"** to save time to ftrack
6. **Mini Timer**: When minimized, a compact floating timer appears (always on top)
7. **Task History**: Recently tracked tasks appear in the history for quick access
8. **Manual Entry**: Enter time manually if you forgot to start the timer

**Time Tracker Features:**
- Window persists when changing Flame projects
- Auto-pause on 5 minutes of inactivity
- Visual alert when timer is paused
- Confirmation when switching tasks with active timer
- Saves time logs directly to ftrack

### 🔑 Configuring Credentials

On first use, or to update credentials:

1. Right-click → **"🔑 Configure Credentials..."** (available from any menu)
2. Enter your ftrack credentials:
   - **Server URL**: Your ftrack server (e.g., `https://yourcompany.ftrackapp.com`)
   - **API Key**: Your personal API key from ftrack
   - **Username**: Your ftrack username
3. Click **"Test Connection"** to verify
4. Click **"Save"** to store credentials securely

Credentials are stored in `~/.config/flame_ftrack/credentials.json`

### 📋 Demo Mode

Test the integration without Flame selection:

1. Right-click → **"📋 Demo Mode"** (or Main Menu → ftrack → Demo Mode)
2. The main window opens with demo data
3. Explore all features without needing a Flame selection

### Standalone Demo Mode

For testing without Flame entirely:

```bash
cd flame-ftrack-integration
python run_demo.py
```

## Project Structure

```
flame-ftrack-integration/
├── flame_ftrack_hook.py      # Flame Python hook (entry point)
├── run_demo.py               # Standalone demo launcher
├── diagnose_environment.py   # Environment diagnostic tool
├── setup_environment.sh      # Virtual environment setup (recommended)
├── setup_simple.sh           # Simple system-wide installation
├── clean_install.sh          # Clean uninstall & reinstall script
│
├── src/
│   ├── core/
│   │   ├── flame_exporter.py    # Flame export logic (thumbnails, videos)
│   │   └── ftrack_manager.py    # ftrack API operations
│   │
│   ├── gui/
│   │   ├── main_window.py       # Main application window (shot creation)
│   │   ├── shot_table.py        # Shot table widget with batch editing
│   │   ├── publish_review.py    # Publish Review dialog
│   │   ├── time_tracker.py      # Time Tracker window
│   │   ├── dialogs.py           # Progress and settings dialogs
│   │   └── styles.py            # Dark theme stylesheet
│   │
│   ├── config/
│   │   └── credentials_manager.py  # Credential storage and GUI
│   │
│   ├── ftrack_api/
│   │   └── ftrack_wrapper.py    # ftrack API wrapper with mock support
│   │
│   └── flame_hooks/
│       └── exporter.py          # Flame hook utilities
│
├── presets/
│   ├── thumb_for_ftrack.xml           # JPEG thumbnail preset
│   └── ftrack_video__shot_version.xml # H.264/MP4 video preset
│
├── config/
│   └── .env.template            # Environment variables template
│
└── docs/
    └── API_COMPATIBILITY.md     # ftrack API compatibility notes
```

## Configuration

### Export Presets

The integration uses custom Flame export presets with `<shot name>` in the namePattern to generate individual files per shot:

**Thumbnail Preset** (`thumb_for_ftrack.xml`):
- Format: JPEG
- Resolution: Source
- Pattern: `<name>/<shot name>` (creates: `sequence_name/shot_name.jpg`)

**Video Preset** (`ftrack_video__shot_version.xml`):
- Format: MP4 (H.264)
- Resolution: 50% of source
- Pattern: `<name>/<shot name>` (creates: `sequence_name/shot_name.mp4`)

### Output Directories

Default directories (configurable in the UI):
- **Thumbnails**: `~/flame_thumbnails/`
- **Videos**: `~/flame_videos/`
- **Review Exports**: `~/flame_review_exports/` (for Publish Review)

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                         FLAME TIMELINE                          │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐  │
│  │ vfx_010 │ vfx_020 │ vfx_030 │ vfx_040 │ vfx_050 │ vfx_060 │  │
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLAME-FTRACK INTEGRATION                     │
│                                                                 │
│  Step 1: Export Thumbnails (JPEG)                              │
│          └─► ~/flame_thumbnails/SEQUENCE/shot.jpg              │
│                                                                 │
│  Step 2: Export Videos (H.264/MP4)                             │
│          └─► ~/flame_videos/SEQUENCE/shot.mp4                  │
│                                                                 │
│  Step 3: Create in ftrack                                      │
│          ├─► Create Sequences                                  │
│          ├─► Create Shots                                      │
│          ├─► Create Tasks                                      │
│          ├─► Upload Thumbnails                                 │
│          └─► Upload Versions (with encoding for playback)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FTRACK STUDIO                           │
│                                                                 │
│  Project/                                                       │
│  └── SEQUENCE_NAME/                                            │
│      ├── vfx_010 [Shot] ─► Tasks, Thumbnail, Version           │
│      ├── vfx_020 [Shot] ─► Tasks, Thumbnail, Version           │
│      ├── vfx_030 [Shot] ─► Tasks, Thumbnail, Version           │
│      └── ...                                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Security

- **Project Isolation**: All operations are scoped to the explicitly selected project
- **Credential Storage**: Stored locally in user's config directory (not in repository)
- **No Hardcoded Values**: Server URLs, API keys, and project IDs are never hardcoded
- **Validation**: Operations require explicit project selection before execution

## API Compatibility

This integration is compatible with:
- **ftrack-python-api** 2.x
- **ftrack Studio** (cloud and on-premise)

See [docs/API_COMPATIBILITY.md](docs/API_COMPATIBILITY.md) for detailed API notes.

## Troubleshooting

### Common Issues

**"ftrack_api module not found"**
- Run the installation script: `./setup_environment.sh` (for venv) or `./setup_simple.sh` (for system-wide)
- Verify installation: `python diagnose_environment.py`
- Check that the hook can find the virtual environment (if using venv method)

**"Flame module not found"**
- Run from within Flame's Python environment, or use `run_demo.py` for standalone testing

**"Connection failed"**
- Verify server URL includes `https://`
- Check API key is valid and not expired
- Ensure network access to ftrack server

**"Videos not playing in ftrack"**
- Videos require `encode_media()` for streaming playback
- Wait a few seconds after upload for encoding to complete

**"Thumbnails not found"**
- Check preset is installed in `/opt/Autodesk/shared/export/presets/sequence_publish/`
- Verify output directory exists and is writable

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Autodesk Flame](https://www.autodesk.com/products/flame) for the powerful compositing platform
- [ftrack](https://www.ftrack.com/) for the production tracking API
- The VFX community for continuous feedback and inspiration

## Author

**Wilton Matos** - VFX Artist & Pipeline Developer

---

*Built with ❤️ for the VFX community*
