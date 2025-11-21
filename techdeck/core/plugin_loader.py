"""
TechDeck Plugin Loader
Discovers and loads plugins from the plugins directory.
"""

import json
import importlib.util
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import os


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
    Discovers and manages plugins.
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
    
    def discover_plugins(self) -> List[Plugin]:
        """
        Scan plugins directory and discover all valid plugins.
        
        Returns:
            List of discovered Plugin objects
        """
        self.plugins.clear()
        
        if not self.plugins_dir.exists():
            return []
        
        for item in self.plugins_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Look for plugin.json
            metadata_file = item / 'plugin.json'
            if not metadata_file.exists():
                continue
            
            # Look for run.py
            run_file = item / 'run.py'
            if not run_file.exists():
                continue
            
            try:
                # Load metadata
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Create Plugin object
                plugin = Plugin(
                    id=metadata.get('id', item.name),
                    name=metadata.get('name', item.name),
                    description=metadata.get('description', ''),
                    version=metadata.get('version', '1.0.0'),
                    author=metadata.get('author', 'Unknown'),
                    path=item,
                    icon=metadata.get('icon'),
                    requires_admin=metadata.get('requires_admin', False)
                )
                
                self.plugins[plugin.id] = plugin
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Failed to load plugin from {item}: {e}")
                continue
        
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
        
        Args:
            plugin_id: Plugin ID to load
            
        Returns:
            The loaded module object
            
        Raises:
            ValueError: If plugin not found
            ImportError: If plugin can't be loaded
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_id}")
        
        run_file = plugin.path / 'run.py'
        if not run_file.exists():
            raise ImportError(f"Plugin {plugin_id} has no run.py")
        
        # Create module spec
        spec = importlib.util.spec_from_file_location(
            f"techdeck_plugin_{plugin_id}",
            run_file
        )
        
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not create module spec for {plugin_id}")
        
        # Load module
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        
        return module
    
    def validate_plugin(self, plugin_id: str) -> tuple[bool, str]:
        """
        Validate that a plugin can be executed.
        
        Args:
            plugin_id: Plugin ID to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            return False, f"Plugin not found: {plugin_id}"
        
        run_file = plugin.path / 'run.py'
        if not run_file.exists():
            return False, f"Plugin {plugin_id} is missing run.py"
        
        # Try to load the module
        try:
            module = self.load_plugin_module(plugin_id)
            
            # Check for run function
            if not hasattr(module, 'run'):
                return False, f"Plugin {plugin_id} has no run() function"
            
            # Check that run is callable
            if not callable(module.run):
                return False, f"Plugin {plugin_id} run is not callable"
            
            return True, ""
            
        except Exception as e:
            return False, f"Plugin {plugin_id} failed to load: {str(e)}"
    
    def get_plugins_dir(self) -> Path:
        """Get the plugins directory path."""
        return self.plugins_dir