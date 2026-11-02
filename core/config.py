"""
Configuration Manager — centralized config with validation, hot-reload, and defaults.
"""
import os
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "jarvis_config.json"


@dataclass
class ModuleConfig:
    """Configuration for a single module."""
    enabled: bool = True
    check_interval_minutes: int = 5
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceConfig:
    """Voice engine configuration."""
    wake_word: str = "jarvis"
    tts_provider: str = "elevenlabs"  # "elevenlabs" or "local"
    default_language: str = "hi"
    speech_fallback_locales: str = "gu-IN,hi-IN,en-IN"
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    groq_transcription_timeout: int = 6
    groq_retry_cooldown: int = 300


@dataclass
class SchedulerConfig:
    """Background scheduler configuration."""
    enabled: bool = True
    intervals: Dict[str, int] = field(default_factory=lambda: {
        "email": 5,
        "whatsapp": 3,
        "instagram": 10,
        "telegram": 2,
        "calendar": 5,
        "tasks": 15,
        "jobs": 60,
    })


@dataclass
class NotificationConfig:
    """Notification configuration."""
    enabled: bool = True
    windows_toast: bool = True
    sound_alerts: bool = True


@dataclass
class APIConfig:
    """REST API configuration."""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080
    auth_token: str = ""


@dataclass
class BriefingConfig:
    """Daily briefing configuration."""
    enabled: bool = True
    morning_time: str = "08:00"
    evening_time: str = "20:00"
    include: Dict[str, bool] = field(default_factory=lambda: {
        "tasks": True,
        "calendar": True,
        "email": True,
        "whatsapp": True,
        "weather": False,
        "news": False,
    })


@dataclass
class AutoStartConfig:
    """Auto-start configuration."""
    enabled: bool = False
    method: str = "task_scheduler"  # "task_scheduler", "service", "startup_folder"
    run_as_admin: bool = False


@dataclass
class JarvisConfig:
    """Main configuration container."""
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    api: APIConfig = field(default_factory=APIConfig)
    briefing: BriefingConfig = field(default_factory=BriefingConfig)
    auto_start: AutoStartConfig = field(default_factory=AutoStartConfig)
    modules: Dict[str, ModuleConfig] = field(default_factory=lambda: {
        "gmail": ModuleConfig(enabled=True, check_interval_minutes=5),
        "calendar": ModuleConfig(enabled=True, check_interval_minutes=5),
        "whatsapp": ModuleConfig(enabled=True, check_interval_minutes=3),
        "instagram": ModuleConfig(enabled=True, check_interval_minutes=10),
        "telegram": ModuleConfig(enabled=True, check_interval_minutes=2),
        "jobs": ModuleConfig(enabled=True, check_interval_minutes=60),
    })
    groq_api_key: str = ""
    elevenlabs_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    job_updates_email: str = ""
    job_updates_whatsapp: str = ""


class ConfigManager:
    """Thread-safe configuration manager with hot-reload support."""
    
    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._config: JarvisConfig = JarvisConfig()
        self._watchers: list = []
        self._load()
        self._initialized = True
    
    def _load(self):
        """Load configuration from file and environment variables."""
        # Load from JSON file if exists
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                self._config = self._merge_config(self._config, data)
            except Exception as e:
                print(f"⚠ Config load error: {e}")
        
        # Override with environment variables
        self._load_from_env()
    
    def _load_from_env(self):
        """Load sensitive/config values from environment."""
        env_mapping = {
            "GROQ_API_KEY": ("groq_api_key", str),
            "ELEVENLABS_API_KEY": ("elevenlabs_api_key", str),
            "TELEGRAM_BOT_TOKEN": ("telegram_bot_token", str),
            "TELEGRAM_CHAT_ID": ("telegram_chat_id", str),
            "JOB_UPDATES_EMAIL": ("job_updates_email", str),
            "JOB_UPDATES_WHATSAPP": ("job_updates_whatsapp", str),
            "WAKE_WORD": ("voice.wake_word", str),
            "TTS_PROVIDER": ("voice.tts_provider", str),
            "DEFAULT_LANGUAGE": ("voice.default_language", str),
            "SPEECH_FALLBACK_LOCALES": ("voice.speech_fallback_locales", str),
            "ELEVENLABS_VOICE_ID": ("voice.elevenlabs_voice_id", str),
        }
        
        for env_key, (config_path, converter) in env_mapping.items():
            value = os.getenv(env_key)
            if value is not None:
                self._set_nested(config_path, converter(value))
    
    def _set_nested(self, path: str, value: Any):
        """Set a nested config value using dot notation."""
        parts = path.split('.')
        obj = self._config
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
    
    def _merge_config(self, base: JarvisConfig, override: dict) -> JarvisConfig:
        """Recursively merge config dictionaries."""
        result = asdict(base)
        self._deep_merge(result, override)
        return self._dict_to_config(result)
    
    def _deep_merge(self, base: dict, override: dict):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _dict_to_config(self, data: dict) -> JarvisConfig:
        """Convert dictionary to config object."""
        # This is a simplified version - in practice you'd want proper dataclass reconstruction
        return JarvisConfig(**data)
    
    def get(self) -> JarvisConfig:
        """Get current configuration."""
        return self._config
    
    def update(self, path: str, value: Any) -> bool:
        """Update a config value and notify watchers."""
        try:
            self._set_nested(path, value)
            self._notify_watchers(path, value)
            return True
        except Exception as e:
            print(f"⚠ Config update error: {e}")
            return False
    
    def save(self) -> bool:
        """Save configuration to file."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            # Only save non-sensitive config
            safe_config = asdict(self._config)
            # Remove sensitive keys
            for key in ['groq_api_key', 'elevenlabs_api_key', 'telegram_bot_token', 
                       'telegram_chat_id', 'job_updates_email', 'job_updates_whatsapp']:
                if key in safe_config:
                    safe_config[key] = ""
            for mod in safe_config.get('modules', {}).values():
                mod.pop('config', None)
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(safe_config, f, indent=2, default=str)
            return True
        except Exception as e:
            print(f"⚠ Config save error: {e}")
            return False
    
    def add_watcher(self, callback):
        """Add a config change watcher."""
        self._watchers.append(callback)
    
    def _notify_watchers(self, path: str, value: Any):
        for watcher in self._watchers:
            try:
                watcher(path, value)
            except Exception:
                pass


# Global instance
config = ConfigManager()