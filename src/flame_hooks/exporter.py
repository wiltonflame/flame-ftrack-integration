"""
Flame Thumbnail Exporter

Based on Autodesk's export_selection.py, adapted for ftrack integration.

THUMBNAIL FLOW:
===============
1. For each shot in timeline, exports ONLY 1 FRAME (not the entire sequence)
2. Frame is defined by: first, middle, last or specific
3. Files go to temporary directory (/tmp/flame_ftrack_XXXXX/)
4. After upload to ftrack, directory is automatically cleaned

IMPORTANT:
- Does NOT export all frames of the shot
- Uses "Poster Frame Jpeg" preset that generates 1 .jpg file
- Cleanup is automatic when using context manager (with)
"""

import os
import logging
import tempfile
import shutil
from typing import Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class FlameExporter:
    """
    Exports thumbnails and movies from Flame clips
    
    Recommended usage (with automatic cleanup):
        with FlameExporter() as exporter:
            results = exporter.export_timeline_thumbnails(selection)
            # Upload to ftrack here
        # Directory is automatically cleaned when exiting with
    """
    
    # Options for which frame to export
    FRAME_FIRST = "first"
    FRAME_MIDDLE = "middle"  
    FRAME_LAST = "last"
    
    def __init__(self, export_dir: str = None, auto_cleanup: bool = True):
        """
        Args:
            export_dir: Base directory for export. 
                       If None, uses temporary directory.
            auto_cleanup: If True, removes files when exiting context manager
        """
        self.export_dir = export_dir or tempfile.mkdtemp(prefix='flame_ftrack_')
        self.auto_cleanup = auto_cleanup
        self._temp_files: List[str] = []  # Tracks created files
        self._ensure_dir(self.export_dir)
        
        logger.info(f"FlameExporter initialized: {self.export_dir}")
    
    def __enter__(self):
        """Context manager - permite usar 'with FlameExporter() as exporter:'"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager - limpa automaticamente ao sair"""
        if self.auto_cleanup:
            self.cleanup()
    
    def _ensure_dir(self, path: str):
        """Create directory if it doesn't exist"""
        os.makedirs(path, exist_ok=True)
    
    def _get_flame(self):
        """Import flame module (only available inside Flame)"""
        try:
            import flame
            return flame
        except ImportError:
            raise ImportError(
                "Module 'flame' not available. "
                "This code must be executed inside Flame."
            )
    
    def get_thumbnail_preset_path(self) -> str:
        """Return path to JPEG thumbnail preset"""
        flame = self._get_flame()
        
        preset_dir = flame.PyExporter.get_presets_dir(
            flame.PyExporter.PresetVisibility.Autodesk,
            flame.PyExporter.PresetType.Image_Sequence
        )
        
        # Try default preset
        preset_path = os.path.join(preset_dir, "Jpeg", "Poster Frame Jpeg (8-bit).xml")
        
        if not os.path.exists(preset_path):
            # Fallback: search for any JPEG preset
            jpeg_dir = os.path.join(preset_dir, "Jpeg")
            if os.path.exists(jpeg_dir):
                for f in os.listdir(jpeg_dir):
                    if f.endswith('.xml'):
                        preset_path = os.path.join(jpeg_dir, f)
                        logger.info(f"Using alternative preset: {f}")
                        break
        
        return preset_path
    
    def get_movie_preset_path(self) -> str:
        """Return path to QuickTime movie preset"""
        flame = self._get_flame()
        
        preset_dir = flame.PyExporter.get_presets_dir(
            flame.PyExporter.PresetVisibility.Autodesk,
            flame.PyExporter.PresetType.Movie
        )
        
        return os.path.join(preset_dir, "QuickTime", "QuickTime (8-bit Uncompressed).xml")
    
    def _calculate_frame_to_export(
        self, 
        clip_or_segment,
        frame_position: str = "middle"
    ) -> int:
        """
        Calculate which frame to export based on desired position
        
        Args:
            clip_or_segment: Flame clip or segment
            frame_position: "first", "middle", "last", or specific number
            
        Returns:
            Frame number to export
        """
        try:
            # Try to get duration from clip/segment
            if hasattr(clip_or_segment, 'record_duration'):
                duration = clip_or_segment.record_duration.get_value()
                start = clip_or_segment.record_in.get_value()
            elif hasattr(clip_or_segment, 'duration'):
                duration = clip_or_segment.duration.get_value()
                start = 1
            else:
                # Fallback: try in/out marks
                start = clip_or_segment.in_mark.get_value() if hasattr(clip_or_segment, 'in_mark') else 1
                end = clip_or_segment.out_mark.get_value() if hasattr(clip_or_segment, 'out_mark') else start + 100
                duration = end - start
            
            if frame_position == self.FRAME_FIRST:
                return start
            elif frame_position == self.FRAME_LAST:
                return start + duration - 1
            elif frame_position == self.FRAME_MIDDLE:
                return start + (duration // 2)
            elif isinstance(frame_position, int):
                return frame_position
            else:
                return start + (duration // 2)  # Default: middle
                
        except Exception as e:
            logger.warning(f"Could not calculate frame: {e}, using frame 1")
            return 1
    
    def export_thumbnail(
        self, 
        clip, 
        output_dir: str = None,
        frame: int = None,
        frame_position: str = "middle"
    ) -> Optional[str]:
        """
        Export single frame from a clip as JPEG
        
        IMPORTANT: Exports only 1 frame, not the entire sequence!
        
        Args:
            clip: Flame PyClip or PySequence
            output_dir: Destination directory (default: self.export_dir)
            frame: Specific frame to export (if None, uses frame_position)
            frame_position: "first", "middle", "last" (default: middle)
            
        Returns:
            Path to exported file or None if fails
        """
        flame = self._get_flame()
        
        output_dir = output_dir or self.export_dir
        self._ensure_dir(output_dir)
        
        preset_path = self.get_thumbnail_preset_path()
        
        if not os.path.exists(preset_path):
            logger.error(f"Preset not found: {preset_path}")
            return None
        
        # Determine which frame to export
        if frame is None:
            frame = self._calculate_frame_to_export(clip, frame_position)
        
        logger.info(f"Exporting frame {frame} from '{clip.name.get_value()}'")
        
        # Configure exporter
        exporter = flame.PyExporter()
        exporter.foreground = True
        exporter.export_between_marks = True
        
        # Save original marks
        in_mark = clip.in_mark.get_value()
        out_mark = clip.out_mark.get_value()
        
        try:
            # ================================================================
            # CRITICAL: Set marks to export ONLY 1 FRAME
            # ================================================================
            clip.in_mark = frame
            clip.out_mark = frame + 1  # out_mark is exclusive
            
            # Export
            exporter.export(clip, preset_path, output_dir)
            
            # Determine exported file name
            clip_name = str(clip.name.get_value())
            # Remove PyFlame characters
            if clip_name.startswith("'") and clip_name.endswith("'"):
                clip_name = clip_name[1:-1]
            
            # Flame adds frame number to name
            expected_file = os.path.join(output_dir, f"{clip_name}.{frame:08d}.jpg")
            
            if os.path.exists(expected_file):
                self._temp_files.append(expected_file)
                logger.info(f"Thumbnail exported: {expected_file}")
                return expected_file
            
            # Try to find file (may have different name)
            for f in os.listdir(output_dir):
                if f.endswith('.jpg') and clip_name in f:
                    found_path = os.path.join(output_dir, f)
                    self._temp_files.append(found_path)
                    logger.info(f"Thumbnail found: {found_path}")
                    return found_path
            
            logger.warning(f"Thumbnail file not found for: {clip_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error exporting thumbnail: {e}")
            return None
            
        finally:
            # Restore original marks
            clip.in_mark = in_mark
            clip.out_mark = out_mark
    
    def export_movie(
        self, 
        clip, 
        output_dir: str = None
    ) -> Optional[str]:
        """
        Export clip as QuickTime
        
        Args:
            clip: Flame PyClip or PySequence
            output_dir: Destination directory
            
        Returns:
            Path to exported file or None if fails
        """
        flame = self._get_flame()
        
        output_dir = output_dir or self.export_dir
        self._ensure_dir(output_dir)
        
        preset_path = self.get_movie_preset_path()
        
        if not os.path.exists(preset_path):
            logger.error(f"Preset not found: {preset_path}")
            return None
        
        # Configura exporter
        exporter = flame.PyExporter()
        exporter.foreground = True
        
        try:
            exporter.export(clip, preset_path, output_dir)
            
            clip_name = str(clip.name.get_value())
            if clip_name.startswith("'") and clip_name.endswith("'"):
                clip_name = clip_name[1:-1]
            
            expected_file = os.path.join(output_dir, f"{clip_name}.mov")
            
            if os.path.exists(expected_file):
                logger.info(f"Movie exportado: {expected_file}")
                return expected_file
            
            # Procura arquivo
            for f in os.listdir(output_dir):
                if f.endswith('.mov') and clip_name in f:
                    return os.path.join(output_dir, f)
            
            return None
            
        except Exception as e:
            logger.error(f"Error exporting movie: {e}")
            return None
    
    def export_timeline_thumbnails(
        self, 
        selection,
        progress_callback: callable = None,
        frame_position: str = "middle"
    ) -> List[Tuple[str, str]]:
        """
        Export thumbnails from all segments in a timeline
        
        IMPORTANT: 
        - Exports only 1 frame per shot (not the entire sequence!)
        - Use context manager for automatic cleanup
        
        Args:
            selection: Flame selection (containing PySequence)
            progress_callback: Function (current, total, shot_name) for progress
            frame_position: "first", "middle", "last" - which frame to use
            
        Returns:
            List of tuples (shot_name, thumbnail_path)
            
        Example:
            with FlameExporter() as exporter:
                results = exporter.export_timeline_thumbnails(selection)
                for shot_name, thumb_path in results:
                    ftrack.upload_thumbnail(shot_id, thumb_path)
            # Files are automatically cleaned
        """
        flame = self._get_flame()
        results = []
        
        # Coleta todos os segmentos primeiro
        segments_info = []
        
        for sequence in selection:
            if not isinstance(sequence, flame.PySequence):
                continue
            
            seq_name = str(sequence.name.get_value())
            if seq_name.startswith("'"):
                seq_name = seq_name[1:-1]
            
            for ver in sequence.versions:
                for track in ver.tracks:
                    for segment in track.segments:
                        shot_name = str(segment.shot_name.get_value())
                        if shot_name.startswith("'"):
                            shot_name = shot_name[1:-1]
                        
                        if shot_name:
                            segments_info.append({
                                'segment': segment,
                                'shot_name': shot_name,
                                'seq_name': seq_name
                            })
        
        total = len(segments_info)
        logger.info(f"Exporting thumbnails from {total} shots...")
        
        for i, info in enumerate(segments_info):
            shot_name = info['shot_name']
            
            if progress_callback:
                progress_callback(i + 1, total, shot_name)
            
            try:
                # Create subdirectory per sequence
                seq_dir = os.path.join(self.export_dir, info['seq_name'])
                self._ensure_dir(seq_dir)
                
                # For segments, get the source clip
                source = info['segment'].source
                if source:
                    # Export only 1 frame from middle of shot
                    thumb_path = self.export_thumbnail(
                        source, 
                        seq_dir,
                        frame_position=frame_position
                    )
                    
                    if thumb_path:
                        # Rename to use shot name (without frame number)
                        final_path = os.path.join(seq_dir, f"{shot_name}.jpg")
                        if thumb_path != final_path:
                            try:
                                if os.path.exists(final_path):
                                    os.remove(final_path)
                                os.rename(thumb_path, final_path)
                                thumb_path = final_path
                            except Exception as e:
                                logger.warning(f"Could not rename: {e}")
                        
                        results.append((shot_name, thumb_path))
                        logger.info(f"✅ Thumbnail: {shot_name}")
                    else:
                        results.append((shot_name, None))
                        logger.warning(f"❌ Failed: {shot_name}")
                else:
                    results.append((shot_name, None))
                    logger.warning(f"❌ No source: {shot_name}")
                    
            except Exception as e:
                logger.error(f"Error processing {shot_name}: {e}")
                results.append((shot_name, None))
        
        success_count = sum(1 for _, path in results if path is not None)
        logger.info(f"Export complete: {success_count}/{total} thumbnails created")
        
        return results
    
    def cleanup(self, force: bool = False):
        """
        Remove temporary export directory
        
        Args:
            force: Se True, remove mesmo se auto_cleanup=False
        """
        if not (self.auto_cleanup or force):
            logger.info(f"Cleanup ignored (auto_cleanup=False). Files in: {self.export_dir}")
            return
        
        if self.export_dir and os.path.exists(self.export_dir):
            try:
                # Count files before removing
                file_count = sum(1 for _ in Path(self.export_dir).rglob('*') if _.is_file())
                
                shutil.rmtree(self.export_dir)
                logger.info(f"🧹 Cleanup: {file_count} file(s) removed from {self.export_dir}")
                
            except Exception as e:
                logger.warning(f"Could not remove {self.export_dir}: {e}")
    
    def get_temp_files(self) -> List[str]:
        """Return list of temporary files created"""
        return self._temp_files.copy()
    
    def get_export_summary(self) -> dict:
        """Return export summary"""
        if not os.path.exists(self.export_dir):
            return {'exists': False, 'files': 0, 'size_mb': 0}
        
        files = list(Path(self.export_dir).rglob('*'))
        file_count = sum(1 for f in files if f.is_file())
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        
        return {
            'exists': True,
            'path': self.export_dir,
            'files': file_count,
            'size_mb': round(total_size / (1024 * 1024), 2)
        }


class ThumbnailExportDialog:
    """
    Dialog for thumbnail export with progress
    """
    
    def __init__(self, parent=None):
        self.parent = parent
        self.cancelled = False
    
    def export_with_progress(
        self, 
        exporter: FlameExporter,
        selection
    ) -> List[Tuple[str, str]]:
        """
        Export with progress dialog
        """
        from PySide6 import QtWidgets, QtCore
        
        # Create progress dialog
        progress = QtWidgets.QProgressDialog(
            "Exporting thumbnails...",
            "Cancel",
            0, 100,
            self.parent
        )
        progress.setWindowTitle("Export")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        
        def on_cancel():
            self.cancelled = True
        
        progress.canceled.connect(on_cancel)
        
        def update_progress(current, total, shot_name):
            if self.cancelled:
                return
            
            percent = int((current / total) * 100)
            progress.setValue(percent)
            progress.setLabelText(f"Exporting: {shot_name}\n({current}/{total})")
            QtWidgets.QApplication.processEvents()
        
        # Execute export
        results = exporter.export_timeline_thumbnails(
            selection,
            progress_callback=update_progress
        )
        
        progress.close()
        
        return results


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_export_directory(default_path: str = "/tmp") -> Optional[str]:
    """
    Show browser for directory selection
    """
    try:
        import flame
        
        flame.browser.show(
            title="Select export directory",
            default_path=default_path,
            multi_selection=False,
            select_directory=True
        )
        
        return flame.browser.selection[0] if flame.browser.selection else None
        
    except ImportError:
        # Fallback to Qt
        from PySide6 import QtWidgets
        
        dialog = QtWidgets.QFileDialog()
        dialog.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)
        dialog.setOption(QtWidgets.QFileDialog.Option.ShowDirsOnly, True)
        
        if dialog.exec():
            return dialog.selectedFiles()[0]
        
        return None


def extract_segment_info(selection) -> List[dict]:
    """
    Extract information from timeline segments
    
    Args:
        selection: Flame selection
        
    Returns:
        List of dicts with segment information
    """
    try:
        import flame
    except ImportError:
        return []
    
    segments = []
    
    for sequence in selection:
        if not isinstance(sequence, flame.PySequence):
            continue
        
        seq_name = str(sequence.name.get_value())
        if seq_name.startswith("'"):
            seq_name = seq_name[1:-1]
        
        for ver in sequence.versions:
            for track in ver.tracks:
                for segment in track.segments:
                    shot_name = segment.shot_name.get_value()
                    if isinstance(shot_name, str):
                        if shot_name.startswith("'"):
                            shot_name = shot_name[1:-1]
                    else:
                        shot_name = str(shot_name)
                    
                    comment = segment.comment.get_value() if segment.comment else ""
                    if isinstance(comment, str) and comment.startswith("'"):
                        comment = comment[1:-1]
                    
                    if shot_name:
                        segments.append({
                            'sequence_name': seq_name,
                            'shot_name': shot_name,
                            'comment': comment,
                            'segment': segment,
                            'start_frame': segment.record_in.get_value(),
                            'end_frame': segment.record_out.get_value(),
                            'duration': segment.record_duration.get_value()
                        })
    
    return segments
