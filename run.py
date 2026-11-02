#!/usr/bin/env python3
"""
JARVIS Launcher — convenient entry point with common commands.
"""
import sys
import os
import subprocess
from pathlib import Path


def main():
    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Check for virtual environment
    venv_python = project_root / "vvenv" / "Scripts" / "python.exe"
    python_cmd = str(venv_python) if venv_python.exists() else "python"
    
    if len(sys.argv) < 2:
        print("""
JARVIS Launcher
================

Usage: python run.py <command>

Commands:
  start           Start JARVIS (default)
  autostart       Configure auto-start on Windows boot
  install         Install/update dependencies
  test            Run quick tests
  config          Show current configuration
  dashboard       Start web dashboard only
  plugin          Create a new plugin template
        """)
        return
    
    command = sys.argv[1]
    
    if command == "start":
        # Start JARVIS
        os.execv(python_cmd, [python_cmd, "jarvis.py"] + sys.argv[2:])
    
    elif command == "autostart":
        # Auto-start management
        args = sys.argv[2:]
        os.execv(python_cmd, [python_cmd, "jarvis.py", "autostart"] + args)
    
    elif command == "install":
        # Install dependencies
        print("Installing dependencies...")
        subprocess.run([python_cmd, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Done!")
    
    elif command == "test":
        # Run tests
        print("Running tests...")
        test_imports()
    
    elif command == "config":
        # Show configuration
        show_config()
    
    elif command == "dashboard":
        # Start only the dashboard
        start_dashboard()
    
    elif command == "plugin":
        # Create plugin template
        create_plugin(sys.argv[2] if len(sys.argv) > 2 else "my_plugin")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


def test_imports():
    """Test that all core modules can be imported."""
    modules_to_test = [
        "core.config",
        "core.brain", 
        "core.voice",
        "core.tasks",
        "core.notifier",
        "core.api",
        "core.briefing",
        "core.plugins",
        "core.recovery",
        "core.autostart",
    ]
    
    print("Testing imports...")
    for mod in modules_to_test:
        try:
            __import__(mod)
            print(f"  OK {mod}")
        except Exception as e:
            print(f"  FAIL {mod}: {e}")
    
    # Test plugin discovery
    from core.plugins import plugin_manager
    plugins = plugin_manager.discover_plugins()
    print(f"\nDiscovered plugins: {plugins}")


def show_config():
    """Display current configuration."""
    from core.config import config
    cfg = config.get()
    
    print("\nCurrent Configuration")
    print("=" * 40)
    print(f"Wake word: {cfg.voice.wake_word}")
    print(f"TTS Provider: {cfg.voice.tts_provider}")
    print(f"Default Language: {cfg.voice.default_language}")
    print(f"Scheduler Enabled: {cfg.scheduler.enabled}")
    print(f"API Enabled: {cfg.api.enabled}")
    print(f"Briefing Enabled: {cfg.briefing.enabled}")
    print(f"Auto-start: {cfg.auto_start.enabled} ({cfg.auto_start.method})")
    print("\nModules:")
    for name, mod in cfg.modules.items():
        print(f"  {name}: enabled={mod.enabled}, interval={mod.check_interval_minutes}min")


def start_dashboard():
    """Start only the web dashboard."""
    from core.api import app
    from core.config import config
    
    cfg = config.get()
    print(f"Starting dashboard on http://{cfg.api.host}:{cfg.api.port}")
    app.run(host=cfg.api.host, port=cfg.api.port, debug=True)


def create_plugin(name: str):
    """Create a new plugin template."""
    plugin_dir = Path("plugins")
    plugin_dir.mkdir(exist_ok=True)
    
    class_name = name.title().replace('_', '') + "Plugin"
    upper_name = name.upper()
    
    template = '''"""
{class_name} Plugin -- Template for custom JARVIS plugins.
"""

from core.plugins import Plugin, VoiceCommandPlugin, PluginInfo, register_plugin


@register_plugin
class {class_name}(VoiceCommandPlugin):
    PLUGIN_INFO = PluginInfo(
        name="{name}",
        version="1.0.0",
        description="Custom plugin for {name}",
        author="Your Name",
        dependencies=[],
        config_schema={{
            "type": "object",
            "properties": {{
                "enabled": {{"type": "boolean", "default": True}},
                "api_key": {{"type": "string"}}
            }}
        }}
    )
    
    COMMAND_ACTIONS = {{
        "custom_action": "handle_custom_action",
    }}
    
    def __init__(self, jarvis_instance=None):
        super().__init__(jarvis_instance)
        self.api_key = ""
    
    def initialize(self) -> bool:
        """Initialize plugin configuration."""
        import os
        self.api_key = os.getenv("{upper_name}_API_KEY", "")
        return True
    
    def start(self) -> bool:
        return True
    
    def stop(self) -> bool:
        return True
    
    def get_summary(self) -> str:
        return f"{{self.PLUGIN_INFO.name}}: Ready"
    
    def handle_custom_action(self, command: str, action: dict) -> bool:
        """Handle custom voice commands."""
        # action contains parsed parameters from brain.decide_action()
        # Example: {{"action": "custom_action", "param1": "value"}}
        
        param = action.get("param1", "")
        self.jarvis._say(f"Custom action triggered with: {{param}}")
        return True
'''.format(class_name=class_name, name=name, upper_name=upper_name)
    
    plugin_file = plugin_dir / f"{name}_plugin.py"
    plugin_file.write_text(template)
    print(f"Created plugin template: {plugin_file}")
    print(f"   Add your logic to handle_custom_action()")
    print(f"   Set {name.upper()}_API_KEY in .env if needed")


if __name__ == "__main__":
    main()