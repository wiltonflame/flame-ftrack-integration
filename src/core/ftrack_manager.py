"""
ftrack Manager - Business logic for ftrack operations

Handles all ftrack API operations including:
- Project and sequence management
- Shot and task creation
- Thumbnail uploads
- Version creation with video uploads

Security considerations:
- Only fetches active projects
- Limits project list to 50 for performance
- Proper error handling without silent fallback to mock
"""

import os
import glob
import logging
from datetime import datetime
from typing import List, Dict, Optional, Callable, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum number of projects to load (performance/security)
# With active_only filter, we can safely increase this limit
MAX_PROJECTS = 200

# Available task types in ftrack
TASK_TYPES = [
    "Compositing", 
    "Rotoscoping",
    "Tracking", 
    "Texture",
    "FX",
    "Lighting",
    "Animation",
    "Modeling",
    "Rigging",
    "Lookdev",
    "Layout",
    "Previz",
    "Rendering",
    "Matte Painting",
    "Conform",
    "Color",
    "Editing"
]

# Available statuses - exact names from production ftrack
STATUSES = [
    "not_started",
    "ready_to_start",
    "in_progress", 
    "pending_review", 
    "approved",
    "on_hold",
    "omitted",
    "client_approved",
    "could_be_better",
    "archived",
    "backup_ok",
    "cbb_conformed",
    "normal",
    "paused",
]

# Default status for new shots/tasks
DEFAULT_STATUS = "ready_to_start"

# Type name mapping
TYPE_MAPPING = {
    "roto": "Rotoscoping",
    "rotoscoping": "Rotoscoping",
    "comp": "Compositing",
    "compositing": "Compositing",
    "track": "Tracking",
    "tracking": "Tracking",
    "paint": "Texture",
    "cleanup": "Texture",
    "prep": "Texture",
    "fx": "FX",
    "lighting": "Lighting",
    "animation": "Animation",
    "texture": "Texture",
    "matchmove": "Tracking",
}

# =============================================================================
# STATUS NORMALIZATION UTILITIES
# =============================================================================
# Different ftrack instances may use different naming conventions for statuses:
# - Production: "in_progress" (underscore, lowercase)
# - Test/Other: "In Progress" (space, title case)
# - Some: "In progress", "IN_PROGRESS", etc.
#
# These utilities handle all variations transparently.

def normalize_status_name(status: str) -> str:
    """
    Normalize a status name for comparison.
    
    Converts any status variation to a canonical form:
    - Lowercase
    - Underscores replaced with spaces removed
    - All whitespace collapsed
    
    Examples:
        "in_progress" -> "inprogress"
        "In Progress" -> "inprogress"
        "IN_PROGRESS" -> "inprogress"
        "pending_review" -> "pendingreview"
        "Pending Review" -> "pendingreview"
    
    Args:
        status: Status name in any format
        
    Returns:
        Normalized status string for comparison
    """
    if not status:
        return ""
    # Convert to lowercase, remove underscores and spaces
    return status.lower().replace("_", "").replace(" ", "")


def statuses_match(status1: str, status2: str) -> bool:
    """
    Check if two status names refer to the same status.
    
    Args:
        status1: First status name
        status2: Second status name
        
    Returns:
        True if both statuses normalize to the same value
    """
    return normalize_status_name(status1) == normalize_status_name(status2)


# Common status canonical names (normalized form -> list of known variations)
# This helps with logging and debugging
STATUS_CANONICAL = {
    "inprogress": ["in_progress", "In Progress", "In progress", "IN_PROGRESS"],
    "notstarted": ["not_started", "Not Started", "Not started", "NOT_STARTED"],
    "readytostart": ["ready_to_start", "Ready To Start", "Ready to start"],
    "pendingreview": ["pending_review", "Pending Review", "Pending review"],
    "approved": ["approved", "Approved", "APPROVED"],
    "onhold": ["on_hold", "On Hold", "On hold"],
    "omitted": ["omitted", "Omitted", "OMITTED"],
}


# =============================================================================
# FTRACK MANAGER
# =============================================================================

class FtrackManager:
    """
    Manages ftrack operations for Flame integration
    
    Features:
    - Connection management with proper error handling
    - Project/Sequence/Shot hierarchy navigation
    - Task creation with types and status
    - Thumbnail uploads
    - Version creation with video uploads
    - Batch operations
    
    Security:
    - Only loads active projects
    - Limits to MAX_PROJECTS (50) for performance
    - No silent fallback to mock mode
    """
    
    def __init__(self):
        self.session = None
        self.is_mock = False
        self._connected = False
        self._task_type_cache = {}
        self._status_cache = {}
        self._asset_type_cache = {}
        self._server_url = None
        # Cache for dynamically discovered status names
        # Key: normalized status name, Value: actual server status name
        self._discovered_status_cache = {}
    
    # -------------------------------------------------------------------------
    # CONNECTION
    # -------------------------------------------------------------------------
    
    def connect(self, server_url: str = None, api_user: str = None,
                api_key: str = None) -> Tuple[bool, str]:
        """
        Connect to ftrack server
        
        Args:
            server_url: ftrack server URL
            api_user: API username
            api_key: API key
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Reset state
        self.is_mock = False
        self._connected = False
        self.session = None
        
        try:
            import ftrack_api
            
            logger.info(f"Connecting to ftrack: {server_url}")
            
            # Create session with minimal options
            self.session = ftrack_api.Session(
                server_url=server_url,
                api_key=api_key,
                api_user=api_user,
                auto_connect_event_hub=False  # Disable event hub for simplicity
            )
            
            self._connected = True
            self.is_mock = False
            self._server_url = server_url
            
            logger.info("Connected to ftrack successfully")
            return True, f"Connected to {server_url}"
            
        except ImportError as e:
            error_msg = (
                "ftrack_api not installed. "
                "Run: ./setup_environment.sh (for venv) or ./setup_simple.sh (system-wide)"
            )
            logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def enable_mock_mode(self):
        """Explicitly enable mock mode for testing"""
        self.is_mock = True
        self._connected = True
        self.session = None
        logger.info("Mock mode enabled")
    
    def disconnect(self):
        """Disconnect from ftrack"""
        if self.session:
            try:
                self.session.close()
            except:
                pass
        self.session = None
        self._connected = False
        self.is_mock = False
    
    def reset_cache(self):
        """
        Reset session cache to force fresh data from server.
        
        Call this when hierarchy seems stale or when projects don't show children.
        """
        if self.session:
            try:
                # Clear the local cache
                self.session.cache.clear()
                logger.info("Session cache cleared")
                
                # Also clear any cached lookups
                self._task_type_cache = {}
                self._status_cache = {}
                self._asset_type_cache = {}
                self._discovered_status_cache = {}
                
            except Exception as e:
                logger.warning(f"Could not clear cache: {e}")
    
    @property
    def connected(self) -> bool:
        """Check if connected"""
        return self._connected and (self.session is not None or self.is_mock)
    
    # -------------------------------------------------------------------------
    # PROJECTS
    # -------------------------------------------------------------------------
    
    def get_projects(self, limit: int = MAX_PROJECTS, active_only: bool = True) -> List[Dict]:
        """
        Get projects (limited for performance)
        
        Args:
            limit: Maximum number of projects to return (default: 200)
            active_only: If True, only return active projects (default: True)
        
        Returns:
            List of project dicts with id, name, status
        """
        if self.is_mock:
            return self._mock_projects()
        
        if not self.session:
            logger.warning("No active session")
            return []
        
        try:
            logger.info(f"Querying projects (active_only={active_only}, limit={limit})...")
            
            # Build query - filter active on server side
            query = 'Project'
            if active_only:
                query += ' where status is "active"'
            
            logger.info(f"Executing query: {query}")
            projects = self.session.query(query).all()
            logger.info(f"Query returned {len(projects)} projects")
            
            if not projects:
                return []
            
            # Build result
            result = []
            for p in projects:
                try:
                    # Get status safely
                    status_name = 'Active'
                    try:
                        status = p.get('status')
                        if status:
                            status_name = status.get('name', 'Active')
                    except:
                        pass
                    
                    result.append({
                        'id': p['id'],
                        'name': p['name'],
                        'status': status_name
                    })
                    
                except Exception as item_error:
                    logger.warning(f"Error processing project: {item_error}")
                    continue
            
            # Sort by name and limit
            result.sort(key=lambda x: x['name'].lower())
            result = result[:limit]
            
            logger.info(f"Returning {len(result)} projects")
            return result
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Error fetching projects: {e}")
            return []
    
    def _mock_projects(self) -> List[Dict]:
        """Return mock projects for testing"""
        return [
            {'id': 'proj_001', 'name': 'Demo - Commercial Brand X', 'status': 'Active'},
            {'id': 'proj_002', 'name': 'Demo - Film The Journey', 'status': 'Active'},
            {'id': 'proj_003', 'name': 'Demo - Series Episode 01', 'status': 'Active'},
        ]
    
    def search_projects(self, search_term: str, limit: int = 50, active_only: bool = True) -> List[Dict]:
        """
        Search projects by name - FAST method that filters in the query.
        
        Args:
            search_term: Text to search for in project name
            limit: Maximum number of results (default: 50)
            active_only: If True, only return active projects (default: True)
        
        Returns:
            List of project dicts with id, name, status
        """
        if self.is_mock:
            # Mock search
            all_projects = self._mock_projects()
            return [p for p in all_projects if search_term.lower() in p['name'].lower()]
        
        if not self.session:
            logger.warning("No session available for search")
            return []
        
        try:
            logger.info(f"Searching projects with name containing '{search_term}' (active_only={active_only})...")
            
            # Build query with active filter
            if active_only:
                query = f'Project where name like "%{search_term}%" and status is "active"'
            else:
                query = f'Project where name like "%{search_term}%"'
            
            logger.info(f"Executing query: {query}")
            
            try:
                projects = self.session.query(query).all()
                logger.info(f"Query returned {len(projects)} projects")
            except Exception as e1:
                logger.warning(f"Query with LIKE failed: {e1}, trying fallback...")
                
                # Fallback: fetch all active and filter in Python
                try:
                    if active_only:
                        fallback_query = 'Project where status is "active"'
                    else:
                        fallback_query = 'Project'
                    
                    all_projects = self.session.query(fallback_query).all()
                    search_lower = search_term.lower()
                    projects = [p for p in all_projects if search_lower in p['name'].lower()]
                    logger.info(f"Fallback filter found {len(projects)} matching projects")
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}")
                    return []
            
            if not projects:
                return []
            
            # Build result
            result = []
            for p in projects[:limit]:
                try:
                    # Get status safely
                    status_name = 'Active'
                    try:
                        status = p.get('status')
                        if status:
                            status_name = status.get('name', 'Active')
                    except:
                        pass
                    
                    result.append({
                        'id': p['id'],
                        'name': p['name'],
                        'status': status_name
                    })
                except Exception as item_error:
                    logger.warning(f"Error processing project in search: {item_error}")
                    continue
            
            # Sort by name
            result.sort(key=lambda x: x['name'].lower())
            
            logger.info(f"Search returning {len(result)} projects")
            return result
            
        except Exception as e:
            logger.error(f"Error searching projects: {e}")
            return []
    
    def get_project_children(self, parent_id: str, parent_type: str = 'Project') -> List[Dict]:
        """
        Get children (folders/sequences) of a project or folder using EXPLICIT query.
        
        Uses direct TypedContext query instead of lazy-loaded 'children' relationship,
        which can fail due to cache or session issues.
        
        Args:
            parent_id: Parent entity ID (Project or Folder)
            parent_type: Type of parent ('Project', 'Folder', etc.)
        
        Returns:
            List of child dicts with id, name, type, has_children
        """
        if self.is_mock:
            return [
                {'id': f'{parent_id}_folder_01', 'name': 'VFX', 'type': 'Folder', 'has_children': True},
                {'id': f'{parent_id}_seq_010', 'name': 'SEQ010', 'type': 'Sequence', 'has_children': True},
                {'id': f'{parent_id}_seq_020', 'name': 'SEQ020', 'type': 'Sequence', 'has_children': True},
            ]
        
        if not self.session:
            logger.warning("No session available")
            return []
        
        result = []
        
        try:
            # Log parent info
            logger.info(f"Getting children for parent_id: {parent_id} ({parent_type})")
            
            # METHOD 1: EXPLICIT query for direct children
            # This approach is more reliable than using the 'children' property
            # which depends on lazy loading and can have cache issues
            
            # Search ALL context types that have this parent
            query = f'TypedContext where parent.id is "{parent_id}"'
            logger.info(f"Executing query: {query}")
            
            children = self.session.query(query).all()
            logger.info(f"Query returned {len(children)} children")
            
            # If nothing found, try with select to force loading
            if not children:
                logger.info("Trying with explicit select...")
                children = self.session.query(
                    f'select id, name from TypedContext where parent.id is "{parent_id}"'
                ).all()
                logger.info(f"Select query returned {len(children)} children")
            
            # Types that can have their own children (expandable in tree)
            expandable_types = ['Folder', 'Sequence', 'Episode', 'AssetBuild', 'Milestone', 'Task']
            
            for child in children:
                try:
                    # Get entity type (Folder, Sequence, Shot, etc.)
                    entity_type = child.entity_type if hasattr(child, 'entity_type') else 'Unknown'
                    child_name = child['name']
                    child_id = child['id']
                    
                    # Check if this entity type can have children
                    # Folders and Sequences can have children, Shots typically not
                    can_have_children = entity_type in expandable_types
                    
                    # For Folders, we KNOW they can have children
                    # For other types, we could do a sub-query but that's expensive
                    
                    child_data = {
                        'id': child_id,
                        'name': child_name,
                        'type': entity_type,
                        'has_children': can_have_children,
                        # Store project_id for later use when creating shots
                        'project_id': parent_id if parent_type == 'Project' else None
                    }
                    result.append(child_data)
                    logger.info(f"  - {child_name} ({entity_type}) [id: {child_id}]")
                    
                except Exception as ce:
                    logger.warning(f"Error processing child: {ce}")
            
            # METHOD 2: If still not found, try fetching parent and using children
            if not result:
                logger.info("No children found via query, trying parent.children...")
                try:
                    if parent_type == 'Project':
                        parent = self.session.get('Project', parent_id)
                    else:
                        parent = self.session.get('TypedContext', parent_id)
                    
                    if parent:
                        # Force cache refresh
                        self.session.populate(parent, 'children')
                        children = parent['children']
                        logger.info(f"parent.children returned {len(children)} items")
                        
                        for child in children:
                            entity_type = child.entity_type if hasattr(child, 'entity_type') else 'Unknown'
                            child_data = {
                                'id': child['id'],
                                'name': child['name'],
                                'type': entity_type,
                                'has_children': entity_type in expandable_types
                            }
                            result.append(child_data)
                            
                except Exception as backup_err:
                    logger.warning(f"Backup method also failed: {backup_err}")
            
            # Sort: Folders first, then Sequences, then by name
            type_order = {'Folder': 0, 'Episode': 1, 'Sequence': 2, 'AssetBuild': 3, 'Shot': 10}
            result.sort(key=lambda x: (type_order.get(x['type'], 99), x['name'].lower()))
            
            logger.info(f"Returning {len(result)} children total")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching children: {e}", exc_info=True)
            return []
    
    # -------------------------------------------------------------------------
    # SEQUENCES
    # -------------------------------------------------------------------------
    
    def get_sequences(self, project_id: str) -> List[Dict]:
        """
        Get sequences for a project
        
        Args:
            project_id: Project ID
        
        Returns:
            List of sequence dicts
        """
        if self.is_mock:
            return self._mock_sequences(project_id)
        
        if not self.session:
            return []
        
        try:
            sequences = self.session.query(
                f'Sequence where project_id is "{project_id}"'
            ).all()
            
            return [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'parent_id': project_id
                }
                for s in sequences
            ]
        except Exception as e:
            logger.error(f"Error fetching sequences: {e}")
            return []
    
    def _mock_sequences(self, project_id: str) -> List[Dict]:
        """Return mock sequences"""
        return [
            {'id': f'{project_id}_seq_010', 'name': 'SEQ010', 'parent_id': project_id},
            {'id': f'{project_id}_seq_020', 'name': 'SEQ020', 'parent_id': project_id},
        ]
    
    def get_or_create_sequence(self, project_id: str, sequence_name: str, 
                               parent_id: str = None, parent_type: str = 'Project'):
        """
        Get existing sequence or create new one
        
        Args:
            project_id: Project ID (required for API queries)
            sequence_name: Sequence name
            parent_id: Parent entity ID (Project or Folder). If None, uses project_id
            parent_type: Type of parent ('Project' or 'Folder')
        
        Returns:
            Sequence entity or dict in mock mode
        """
        if self.is_mock:
            return {'id': f'{project_id}_{sequence_name}', 'name': sequence_name}
        
        if not self.session:
            return None
        
        # Use project_id as parent if not specified
        if parent_id is None:
            parent_id = project_id
            parent_type = 'Project'
        
        try:
            # Check if sequence exists under this parent
            existing = self.session.query(
                f'Sequence where name is "{sequence_name}" and parent.id is "{parent_id}"'
            ).first()
            
            if existing:
                logger.info(f"Sequence exists: {sequence_name}")
                return existing
            
            # Get parent entity based on type
            parent = None
            if parent_type == 'Project':
                parent = self.session.get('Project', parent_id)
            elif parent_type == 'Folder':
                parent = self.session.get('Folder', parent_id)
            else:
                # Try TypedContext for other types
                parent = self.session.get('TypedContext', parent_id)
            
            if not parent:
                logger.error(f"Parent not found: {parent_id} ({parent_type})")
                return None
            
            # Create new sequence
            sequence = self.session.create('Sequence', {
                'name': sequence_name,
                'parent': parent
            })
            self.session.commit()
            logger.info(f"Sequence created: {sequence_name} under {parent_type} {parent_id}")
            return sequence
            
        except Exception as e:
            logger.error(f"Error creating sequence {sequence_name}: {e}")
            if self.session:
                self.session.rollback()
            return None
    
    # -------------------------------------------------------------------------
    # SHOTS
    # -------------------------------------------------------------------------
    
    def get_shots(self, parent_id: str) -> List[Dict]:
        """
        Get shots for a sequence
        
        Args:
            parent_id: Sequence ID
        
        Returns:
            List of shot dicts
        """
        if self.is_mock:
            return self._mock_shots(parent_id)
        
        if not self.session:
            return []
        
        try:
            shots = self.session.query(
                f'Shot where parent_id is "{parent_id}"'
            ).all()
            
            return [
                {
                    'id': s['id'],
                    'name': s['name'],
                    'status': s['status']['name'] if s['status'] else 'Unknown'
                }
                for s in shots
            ]
        except Exception as e:
            logger.error(f"Error fetching shots: {e}")
            return []
    
    def _mock_shots(self, parent_id: str) -> List[Dict]:
        """Return mock shots"""
        return [
            {'id': f'{parent_id}_shot_010', 'name': 'shot_010', 'status': 'Not started'},
            {'id': f'{parent_id}_shot_020', 'name': 'shot_020', 'status': 'In Progress'},
        ]
    
    def create_shot(self, parent, shot_name: str, description: str = ""):
        """
        Create a shot
        
        Args:
            parent: Sequence entity
            shot_name: Shot name
            description: Optional description
        
        Returns:
            Shot entity or dict in mock mode
        """
        if self.is_mock:
            parent_id = parent.get('id', 'mock') if isinstance(parent, dict) else 'mock'
            return {
                'id': f'{parent_id}_{shot_name}',
                'name': shot_name,
                'description': description
            }
        
        if not self.session or not parent:
            return None
        
        try:
            parent_id = parent['id']
            
            # Check if exists
            existing = self.session.query(
                f'Shot where name is "{shot_name}" and parent.id is "{parent_id}"'
            ).first()
            
            if existing:
                logger.info(f"Shot exists: {shot_name}")
                return existing
            
            # Create
            shot = self.session.create('Shot', {
                'name': shot_name,
                'parent': parent,
                'description': description
            })
            self.session.commit()
            logger.info(f"Shot created: {shot_name}")
            return shot
            
        except Exception as e:
            logger.error(f"Error creating shot {shot_name}: {e}")
            if self.session:
                self.session.rollback()
            return None
    
    # -------------------------------------------------------------------------
    # TASKS
    # -------------------------------------------------------------------------
    
    def _get_task_type(self, type_name: str):
        """Get task type by name (with cache)"""
        if not self.session:
            return None
        
        # Normalize
        type_lower = type_name.lower().strip()
        ftrack_name = TYPE_MAPPING.get(type_lower, type_name)
        
        # Cache
        if ftrack_name in self._task_type_cache:
            return self._task_type_cache[ftrack_name]
        
        try:
            type_entity = self.session.query(f'Type where name is "{ftrack_name}"').first()
            
            if not type_entity:
                # Fallback to Compositing
                type_entity = self.session.query('Type where name is "Compositing"').first()
            
            self._task_type_cache[ftrack_name] = type_entity
            return type_entity
            
        except Exception as e:
            logger.warning(f"Could not find type '{type_name}': {e}")
            return None
    
    def _get_task_status(self, status_name: str):
        """
        Get status entity by name with intelligent auto-detection.
        
        Handles different naming conventions across ftrack instances:
        - "pending_review" vs "Pending Review" vs "Pending review"
        - "in_progress" vs "In Progress" vs "In progress"
        - etc.
        
        Args:
            status_name: Status name in any format
            
        Returns:
            Status entity or None if not found
        """
        if not self.session:
            return None
        
        if not status_name:
            return None
        
        # Check entity cache first (stores actual ftrack entities)
        if status_name in self._status_cache:
            return self._status_cache[status_name]
        
        # Check if we already discovered the server name for this normalized status
        normalized = normalize_status_name(status_name)
        
        if normalized in self._discovered_status_cache:
            server_name = self._discovered_status_cache[normalized]
            if server_name and server_name in self._status_cache:
                return self._status_cache[server_name]
        
        try:
            # First, try exact match (fast path for when names match exactly)
            status = self.session.query(f'Status where name is "{status_name}"').first()
            
            if status:
                self._status_cache[status_name] = status
                self._discovered_status_cache[normalized] = status_name
                logger.info(f"Status found (exact match): '{status_name}'")
                return status
            
            # Exact match failed - use intelligent discovery
            logger.info(f"Status '{status_name}' not found exactly, searching for equivalent...")
            
            # Query all statuses and find matching one
            all_statuses = self.session.query('Status').all()
            
            for s in all_statuses:
                s_name = s.get('name', '') if hasattr(s, 'get') else str(s)
                if normalize_status_name(s_name) == normalized:
                    # Found it!
                    self._status_cache[s_name] = s
                    self._discovered_status_cache[normalized] = s_name
                    logger.info(f"Status discovered: '{status_name}' -> '{s_name}' (server format)")
                    return s
            
            # Still not found
            available = [s.get('name', str(s)) for s in all_statuses[:15]]
            logger.warning(
                f"Status '{status_name}' not found on server. "
                f"Available statuses (first 15): {available}"
            )
            return None
            
        except Exception as e:
            logger.warning(f"Error finding status '{status_name}': {e}")
            return None
    
    def get_available_statuses(self) -> list:
        """Get list of available status names"""
        return STATUSES
    
    def create_task(self, parent, task_name: str, task_type: str = "Compositing",
                    status_name: str = None, assign_current_user: bool = False):
        """
        Create a task with type and status
        
        Args:
            parent: Shot or other parent entity
            task_name: Task name
            task_type: Type (Compositing, Rotoscoping, etc)
            status_name: Initial status (defaults to DEFAULT_STATUS)
            assign_current_user: If True, assigns the current API user to the task
        
        Returns:
            Task entity or dict in mock mode
        """
        if status_name is None:
            status_name = DEFAULT_STATUS
            
        if self.is_mock:
            parent_id = parent.get('id', 'mock') if isinstance(parent, dict) else 'mock'
            return {
                'id': f'{parent_id}_{task_name}',
                'name': task_name,
                'type': task_type,
                'status': status_name,
                'assigned_to': self.session.api_user if self.session and assign_current_user else None
            }
        
        if not self.session or not parent:
            return None
        
        try:
            parent_id = parent['id']
            parent_name = parent.get('name', 'unknown')
            
            logger.info(f"[DEBUG] Creating task '{task_name}' in parent '{parent_name}' (id: {parent_id})")
            logger.info(f"[DEBUG] Requested status: '{status_name}', type: '{task_type}'")
            
            # Check if exists
            existing = self.session.query(
                f'Task where name is "{task_name}" and parent.id is "{parent_id}"'
            ).first()
            
            if existing:
                existing_status = existing['status']['name'] if existing.get('status') else 'unknown'
                logger.info(f"[DEBUG] Task already exists: {task_name} (current status: {existing_status})")
                return existing
            
            # Get type
            type_entity = self._get_task_type(task_type)
            logger.info(f"[DEBUG] Task type entity: {type_entity['name'] if type_entity else 'NOT FOUND'}")
            
            # Create task data (WITHOUT status - let ftrack use default first)
            task_data = {
                'name': task_name,
                'parent': parent,
            }
            
            if type_entity:
                task_data['type'] = type_entity
            
            # Create task
            task = self.session.create('Task', task_data)
            self.session.commit()
            
            # Check what status ftrack assigned by default
            default_status = task['status']['name'] if task.get('status') else 'none'
            logger.info(f"[DEBUG] Task created with ftrack default status: '{default_status}'")
            
            # NOW set our desired status (after initial commit)
            logger.info(f"[DEBUG] Setting desired status '{status_name}'...")
            status = self._get_task_status(status_name)
            
            if status:
                task['status'] = status
                self.session.commit()
                final_status = task['status']['name'] if task.get('status') else 'unknown'
                logger.info(f"[DEBUG] Status updated to: '{final_status}'")
                
                if final_status != status_name:
                    logger.warning(f"[DEBUG] WARNING: Final status '{final_status}' differs from requested '{status_name}'!")
            else:
                logger.warning(f"[DEBUG] Could not find status '{status_name}' - keeping default")
            
            logger.info(f"Task created: {task_name} ({task_type}) - final status: {task['status']['name'] if task.get('status') else 'unknown'}")
            
            # Assign current user if requested
            if assign_current_user:
                assign_success = self._assign_current_user_to_task(task)
                if not assign_success:
                    logger.warning(f"Task '{task_name}' created but user assignment failed")
            
            return task
            
        except Exception as e:
            logger.error(f"Error creating task {task_name}: {e}")
            import traceback
            traceback.print_exc()
            if self.session:
                self.session.rollback()
            return None
    
    def _assign_current_user_to_task(self, task) -> bool:
        """
        Assign the current API user to a task.
        
        Uses multiple strategies to handle different ftrack configurations:
        1. First tries to use the 'assignments' relationship directly
        2. Falls back to creating an 'Appointment' entity
        
        Args:
            task: Task entity to assign user to
            
        Returns:
            bool: True if successful
        """
        if not self.session or not task:
            logger.warning("Cannot assign user: no session or task")
            return False
        
        task_name = task.get('name', 'unknown') if hasattr(task, 'get') else str(task)
        
        try:
            # Get current user
            user = self.session.query(
                f'User where username is "{self.session.api_user}"'
            ).first()
            
            if not user:
                logger.warning(f"Could not find user: {self.session.api_user}")
                return False
            
            user_name = user.get('username', self.session.api_user)
            logger.info(f"Assigning user '{user_name}' to task '{task_name}'...")
            
            # Strategy 1: Try using assignments collection directly
            # This is the preferred method in newer ftrack versions
            try:
                # Check if task has assignments attribute
                if hasattr(task, 'get') and 'assignments' in task.keys():
                    # Check if user is already assigned
                    existing_assignments = task['assignments']
                    for assignment in existing_assignments:
                        resource = assignment.get('resource')
                        if resource and resource.get('id') == user['id']:
                            logger.info(f"User '{user_name}' already assigned to task '{task_name}'")
                            return True
            except Exception as check_err:
                logger.debug(f"Could not check existing assignments: {check_err}")
            
            # Strategy 2: Create Appointment entity (standard ftrack method)
            try:
                appointment = self.session.create('Appointment', {
                    'context': task,
                    'resource': user,
                    'type': 'assignment'
                })
                self.session.commit()
                logger.info(f"✓ User '{user_name}' assigned to task '{task_name}' (via Appointment)")
                return True
                
            except Exception as appt_err:
                logger.debug(f"Appointment creation failed: {appt_err}")
                # Try without 'type' field (some ftrack versions don't use it)
                try:
                    self.session.rollback()
                    appointment = self.session.create('Appointment', {
                        'context': task,
                        'resource': user
                    })
                    self.session.commit()
                    logger.info(f"✓ User '{user_name}' assigned to task '{task_name}' (via Appointment, no type)")
                    return True
                except Exception as appt_err2:
                    logger.debug(f"Appointment without type also failed: {appt_err2}")
                    self.session.rollback()
            
            # Strategy 3: Try allocating resource directly
            try:
                task['assignments'].append(
                    self.session.create('Appointment', {
                        'resource': user
                    })
                )
                self.session.commit()
                logger.info(f"✓ User '{user_name}' assigned to task '{task_name}' (via assignments.append)")
                return True
            except Exception as alloc_err:
                logger.debug(f"Direct assignment append failed: {alloc_err}")
                self.session.rollback()
            
            # All strategies failed
            logger.error(
                f"Could not assign user '{user_name}' to task '{task_name}'. "
                "Please check ftrack permissions and schema configuration."
            )
            return False
            
        except Exception as e:
            logger.error(f"Error assigning user to task '{task_name}': {e}")
            import traceback
            traceback.print_exc()
            if self.session:
                try:
                    self.session.rollback()
                except:
                    pass
            return False
    
    def verify_task_assignment(self, task) -> Dict:
        """
        Verify if a task has assignments and return details.
        
        Useful for debugging assignment issues.
        
        Args:
            task: Task entity to check
            
        Returns:
            Dict with assignment info: {
                'has_assignments': bool,
                'assigned_users': list of usernames,
                'current_user_assigned': bool
            }
        """
        result = {
            'has_assignments': False,
            'assigned_users': [],
            'current_user_assigned': False
        }
        
        if not self.session or not task:
            return result
        
        try:
            task_id = task.get('id') if hasattr(task, 'get') else task['id']
            
            # Query appointments for this task
            appointments = self.session.query(
                f'Appointment where context.id is "{task_id}"'
            ).all()
            
            if appointments:
                result['has_assignments'] = True
                for appt in appointments:
                    resource = appt.get('resource')
                    if resource:
                        username = resource.get('username', 'unknown')
                        result['assigned_users'].append(username)
                        if username == self.session.api_user:
                            result['current_user_assigned'] = True
            
            logger.debug(f"Task assignment verification: {result}")
            return result
            
        except Exception as e:
            logger.debug(f"Could not verify task assignments: {e}")
            return result
    
    # -------------------------------------------------------------------------
    # THUMBNAILS
    # -------------------------------------------------------------------------
    
    def upload_thumbnail(self, entity, thumbnail_path: str) -> bool:
        """
        Upload thumbnail to an entity
        
        Args:
            entity: Shot or Task
            thumbnail_path: Path to image file
        
        Returns:
            bool: Upload success
        """
        if self.is_mock:
            logger.info(f"[MOCK] Thumbnail upload: {thumbnail_path}")
            return True
        
        if not self.session:
            return False
        
        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.warning(f"Thumbnail not found: {thumbnail_path}")
            return False
        
        try:
            entity.create_thumbnail(thumbnail_path)
            self.session.commit()
            logger.info(f"Thumbnail uploaded: {thumbnail_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error uploading thumbnail: {e}")
            return False
    
    def _find_thumbnail(self, thumb_dir: str, shot_name: str) -> Optional[str]:
        """
        Find thumbnail for a shot in various directory structures
        
        Args:
            thumb_dir: Base thumbnail directory
            shot_name: Shot name
        
        Returns:
            Thumbnail path or None
        """
        if not thumb_dir or not shot_name:
            return None
        
        # Search patterns - from most specific to most generic
        search_patterns = [
            # Direct in folder
            os.path.join(thumb_dir, f"{shot_name}.jpg"),
            os.path.join(thumb_dir, f"{shot_name}.0001.jpg"),
            os.path.join(thumb_dir, f"{shot_name}.00000001.jpg"),
            
            # In subfolder (sequence_name/shot.jpg)
            os.path.join(thumb_dir, "*", f"{shot_name}.jpg"),
            os.path.join(thumb_dir, "*", f"{shot_name}.0001.jpg"),
            os.path.join(thumb_dir, "*", f"{shot_name}.00000001.jpg"),
            
            # Any file starting with shot_name
            os.path.join(thumb_dir, f"{shot_name}*.jpg"),
            os.path.join(thumb_dir, "*", f"{shot_name}*.jpg"),
            
            # Recursive search
            os.path.join(thumb_dir, "**", f"{shot_name}*.jpg"),
        ]
        
        for pattern in search_patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                matches.sort()
                logger.info(f"Found thumbnail: {matches[0]}")
                return matches[0]
        
        logger.warning(f"No thumbnail found for shot: {shot_name}")
        return None
    
    # -------------------------------------------------------------------------
    # VERSIONS (Video upload)
    # -------------------------------------------------------------------------
    
    def _get_asset_type(self, type_name: str = "Upload"):
        """Get asset type by name (with cache)"""
        if not self.session:
            return None
        
        if type_name in self._asset_type_cache:
            return self._asset_type_cache[type_name]
        
        try:
            asset_type = self.session.query(
                f'AssetType where name is "{type_name}"'
            ).first()
            
            if not asset_type:
                # Try common types
                for fallback in ["Upload", "Review", "Plate", "Comp"]:
                    asset_type = self.session.query(
                        f'AssetType where name is "{fallback}"'
                    ).first()
                    if asset_type:
                        break
            
            self._asset_type_cache[type_name] = asset_type
            return asset_type
            
        except Exception as e:
            logger.warning(f"Could not find asset type '{type_name}': {e}")
            return None
    
    def create_version(self, shot, video_path: str, version_name: str = None,
                       comment: str = "Initial version from Flame") -> bool:
        """
        Create a version with video upload
        
        Args:
            shot: Shot entity
            video_path: Path to video file
            version_name: Version name (defaults to shot name)
            comment: Version comment
        
        Returns:
            bool: Success
        """
        if self.is_mock:
            shot_name = shot.get('name', 'unknown') if isinstance(shot, dict) else 'unknown'
            logger.info(f"[MOCK] Version created for {shot_name}: {video_path}")
            return True
        
        if not self.session or not shot:
            logger.warning("No session or shot provided for version creation")
            return False
        
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"Video not found: {video_path}")
            return False
        
        try:
            shot_name = shot['name']
            file_ext = os.path.splitext(video_path)[1].lower()
            file_size = os.path.getsize(video_path)
            
            logger.info(f"Creating version for {shot_name}")
            logger.info(f"  Video: {video_path}")
            logger.info(f"  Format: {file_ext}, Size: {file_size / (1024*1024):.1f} MB")
            
            # Get or create asset
            asset_type = self._get_asset_type("Upload")
            
            # Check for existing asset
            existing_asset = self.session.query(
                f'Asset where name is "{shot_name}" and parent.id is "{shot["id"]}"'
            ).first()
            
            if existing_asset:
                asset = existing_asset
                logger.info(f"  Using existing asset: {asset['id']}")
            else:
                # Create asset
                asset_data = {
                    'name': shot_name,
                    'parent': shot,
                }
                if asset_type:
                    asset_data['type'] = asset_type
                
                asset = self.session.create('Asset', asset_data)
                self.session.commit()
                logger.info(f"  Created new asset: {asset['id']}")
            
            # Get task for version (optional)
            task = self.session.query(
                f'Task where parent.id is "{shot["id"]}"'
            ).first()
            
            # Create version
            version_data = {
                'asset': asset,
                'comment': comment,
            }
            if task:
                version_data['task'] = task
            
            version = self.session.create('AssetVersion', version_data)
            self.session.commit()
            logger.info(f"  Created version: {version['id']}")
            
            # Upload video as component
            server_location = self.session.query(
                'Location where name is "ftrack.server"'
            ).one()
            
            # Use 'main' as component name - ftrack will create review components
            component_name = 'main'
            
            logger.info(f"  Uploading component '{component_name}'...")
            version.create_component(
                path=video_path,
                data={'name': component_name},
                location=server_location
            )
            
            # Encode media for web review - required for ftrack player
            # This creates the streaming versions needed for playback
            logger.info(f"  Encoding media for web review (required for playback)...")
            version.encode_media(video_path)
            
            self.session.commit()
            
            logger.info(f"✅ Version created successfully for {shot_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating version: {e}", exc_info=True)
            if self.session:
                try:
                    self.session.rollback()
                except:
                    pass
            return False
    
    def _find_video(self, video_dir: str, shot_name: str) -> Optional[str]:
        """
        Find video for a shot
        
        Args:
            video_dir: Video directory
            shot_name: Shot name
        
        Returns:
            Video path or None
        """
        if not video_dir or not shot_name:
            return None
        
        # Search patterns for both .mp4 (H.264) and .mov (ProRes)
        # Preset uses: <name>/<shot name> so videos are in subfolders
        patterns = [
            # In subfolder (sequence_name/shot.mp4) - expected from preset
            os.path.join(video_dir, "*", f"{shot_name}.mov"),
            os.path.join(video_dir, "*", f"{shot_name}.mp4"),
            
            # Direct in folder
            os.path.join(video_dir, f"{shot_name}.mov"),
            os.path.join(video_dir, f"{shot_name}.mp4"),
            
            # With wildcards
            os.path.join(video_dir, "*", f"{shot_name}*.mov"),
            os.path.join(video_dir, "*", f"{shot_name}*.mp4"),
            os.path.join(video_dir, f"{shot_name}*.mov"),
            os.path.join(video_dir, f"{shot_name}*.mp4"),
            
            # Recursive search
            os.path.join(video_dir, "**", f"*{shot_name}*.mov"),
            os.path.join(video_dir, "**", f"*{shot_name}*.mp4"),
        ]
        
        for pattern in patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                logger.info(f"Found video for {shot_name}: {matches[0]}")
                return matches[0]
        
        logger.warning(f"No video found for {shot_name} in {video_dir}")
        return None
    
    # -------------------------------------------------------------------------
    # BATCH OPERATIONS
    # -------------------------------------------------------------------------
    
    def create_shots_batch(self, project_id: str, shots_data: List[Dict],
                          progress_callback: Callable = None,
                          export_thumbs: bool = False,
                          upload_thumbs: bool = False,
                          thumb_dir: str = "",
                          upload_versions: bool = False,
                          video_dir: str = "",
                          parent_id: str = None,
                          parent_type: str = 'Project') -> Dict:
        """
        Create multiple shots in batch
        
        Args:
            project_id: Project ID (required for API)
            shots_data: List of dicts with shot data
            progress_callback: Function (step, current, total, message) for progress
            export_thumbs: Whether to consider thumbnails
            upload_thumbs: Whether to upload thumbnails
            thumb_dir: Thumbnails directory
            upload_versions: Whether to upload video versions
            video_dir: Videos directory
            parent_id: Parent entity ID where sequences will be created (Folder or Project)
            parent_type: Type of parent ('Project', 'Folder', or 'Sequence')
        
        Returns:
            Dict with results: sequences, shots, tasks, thumbnails, versions, errors
        """
        results = {
            'sequences': 0,
            'shots': 0,
            'tasks': 0,
            'conform_tasks': 0,  # New count for Conform tasks
            'thumbnails': 0,
            'versions': 0,
            'errors': []
        }
        
        if not shots_data:
            return results
        
        # Use project_id as parent if not specified
        if parent_id is None:
            parent_id = project_id
            parent_type = 'Project'
        
        # Special case: if user selected a Sequence directly, create shots there
        if parent_type == 'Sequence':
            # Get the selected sequence
            selected_sequence = self.session.get('Sequence', parent_id) if self.session else None
            
            if self.is_mock:
                selected_sequence = {'id': parent_id, 'name': 'SelectedSequence'}
            
            if not selected_sequence:
                results['errors'].append(f"Selected sequence not found: {parent_id}")
                return results
            
            total_shots = len(shots_data)
            
            # Create all shots directly in the selected sequence
            for i, shot_data in enumerate(shots_data):
                shot_name = shot_data.get('Shot Name', '')
                if not shot_name:
                    continue
                
                if progress_callback:
                    progress_callback(2, i + 1, total_shots, f"Creating: {shot_name}")
                
                try:
                    description = shot_data.get('Description', '')
                    shot = self.create_shot(selected_sequence, shot_name, description)
                    
                    if shot:
                        results['shots'] += 1
                        
                        # =========================================================
                        # CONFORM TASK - Created automatically with "pending_review"
                        # This task is independent of others and indicates that the shot
                        # was created from Flame and needs to be verified
                        # The current user is automatically assigned to the task
                        # =========================================================
                        conform_task = self.create_task(
                            shot, 
                            'conform',  # task name
                            'Conform',  # task type
                            'pending_review',  # automatic status
                            assign_current_user=True  # assigns the artist who is creating
                        )
                        if conform_task:
                            results['conform_tasks'] += 1
                            assigned_user = self.session.api_user if self.session else 'N/A'
                            logger.info(f"✓ Conform task created: {shot_name}/conform (pending_review) → assigned: {assigned_user}")
                        
                        # Create tasks (other tasks defined by user)
                        task_types = shot_data.get('Task Types', 'Compositing')
                        if isinstance(task_types, str):
                            task_types = [t.strip() for t in task_types.split(",")]
                        
                        status = shot_data.get("Status", DEFAULT_STATUS)
                        
                        for task_type in task_types:
                            if task_type:
                                task = self.create_task(shot, task_type.lower(), task_type, status)
                                if task:
                                    results['tasks'] += 1
                        
                        # Upload thumbnail
                        if upload_thumbs and thumb_dir:
                            thumb_path = self._find_thumbnail(thumb_dir, shot_name)
                            if thumb_path and self.upload_thumbnail(shot, thumb_path):
                                results['thumbnails'] += 1
                        
                        # Upload version
                        if upload_versions and video_dir:
                            video_path = self._find_video(video_dir, shot_name)
                            if video_path and self.create_version(shot, video_path):
                                results['versions'] += 1
                                
                except Exception as e:
                    results['errors'].append(f"Error creating shot {shot_name}: {str(e)}")
            
            return results
        
        # Normal flow: Group shots by sequence and create under Project/Folder
        by_sequence = {}
        for shot_data in shots_data:
            seq_name = shot_data.get('Sequence', 'default')
            if seq_name not in by_sequence:
                by_sequence[seq_name] = []
            by_sequence[seq_name].append(shot_data)
        
        total_shots = len(shots_data)
        current = 0
        
        # Process each sequence
        for seq_name, shots in by_sequence.items():
            # Get or create sequence under the selected parent
            sequence = self.get_or_create_sequence(
                project_id, 
                seq_name, 
                parent_id=parent_id,
                parent_type=parent_type
            )
            if sequence:
                results['sequences'] += 1
            else:
                results['errors'].append(f"Failed to create sequence: {seq_name}")
                continue
            
            # Create shots
            for shot_data in shots:
                current += 1
                shot_name = shot_data.get('Shot Name', '')
                
                if not shot_name:
                    continue
                
                if progress_callback:
                    progress_callback(2, current, total_shots, f"Creating: {shot_name}")
                
                try:
                    # Create shot
                    description = shot_data.get('Description', '')
                    shot = self.create_shot(sequence, shot_name, description)
                    
                    if shot:
                        results['shots'] += 1
                        
                        # =========================================================
                        # CONFORM TASK - Created automatically with "pending_review"
                        # This task is independent of others and indicates that the shot
                        # was created from Flame and needs to be verified
                        # The current user is automatically assigned to the task
                        # =========================================================
                        conform_task = self.create_task(
                            shot, 
                            'conform',  # task name
                            'Conform',  # task type
                            'pending_review',  # automatic status
                            assign_current_user=True  # assigns the artist who is creating
                        )
                        if conform_task:
                            results['conform_tasks'] += 1
                            assigned_user = self.session.api_user if self.session else 'N/A'
                            logger.info(f"✓ Conform task created: {shot_name}/conform (pending_review) → assigned: {assigned_user}")
                        
                        # Create tasks (other tasks defined by user)
                        task_types = shot_data.get('Task Types', 'Compositing')
                        if isinstance(task_types, str):
                            task_types = [t.strip() for t in task_types.split(",")]
                        
                        status = shot_data.get("Status", DEFAULT_STATUS)
                        
                        for task_type in task_types:
                            if task_type:
                                task = self.create_task(
                                    shot,
                                    task_type.lower(),
                                    task_type,
                                    status
                                )
                                if task:
                                    results['tasks'] += 1
                        
                        # Upload thumbnail
                        if upload_thumbs and thumb_dir:
                            thumb_path = self._find_thumbnail(thumb_dir, shot_name)
                            if thumb_path:
                                if self.upload_thumbnail(shot, thumb_path):
                                    results['thumbnails'] += 1
                        
                        # Upload version (video)
                        if upload_versions and video_dir:
                            video_path = self._find_video(video_dir, shot_name)
                            if video_path:
                                if self.create_version(shot, video_path):
                                    results['versions'] += 1
                
                except Exception as e:
                    error_msg = f"{shot_name}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
        
        return results
    
    # -------------------------------------------------------------------------
    # TIME TRACKING
    # -------------------------------------------------------------------------
    
    def _discover_status_name(self, canonical_status: str) -> Optional[str]:
        """
        Discover the actual status name used on this ftrack server.
        
        Different ftrack instances use different naming conventions:
        - "in_progress" vs "In Progress" vs "In progress"
        - "not_started" vs "Not Started" vs "Not started"
        
        This method queries the server for all available statuses and finds
        the one that matches the canonical name (case/underscore insensitive).
        
        Args:
            canonical_status: The status to find (e.g., "in_progress", "In Progress")
            
        Returns:
            The exact status name as used on this server, or None if not found
        """
        normalized_target = normalize_status_name(canonical_status)
        
        # Check cache first
        if normalized_target in self._discovered_status_cache:
            return self._discovered_status_cache[normalized_target]
        
        if not self.session:
            logger.warning("No session available for status discovery")
            return None
        
        try:
            # Query all available statuses from the server
            statuses = self.session.query('Status').all()
            
            logger.info(f"Discovering status matching '{canonical_status}' from {len(statuses)} available statuses...")
            
            for status in statuses:
                status_name = status.get('name', '') if hasattr(status, 'get') else str(status)
                
                if normalize_status_name(status_name) == normalized_target:
                    # Found it! Cache and return
                    self._discovered_status_cache[normalized_target] = status_name
                    logger.info(f"Status discovered: '{canonical_status}' -> '{status_name}' (server format)")
                    return status_name
            
            # Not found - log available statuses for debugging
            available = [s.get('name', str(s)) for s in statuses[:20]]  # First 20
            logger.warning(
                f"Status '{canonical_status}' not found on server. "
                f"Available statuses (first 20): {available}"
            )
            
            # Cache the negative result as None
            self._discovered_status_cache[normalized_target] = None
            return None
            
        except Exception as e:
            logger.error(f"Error discovering status '{canonical_status}': {e}")
            return None
    
    def _get_in_progress_status_name(self) -> Optional[str]:
        """
        Get the exact 'in progress' status name for this ftrack server.
        
        Convenience method that handles the common case of finding
        tasks that are "in progress".
        
        Returns:
            The exact status name (e.g., "in_progress" or "In Progress")
        """
        # Try common variations
        result = self._discover_status_name("in_progress")
        if result:
            return result
        
        # Try alternative
        result = self._discover_status_name("In Progress")
        return result
    
    def get_my_tasks_in_progress(self) -> List[Dict]:
        """
        Get tasks with status 'in_progress' (or equivalent) assigned to current user.
        
        This method automatically discovers the correct status name format
        used by the ftrack server (handles "in_progress", "In Progress", etc.).
        
        Returns:
            List of task dicts with id, name, project, parent info
        """
        if self.is_mock:
            return [
                {'id': 'task_001', 'name': 'compositing', 'project': 'Demo Project', 
                 'parent': 'vfx_010', 'type': 'Compositing'},
                {'id': 'task_002', 'name': 'roto', 'project': 'Demo Project', 
                 'parent': 'vfx_020', 'type': 'Rotoscoping'},
            ]
        
        if not self.session:
            logger.warning("No session available for get_my_tasks_in_progress")
            return []
        
        try:
            # Get current user ID first
            user_query = f'User where username is "{self.session.api_user}"'
            user = self.session.query(user_query).first()
            
            if not user:
                logger.warning(f"Could not find current user: {self.session.api_user}")
                return []
            
            user_id = user['id']
            logger.info(f"Loading in_progress tasks for user: {self.session.api_user}")
            
            # Discover the correct status name for this ftrack server
            in_progress_status = self._get_in_progress_status_name()
            
            if not in_progress_status:
                logger.warning(
                    "Could not find 'in progress' status on this server. "
                    "Please check your ftrack status configuration."
                )
                return []
            
            logger.info(f"Using status name: '{in_progress_status}'")
            
            # Build query with the discovered status name
            # Filter project.status is "active" (without .name)
            query = (
                'select id, name, type.name, parent.name, project.name, project.id '
                'from Task where assignments any (resource.id is "{}") '
                'and status.name is "{}" '
                'and project.status is "active" '
                'limit 200'
            ).format(user_id, in_progress_status)
            
            logger.info(f"Executing query for '{in_progress_status}' tasks (active projects only)...")
            
            tasks = None
            use_python_filter = False
            
            try:
                tasks = self.session.query(query).all()
                logger.info(f"Query returned {len(tasks)} tasks from active projects")
            except Exception as query_error:
                # If it fails, use query without project filter and filter in Python
                logger.warning(f"Query with project.status filter failed: {query_error}")
                logger.info("Falling back to Python filtering...")
                
                fallback_query = (
                    'select id, name, type.name, parent.name, project.name, project.id, project.status.name '
                    'from Task where assignments any (resource.id is "{}") '
                    'and status.name is "{}" '
                    'limit 200'
                ).format(user_id, in_progress_status)
                
                tasks = self.session.query(fallback_query).all()
                use_python_filter = True
                logger.info(f"Fallback query returned {len(tasks)} tasks total")
            
            if not tasks:
                return []
            
            # Build result
            result = []
            filtered_count = 0
            
            for task in tasks:
                try:
                    project = task.get('project')
                    if not project:
                        continue
                    
                    # If using fallback, filter by project status in Python
                    if use_python_filter:
                        project_status_name = ''
                        try:
                            proj_status = project.get('status') if hasattr(project, 'get') else None
                            if proj_status:
                                if hasattr(proj_status, 'get'):
                                    project_status_name = proj_status.get('name', '')
                                elif hasattr(proj_status, '__getitem__'):
                                    project_status_name = proj_status['name']
                                elif hasattr(proj_status, 'name'):
                                    project_status_name = proj_status.name
                                else:
                                    project_status_name = str(proj_status)
                        except Exception as e:
                            logger.debug(f"Could not get project status: {e}")
                        
                        if project_status_name and project_status_name.lower() != 'active':
                            filtered_count += 1
                            continue
                    
                    project_name = project.get('name', '') if hasattr(project, 'get') else str(project)
                    project_id = project.get('id', None) if hasattr(project, 'get') else None
                    
                    # Get parent info
                    parent = task.get('parent')
                    parent_name = ''
                    parent_id = None
                    if parent:
                        parent_name = parent.get('name', '') if hasattr(parent, 'get') else str(parent)
                        parent_id = parent.get('id', None) if hasattr(parent, 'get') else None
                    
                    # Get type info
                    task_type = task.get('type')
                    type_name = ''
                    if task_type:
                        type_name = task_type.get('name', '') if hasattr(task_type, 'get') else str(task_type)
                    
                    result.append({
                        'id': task['id'],
                        'name': task['name'],
                        'project': project_name,
                        'project_id': project_id,
                        'parent': parent_name,
                        'parent_id': parent_id,
                        'type': type_name,
                    })
                except Exception as e:
                    logger.warning(f"Error processing task: {e}")
                    continue
            
            if use_python_filter:
                logger.info(f"Result: {len(result)} tasks from active projects (filtered out {filtered_count} in Python)")
            else:
                logger.info(f"Result: {len(result)} tasks from active projects")
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching tasks in_progress: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def create_timelog(self, task_id: str, hours: float, comment: str = "", date=None) -> bool:
        """
        Create a time log entry for a task.
        
        Args:
            task_id: ID of the task
            hours: Number of hours to log
            comment: Optional comment for the time log
            date: Optional date for the time log (defaults to today)
        
        Returns:
            bool: Success status
        """
        if self.is_mock:
            logger.info(f"[MOCK] Time log created: {hours:.2f} hours on task {task_id}")
            return True
        
        if not self.session:
            logger.warning("No session available for create_timelog")
            return False
        
        try:
            # Get task
            task = self.session.query(f'Task where id is "{task_id}"').first()
            if not task:
                logger.error(f"Task not found: {task_id}")
                return False
            
            # Get current user
            user = self.session.query('User where username is "{}"'.format(
                self.session.api_user
            )).first()
            
            if not user:
                logger.error("Could not find current user for timelog")
                return False
            
            # Create timelog
            # ftrack uses seconds for duration
            duration_seconds = int(hours * 3600)
            
            # Use provided date or default to now
            if date:
                # Create datetime from date at noon
                log_datetime = datetime.combine(date, datetime.min.time().replace(hour=12))
            else:
                log_datetime = datetime.now()
            
            timelog = self.session.create('Timelog', {
                'user': user,
                'context': task,
                'duration': duration_seconds,
                'start': log_datetime,
                'comment': comment or f"Logged {hours:.2f} hours from Flame"
            })
            
            self.session.commit()
            
            logger.info(f"Time log created: {hours:.2f} hours on task '{task['name']}'")
            return True
            
        except Exception as e:
            logger.error(f"Error creating timelog: {e}")
            if self.session:
                self.session.rollback()
            return False
    
    def get_today_timelogs(self, task_id: str = None) -> List[Dict]:
        """
        Get today's time logs for current user, optionally filtered by task.
        
        Args:
            task_id: Optional task ID to filter
        
        Returns:
            List of timelog dicts
        """
        if self.is_mock:
            return [
                {'id': 'tl_001', 'task': 'compositing', 'hours': 2.5, 
                 'comment': 'Morning work'},
                {'id': 'tl_002', 'task': 'compositing', 'hours': 1.0, 
                 'comment': 'Afternoon fixes'},
            ]
        
        if not self.session:
            return []
        
        try:
            # Get current user
            user = self.session.query('User where username is "{}"'.format(
                self.session.api_user
            )).first()
            
            if not user:
                return []
            
            # Build query for today's logs
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            query = 'Timelog where user.id is "{}" and start >= "{}"'.format(
                user['id'],
                today.isoformat()
            )
            
            if task_id:
                query += f' and context.id is "{task_id}"'
            
            timelogs = self.session.query(query).all()
            
            result = []
            for tl in timelogs:
                try:
                    context = tl.get('context')
                    result.append({
                        'id': tl['id'],
                        'task': context['name'] if context else 'Unknown',
                        'hours': tl['duration'] / 3600,
                        'comment': tl.get('comment', ''),
                        'start': tl.get('start'),
                    })
                except:
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching timelogs: {e}")
            return []
