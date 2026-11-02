"""
JARVIS Core Package
===================
Core components for the JARVIS personal AI agent.
"""

from .config import config, JarvisConfig, ConfigManager
from .brain import JarvisBrain
from .voice import VoiceEngine, sanitize_speech_text
from .tasks import TaskManager
from .notifier import notify
from .api import start_api_server
from .briefing import create_briefing_manager, BriefingManager
from .plugins import plugin_manager, Plugin, VoiceCommandPlugin, BackgroundTaskPlugin, PluginInfo, register_plugin
from .recovery import HealthMonitor, CircuitBreaker, with_retry, safe_execute
from .autostart import AutoStartManager, setup_autostart, remove_autostart

__all__ = [
    "config",
    "JarvisConfig", 
    "ConfigManager",
    "JarvisBrain",
    "VoiceEngine",
    "sanitize_speech_text",
    "TaskManager",
    "notify",
    "start_api_server",
    "create_briefing_manager",
    "BriefingManager",
    "plugin_manager",
    "Plugin",
    "VoiceCommandPlugin",
    "BackgroundTaskPlugin",
    "PluginInfo",
    "register_plugin",
    "HealthMonitor",
    "CircuitBreaker",
    "with_retry",
    "safe_execute",
    "AutoStartManager",
    "setup_autostart",
    "remove_autostart",
]

__version__ = "2.0.0"