# 🤖 J.A.R.V.I.S. — Personal AI Background Agent

**Just A Rather Very Intelligent System**

A voice-controlled AI agent that runs in the background, manages your digital life, and responds when you say **"Jarvis"**.

## 🏗️ Architecture

```
jarvis-agent/
├── jarvis.py              ← Main entry point
├── .env                   ← API keys & config
├── requirements.txt       ← Dependencies
├── core/
│   ├── brain.py           ← AI brain (Groq)
│   ├── voice.py           ← Speech recognition + TTS
│   ├── tasks.py           ← Task manager with persistence
│   └── notifier.py        ← Windows toast notifications
├── modules/
│   ├── email_gmail.py     ← Gmail (OAuth2)
│   ├── whatsapp.py        ← WhatsApp Web (Selenium)
│   ├── instagram.py       ← Instagram DMs (Selenium)
│   ├── telegram_bot.py    ← Telegram (Bot API)
│   ├── calendar_mod.py    ← Google Calendar
│   └── jobs.py            ← LinkedIn / Naukri / Indeed job search
├── config/
│   ├── gmail_credentials.json  ← Google OAuth (you provide)
│   └── resume.pdf              ← Your resume for job apps
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
pip install -r requirements.txt
```

> **Windows** — PyAudio 0.2.14 has no prebuilt wheel for Python 3.15, so pip tries and fails to build it from source. Use Python 3.12 for this project:
> ```bash
> deactivate
> py -3.12 -m venv .venv
> source .venv/Scripts/activate
> python --version
> python -m pip install -r requirements.txt
> ```
> Confirm `python --version` reports Python 3.12 before installing. The existing `venv` may remain; make sure the prompt shows `(.venv)`, not `(venv)`.

### 2. Configure `.env`
```env
# Required — get free key at https://console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxx

# ElevenLabs is the default speech provider; local TTS is used if it is unavailable.
ELEVENLABS_API_KEY=your_rotated_elevenlabs_key
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
TTS_PROVIDER=elevenlabs
# Set TTS_PROVIDER=local to always use the local voice instead.
DEFAULT_LANGUAGE=hi

# Optional — configure what you need
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_CHAT_ID=123456789
JOB_UPDATES_EMAIL=you@example.com
JOB_UPDATES_WHATSAPP=your_saved_contact_or_phone_number

# Instagram uses a separate Jarvis Chrome profile by default.
INSTAGRAM_CHROME_PROFILE=Default
# Optional: override the default data/instagram_profile user-data directory.
# INSTAGRAM_CHROME_USER_DATA_DIR=C:\Users\you\AppData\Local\Jarvis\Instagram
```
Instagram and WhatsApp each open a normal, visible Chrome window using separate Jarvis profiles under `data/instagram_profile/` and `data/whatsapp_profile/` (not incognito or headless). Log in to Instagram and scan the WhatsApp QR code in their respective windows on first use; each profile retains its session for later runs. If WhatsApp's initial login wait times out, leave its window open; Jarvis keeps checking and detects a later QR login. Instagram no longer needs to open your everyday Chrome profile, so close-conflict errors are less likely.

Jarvis defaults to Hindi (`DEFAULT_LANGUAGE=hi`). Groq's multilingual Whisper detects whether you are speaking Hindi or English, and Jarvis responds in that detected language (naturally mirroring mixed Hindi-English speech). Non-Hindi/English language detections use the configured default language. ElevenLabs is the default speech provider and uses the multilingual Eleven v3 model with the selected language code (`hi` or `en`). If ElevenLabs is unavailable or not configured, Jarvis falls back to local speech. Set `TTS_PROVIDER=local` to always use local speech. Voice audio is sent to Groq for transcription, and generated speech text is sent to ElevenLabs for audio.

### 3. Gmail & Calendar Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project → Enable **Gmail API** + **Calendar API**
3. Create **OAuth2 credentials** (Desktop app)
4. Download → save as `config/gmail_credentials.json`
5. First run opens browser for authorization

Emailing job links requires Gmail's send permission. If your existing token lacks it, Jarvis opens Google authorization again to request the added permission.

### 4. Run Jarvis
```bash
python jarvis.py
```

## 🎤 Voice Commands

| Say This | Jarvis Does |
|---|---|
| **"Jarvis, check my email"** | Checks Gmail and speaks a summary of unread senders and subjects |
| **"Jarvis, check WhatsApp"** | Speaks unread WhatsApp chats and available message previews |
| **"Jarvis, reply to [name] saying [message]"** | Sends WhatsApp reply |
| **"Jarvis, check Instagram"** | Speaks unread DMs |
| **"Jarvis, check Telegram"** | Speaks new Telegram messages |
| **"Jarvis, reply to [name] on Instagram"** | Sends Instagram DM |
| **"Jarvis, check my calendar"** | Reads upcoming events |
| **"Jarvis, add task [description] by [date]"** | Creates a tracked task |
| **"Jarvis, check my tasks"** | Lists pending/overdue tasks |
| **"Jarvis, search for Python developer jobs"** | Searches LinkedIn/Naukri/Indeed |
| **"Jarvis, send me the job links by email/WhatsApp/both"** | Sends the latest found job links to configured destinations |
| **"Jarvis, open [app name]"** | Opens Windows app |
| **"Jarvis, search [query]"** | Google search |
| **"Jarvis, status"** | Full status report of everything |
| **"Jarvis, [any question]"** | AI chat via Groq |
| **"Jarvis, quit"** | Shuts down |

You can interrupt Jarvis while it is speaking by saying **"Jarvis"** followed by a new command. It stops the current reply, acknowledges you in English (for example, "Yes sir, I hear you"), and handles the new request. Saying only **"Jarvis"** stops the speech and prompts in English: "Yes sir, I'm listening. Tell me what you need." Replies to your command still follow the detected spoken language.

Email checks include unread messages received within the last 30 minutes. WhatsApp checks run immediately after WhatsApp Web logs in and repeat at the configured interval. Spoken updates replace URLs with a short link mention and omit meeting dial-in numbers, IDs, and access codes.

Job links are sent only when you explicitly ask. Configure `JOB_UPDATES_EMAIL` and `JOB_UPDATES_WHATSAPP` in `.env`; WhatsApp must be logged in and the number should be searchable in your WhatsApp contacts/chats.

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

Jarvis sends **Windows toast notifications** and speaks new email, WhatsApp, Instagram, Telegram, calendar, overdue-task, and job updates in the last detected spoken language. Alerts are deduplicated so the same update is not repeatedly announced. Say **"Jarvis, status"** for a spoken summary or ask for any individual update.

## ⚠️ Important Notes

- **WhatsApp/Instagram**: First run opens Chrome — log in manually. Sessions persist after that.
- **Job auto-apply**: Currently searches only. Auto-clicking "Apply" may violate platform ToS.
- **Modules are independent**: If Gmail isn't configured, everything else still works.
- **Keep API keys in `.env`, never in source code.** Rotate the ElevenLabs key shared in chat, then set the replacement in `.env`.
