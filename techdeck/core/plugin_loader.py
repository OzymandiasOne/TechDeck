"""
TechDeck Plugin Loader
Discovers and loads plugins from the plugins directory.

PHASE 1 FIX: Added comprehensive error handling for JSON parsing and module loading
"""

import json
import importlib.util
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import os
import logging


# Set up logging for better error tracking
logger = logging.getLogger(__name__)


@dataclass
class Plugin:
    """
    Represents a discovered plugin.
    
    Attributes:
        id: Unique plugin identifier
        name: Display name
        description: Short description
        version: Plugin version
        author: Plugin author
        path: Path to plugin directory
        icon: Optional icon path
        requires_admin: Whether plugin needs admin rights
    """
    id: str
    name: str
    description: str
    version: str
    author: str
    path: Path
    icon: Optional[str] = None
    requires_admin: bool = False


class PluginLoader:
    """
    Discovers and manages plugins with robust error handling.
    """
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        """
        Initialize plugin loader.
        
        Args:
            plugins_dir: Custom plugins directory. 
                        Defaults to %LOCALAPPDATA%/TechDeck/plugins
        """
        if plugins_dir is None:
            if os.name == 'nt':
                base = Path(os.environ.get('LOCALAPPDATA', Path.home()))
            else:
                base = Path.home() / '.local' / 'share'
            plugins_dir = base / 'TechDeck' / 'plugins'
        
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        self.plugins: Dict[str, Plugin] = {}
    
    def _validate_plugin_path(self, plugin_path: Path) -> bool:
        """
        PHASE 1 FIX: Validate that plugin path is within plugins directory.
        
        This prevents directory traversal attacks where a malicious plugin
        could reference files outside the intended directory.
        
        Args:
            plugin_path: Path to validate
            
        Returns:
            True if path is safe, False otherwise
        """
        try:
            resolved = plugin_path.resolve()
            plugins_resolved = self.plugins_dir.resolve()
            
            # Check if resolved path starts with plugins dir
            return str(resolved).startswith(str(plugins_resolved))
        except (OSError, ValueError) as e:
            logger.warning(f"Path validation error for {plugin_path}: {e}")
            return False
    
    def discover_plugins(self) -> List[Plugin]:
        """
        Scan plugins directory and discover all valid plugins.
        
        PHASE 1 FIX: Enhanced error handling for malformed plugins
        
        Returns:
            List of discovered Plugin objects
        """
        self.plugins.clear()
        
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            return []
        
        for item in self.plugins_dir.iterdir():
            if not item.is_dir():
                continue
            
            # PHASE 1 FIX: Validate plugin path before processing
            if not self._validate_plugin_path(item):
                logger.warning(f"Skipping plugin with invalid path: {item}")
                continue
            
            # Look for plugin.json
            metadata_file = item / 'plugin.json'
            if not metadata_file.exists():
                logger.debug(f"Skipping {item.name}: no plugin.json found")
                continue
            
            # Look for run.py
            run_file = item / 'run.py'
            if not run_file.exists():
                logger.debug(f"Skipping {item.name}: no run.py found")
                continue
            
            try:
                # PHASE 1 FIX: Enhanced JSON error handling
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in {metadata_file}: {e}")
                    logger.error(f"  Line {e.lineno}, Column {e.colno}: {e.msg}")
                    continue
                except UnicodeDecodeError as e:
                    logger.error(f"Encoding error reading {metadata_file}: {e}")
                    continue
                except IOError as e:
                    logger.error(f"IO error reading {metadata_file}: {e}")
                    continue
                
                # PHASE 1 FIX: Validate required fields exist
                if not isinstance(metadata, dict):
                    logger.error(f"Invalid plugin.json in {item}: root must be an object")
                    continue
                
                # Extract fields with defaults for optional ones
                plugin_id = metadata.get('id', item.name)
                plugin_name = metadata.get('name', item.name)
                
                # Validate plugin_id is safe (no path separators, etc.)
                if not plugin_id or '/' in plugin_id or '\\' in plugin_id or '..' in plugin_id:
                    logger.error(f"Invalid plugin ID in {item}: '{plugin_id}'")
                    continue
                
                # Create Plugin object
                plugin = Plugin(
                    id=plugin_id,
                    name=plugin_name,
                    description=metadata.get('description', ''),
                    version=metadata.get('version', '1.0.0'),
                    author=metadata.get('author', 'Unknown'),
                    path=item,
                    icon=metadata.get('icon'),
                    requires_admin=metadata.get('requires_admin', False)
                )
                
                # Check for duplicate plugin IDs
                if plugin.id in self.plugins:
                    logger.warning(f"Duplicate plugin ID '{plugin.id}' in {item}, skipping")
                    continue
                
                self.plugins[plugin.id] = plugin
                logger.info(f"Loaded plugin: {plugin.name} (v{plugin.version})")
                
            except KeyError as e:
                logger.error(f"Missing required field in {metadata_file}: {e}")
                continue
            except Exception as e:
                # Catch-all for unexpected errors
                logger.error(f"Unexpected error loading plugin from {item}: {e}", exc_info=True)
                continue
        
        logger.info(f"Discovered {len(self.plugins)} plugin(s)")
        return list(self.plugins.values())
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """Get a plugin by ID."""
        return self.plugins.get(plugin_id)
    
    def get_all_plugins(self) -> List[Plugin]:
        """Get all discovered plugins."""
        return list(self.plugins.values())
    
    def load_plugin_module(self, plugin_id: str):
        """
        Load a plugin's Python module.
        
        PHASE 1 FIX: Comprehensive error handling for module loading
        
        Args:
            plugin_id: Plugin ID to load
            
        Returns:
            The loaded module object
            
        Raises:
            ValueError: If plugin not found
            ImportError: If plugin can't be loaded
            SyntaxError: If plugin has syntax errors
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_id}")
        
        run_file = plugin.path / 'run.py'
        if not run_file.exists():
            raise ImportError(f"Plugin {plugin_id} has no run.py")
        
        # PHASE 1 FIX: Validate run.py is actually a file and readable
        if not run_file.is_file():
            raise ImportError(f"Plugin {plugin_id} run.py is not a file")
        
        try:
            # Create module spec
            spec = importlib.util.spec_from_file_location(
                f"techdeck_plugin_{plugin_id}",
                run_file
            )
            
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not create module spec for {plugin_id}")
            
            # PHASE 1 FIX: Enhanced module loading with error handling
            try:
                # Load module
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                
            except SyntaxError as e:
                # Python syntax error in plugin code
                raise SyntaxError(
                    f"Syntax error in {plugin_id} at line {e.lineno}: {e.msg}"
                ) from e
            
            except ImportError as e:
                # Plugin tried to import something that doesn't exist
                raise ImportError(
                    f"Plugin {plugin_id} has missing dependency: {e}"
                ) from e
            
            except Exception as e:
                # Other runtime errors during module initialization
                raise RuntimeError(
                    f"Error initializing plugin {plugin_id}: {type(e).__name__}: {e}"
                ) from e
            
            return module
            
        except (OSError, IOError) as e:
            # File system errors
            raise ImportError(
                f"Could not read plugin {plugin_id}: {e}"
            ) from e
    
    def validate_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        """
        Validate that a plugin can be executed.
        
        PHASE 1 FIX: More detailed validation with specific error messages
        
        Args:
            plugin_id: Plugin ID to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return False, f"Plugin not found: {plugin_id}"
        
        # Validate path security
        if not self._validate_plugin_path(plugin.path):
            return False, f"Plugin {plugin_id} has invalid path"
        
        run_file = plugin.path / 'run.py'
        if not run_file.exists():
            return False, f"Plugin {plugin_id} is missing run.py"
        
        if not run_file.is_file():
            return False, f"Plugin {plugin_id} run.py is not a file"
        
        # Try to load the module
        try:
            module = self.load_plugin_module(plugin_id)
            
            # Check for run function
            if not hasattr(module, 'run'):
                return False, f"Plugin {plugin_id} has no run() function"
            
            # Check that run is callable
            if not callable(module.run):
                return False, f"Plugin {plugin_id} run is not callable"
            
            # PHASE 1 FIX: Additional validation - check function signature
            import inspect
            try:
                sig = inspect.signature(module.run)
                # Expected: run(params, progress_callback, cancel_event)
                if len(sig.parameters) != 3:
                    logger.warning(
                        f"Plugin {plugin_id} run() has {len(sig.parameters)} parameters, "
                        f"expected 3 (params, progress_callback, cancel_event)"
                    )
                    # Note: This is a warning, not a failure - allow flexibility
            except (ValueError, TypeError):
                # Can't inspect signature - that's okay
                pass
            
            return True, ""
            
        except SyntaxError as e:
            return False, f"Syntax error in {plugin_id}: {str(e)}"
        
        except ImportError as e:
            return False, f"Import error in {plugin_id}: {str(e)}"
        
        except ValueError as e:
            return False, f"Plugin {plugin_id} validation error: {str(e)}"
        
        except Exception as e:
            return False, f"Plugin {plugin_id} failed to load: {type(e).__name__}: {str(e)}"
    
    def get_plugins_dir(self) -> Path:
        """Get the plugins directory path."""
        return self.plugins_dir
