# 🤖 J.A.R.V.I.S. — Personal AI Background Agent

**Just A Rather Very Intelligent System**

A voice-controlled AI agent that runs in the background, manages your digital life, and responds when you say **"Jarvis"**.

## 🏗️ Architecture

```
jarvis-agent/
├── jarvis.py              ← Main entry point
├── run.py                 ← Convenience launcher
├── .env                   ← API keys & config
├── requirements.txt       ← Dependencies
├── core/
│   ├── __init__.py        ← Package exports
│   ├── config.py          ← Configuration manager (hot-reload, validation)
│   ├── brain.py           ← AI brain (Groq)
│   ├── voice.py           ← Speech recognition + TTS
│   ├── tasks.py           ← Task manager with persistence
│   ├── notifier.py        ← Windows toast notifications
│   ├── api.py             ← REST API + Web Dashboard
│   ├── briefing.py        ← Automated daily briefings
│   ├── plugins.py         ← Plugin system
│   ├── recovery.py        ← Health monitoring & auto-recovery
│   └── autostart.py       ← Windows auto-start manager
├── modules/
│   ├── email_gmail.py     ← Gmail (OAuth2)
│   ├── whatsapp.py        ← WhatsApp Web (Selenium)
│   ├── instagram.py       ← Instagram DMs (Selenium)
│   ├── telegram_bot.py    ← Telegram (Bot API)
│   ├── calendar_mod.py    ← Google Calendar
│   └── jobs.py            ← LinkedIn / Naukri / Indeed job search
├── plugins/               ← Custom plugins (auto-discovered)
│   └── weather_plugin.py  ← Example: weather plugin
├── config/
│   ├── gmail_credentials.json  ← Google OAuth (you provide)
│   └── jarvis_config.json      ← Auto-generated config
├── data/
│   ├── tasks.json         ← Persisted tasks
│   ├── whatsapp_profile/  ← WhatsApp browser session
│   └── jobs_profile/      ← Jobs browser session
└── logs/
```

## ⚡ Quick Start

### 1. Install dependencies
```bash
cd jarvis-agent
python run.py install
```

> **Windows** — PyAudio 0.2.14 has no prebuilt wheel for Python 3.15. Use Python 3.12:
> ```bash
> deactivate
> py -3.12 -m venv vvenv
> source vvenv/Scripts/activate
> python --version
> python -m pip install -r requirements.txt
> ```

### 2. Configure `.env`
```env
# Required — get free key at https://console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxx

# ElevenLabs is the default speech provider; local TTS is used if unavailable.
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
TTS_PROVIDER=elevenlabs
# Set TTS_PROVIDER=local to always use local voice
DEFAULT_LANGUAGE=hi
SPEECH_FALLBACK_LOCALES=gu-IN,hi-IN,en-IN

# Optional — configure what you need
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_CHAT_ID=123456789
JOB_UPDATES_EMAIL=you@example.com
JOB_UPDATES_WHATSAPP=your_saved_contact_or_phone_number

# Weather plugin (optional)
OPENWEATHER_API_KEY=your_openweathermap_key

# Instagram uses a separate Jarvis Chrome profile by default.
# Log in to Instagram in the Jarvis window the first time.
INSTAGRAM_CHROME_PROFILE=Default
# INSTAGRAM_CHROME_USER_DATA_DIR=C:\path\to\custom\instagram_profile
```

### 3. Gmail & Calendar Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project → Enable **Gmail API** + **Calendar API**
3. Create **OAuth2 credentials** (Desktop app)
4. Download → save as `config/gmail_credentials.json`
5. First run opens browser for authorization

### 4. Run Jarvis
```bash
# Using launcher (recommended)
python run.py start

# Or directly
python jarvis.py
```

## 🎤 Voice Commands

| Say This | Jarvis Does |
|---|---|
| **"Jarvis, check my email"** | Checks Gmail and speaks summary of unread senders/subjects |
| **"Jarvis, check WhatsApp"** | Speaks unread WhatsApp chats and message previews |
| **"Jarvis, reply to [name] saying [message]"** | Sends WhatsApp reply |
| **"Jarvis, WhatsApp [number] saying [message]"** | Sends a WhatsApp message to an international phone number, including country code |
| **"Jarvis, send a WhatsApp message"** | Asks for recipient, then text/photo/voice recording; confirms before sending |
| **"Jarvis, send an email"** | Asks for recipient, then text/photo/voice recording and subject; confirms before sending |
| **"Jarvis, check Instagram"** | Speaks unread DMs |
| **"Jarvis, reply to [name] on Instagram"** | Sends Instagram DM |
| **"Jarvis, check Telegram"** | Speaks new Telegram messages |
| **"Jarvis, reply on Telegram [message]"** | Sends Telegram message |
| **"Jarvis, check my calendar"** | Reads upcoming events |
| **"Jarvis, add task [description] by [date]"** | Creates a tracked task |
| **"Jarvis, check my tasks"** | Lists pending/overdue tasks |
| **"Jarvis, search for Python developer jobs"** | Searches LinkedIn/Naukri/Indeed |
| **"Jarvis, send me the job links by email/WhatsApp/both"** | Sends latest job links |
| **"Jarvis, open [app name]"** | Opens Windows app (notepad, calculator, vscode, etc.) |
| **"Jarvis, search [query]"** | Google search |
| **"Jarvis, what's the weather in [city]"** | Checks current weather (requires plugin) |
| **"Jarvis, forecast for [city]"** | 3-day weather forecast |
| **"Jarvis, calculate [expression]"** | Basic math calculations |
| **"Jarvis, status"** | Full status report of everything |
| **"Jarvis, briefing"** | Manual daily briefing |
| **"Jarvis, [any question]"** | AI chat via Groq |
| **"Jarvis, quit"** | Shuts down |

### Interruption
You can interrupt Jarvis while speaking by saying **"Jarvis"** followed by a new command. It stops the current reply, acknowledges in English ("Yes sir, I hear you"), and handles the new request. Saying only **"Jarvis"** stops speech and prompts: "Yes sir, I'm listening. Tell me what you need."

## 🔄 Background Tasks (Automatic)

| Task | Default Interval |
|---|---|
| Check email | Every 5 min |
| Check WhatsApp | Every 3 min |
| Check Instagram | Every 10 min |
| Check Telegram | Every 2 min |
| Check calendar | Every 5 min |
| Task reminders | Every 15 min |
| Job search | Every 60 min |

Jarvis sends **Windows toast notifications** and speaks updates in the last detected spoken language. Alerts are deduplicated. Say **"Jarvis, status"** for a spoken summary.

## 🌅 Daily Briefings (Automatic)

- **Morning** (08:00): Tasks, calendar, email, WhatsApp
- **Evening** (20:00): Summary of the day

Configure in `.env` or via config file:
```env
BRIEFING_ENABLED=true
BRIEFING_MORNING_TIME=08:00
BRIEFING_EVENING_TIME=20:00
```

Or trigger manually: **"Jarvis, briefing"**

## 🌐 Web Dashboard & REST API

Start the dashboard:
```bash
python run.py dashboard
```

Then open http://localhost:8080 in your browser.

### Features
- Real-time module status
- Task management (view, complete, add)
- Send voice commands from browser
- Trigger briefings
- Configuration UI
- Activity log

### API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | System status |
| POST | `/api/command` | Send command `{ "command": "..." }` |
| POST | `/api/speak` | Make Jarvis speak `{ "text": "...", "language": "hi" }` |
| GET | `/api/tasks` | List all tasks |
| POST | `/api/tasks` | Create task `{ "title": "...", "deadline": "2024-12-31" }` |
| POST | `/api/tasks/:id/complete` | Complete task |
| POST | `/api/modules/:name/check` | Trigger module check |
| GET | `/api/config` | Get configuration |
| PUT | `/api/config` | Update configuration |
| POST | `/api/briefing` | Trigger briefing `{ "type": "full|morning|evening" }` |
| POST | `/api/shutdown` | Shutdown Jarvis |

### Authentication
Set `API_AUTH_TOKEN` in `.env` to enable Bearer token authentication.

## 🔌 Plugin System

Create custom capabilities by adding Python files to `plugins/`:

```python
# plugins/my_plugin.py
from core.plugins import Plugin, VoiceCommandPlugin, PluginInfo, register_plugin

@register_plugin
class MyPlugin(VoiceCommandPlugin):
    PLUGIN_INFO = PluginInfo(
        name="my_plugin",
        version="1.0.0",
        description="My custom plugin",
        author="Me",
        dependencies=["requests"],
        config_schema={...}
    )
    
    COMMAND_ACTIONS = {
        "my_action": "handle_my_action"
    }
    
    def initialize(self): return True
    def start(self): return True
    def stop(self): return True
    def get_summary(self): return "My Plugin: Ready"
    
    def handle_my_action(self, command: str, action: dict) -> bool:
        self.jarvis._say("Custom action executed!")
        return True
```

### Example: Weather Plugin
Included at `plugins/weather_plugin.py`. Requires `OPENWEATHER_API_KEY` in `.env`.

Commands:
- **"Jarvis, what's the weather in London"**
- **"Jarvis, forecast for Tokyo"**

### Example: Calculator Plugin
Included in `plugins/weather_plugin.py` (same file).

Commands:
- **"Jarvis, calculate 25 * 4"**
- **"Jarvis, what is 100 / 3"**

## 🛡️ Health Monitoring & Auto-Recovery

Jarvis automatically monitors module health and attempts recovery:

- **Circuit Breakers**: Prevent cascade failures
- **Health Checks**: Every 30 seconds
- **Auto-Recovery**: Restarts failed modules (max 3 attempts)
- **Manual Recovery**: Via dashboard or API

## 🚀 Auto-Start on Windows Boot

Configure Jarvis to start automatically:

```bash
# Enable (Task Scheduler - recommended)
python run.py autostart --enable --method task_scheduler

# Enable with admin privileges
python run.py autostart --enable --method task_scheduler --admin

# Disable
python run.py autostart --disable --method task_scheduler

# Check status
python run.py autostart --method task_scheduler
```

Methods:
- `task_scheduler` — Windows Task Scheduler (most reliable)
- `startup_folder` — Shortcut in Startup folder
- `registry` — HKCU Run key

## ⚙️ Configuration

Configuration is managed via:
1. **`.env`** — Secrets and critical settings (never committed)
2. **`config/jarvis_config.json`** — Auto-generated, non-sensitive settings
3. **Hot-reload** — Changes via API/dashboard apply immediately

### Key Settings
```json
{
  "voice": {
    "wake_word": "jarvis",
    "tts_provider": "elevenlabs",
    "default_language": "hi"
  },
  "scheduler": {
    "enabled": true,
    "intervals": {
      "email": 5,
      "whatsapp": 3,
      "instagram": 10,
      "telegram": 2,
      "calendar": 5,
      "tasks": 15,
      "jobs": 60
    }
  },
  "briefing": {
    "enabled": true,
    "morning_time": "08:00",
    "evening_time": "20:00"
  },
  "auto_start": {
    "enabled": false,
    "method": "task_scheduler"
  },
  "modules": {
    "gmail": {"enabled": true, "check_interval_minutes": 5},
    "whatsapp": {"enabled": true, "check_interval_minutes": 3}
  }
}
```

## 🧪 Testing

```bash
# Test all imports
python run.py test

# Check configuration
python run.py config
```

## 📁 Project Structure Details

### Core Modules
- **config.py** — Thread-safe config with hot-reload, env override, validation
- **brain.py** — Groq integration, action classification, context management
- **voice.py** — Wake word, STT (Groq Whisper + Google fallback), TTS (ElevenLabs + local)
- **tasks.py** — Persistent task management (JSON)
- **notifier.py** — Windows toast notifications
- **api.py** — Flask REST API + React-like dashboard (embedded HTML)
- **briefing.py** — Scheduled daily briefings with cron triggers
- **plugins.py** — Plugin base classes, manager, decorators
- **recovery.py** — Circuit breakers, health monitor, retry decorators
- **autostart.py** — Windows auto-start via Task Scheduler/Registry/Startup

### Modules (in `modules/`)
Each module is independent and can fail without affecting others:
- **email_gmail.py** — Gmail OAuth2, read/send, unread tracking
- **whatsapp.py** — WhatsApp Web via Selenium, persistent profile
- **instagram.py** — Instagram DMs via Selenium, uses a dedicated persistent profile
- **telegram_bot.py** — Telegram Bot API, polling
- **calendar_mod.py** — Google Calendar API, upcoming events
- **jobs.py** — LinkedIn/Naukri/Indeed scraping, job link collection

## ⚠️ Important Notes

- **WhatsApp/Instagram**: First run opens separate Chrome profiles — log in manually. Sessions persist.
- **Media sending**: Photos are selected in a file picker; voice messages are recorded from the microphone for up to 30 seconds. Jarvis asks for spoken confirmation before sending.
- **Telegram polling**: Run only one Jarvis instance per bot token; Telegram allows only one active `getUpdates` poller.
- **Job auto-apply**: Currently searches only. Auto-clicking "Apply" may violate platform ToS.
- **Modules are independent**: If Gmail isn't configured, everything else still works.
- **Keep API keys in `.env`, never in source code.** Rotate keys periodically.
- **Python 3.12 required** for PyAudio compatibility on Windows.

## 🤝 Contributing

1. Fork the repo
2. Create a plugin in `plugins/` or improve core modules
3. Submit a PR

## 📄 License

MIT License — see LICENSE file.