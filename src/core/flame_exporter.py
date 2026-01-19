"""
Flame Exporter - Business logic for Flame export operations

Responsible for:
- Extracting shot data from timeline segments
- Exporting thumbnails using XML preset
- Exporting videos using native Flame H.264/MP4 preset

Both thumbnail and video export use the same approach:
1. Export entire sequence with preset
2. Flame generates individual files per shot (using <shot name> in namePattern)
3. Match exported files to shot data
"""

import os
import logging
import glob
import time
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Callable, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Default export preset paths
DEFAULT_THUMB_PRESET_PATH = "/opt/Autodesk/shared/export/presets/sequence_publish/thumb_for_ftrack.xml"
DEFAULT_VIDEO_PRESET_PATH = "/opt/Autodesk/shared/export/presets/sequence_publish/ftrack_video__shot_version.xml"

# Default output directories
DEFAULT_THUMB_DIR = os.path.expanduser("~/flame_thumbnails")
DEFAULT_VIDEO_DIR = os.path.expanduser("~/flame_videos")


# =============================================================================
# FLAME EXPORTER
# =============================================================================

class FlameExporter:
    """
    Manages thumbnail and video exports from Flame
    
    Uses configurable XML presets for both thumbnails and videos.
    Both presets use <shot name> in namePattern to generate individual files per shot.
    """
    
    def __init__(self, thumb_preset_path: str = None, video_preset_path: str = None,
                 output_dir: str = None, video_dir: str = None):
        """
        Args:
            thumb_preset_path: Path to XML export preset for thumbnails
            video_preset_path: Path to XML export preset for videos
            output_dir: Output directory for thumbnails
            video_dir: Output directory for videos
        """
        # Thumbnail preset
        self.thumb_preset_path = thumb_preset_path or DEFAULT_THUMB_PRESET_PATH
        self.output_dir = output_dir or DEFAULT_THUMB_DIR
        
        # Video preset
        self.video_preset_path = video_preset_path or DEFAULT_VIDEO_PRESET_PATH
        self.video_dir = video_dir or DEFAULT_VIDEO_DIR
        
        # Legacy compatibility
        self.preset_path = self.thumb_preset_path
        self._flame = None
    
    # -------------------------------------------------------------------------
    # PROPERTIES
    # -------------------------------------------------------------------------
    
    @property
    def is_flame_available(self) -> bool:
        """Check if Flame is available"""
        try:
            import flame
            self._flame = flame
            return True
        except ImportError:
            return False
    
    @property
    def preset_exists(self) -> bool:
        """Check if thumbnail preset file exists"""
        return os.path.exists(self.thumb_preset_path)
    
    @property
    def thumb_preset_exists(self) -> bool:
        """Check if thumbnail preset file exists"""
        return os.path.exists(self.thumb_preset_path)
    
    @property
    def video_preset_exists(self) -> bool:
        """Check if video preset file exists"""
        return os.path.exists(self.video_preset_path)
    
    # -------------------------------------------------------------------------
    # DATA EXTRACTION
    # -------------------------------------------------------------------------
    
    def extract_shots_from_selection(self, selection) -> List[Dict]:
        """
        Extract shot data from Flame selection
        
        Args:
            selection: Flame selection (PySequence, etc)
        
        Returns:
            List of dicts with shot data
        """
        shots = []
        
        if not self.is_flame_available:
            logger.warning("Flame not available")
            return shots
        
        flame = self._flame
        
        try:
            for sequence in selection:
                if not isinstance(sequence, flame.PySequence):
                    continue
                
                # Sequence name
                seq_name = self._clean_flame_string(sequence.name.get_value())
                
                for ver in sequence.versions:
                    for track in ver.tracks:
                        for segment in track.segments:
                            shot_name = self._clean_flame_string(segment.shot_name.get_value())
                            
                            if not shot_name:
                                continue
                            
                            # Comment as description
                            comment = ""
                            if segment.comment:
                                comment = self._clean_flame_string(segment.comment.get_value())
                            
                            # Shot data
                            shot_data = {
                                'Sequence': seq_name,
                                'Shot Name': shot_name,
                                'Task Types': 'Compositing',
                                'Status': 'ready_to_start',
                                'Description': comment,
                                '_segment': segment,
                                '_sequence': sequence,
                            }
                            
                            shots.append(shot_data)
            
            logger.info(f"Extracted {len(shots)} shots from selection")
            
        except Exception as e:
            logger.error(f"Error extracting shots: {e}")
        
        return shots
    
    def _clean_flame_string(self, value) -> str:
        """Remove quotes from Flame string format"""
        s = str(value)
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1]
        return s
    
    # -------------------------------------------------------------------------
    # THUMBNAIL EXPORT
    # -------------------------------------------------------------------------
    
    def export_thumbnails(self, selection, shots_data: List[Dict],
                         progress_callback: Callable = None) -> Dict:
        """
        Export thumbnails using Flame preset
        
        Args:
            selection: Flame selection (sequences)
            shots_data: List of dicts with shot data
            progress_callback: Function (step, current, total, message)
        
        Returns:
            Dict with results: exported, failed, paths
        """
        results = {
            'exported': 0,
            'failed': 0,
            'paths': {},  # shot_name -> path
            'errors': []
        }
        
        if not self.is_flame_available:
            results['errors'].append("Flame not available")
            return results
        
        if not self.preset_exists:
            results['errors'].append(f"Preset not found: {self.preset_path}")
            return results
        
        # Validate preset
        preset_valid, preset_error = self._validate_preset()
        if not preset_valid:
            results['errors'].append(f"Invalid preset: {preset_error}")
            return results
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        flame = self._flame
        
        # Collect valid sequences
        sequences_to_export = []
        for item in selection:
            if isinstance(item, flame.PySequence):
                sequences_to_export.append(item)
        
        if not sequences_to_export:
            results['errors'].append("No sequences found in selection")
            return results
        
        total = len(sequences_to_export)
        
        # Export each sequence
        for i, sequence in enumerate(sequences_to_export):
            seq_name = self._clean_flame_string(sequence.name.get_value())
            
            if progress_callback:
                progress_callback(1, i + 1, total, f"Exporting thumbnails: {seq_name}")
            
            try:
                # Create PyExporter - based on SammieRoto
                exporter = flame.PyExporter()
                exporter.foreground = True
                
                # Correct API: export(source, preset_path, destination)
                exporter.export(sequence, self.preset_path, self.output_dir)
                
                logger.info(f"Thumbnail export completed for: {seq_name}")
                
            except Exception as e:
                error_msg = f"Thumbnail export error for {seq_name}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Wait for files to be written
        time.sleep(2)
        
        # Find exported thumbnails for each shot
        for shot_data in shots_data:
            shot_name = shot_data.get('Shot Name', '')
            if not shot_name:
                continue
            
            thumb_file = self._find_exported_thumbnail(shot_name)
            if thumb_file:
                results['exported'] += 1
                results['paths'][shot_name] = thumb_file
                logger.info(f"Found thumbnail: {thumb_file}")
            else:
                results['failed'] += 1
                logger.warning(f"Thumbnail not found for: {shot_name}")
        
        return results
    
    # -------------------------------------------------------------------------
    # VIDEO EXPORT (using custom H.264/MP4 preset)
    # -------------------------------------------------------------------------
    
    def export_videos(self, selection, shots_data: List[Dict],
                     progress_callback: Callable = None) -> Dict:
        """
        Export videos using custom Flame preset (H.264/MP4)
        
        Uses the same approach as thumbnails:
        1. Export entire sequence with preset
        2. Flame creates individual files per shot (using <shot name> in namePattern)
        3. Match exported files to shot data
        
        Args:
            selection: Flame selection (sequences)
            shots_data: List of dicts with shot data
            progress_callback: Function (step, current, total, message)
        
        Returns:
            Dict with results: exported, failed, paths
        """
        results = {
            'exported': 0,
            'failed': 0,
            'paths': {},  # shot_name -> path
            'errors': []
        }
        
        if not self.is_flame_available:
            results['errors'].append("Flame not available")
            logger.error("Flame not available for video export")
            return results
        
        # Check video preset exists
        if not self.video_preset_exists:
            results['errors'].append(f"Video preset not found: {self.video_preset_path}")
            logger.error(f"Video preset not found: {self.video_preset_path}")
            return results
        
        # Ensure output directory exists
        os.makedirs(self.video_dir, exist_ok=True)
        logger.info(f"Video output directory: {self.video_dir}")
        logger.info(f"Using video preset: {self.video_preset_path}")
        
        flame = self._flame
        total = len(shots_data)
        
        if progress_callback:
            progress_callback(2, 0, total, "Exporting videos...")
        
        try:
            # Export entire selection (same approach as thumbnails)
            exporter = flame.PyExporter()
            exporter.foreground = True
            
            logger.info("Starting video export for entire selection...")
            
            # Export all sequences in selection
            for sequence in selection:
                if hasattr(sequence, 'name'):
                    seq_name = self._clean_flame_string(sequence.name.get_value())
                    logger.info(f"Exporting sequence: {seq_name}")
                    
                    exporter.export(sequence, self.video_preset_path, self.video_dir)
            
            # Wait for export to complete
            time.sleep(2)
            
            # Find exported videos (mp4 for H.264, mov for ProRes)
            video_files = []
            for ext in ["*.mov", "*.mp4", "*.m4v"]:
                video_files.extend(glob.glob(os.path.join(self.video_dir, ext)))
                video_files.extend(glob.glob(os.path.join(self.video_dir, "**", ext), recursive=True))
            
            video_files = list(set(video_files))  # Remove duplicates
            
            logger.info(f"Found {len(video_files)} video files after export")
            for vf in video_files[:10]:
                logger.info(f"  - {vf}")
            
            # Match exported files to shots
            for shot_data in shots_data:
                shot_name = shot_data.get('Shot Name', '')
                if not shot_name:
                    continue
                
                # Look for matching video file
                video_path = self._find_video_file(shot_name)
                
                if video_path:
                    results['exported'] += 1
                    results['paths'][shot_name] = video_path
                    logger.info(f"Found video for {shot_name}: {video_path}")
                else:
                    results['failed'] += 1
                    logger.warning(f"No video found for {shot_name}")
            
            if progress_callback:
                progress_callback(2, total, total, "Video export complete")
                
        except Exception as e:
            error_msg = f"Video export error: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg, exc_info=True)
        
        return results
    
    def _find_video_file(self, shot_name: str) -> Optional[str]:
        """
        Find exported video file for a shot
        
        The preset uses namePattern: <name>/<shot name>
        So videos are in: video_dir/sequence_name/shot_name.mov
        
        Args:
            shot_name: Shot name to search for
        
        Returns:
            Path to video file or None
        """
        # Search patterns (from most specific to most generic)
        patterns = [
            # In subfolder (sequence_name/shot.mov) - expected pattern
            os.path.join(self.video_dir, "*", f"{shot_name}.mov"),
            os.path.join(self.video_dir, "*", f"{shot_name}.mp4"),
            
            # Direct in folder
            os.path.join(self.video_dir, f"{shot_name}.mov"),
            os.path.join(self.video_dir, f"{shot_name}.mp4"),
            
            # With frame number suffix
            os.path.join(self.video_dir, "*", f"{shot_name}.*.mov"),
            os.path.join(self.video_dir, "*", f"{shot_name}.*.mp4"),
            
            # Wildcard patterns
            os.path.join(self.video_dir, "*", f"{shot_name}*.mov"),
            os.path.join(self.video_dir, "*", f"{shot_name}*.mp4"),
            os.path.join(self.video_dir, f"{shot_name}*.mov"),
            os.path.join(self.video_dir, f"{shot_name}*.mp4"),
            
            # Recursive search
            os.path.join(self.video_dir, "**", f"*{shot_name}*.mov"),
            os.path.join(self.video_dir, "**", f"*{shot_name}*.mp4"),
        ]
        
        for pattern in patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return matches[0]
        
        return None
    
    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------
    
    def _validate_preset(self) -> tuple:
        """
        Validate XML preset file
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        try:
            import xml.etree.ElementTree as ET
            
            tree = ET.parse(self.preset_path)
            root = tree.getroot()
            
            if root.tag != 'preset':
                return False, "Root element is not 'preset'"
            
            type_elem = root.find('type')
            if type_elem is None:
                return False, "Missing 'type' element"
            
            return True, ""
            
        except ET.ParseError as e:
            return False, f"XML parse error: {str(e)}"
        except Exception as e:
            return False, str(e)
    
    def _find_exported_thumbnail(self, shot_name: str) -> Optional[str]:
        """
        Find exported thumbnail for a shot
        
        Searches multiple directory structures and filename patterns.
        """
        if not shot_name:
            return None
        
        # Search patterns - from most specific to most generic
        search_patterns = [
            # Direct in folder
            os.path.join(self.output_dir, f"{shot_name}.jpg"),
            os.path.join(self.output_dir, f"{shot_name}.0001.jpg"),
            os.path.join(self.output_dir, f"{shot_name}.00000001.jpg"),
            
            # In subfolder (sequence_name/shot.jpg)
            os.path.join(self.output_dir, "*", f"{shot_name}.jpg"),
            os.path.join(self.output_dir, "*", f"{shot_name}.0001.jpg"),
            os.path.join(self.output_dir, "*", f"{shot_name}.00000001.jpg"),
            
            # Any file starting with shot_name
            os.path.join(self.output_dir, f"{shot_name}*.jpg"),
            os.path.join(self.output_dir, "*", f"{shot_name}*.jpg"),
            
            # Recursive search
            os.path.join(self.output_dir, "**", f"{shot_name}*.jpg"),
        ]
        
        for pattern in search_patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                matches.sort()
                return matches[0]
        
        return None
    
    def find_exported_video(self, shot_name: str) -> Optional[str]:
        """
        Find exported video for a shot
        
        Args:
            shot_name: Name of the shot
        
        Returns:
            Path to video file or None
        """
        if not shot_name:
            return None
        
        video_path = os.path.join(self.video_dir, f"{shot_name}.mp4")
        if os.path.exists(video_path):
            return video_path
        
        # Search with patterns
        patterns = [
            os.path.join(self.video_dir, f"{shot_name}*.mp4"),
            os.path.join(self.video_dir, "*", f"{shot_name}*.mp4"),
        ]
        
        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
        
        return None
    
    def get_thumbnail_path(self, shot_name: str) -> str:
        """Return expected thumbnail path"""
        return os.path.join(self.output_dir, f"{shot_name}.jpg")
    
    def get_video_path(self, shot_name: str) -> str:
        """Return expected video path"""
        return os.path.join(self.video_dir, f"{shot_name}.mp4")
    
    def thumbnail_exists(self, shot_name: str) -> bool:
        """Check if thumbnail exists"""
        return self._find_exported_thumbnail(shot_name) is not None
    
    def video_exists(self, shot_name: str) -> bool:
        """Check if video exists"""
        return self.find_exported_video(shot_name) is not None
    
    def clear_thumbnails(self):
        """Remove all thumbnails from directory"""
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def clear_videos(self):
        """Remove all videos from directory"""
        if os.path.exists(self.video_dir):
            shutil.rmtree(self.video_dir)
        os.makedirs(self.video_dir, exist_ok=True)
    
    def list_exported_thumbnails(self) -> List[str]:
        """List all exported thumbnails"""
        if not os.path.exists(self.output_dir):
            return []
        
        thumbnails = []
        for pattern in ["*.jpg", "**/*.jpg"]:
            thumbnails.extend(glob.glob(
                os.path.join(self.output_dir, pattern), 
                recursive=True
            ))
        
        return thumbnails
    
    def list_exported_videos(self) -> List[str]:
        """List all exported videos"""
        if not os.path.exists(self.video_dir):
            return []
        
        return glob.glob(os.path.join(self.video_dir, "*.mp4"))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_flame_selection():
    """
    Get current Flame selection
    
    Returns:
        List of selected items or None
    """
    try:
        import flame
        return flame.media_panel.selected_entries
    except:
        return None


def is_sequence_selection(selection) -> bool:
    """Check if selection contains sequences"""
    try:
        import flame
        if selection:
            for item in selection:
                if isinstance(item, flame.PySequence):
                    return True
    except ImportError:
        pass
    return False


def check_video_export_requirements() -> Dict:
    """
    Check if video export requirements are met
    
    Returns:
        Dict with status of each requirement
    """
    return {
        'flame': is_flame_available(),
        'thumb_preset': os.path.exists(DEFAULT_THUMB_PRESET_PATH),
        'video_preset': os.path.exists(DEFAULT_VIDEO_PRESET_PATH),
    }
