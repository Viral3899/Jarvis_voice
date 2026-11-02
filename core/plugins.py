"""
Plugin System — extensible module architecture for JARVIS.
"""
import os
import sys
import importlib
import importlib.util
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Type
from dataclasses import dataclass, field
from threading import Lock

from core.config import config


@dataclass
class PluginInfo:
    """Metadata about a plugin."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


class Plugin(ABC):
    """Base class for all JARVIS plugins."""
    
    # Plugin metadata
    PLUGIN_INFO = PluginInfo(name="base")
    
    def __init__(self, jarvis_instance=None):
        self.jarvis = jarvis_instance
        self.config = config.get()
        self._initialized = False
        self._running = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the plugin. Return True on success."""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Start the plugin (background tasks, connections, etc.)."""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop the plugin gracefully."""
        pass
    
    def get_summary(self) -> str:
        """Get a brief status summary."""
        return f"{self.PLUGIN_INFO.name}: {'Running' if self._running else 'Stopped'}"
    
    def handle_command(self, command: str, action: dict) -> bool:
        """Handle a voice command. Return True if handled."""
        return False
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return JSON schema for plugin configuration."""
        return self.PLUGIN_INFO.config_schema
    
    def update_config(self, key: str, value: Any) -> bool:
        """Update plugin configuration."""
        return True


class VoiceCommandPlugin(Plugin):
    """Mixin for plugins that handle voice commands."""
    
    # Map of action names to handler methods
    COMMAND_ACTIONS: Dict[str, str] = {}
    
    def handle_command(self, command: str, action: dict) -> bool:
        action_type = action.get('action')
        if action_type in self.COMMAND_ACTIONS:
            handler_name = self.COMMAND_ACTIONS[action_type]
            handler = getattr(self, handler_name, None)
            if handler:
                return handler(command, action)
        return False


class BackgroundTaskPlugin(Plugin):
    """Mixin for plugins that run background tasks."""
    
    # Interval in minutes for background checks
    CHECK_INTERVAL: int = 5
    
    def start(self) -> bool:
        if not self._running:
            self._running = True
            return True
        return False
    
    def stop(self) -> bool:
        self._running = False
        return True


class PluginManager:
    """Manages plugin discovery, loading, and lifecycle."""
    
    _instance: Optional['PluginManager'] = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_classes: Dict[str, Type[Plugin]] = {}
        self.plugin_dirs: List[Path] = []
        self.jarvis_instance = None
        self._initialized = True
    
    def set_jarvis(self, jarvis):
        """Set the JARVIS instance for plugins."""
        self.jarvis_instance = jarvis
        for plugin in self.plugins.values():
            plugin.jarvis = jarvis
    
    def add_plugin_dir(self, path: Path):
        """Add a directory to search for plugins."""
        if path not in self.plugin_dirs:
            self.plugin_dirs.append(path)
    
    def discover_plugins(self) -> List[str]:
        """Discover available plugins in plugin directories."""
        discovered = []
        
        # Built-in modules directory
        builtin_dir = Path(__file__).parent.parent / "modules"
        if builtin_dir.exists():
            self._scan_directory(builtin_dir, discovered, "modules")
        
        # Custom plugin directories
        for plugin_dir in self.plugin_dirs:
            if plugin_dir.exists():
                self._scan_directory(plugin_dir, discovered, "plugins")
        
        return discovered
    
    def _scan_directory(self, directory: Path, discovered: List[str], namespace: str):
        """Scan a directory for plugin modules."""
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            full_name = f"{namespace}.{module_name}"
            discovered.append(full_name)
    
    def load_plugin(self, module_name: str) -> Optional[Plugin]:
        """Load a plugin by module name."""
        if module_name in self.plugins:
            return self.plugins[module_name]
        
        try:
            # Import the module
            module = importlib.import_module(module_name)
            
            # Find plugin class
            plugin_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Plugin) and obj is not Plugin:
                    plugin_class = obj
                    break
            
            if not plugin_class:
                print(f"⚠ No plugin class found in {module_name}")
                return None
            
            # Check if enabled in config
            plugin_name = plugin_class.PLUGIN_INFO.name
            cfg = config.get()
            module_cfg = cfg.modules.get(plugin_name)
            if module_cfg and not module_cfg.enabled:
                print(f"⏭ Plugin {plugin_name} disabled in config")
                return None
            
            # Instantiate
            plugin = plugin_class(self.jarvis_instance)
            self.plugin_classes[plugin_name] = plugin_class
            
            # Initialize
            if plugin.initialize():
                self.plugins[plugin_name] = plugin
                print(f"✅ Loaded plugin: {plugin_name} v{plugin.PLUGIN_INFO.version}")
                return plugin
            else:
                print(f"❌ Plugin {plugin_name} initialization failed")
                return None
                
        except Exception as e:
            print(f"❌ Failed to load plugin {module_name}: {e}")
            return None
    
    def load_all(self) -> Dict[str, Plugin]:
        """Load all discovered plugins."""
        discovered = self.discover_plugins()
        for module_name in discovered:
            self.load_plugin(module_name)
        return self.plugins
    
    def start_all(self):
        """Start all loaded plugins."""
        for name, plugin in self.plugins.items():
            try:
                if plugin.start():
                    print(f"▶️ Started plugin: {name}")
                else:
                    print(f"⚠ Plugin {name} start returned False")
            except Exception as e:
                print(f"❌ Error starting plugin {name}: {e}")
    
    def stop_all(self):
        """Stop all plugins gracefully."""
        for name, plugin in self.plugins.items():
            try:
                plugin.stop()
                print(f"⏹ Stopped plugin: {name}")
            except Exception as e:
                print(f"❌ Error stopping plugin {name}: {e}")
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self.plugins.get(name)
    
    def handle_command(self, command: str, action: dict) -> bool:
        """Route command to plugins."""
        for plugin in self.plugins.values():
            try:
                if plugin.handle_command(command, action):
                    return True
            except Exception as e:
                print(f"⚠ Plugin {plugin.PLUGIN_INFO.name} command error: {e}")
        return False
    
    def reload_plugin(self, name: str) -> bool:
        """Hot-reload a plugin."""
        if name in self.plugins:
            self.plugins[name].stop()
            del self.plugins[name]
            if name in self.plugin_classes:
                del self.plugin_classes[name]
            # Re-import module
            module_name = None
            for mod_name, cls in self.plugin_classes.items():
                if cls.PLUGIN_INFO.name == name:
                    module_name = cls.__module__
                    break
            if module_name:
                importlib.reload(sys.modules[module_name])
            return self.load_plugin(module_name) is not None
        return False


# Global instance
plugin_manager = PluginManager()


def register_plugin(plugin_class: Type[Plugin]):
    """Decorator to register a plugin class."""
    plugin_manager.plugin_classes[plugin_class.PLUGIN_INFO.name] = plugin_class
    return plugin_class


# Example plugin template
"""
# Save as modules/my_plugin.py or plugins/my_plugin.py

from core.plugins import Plugin, VoiceCommandPlugin, register_plugin, PluginInfo

@register_plugin
class MyPlugin(VoiceCommandPlugin):
    PLUGIN_INFO = PluginInfo(
        name="my_plugin",
        version="1.0.0",
        description="My custom plugin",
        author="Me",
        dependencies=["groq", "requests"],
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "enabled": {"type": "boolean", "default": True}
            }
        }
    )
    
    COMMAND_ACTIONS = {
        "my_custom_action": "handle_my_action"
    }
    
    def initialize(self):
        # Setup connections, load config, etc.
        return True
    
    def start(self):
        # Start background tasks
        return True
    
    def stop(self):
        # Cleanup
        return True
    
    def handle_my_action(self, command: str, action: dict):
        # Handle the action
        self.jarvis._say("My plugin handled this!")
        return True
"""