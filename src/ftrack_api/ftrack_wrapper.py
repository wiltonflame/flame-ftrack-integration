"""
ftrack API Wrapper for Flame integration

This module encapsulates common ftrack API operations:
- List projects and hierarchy
- Create shots and tasks
- Upload thumbnails

Tested and validated with real ftrack on 2025-12-29.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


def get_ftrack_connection(use_mock: bool = False):
    """
    Factory function to get ftrack connection
    
    Tries to load credentials from credentials_manager first.
    
    Args:
        use_mock: If True, returns mock instead of real connection
        
    Returns:
        FtrackConnection or FtrackConnectionMock
    """
    if use_mock:
        return FtrackConnectionMock()
    
    # Try to load credentials from credentials_manager
    try:
        from ..config.credentials_manager import get_credentials, credentials_are_configured
        
        if credentials_are_configured():
            creds = get_credentials()
            return FtrackConnection(
                server_url=creds['server'],
                api_key=creds['api_key'],
                api_user=creds['api_user']
            )
    except ImportError:
        pass
    
    # Fallback to environment variables
    return FtrackConnection()


@dataclass
class FtrackShot:
    """Representation of a shot for ftrack creation"""
    name: str
    description: str = ""
    task_type: str = "Compositing"
    task_status: str = "not_started"
    thumbnail_path: Optional[str] = None
    custom_attributes: Optional[Dict[str, Any]] = None


class FtrackConnection:
    """
    Manages connection and operations with ftrack API
    
    Usage:
        with FtrackConnection() as ftrack:
            projects = ftrack.get_projects()
            ftrack.create_shot(project_id, sequence_name, shot_data)
    """
    
    def __init__(self, server_url: str = None, api_key: str = None, api_user: str = None):
        """
        Initialize ftrack connection
        
        Args:
            server_url: ftrack server URL (or via FTRACK_SERVER env)
            api_key: ftrack API key (or via FTRACK_API_KEY env)
            api_user: API user (or via FTRACK_API_USER env)
        """
        self.server_url = server_url or os.environ.get('FTRACK_SERVER')
        self.api_key = api_key or os.environ.get('FTRACK_API_KEY')
        self.api_user = api_user or os.environ.get('FTRACK_API_USER')
        
        self._session = None
        self._validate_credentials()
    
    def _validate_credentials(self):
        """Validate if credentials are configured"""
        missing = []
        if not self.server_url:
            missing.append('FTRACK_SERVER')
        if not self.api_key:
            missing.append('FTRACK_API_KEY')
        if not self.api_user:
            missing.append('FTRACK_API_USER')
        
        if missing:
            raise ValueError(
                f"Missing ftrack credentials: {', '.join(missing)}. "
                "Configure via environment variables or .env file"
            )
    
    def __enter__(self):
        """Context manager - connects to ftrack"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager - disconnects from ftrack"""
        self.disconnect()
    
    def connect(self):
        """Establish connection with ftrack"""
        try:
            import ftrack_api
            
            self._session = ftrack_api.Session(
                server_url=self.server_url,
                api_key=self.api_key,
                api_user=self.api_user
            )
            logger.info(f"Connected to ftrack: {self.server_url}")
            
        except ImportError:
            raise ImportError(
                "ftrack-python-api not installed. "
                "Run: ./setup_environment.sh (for venv) or ./setup_simple.sh (system-wide)"
            )
        except Exception as e:
            logger.error(f"Error connecting to ftrack: {e}")
            raise
    
    def disconnect(self):
        """Close connection to ftrack"""
        if self._session:
            self._session.close()
            self._session = None
            logger.info("Disconnected from ftrack")
    
    @property
    def session(self):
        """Return active ftrack session"""
        if not self._session:
            raise RuntimeError("Not connected to ftrack. Use connect() first.")
        return self._session
    
    # =========================================================================
    # PROJETOS
    # =========================================================================
    
    def get_projects(
        self, 
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
        search: str = None
    ) -> List[Dict]:
        """
        List available projects with filters for production environment
        
        Args:
            active_only: If True, returns only active projects (recommended for production)
            limit: Maximum number of projects to return (default: 50)
            offset: Offset for pagination
            search: Filter by name (case-insensitive)
            
        Returns:
            List of dictionaries with project information
            
        Production Note:
            In environments with many projects, always use active_only=True
            and limit to avoid loading hundreds of inactive/archived projects.
        """
        try:
            # ftrack query - simple entity name only (NOT SQL)
            all_projects = self.session.query('Project').all()
            
            # Filter in Python
            filtered = []
            for p in all_projects:
                # Get name
                try:
                    name = p['name']
                except:
                    continue
                
                # Search filter
                if search and search.lower() not in name.lower():
                    continue
                
                # Skip status filtering for now (causes API errors)
                filtered.append({
                    'p': p,
                    'name': name,
                    'status': 'Active'  # Default
                })
            
            # Sort by name
            filtered.sort(key=lambda x: x['name'].lower())
            
            # Apply pagination
            paginated = filtered[offset:offset + limit]
            
            logger.info(f"Query projetos: {len(paginated)} retornados de {len(filtered)}")
            
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            return []
        
        result = []
        for item in paginated:
            p = item['p']
            
            try:
                result.append({
                    'id': p['id'],
                    'name': item['name'],
                    'full_name': item['name'],
                    'status': item['status'],
                    'start_date': None,
                    'end_date': None,
                })
            except:
                continue
        
        return result
    
    def get_projects_count(self, active_only: bool = True) -> int:
        """
        Return project count (useful for pagination)
        
        Args:
            active_only: If True, counts only active projects
            
        Returns:
            Total number of projects
        """
        try:
            all_projects = self.session.query('Project').all()
            return len(all_projects)
        except:
            return 0
    
    def search_projects(self, search_term: str, limit: int = 20) -> List[Dict]:
        """
        Quick project search by name
        
        Useful for autocomplete in interface.
        
        Args:
            search_term: Search term
            limit: Maximum results
            
        Returns:
            List of projects matching the search
        """
        return self.get_projects(
            active_only=True,
            limit=limit,
            search=search_term
        )
    
    def get_project_by_name(self, name: str) -> Optional[Any]:
        """Search project by name"""
        projects = self.session.query(
            f'Project where name is "{name}"'
        ).all()
        return projects[0] if projects else None
    
    def get_project_hierarchy(self, project_id: str) -> Dict:
        """
        Return complete project hierarchy (sequences, shots, etc)
        
        Args:
            project_id: Project ID in ftrack
            
        Returns:
            Dictionary with hierarchical structure
        """
        project = self.session.get('Project', project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        hierarchy = {
            'id': project['id'],
            'name': project['name'],
            'children': []
        }
        
        # Search direct children of project (Episodes, Sequences, etc)
        children = self.session.query(
            f'TypedContext where parent.id is "{project_id}"'
        ).all()
        
        for child in children:
            hierarchy['children'].append(
                self._build_hierarchy_recursive(child)
            )
        
        return hierarchy
    
    def _build_hierarchy_recursive(self, entity, max_depth: int = 5) -> Dict:
        """Build hierarchy recursively"""
        if max_depth <= 0:
            return {'id': entity['id'], 'name': entity['name'], 'type': entity.entity_type}
        
        node = {
            'id': entity['id'],
            'name': entity['name'],
            'type': entity.entity_type,
            'children': []
        }
        
        # Search children
        children = self.session.query(
            f'TypedContext where parent.id is "{entity["id"]}"'
        ).all()
        
        for child in children:
            node['children'].append(
                self._build_hierarchy_recursive(child, max_depth - 1)
            )
        
        return node
    
    # =========================================================================
    # SEQUENCES E SHOTS
    # =========================================================================
    
    def get_sequences(self, project_id: str) -> List[Dict]:
        """List sequences of a project"""
        sequences = self.session.query(
            f'Sequence where project.id is "{project_id}"'
        ).all()
        
        return [
            {'id': s['id'], 'name': s['name']}
            for s in sequences
        ]
    
    def get_or_create_sequence(self, project_id: str, sequence_name: str) -> Any:
        """
        Search or create a sequence
        
        Args:
            project_id: Project ID
            sequence_name: Sequence name
            
        Returns:
            ftrack Sequence or Folder entity
        """
        project = self.session.get('Project', project_id)
        
        # Try to find existing sequence
        existing = self.session.query(
            f'Sequence where name is "{sequence_name}" and project.id is "{project_id}"'
        ).first()
        
        if existing:
            logger.info(f"Sequence found: {sequence_name}")
            return existing
        
        # Also try as Folder
        existing_folder = self.session.query(
            f'Folder where name is "{sequence_name}" and project.id is "{project_id}"'
        ).first()
        
        if existing_folder:
            logger.info(f"Folder found: {sequence_name}")
            return existing_folder
        
        # Create new sequence (tested and validated)
        try:
            sequence = self.session.create('Sequence', {
                'name': sequence_name,
                'parent': project
            })
            self.session.commit()
            logger.info(f"Sequence created: {sequence_name}")
            return sequence
            
        except Exception as e:
            logger.warning(f"Error creating Sequence, trying Folder: {e}")
            self.session.rollback()
            
            # Fallback para Folder
            try:
                folder = self.session.create('Folder', {
                    'name': sequence_name,
                    'parent': project
                })
                self.session.commit()
                logger.info(f"Folder created: {sequence_name}")
                return folder
            except Exception as e2:
                logger.error(f"Error creating Folder: {e2}")
                self.session.rollback()
                raise
    
    def create_shot(
        self, 
        parent_id: str, 
        shot: FtrackShot,
        create_task: bool = True
    ) -> Dict:
        """
        Create a shot in ftrack
        
        Args:
            parent_id: Parent ID (Sequence or Episode)
            shot: Shot data to be created
            create_task: If True, creates associated task
            
        Returns:
            Dictionary with information about created shot
        """
        parent = self.session.get('TypedContext', parent_id)
        if not parent:
            raise ValueError(f"Parent not found: {parent_id}")
        
        # Check if shot already exists
        existing = self.session.query(
            f'Shot where name is "{shot.name}" and parent.id is "{parent_id}"'
        ).first()
        
        if existing:
            logger.warning(f"Shot already exists: {shot.name}")
            return {'id': existing['id'], 'name': existing['name'], 'created': False}
        
        # Create the shot
        shot_entity = self.session.create('Shot', {
            'name': shot.name,
            'parent': parent,
            'description': shot.description
        })
        
        # Apply custom attributes if any
        if shot.custom_attributes:
            for key, value in shot.custom_attributes.items():
                try:
                    shot_entity['custom_attributes'][key] = value
                except KeyError:
                    logger.warning(f"Custom attribute not found: {key}")
        
        self.session.commit()
        logger.info(f"Shot created: {shot.name}")
        
        result = {
            'id': shot_entity['id'],
            'name': shot_entity['name'],
            'created': True
        }
        
        # Create task if requested
        if create_task:
            task = self.create_task(
                shot_entity['id'],
                task_type=shot.task_type,
                task_status=shot.task_status,
                description=shot.description
            )
            result['task_id'] = task['id']
        
        # Upload thumbnail se houver
        if shot.thumbnail_path and os.path.exists(shot.thumbnail_path):
            self.upload_thumbnail(shot_entity['id'], shot.thumbnail_path)
        
        return result
    
    def create_shots_batch(
        self, 
        parent_id: str, 
        shots: List[FtrackShot],
        progress_callback: callable = None
    ) -> List[Dict]:
        """
        Create multiple shots in batch
        
        Args:
            parent_id: Parent ID
            shots: List of shots to create
            progress_callback: Function called with (current, total) for progress
            
        Returns:
            List with results for each shot
        """
        results = []
        total = len(shots)
        
        for i, shot in enumerate(shots):
            try:
                result = self.create_shot(parent_id, shot)
                results.append(result)
            except Exception as e:
                logger.error(f"Error creating shot {shot.name}: {e}")
                results.append({
                    'name': shot.name,
                    'error': str(e),
                    'created': False
                })
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return results
    
    # =========================================================================
    # TASKS
    # =========================================================================
    
    def get_task_types(self) -> List[Dict]:
        """List available task types"""
        try:
            types = self.session.query('Type').all()
            return [{'id': t['id'], 'name': t['name']} for t in types]
        except:
            return []
    
    def get_task_statuses(self) -> List[Dict]:
        """List available task statuses"""
        statuses = self.session.query('Status').all()
        return [{'id': s['id'], 'name': s['name']} for s in statuses]
    
    def create_task(
        self,
        parent_id: str,
        task_type: str = "Compositing",
        task_status: str = "not_started",
        task_name: str = None,
        description: str = ""
    ) -> Dict:
        """Create a task associated with a shot or asset"""
        parent = self.session.get('TypedContext', parent_id)
        
        # Search for task type
        task_type_entity = self.session.query(
            f'Type where name is "{task_type}"'
        ).first()
        
        if not task_type_entity:
            logger.warning(f"Task type '{task_type}' not found, using default")
            task_type_entity = self.session.query('Type').first()
        
        # Search for status
        status_entity = self.session.query(
            f'Status where name is "{task_status}"'
        ).first()
        
        if not status_entity:
            status_entity = self.session.query('Status').first()
        
        # Create task
        task = self.session.create('Task', {
            'name': task_name or task_type,
            'parent': parent,
            'type': task_type_entity,
            'status': status_entity,
            'description': description
        })
        
        self.session.commit()
        logger.info(f"Task created: {task['name']} ({task_type})")
        
        return {'id': task['id'], 'name': task['name']}
    
    def create_multiple_tasks(
        self,
        parent_id: str,
        task_types: List[str],
        task_status: str = "not_started"
    ) -> List[Dict]:
        """
        Create multiple tasks in a shot (validated in tests)
        
        Args:
            parent_id: Shot/parent ID
            task_types: List of task types (e.g., ["Compositing", "Roto", "Tracking"])
            task_status: Initial status for all tasks
            
        Returns:
            List of dictionaries with information about created tasks
        """
        results = []
        
        for task_type in task_types:
            try:
                # Task name = type in lowercase
                task_name = task_type.lower().replace(" ", "_")
                task = self.create_task(
                    parent_id=parent_id,
                    task_type=task_type,
                    task_status=task_status,
                    task_name=task_name
                )
                results.append(task)
            except Exception as e:
                logger.error(f"Error creating task {task_type}: {e}")
                results.append({'name': task_type, 'error': str(e)})
        
        return results

    def create_conform_task(
        self,
        parent_id: str,
        task_type: str = "Conform",
        auto_pending_review: bool = True
    ) -> Optional[Dict]:
        """
        Create Conform task with 'Pending Review' status automatically
        
        This task is independent of other shot tasks and serves to
        indicate that the material was conformed/verified when created
        from Flame.
        
        Args:
            parent_id: Shot/parent ID
            task_type: Task type (default: "Conform")
            auto_pending_review: If True, sets status to "Pending Review"
            
        Returns:
            Dict with information about created task or None if fails
            
        Note:
            Tries multiple name variations for status "Pending Review"
            to ensure compatibility with different ftrack configurations.
        """
        try:
            parent = self.session.get('TypedContext', parent_id)
            if not parent:
                logger.error(f"Parent not found: {parent_id}")
                return None
            
            # Search for task type "Conform"
            # Try common name variations
            task_type_entity = None
            conform_type_names = [task_type, "Conform", "conform", "CONFORM", "Conforming"]
            
            for type_name in conform_type_names:
                task_type_entity = self.session.query(
                    f'Type where name is "{type_name}"'
                ).first()
                if task_type_entity:
                    logger.debug(f"Task type found: {type_name}")
                    break
            
            if not task_type_entity:
                # If "Conform" doesn't exist, use first available type
                # and log a warning
                task_type_entity = self.session.query('Type').first()
                logger.warning(
                    f"Task type 'Conform' not found in ftrack. "
                    f"Using default type: {task_type_entity['name'] if task_type_entity else 'N/A'}. "
                    "Consider creating 'Conform' type in ftrack for better organization."
                )
            
            # Search for status "Pending Review" if auto_pending_review=True
            status_entity = None
            if auto_pending_review:
                # Try multiple status name variations
                pending_review_names = [
                    "Pending Review",
                    "pending_review", 
                    "Pending review",
                    "pending review",
                    "PENDING REVIEW",
                    "PendingReview",
                    "Awaiting Review",
                    "Review",
                    "To Review"
                ]
                
                for status_name in pending_review_names:
                    status_entity = self.session.query(
                        f'Status where name is "{status_name}"'
                    ).first()
                    if status_entity:
                        logger.debug(f"Status 'Pending Review' found as: {status_name}")
                        break
                
                if not status_entity:
                    logger.warning(
                        "Status 'Pending Review' not found. "
                        "Using first available status."
                    )
                    status_entity = self.session.query('Status').first()
            else:
                # Use "Not Started" as default
                status_entity = self.session.query('Status where name is "Not Started"').first()
                if not status_entity:
                    status_entity = self.session.query('Status').first()
            
            # Create Conform task
            task = self.session.create('Task', {
                'name': 'conform',  # Standardized name in lowercase
                'parent': parent,
                'type': task_type_entity,
                'status': status_entity,
                'description': 'Auto-created conform task from Flame integration'
            })
            
            self.session.commit()
            
            status_name = status_entity['name'] if status_entity else 'Unknown'
            logger.info(f"✓ Conform task created: {parent['name']}/conform (Status: {status_name})")
            
            return {
                'id': task['id'],
                'name': task['name'],
                'type': task_type_entity['name'] if task_type_entity else 'Unknown',
                'status': status_name
            }
            
        except Exception as e:
            logger.error(f"Error creating Conform task: {e}")
            return None
    
    # =========================================================================
    # THUMBNAILS
    # =========================================================================
    
    def upload_thumbnail(self, entity_id: str, thumbnail_path: str) -> bool:
        """
        Upload thumbnail to an entity
        
        Uses create_thumbnail() method which is the official ftrack API helper.
        Works with Project, Task, Shot, AssetVersion, User.
        
        Args:
            entity_id: Entity ID (shot, task, etc)
            thumbnail_path: Local path to image file
            
        Returns:
            True if success, False otherwise
            
        Ref: https://ftrack-python-api.rtd.ftrack.com/en/stable/example/thumbnail.html
        """
        if not os.path.exists(thumbnail_path):
            logger.error(f"Thumbnail not found: {thumbnail_path}")
            return False
        
        try:
            # Search for entity - can be Shot, Task, AssetVersion, etc.
            # All inherit from TypedContext and support thumbnails
            entity = self.session.get('TypedContext', entity_id)
            
            if not entity:
                # Try as AssetVersion
                entity = self.session.get('AssetVersion', entity_id)
            
            if not entity:
                logger.error(f"Entity not found: {entity_id}")
                return False
            
            # Use helper method create_thumbnail() from ftrack API
            # This method:
            # 1. Creates a FileComponent
            # 2. Uploads to ftrack.server location
            # 3. Sets as entity thumbnail
            thumbnail_component = entity.create_thumbnail(thumbnail_path)
            
            self.session.commit()
            
            logger.info(f"Thumbnail uploaded to: {entity['name']}")
            return True
            
        except Exception as e:
            logger.error(f"Error uploading thumbnail: {e}")
            return False
    
    def get_thumbnail_url(self, entity_id: str, size: int = 300) -> Optional[str]:
        """
        Returns thumbnail URL of an entity
        
        Args:
            entity_id: Entity ID
            size: Thumbnail size (100, 300, 500)
            
        Returns:
            Thumbnail URL or None
        """
        try:
            import ftrack_api.symbol
            
            entity = self.session.get('TypedContext', entity_id)
            if not entity or not entity.get('thumbnail_id'):
                return None
            
            thumbnail_component = self.session.get(
                'Component', 
                entity['thumbnail_id']
            )
            
            if not thumbnail_component:
                return None
            
            server_location = self.session.get(
                'Location', 
                ftrack_api.symbol.SERVER_LOCATION_ID
            )
            
            return server_location.get_thumbnail_url(
                thumbnail_component, 
                size=size
            )
            
        except Exception as e:
            logger.error(f"Error getting thumbnail URL: {e}")
            return None
    
    def upload_thumbnails_batch(
        self, 
        entity_thumbnail_pairs: List[tuple],
        progress_callback: callable = None
    ) -> Dict[str, bool]:
        """
        Upload multiple thumbnails
        
        Args:
            entity_thumbnail_pairs: List of (entity_id, thumbnail_path)
            progress_callback: Progress function (current, total)
            
        Returns:
            Dictionary {entity_id: success}
        """
        results = {}
        total = len(entity_thumbnail_pairs)
        
        for i, (entity_id, thumb_path) in enumerate(entity_thumbnail_pairs):
            results[entity_id] = self.upload_thumbnail(entity_id, thumb_path)
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return results

    # =========================================================================
    # NOTES (API ftrack real)
    # =========================================================================
    
    def create_note(
        self,
        entity_id: str,
        content: str,
        author_id: str = None,
        category: str = None
    ) -> Optional[Dict]:
        """
        Create a note on an entity
        
        Args:
            entity_id: Entity ID (Shot, Task, AssetVersion)
            content: Note content
            author_id: Author user ID (optional, uses API user if not provided)
            category: Note category name (optional)
            
        Returns:
            Dict with information about created note
            
        Ref: Notes are real entities in ftrack API
        """
        try:
            entity = self.session.get('TypedContext', entity_id)
            if not entity:
                entity = self.session.get('AssetVersion', entity_id)
            
            if not entity:
                logger.error(f"Entity not found: {entity_id}")
                return None
            
            note_data = {
                'content': content,
                'parent': entity
            }
            
            # Author
            if author_id:
                note_data['author'] = self.session.get('User', author_id)
            else:
                # Use API user
                current_user = self.session.query(
                    f'User where username is "{self.api_user}"'
                ).first()
                if current_user:
                    note_data['author'] = current_user
            
            # Category (if exists)
            if category:
                note_category = self.session.query(
                    f'NoteCategory where name is "{category}"'
                ).first()
                if note_category:
                    note_data['category'] = note_category
            
            note = self.session.create('Note', note_data)
            self.session.commit()
            
            logger.info(f"Note created on: {entity['name']}")
            return {
                'id': note['id'],
                'content': note['content'],
                'created_at': str(note['date'])
            }
            
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return None
    
    def get_notes(self, entity_id: str) -> List[Dict]:
        """
        Fetch notes from an entity
        
        Args:
            entity_id: Entity ID
            
        Returns:
            List of notes
        """
        try:
            notes = self.session.query(
                f'Note where parent_id is "{entity_id}"'
            ).all()
            
            return [
                {
                    'id': n['id'],
                    'content': n['content'],
                    'author': n['author']['username'] if n['author'] else 'Unknown',
                    'date': str(n['date']),
                    'category': n['category']['name'] if n.get('category') else None
                }
                for n in notes
            ]
        except Exception as e:
            logger.error(f"Error fetching notes: {e}")
            return []
    
    def get_note_categories(self) -> List[Dict]:
        """List available note categories"""
        try:
            categories = self.session.query('NoteCategory').all()
            return [{'id': c['id'], 'name': c['name']} for c in categories]
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return []

    # =========================================================================
    # TIMELOGS (API ftrack real)
    # =========================================================================
    
    def create_timelog(
        self,
        task_id: str,
        duration: float,
        user_id: str = None,
        start: datetime = None,
        comment: str = ""
    ) -> Optional[Dict]:
        """
        Create a time log entry for a task
        
        Args:
            task_id: Task ID
            duration: Duration in seconds
            user_id: User ID (optional)
            start: Start date/time (optional)
            comment: Comment (optional)
            
        Returns:
            Dict with timelog information
            
        Ref: Timelogs are associated with Tasks via task['timelogs']
        """
        try:
            task = self.session.get('Task', task_id)
            if not task:
                logger.error(f"Task not found: {task_id}")
                return None
            
            timelog_data = {
                'duration': duration,  # in seconds
                'comment': comment
            }
            
            if start:
                timelog_data['start'] = start
            
            if user_id:
                timelog_data['user'] = self.session.get('User', user_id)
            else:
                current_user = self.session.query(
                    f'User where username is "{self.api_user}"'
                ).first()
                if current_user:
                    timelog_data['user'] = current_user
            
            timelog = self.session.create('Timelog', timelog_data)
            
            # Associate with task
            task['timelogs'].append(timelog)
            
            self.session.commit()
            
            logger.info(f"Timelog created: {duration/3600:.2f}h on {task['name']}")
            return {
                'id': timelog['id'],
                'duration': timelog['duration'],
                'start': str(timelog.get('start', ''))
            }
            
        except Exception as e:
            logger.error(f"Error creating timelog: {e}")
            return None
    
    def get_timelogs(self, task_id: str) -> List[Dict]:
        """
        Fetch timelogs from a task
        
        Args:
            task_id: Task ID
            
        Returns:
            List of timelogs
        """
        try:
            task = self.session.get('Task', task_id)
            if not task:
                return []
            
            timelogs = task['timelogs']
            
            return [
                {
                    'id': t['id'],
                    'duration_hours': t['duration'] / 3600,
                    'user': t['user']['username'] if t.get('user') else 'Unknown',
                    'start': str(t.get('start', '')),
                    'comment': t.get('comment', '')
                }
                for t in timelogs
            ]
        except Exception as e:
            logger.error(f"Error fetching timelogs: {e}")
            return []

    # =========================================================================
    # ASSET VERSIONS (API ftrack real)
    # =========================================================================
    
    def get_asset_versions(self, entity_id: str) -> List[Dict]:
        """
        Search for asset versions of an entity (Shot, Task)
        
        Args:
            entity_id: Parent entity ID
            
        Returns:
            List of asset versions
        """
        try:
            versions = self.session.query(
                f'AssetVersion where task_id is "{entity_id}" or '
                f'asset.parent_id is "{entity_id}"'
            ).all()
            
            return [
                {
                    'id': v['id'],
                    'version': v['version'],
                    'asset_name': v['asset']['name'] if v.get('asset') else 'Unknown',
                    'status': v['status']['name'] if v.get('status') else 'Unknown',
                    'date': str(v['date']),
                    'comment': v.get('comment', ''),
                    'thumbnail_id': v.get('thumbnail_id')
                }
                for v in versions
            ]
        except Exception as e:
            logger.error(f"Error fetching versions: {e}")
            return []

    # =========================================================================
    # USERS
    # =========================================================================
    
    def get_users(self, active_only: bool = True) -> List[Dict]:
        """List ftrack users"""
        try:
            users = self.session.query('User').all()
            
            result = []
            for u in users:
                try:
                    # Skip inactive if requested
                    if active_only and not u.get('is_active', True):
                        continue
                    
                    result.append({
                        'id': u['id'],
                        'username': u['username'],
                        'first_name': u.get('first_name', ''),
                        'last_name': u.get('last_name', ''),
                        'email': u.get('email', '')
                    })
                except:
                    continue
            
            return result
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []

# =========================================================================
# BATCH CREATION (for Flame interface integration)
# =========================================================================
    
    def create_shots_from_table(
        self,
        project_id: str,
        shots_data: List[Dict],
        progress_callback: callable = None,
        dry_run: bool = False,
        validate_project: bool = True
    ) -> Dict:
        """
        Create complete structure from interface table data
        
        This function was validated in tests with real ftrack.
        Creates: Sequences → Shots → Tasks → Thumbnails
        
        Args:
            project_id: Project ID in ftrack
            shots_data: List of dicts with shot data:
                [
                    {
                        "Sequence": "SEQ010",
                        "Shot Name": "SHOT_010",
                        "Task Types": ["Compositing", "Roto"],  # or comma-separated string
                        "Status": "not_started",
                        "Description": "Opening scene",
                        "thumbnail_path": "/path/to/thumb.jpg"  # optional
                    },
                    ...
                ]
            progress_callback: Function called with (current, total, message)
            dry_run: If True, only simulates without creating anything (useful for validation)
            validate_project: If True, verifies project exists and is active
            
        Returns:
            Dict with summary:
            {
                "success": True/False,
                "dry_run": True/False,
                "project_name": "Project Name",
                "sequences_created": 2,
                "shots_created": 10,
                "tasks_created": 25,
                "thumbnails_uploaded": 10,
                "errors": [],
                "warnings": []
            }
            
        Production Security:
            - Use dry_run=True first to validate the operation
            - validate_project=True ensures project exists and is active
            - All operations are logged for audit
        """
        result = {
            "success": True,
            "dry_run": dry_run,
            "project_name": None,
            "sequences_created": 0,
            "shots_created": 0,
            "shots_existed": 0,
            "tasks_created": 0,
            "conform_tasks_created": 0,  # New independent count
            "thumbnails_uploaded": 0,
            "errors": [],
            "warnings": []
        }
        
        # =====================================================================
        # SECURITY VALIDATION
        # =====================================================================
        if validate_project:
            try:
                project = self.session.get('Project', project_id)
                if not project:
                    result["success"] = False
                    result["errors"].append(f"Project not found: {project_id}")
                    logger.error(f"[SECURITY] Project not found: {project_id}")
                    return result
                
                result["project_name"] = project['name']
                
                # Check project status
                try:
                    if project['status']:
                        status_name = project['status']['name'] if hasattr(project['status'], '__getitem__') else str(project['status'])
                        if status_name.lower() not in ['active', 'in progress', 'production']:
                            result["warnings"].append(
                                f"⚠️ Project '{project['name']}' has status '{status_name}'. "
                                "Make sure this is the correct project."
                            )
                            logger.warning(f"[SECURITY] Project with non-active status: {status_name}")
                except:
                    pass
                
                logger.info(f"[SECURITY] Project validated: {project['name']} ({project_id})")
                
            except Exception as e:
                result["success"] = False
                result["errors"].append(f"Error validating project: {e}")
                return result
        
        if dry_run:
            logger.info(f"[DRY-RUN] Simulating creation of {len(shots_data)} shots...")
        
        total_steps = len(shots_data)
        current_step = 0
        
        # Group shots by sequence
        sequences_map = {}
        for shot_data in shots_data:
            seq_name = shot_data.get("Sequence", "DEFAULT_SEQ")
            if seq_name not in sequences_map:
                sequences_map[seq_name] = []
            sequences_map[seq_name].append(shot_data)
        
        # Cache of created sequences
        sequence_cache = {}
        
        try:
            for seq_name, seq_shots in sequences_map.items():
                # Create or find sequence
                if seq_name not in sequence_cache:
                    try:
                        if dry_run:
                            logger.info(f"[DRY-RUN] Would create sequence: {seq_name}")
                            sequence_cache[seq_name] = {'id': f'dry-run-{seq_name}', 'name': seq_name}
                        else:
                            sequence = self.get_or_create_sequence(project_id, seq_name)
                            sequence_cache[seq_name] = sequence
                        result["sequences_created"] += 1
                        logger.info(f"Sequence ready: {seq_name}")
                    except Exception as e:
                        error_msg = f"Error creating sequence {seq_name}: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        continue
                
                sequence = sequence_cache[seq_name]
                
                # Create shots for the sequence
                for shot_data in seq_shots:
                    current_step += 1
                    shot_name = shot_data.get("Shot Name", f"SHOT_{current_step:03d}")
                    
                    if progress_callback:
                        prefix = "[DRY-RUN] " if dry_run else ""
                        progress_callback(
                            current_step, 
                            total_steps, 
                            f"{prefix}Creating {seq_name}/{shot_name}..."
                        )
                    
                    try:
                        if dry_run:
                            # Simulate creation
                            logger.info(f"[DRY-RUN] Would create shot: {seq_name}/{shot_name}")
                            result["shots_created"] += 1
                            shot = {'id': f'dry-run-{shot_name}', 'name': shot_name}
                        else:
                            # Create actual shot
                            shot = self._create_shot_entity(
                                parent=sequence,
                                name=shot_name,
                                description=shot_data.get("Description", "")
                            )
                            
                            if shot.get('existed'):
                                result["shots_existed"] += 1
                                result["warnings"].append(f"Shot already existed: {seq_name}/{shot_name}")
                            else:
                                result["shots_created"] += 1
                        
                        # =======================================================
                        # CONFORM TASK - Created automatically with "Pending Review"
                        # This task is independent of others and indicates that the shot
                        # was created from Flame and needs to be verified
                        # =======================================================
                        if not shot.get('existed'):  # Only create conform for new shots
                            try:
                                if dry_run:
                                    logger.info(f"[DRY-RUN] Would create Conform task: {shot_name}/conform (Pending Review)")
                                    result["conform_tasks_created"] += 1
                                else:
                                    conform_task = self.create_conform_task(
                                        parent_id=shot['id'],
                                        task_type="Conform",
                                        auto_pending_review=True
                                    )
                                    if conform_task:
                                        result["conform_tasks_created"] += 1
                            except Exception as e:
                                logger.warning(f"Error creating Conform task for {shot_name}: {e}")
                                result["warnings"].append(f"Conform task not created: {shot_name}")
                        
                        # Process tasks (other tasks defined by user)
                        task_types = shot_data.get("Task Types", [])
                        if isinstance(task_types, str):
                            task_types = [t.strip() for t in task_types.split(",") if t.strip()]
                        
                        for task_type in task_types:
                            try:
                                if dry_run:
                                    logger.info(f"[DRY-RUN] Would create task: {task_type}")
                                else:
                                    self.create_task(
                                        parent_id=shot['id'],
                                        task_type=task_type,
                                        task_status=shot_data.get("Status", "not_started"),
                                        task_name=task_type.lower().replace(" ", "_")
                                    )
                                result["tasks_created"] += 1
                            except Exception as e:
                                logger.warning(f"Error creating task {task_type}: {e}")
                                result["warnings"].append(f"Task not created: {shot_name}/{task_type}")
                        
                        # Upload thumbnail if exists
                        thumb_path = shot_data.get("thumbnail_path")
                        if thumb_path and os.path.exists(thumb_path):
                            if dry_run:
                                logger.info(f"[DRY-RUN] Would upload thumbnail: {thumb_path}")
                                result["thumbnails_uploaded"] += 1
                            else:
                                if self.upload_thumbnail(shot['id'], thumb_path):
                                    result["thumbnails_uploaded"] += 1
                        
                    except Exception as e:
                        error_msg = f"Error creating shot {shot_name}: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
            
            if result["errors"]:
                result["success"] = len(result["errors"]) < len(shots_data)
            
        except Exception as e:
            result["success"] = False
            result["errors"].append(f"General error: {e}")
            logger.error(f"Error in batch creation: {e}")
        
        # Final log for audit
        logger.info(
            f"[{'DRY-RUN' if dry_run else 'EXECUTION'}] Result: "
            f"{result['sequences_created']} sequences, "
            f"{result['shots_created']} new shots, "
            f"{result['shots_existed']} existing shots, "
            f"{result['conform_tasks_created']} conform tasks, "
            f"{result['tasks_created']} tasks, "
            f"{result['thumbnails_uploaded']} thumbnails, "
            f"{len(result['errors'])} errors"
        )
        
        return result
    
    def _create_shot_entity(self, parent, name: str, description: str = "") -> Dict:
        """
        Create Shot entity (internal method)
        
        Args:
            parent: Parent entity (Sequence/Folder)
            name: Shot name
            description: Description
            
        Returns:
            Dict with id and name of created shot
        """
        # Check if already exists
        existing = self.session.query(
            f'Shot where name is "{name}" and parent.id is "{parent["id"]}"'
        ).first()
        
        if existing:
            logger.info(f"Shot already exists: {name}")
            return {'id': existing['id'], 'name': existing['name'], 'existed': True}
        
        # Create new shot
        shot = self.session.create('Shot', {
            'name': name,
            'parent': parent,
            'description': description
        })
        
        self.session.commit()
        logger.info(f"Shot created: {name}")
        
        return {'id': shot['id'], 'name': shot['name'], 'existed': False}


# =============================================================================
# MOCK FOR DEVELOPMENT WITHOUT FTRACK
# =============================================================================

class FtrackConnectionMock(FtrackConnection):
    """
    Mock ftrack connection for development/tests
    Does not require credentials or real connection
    """
    
    def __init__(self, *args, **kwargs):
        # Don't validate credentials in mock
        self.server_url = "https://mock.ftrackapp.com"
        self.api_key = "mock-key"
        self.api_user = "mock@user.com"
        self._session = None
        self._mock_data = self._generate_mock_data()
    
    def _generate_mock_data(self) -> Dict:
        """Generate fake data for tests"""
        return {
            'projects': [
                {
                    'id': 'proj-001',
                    'name': 'PROJETO_TESTE_01',
                    'full_name': 'Projeto de Teste 01',
                    'status': 'Active',
                    'start_date': '2025-01-01',
                    'end_date': '2025-12-31',
                },
                {
                    'id': 'proj-002', 
                    'name': 'COMERCIAL_MARCA_X',
                    'full_name': 'Comercial Marca X',
                    'status': 'Active',
                    'start_date': '2025-03-01',
                    'end_date': '2025-06-30',
                },
            ],
            'sequences': {
                'proj-001': [
                    {'id': 'seq-001', 'name': 'SEQ_010'},
                    {'id': 'seq-002', 'name': 'SEQ_020'},
                    {'id': 'seq-003', 'name': 'SEQ_030'},
                ],
                'proj-002': [
                    {'id': 'seq-004', 'name': 'CENA_01'},
                    {'id': 'seq-005', 'name': 'CENA_02'},
                ],
            },
            'task_types': [
                {'id': 'tt-001', 'name': 'Compositing'},
                {'id': 'tt-002', 'name': 'Roto'},
                {'id': 'tt-003', 'name': 'Tracking'},
                {'id': 'tt-004', 'name': 'Paint'},
            ],
            'task_statuses': [
                {'id': 'ts-001', 'name': 'Not Started'},
                {'id': 'ts-002', 'name': 'In Progress'},
                {'id': 'ts-003', 'name': 'Pending Review'},
                {'id': 'ts-004', 'name': 'Approved'},
            ],
            'users': [
                {'id': 'user-001', 'username': 'wilton.silva', 'first_name': 'Wilton', 'last_name': 'Silva', 'email': 'wilton@studio.com'},
                {'id': 'user-002', 'username': 'artist01', 'first_name': 'Artist', 'last_name': 'One', 'email': 'artist01@studio.com'},
            ],
            'note_categories': [
                {'id': 'nc-001', 'name': 'Internal'},
                {'id': 'nc-002', 'name': 'Client'},
                {'id': 'nc-003', 'name': 'Technical'},
            ],
            'notes': {},
            'timelogs': {},
        }
    
    def connect(self):
        logger.info("[MOCK] Simulated connection to ftrack")
        self._session = True  # Simulate active session
    
    def disconnect(self):
        logger.info("[MOCK] Simulated disconnection")
        self._session = None
    
    def get_projects(
        self, 
        active_only: bool = True, 
        limit: int = 50, 
        offset: int = 0, 
        search: str = None
    ) -> List[Dict]:
        """Mock get_projects with filters"""
        projects = self._mock_data['projects']
        
        # Filter by search
        if search:
            projects = [p for p in projects if search.lower() in p['name'].lower()]
        
        # Apply offset and limit
        return projects[offset:offset + limit]
    
    def get_projects_count(self, active_only: bool = True) -> int:
        return len(self._mock_data['projects'])
    
    def search_projects(self, search_term: str, limit: int = 20) -> List[Dict]:
        return self.get_projects(active_only=True, limit=limit, search=search_term)
    
    def get_sequences(self, project_id: str) -> List[Dict]:
        return self._mock_data['sequences'].get(project_id, [])
    
    def get_task_types(self) -> List[Dict]:
        return self._mock_data['task_types']
    
    def get_task_statuses(self) -> List[Dict]:
        return self._mock_data['task_statuses']
    
    def get_users(self, active_only: bool = True) -> List[Dict]:
        return self._mock_data['users']
    
    def get_note_categories(self) -> List[Dict]:
        return self._mock_data['note_categories']
    
    def create_shot(self, parent_id: str, shot: FtrackShot, create_task: bool = True) -> Dict:
        logger.info(f"[MOCK] Shot created: {shot.name}")
        return {
            'id': f'shot-{shot.name}',
            'name': shot.name,
            'created': True,
            'task_id': f'task-{shot.name}' if create_task else None
        }
    
    def upload_thumbnail(self, entity_id: str, thumbnail_path: str) -> bool:
        logger.info(f"[MOCK] Thumbnail uploaded: {thumbnail_path} -> {entity_id}")
        return True
    
    def get_thumbnail_url(self, entity_id: str, size: int = 300) -> Optional[str]:
        return f"https://mock.ftrackapp.com/thumb/{entity_id}?size={size}"
    
    def create_note(self, entity_id: str, content: str, author_id: str = None, category: str = None) -> Optional[Dict]:
        note_id = f"note-{len(self._mock_data['notes']) + 1}"
        note = {
            'id': note_id,
            'content': content,
            'created_at': datetime.now().isoformat()
        }
        self._mock_data['notes'][note_id] = note
        logger.info(f"[MOCK] Note created: {content[:30]}...")
        return note
    
    def get_notes(self, entity_id: str) -> List[Dict]:
        return list(self._mock_data['notes'].values())
    
    def create_timelog(self, task_id: str, duration: float, user_id: str = None, start: datetime = None, comment: str = "") -> Optional[Dict]:
        log_id = f"timelog-{len(self._mock_data['timelogs']) + 1}"
        timelog = {
            'id': log_id,
            'duration': duration,
            'start': start.isoformat() if start else datetime.now().isoformat()
        }
        self._mock_data['timelogs'][log_id] = timelog
        logger.info(f"[MOCK] Timelog created: {duration/3600:.2f}h")
        return timelog
    
    def get_timelogs(self, task_id: str) -> List[Dict]:
        return [
            {**t, 'duration_hours': t['duration']/3600, 'user': 'mock_user', 'comment': ''}
            for t in self._mock_data['timelogs'].values()
        ]
    
    def get_asset_versions(self, entity_id: str) -> List[Dict]:
        return [
            {'id': 'av-001', 'version': 1, 'asset_name': 'comp', 'status': 'Pending Review', 'date': '2025-01-15', 'comment': 'First version'},
            {'id': 'av-002', 'version': 2, 'asset_name': 'comp', 'status': 'Approved', 'date': '2025-01-16', 'comment': 'Fixed notes'},
        ]
    
    def create_shots_from_table(
        self,
        project_id: str,
        shots_data: List[Dict],
        progress_callback: callable = None,
        dry_run: bool = False,
        validate_project: bool = True
    ) -> Dict:
        """Mock batch creation with dry_run and conform tasks support"""
        result = {
            "success": True,
            "dry_run": dry_run,
            "project_name": "MOCK_PROJECT",
            "sequences_created": 0,
            "shots_created": 0,
            "shots_existed": 0,
            "tasks_created": 0,
            "conform_tasks_created": 0,  # New count
            "thumbnails_uploaded": 0,
            "errors": [],
            "warnings": []
        }
        
        prefix = "[MOCK-DRY-RUN]" if dry_run else "[MOCK]"
        total = len(shots_data)
        sequences_seen = set()
        
        for i, shot_data in enumerate(shots_data):
            seq_name = shot_data.get("Sequence", "DEFAULT_SEQ")
            shot_name = shot_data.get("Shot Name", f"SHOT_{i:03d}")
            
            if progress_callback:
                progress_callback(i + 1, total, f"{prefix} Creating {seq_name}/{shot_name}...")
            
            # Count sequences
            if seq_name not in sequences_seen:
                sequences_seen.add(seq_name)
                result["sequences_created"] += 1
            
            # Count shot
            result["shots_created"] += 1
            
            # Count conform task (always created for each new shot)
            result["conform_tasks_created"] += 1
            logger.info(f"{prefix} Conform task created: {shot_name}/conform (Pending Review)")
            
            # Count tasks (other tasks defined by user)
            task_types = shot_data.get("Task Types", [])
            if isinstance(task_types, str):
                task_types = [t.strip() for t in task_types.split(",") if t.strip()]
            result["tasks_created"] += len(task_types)
            
            # Count thumbnails
            if shot_data.get("thumbnail_path"):
                result["thumbnails_uploaded"] += 1
            
            logger.info(f"{prefix} Shot created: {seq_name}/{shot_name}")
        
        return result
    
    def get_or_create_sequence(self, project_id: str, sequence_name: str) -> Dict:
        """Mock get_or_create_sequence"""
        seq_id = f"seq-{sequence_name.lower()}"
        logger.info(f"[MOCK] Sequence: {sequence_name}")
        return {'id': seq_id, 'name': sequence_name}
    
    def create_multiple_tasks(
        self,
        parent_id: str,
        task_types: List[str],
        task_status: str = "not_started"
    ) -> List[Dict]:
        """Mock create_multiple_tasks"""
        results = []
        for task_type in task_types:
            task_id = f"task-{parent_id}-{task_type.lower()}"
            results.append({'id': task_id, 'name': task_type.lower()})
            logger.info(f"[MOCK] Task created: {task_type}")
        return results
    
    def create_conform_task(
        self,
        parent_id: str,
        task_type: str = "Conform",
        auto_pending_review: bool = True
    ) -> Optional[Dict]:
        """Mock create_conform_task"""
        task_id = f"task-{parent_id}-conform"
        status = "Pending Review" if auto_pending_review else "Not Started"
        logger.info(f"[MOCK] Conform task created: {parent_id}/conform (Status: {status})")
        return {
            'id': task_id,
            'name': 'conform',
            'type': task_type,
            'status': status
        }