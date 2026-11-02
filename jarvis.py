"""
🤖 JARVIS — Personal AI Background Agent
==========================================
Main orchestrator: runs all modules in background threads,
listens for voice commands, manages the task loop.

Say "Jarvis" to wake, then give a command.

Architecture:
  ┌────────────────────────────────────────────────────────────┐
  │                      JARVIS MAIN                           │
  │  ┌─────────────┐  ┌────────────────────────────────────┐  │
  │  │  Voice Loop │  │  Background Scheduler              │  │
  │  │  (listen)   │  │  ┌─ Email check                   │  │
  │  └──────┬──────┘  │  ├─ WhatsApp check                │  │
  │         │         │  ├─ Instagram check               │  │
  │         ▼         │  ├─ Telegram check                │  │
  │  ┌─────────────┐  │  ├─ Calendar check                │  │
  │  │  Brain      │  │  ├─ Job search                    │  │
  │  │  (Groq)     │  │  ├─ Task reminders                │  │
  │  └─────────────┘  │  └─ Daily Briefings               │  │
  │  ┌─────────────┐  └────────────────────────────────────┘  │
  │  │  Plugin Mgr │  ┌────────────────────────────────────┐  │
  │  │  (modules)  │  │  Notifier (toasts)                 │  │
  │  └─────────────┘  └────────────────────────────────────┘  │
  │  ┌─────────────┐  ┌────────────────────────────────────┐  │
  │  │  API Server │  │  Health Monitor                    │  │
  │  │  (REST)     │  │  (auto-recovery)                   │  │
  │  └─────────────┘  └────────────────────────────────────┘  │
  └────────────────────────────────────────────────────────────┘
"""

import os
import sys
import time
import threading
import webbrowser
import datetime
import json
import signal
import atexit
import tempfile

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from apscheduler.schedulers.background import BackgroundScheduler

from core.brain import JarvisBrain
from core.voice import VoiceEngine, sanitize_speech_text
from core.tasks import TaskManager
from core.notifier import notify
from core.config import config, JarvisConfig
from core.api import start_api_server
from core.briefing import create_briefing_manager
from core.plugins import plugin_manager
from core.recovery import HealthMonitor, safe_execute
from core.autostart import AutoStartManager

console = Console()

# ── Global module registry (backward compatible) ───────────────────────────
modules = {}


def load_module(name, cls_path):
    """Import and instantiate a module; skip on failure."""
    try:
        parts = cls_path.rsplit(".", 1)
        mod = __import__(parts[0], fromlist=[parts[1]])
        cls = getattr(mod, parts[1])
        instance = cls()
        modules[name] = instance
        console.print(f"  ✅ {name}")
        return instance
    except Exception as e:
        console.print(f"  ⚠️  {name}: {e}", style="yellow")
        return None


APP_ALIASES = {
    "notepad": "notepad.exe", "calculator": "calc.exe",
    "paint": "mspaint.exe", "explorer": "explorer.exe",
    "terminal": "wt.exe", "command prompt": "cmd.exe",
    "task manager": "taskmgr.exe", "settings": "ms-settings:",
    "vscode": "code", "vs code": "code", "browser": "start https://www.google.com",
}


class Jarvis:
    def __init__(self):
        # Load configuration first
        self.cfg: JarvisConfig = config.get()
        
        # Core components
        self.brain = JarvisBrain()
        self.voice = VoiceEngine()
        self.tasks = TaskManager()
        self.scheduler = BackgroundScheduler()
        self.running = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_started = False
        self._start_time = time.time()
        
        # State tracking for deduplication
        self._last_email_ids = set()
        self._last_wa_messages = {}
        self._last_ig_contacts = set()
        self._last_calendar_events = set()
        self._last_overdue_task_ids = set()
        self._last_job_ids = set()
        self._latest_job_updates = []
        
        # New managers
        self.api_thread = None
        self.briefing_manager = None
        self.health_monitor = None
        self.autostart_manager = AutoStartManager()
        
        # Setup plugin manager
        plugin_manager.set_jarvis(self)
        plugin_manager.add_plugin_dir(self.autostart_manager.project_root / "plugins")

    def _load_modules(self):
        """Load all modules (legacy + plugins)."""
        console.print("\n[bold cyan]Loading modules...[/bold cyan]")
        
        # Legacy modules
        load_module("gmail", "modules.email_gmail.GmailModule")
        load_module("calendar", "modules.calendar_mod.CalendarModule")
        load_module("telegram", "modules.telegram_bot.TelegramModule")

        # Browser-based modules
        wa = load_module("whatsapp", "modules.whatsapp.WhatsAppModule")
        if wa:
            threading.Thread(target=self._start_whatsapp, args=(wa,), daemon=True).start()

        ig = load_module("instagram", "modules.instagram.InstagramModule")
        if ig:
            threading.Thread(target=ig.start, daemon=True).start()

        load_module("jobs", "modules.jobs.JobModule")
        
        # Load plugins
        plugin_manager.load_all()
        plugin_manager.start_all()

    def _start_whatsapp(self, whatsapp):
        """Check unread WhatsApp chats as soon as the Web session logs in."""
        whatsapp.start()
        if whatsapp._logged_in:
            self._check_whatsapp()

    # ── Background check functions ───────────────────────────────────────────

    def _say(self, text: str):
        """Speak a natural update in the most recently detected language."""
        text = sanitize_speech_text(text, self.voice.last_language_code)
        spoken_text = self.brain.phrase_for_speech(
            text, self.voice.last_language, self.voice.last_transcript
        )
        spoken_text = sanitize_speech_text(spoken_text, self.voice.last_language_code)
        self.voice.speak(spoken_text)

    def _acknowledge_wake(self, waiting_for_command=False):
        """Acknowledge the wake word in English without changing reply language."""
        text = (
            "Yes sir, I'm listening. Tell me what you need."
            if waiting_for_command
            else "Yes sir, I hear you."
        )
        self.voice.speak(text, language_code="en", prefer_local=True)

    def _check_emails(self, announce=True):
        """Background: check Gmail for new mail."""
        mod = modules.get("gmail")
        if mod:
            emails = mod.get_unread(5) if hasattr(mod, "get_unread") else []
            if emails:
                lines = [f"{len(emails)} unread emails from the last 30 minutes:"]
                lines.extend(f"From {email['from']}: {email['subject']}" for email in emails)
                summary = "\n".join(lines)
            else:
                summary = "No unread emails from the last 30 minutes."
            self.brain.update_context("gmail", {"summary": summary})
            email_ids = {email["id"] for email in emails if email.get("id")}
            new_email_ids = email_ids - self._last_email_ids
            if announce and new_email_ids:
                notify("New Email", summary)
                self._say(summary)
            self._last_email_ids = email_ids

    def _check_whatsapp(self, announce=True):
        wa = modules.get("whatsapp")
        if wa and wa.refresh_login_status():
            chats = wa.get_unread_chats()
            self.brain.update_context("whatsapp", {
                "unread": len(chats),
                "messages": [
                    {"contact": chat.get("contact", ""), "message": chat.get("last_message", "")}
                    for chat in chats
                ],
            })
            current_messages = {
                chat["contact"]: chat.get("last_message", "")
                for chat in chats if chat.get("contact")
            }
            updates = [
                chat for chat in chats
                if chat.get("contact")
                and self._last_wa_messages.get(chat["contact"]) != chat.get("last_message", "")
            ]
            if announce and updates:
                details = []
                for chat in updates[:3]:
                    message = " ".join(chat.get("last_message", "").split())[:160]
                    details.append(
                        f"{chat['contact']} said: {message}" if message
                        else f"There is an unread message from {chat['contact']}."
                    )
                notify("WhatsApp", f"{len(updates)} new unread messages")
                self._say("New WhatsApp messages: " + " ".join(details))
            self._last_wa_messages = current_messages

    def _check_instagram(self, announce=True):
        ig = modules.get("instagram")
        if ig and ig._logged_in:
            dms = ig.get_unread_dms()
            self.brain.update_context("instagram", {"unread": len(dms)})
            contacts = {dm["contact"] for dm in dms if dm.get("contact")}
            new_contacts = contacts - self._last_ig_contacts
            if announce and new_contacts:
                names = ", ".join(sorted(new_contacts))
                notify("Instagram", f"{len(new_contacts)} new unread DMs: {names}")
                self._say(f"You have {len(new_contacts)} new unread Instagram messages from {names}.")
            self._last_ig_contacts = contacts

    def _check_telegram(self, announce=True):
        tg = modules.get("telegram")
        if tg:
            msgs = tg.get_new_messages()
            self.brain.update_context("telegram", {
                "new": len(msgs),
                "messages": [{"from": m["from"], "text": m.get("text", "")} for m in msgs],
            })
            if announce and msgs:
                details = [f"{m['from']} said: {m.get('text') or 'sent a message'}" for m in msgs[:3]]
                notify("Telegram", f"{len(msgs)} new messages")
                self._say("New Telegram messages: " + " ".join(details))
            return msgs
        return []

    def _check_calendar(self, announce=True):
        cal = modules.get("calendar")
        if cal:
            events = cal.get_upcoming_events()
            if events:
                summary = "\n".join(
                    f"{event.get('start', 'Unknown time')}: {event.get('summary', '(no title)')}"
                    for event in events[:5]
                )
            else:
                summary = "No upcoming events today."
            self.brain.update_context("calendar", {"summary": summary})
            event_keys = {(e.get("summary", ""), e.get("start", "")) for e in events}
            new_events = [e for e in events if (e.get("summary", ""), e.get("start", "")) not in self._last_calendar_events]
            if announce and new_events:
                details = [
                    f"{e.get('summary', 'An event')} at {e.get('start', 'an unknown time')}"
                    + (f", at {e['location']}" if e.get("location") else "")
                    for e in new_events[:3]
                ]
                notify("Calendar update", f"{len(new_events)} new upcoming events")
                self._say("You have new calendar events: " + ". ".join(details))
            self._last_calendar_events = event_keys

    def _check_tasks(self, announce=True):
        """Remind about overdue/pending tasks."""
        overdue = self.tasks.get_overdue()
        pending = self.tasks.get_pending()
        overdue_ids = {task["id"] for task in overdue}
        new_overdue = overdue_ids - self._last_overdue_task_ids
        if announce and new_overdue:
            titles = ", ".join(task["title"] for task in overdue if task["id"] in new_overdue)
            notify("Overdue Tasks!", f"{len(new_overdue)} overdue: {titles}")
            self._say(f"You have {len(new_overdue)} overdue tasks: {titles}.")
        self._last_overdue_task_ids = overdue_ids
        self.brain.update_context("tasks", {
            "pending": len(pending), "overdue": len(overdue), "summary": self.tasks.get_summary(),
        })

    def _search_jobs_background(self):
        """Periodically search for new jobs matching preferences."""
        jobs_mod = modules.get("jobs")
        if jobs_mod:
            new_jobs = []
            for title in jobs_mod.job_titles[:2]:
                new_jobs.extend(jobs_mod.search_linkedin(title))
            self.brain.update_context("jobs", {
                "found": len(jobs_mod.found_jobs), "recent": jobs_mod.found_jobs[-5:],
            })
            fresh_jobs = []
            for job in new_jobs:
                job_key = job.get("url") or f"{job.get('title', '')}|{job.get('company', '')}"
                if job_key not in self._last_job_ids:
                    fresh_jobs.append(job)
                    self._last_job_ids.add(job_key)
            if fresh_jobs:
                self._latest_job_updates = fresh_jobs
            if fresh_jobs:
                details = [f"{j.get('title', 'A job')} at {j.get('company', 'an employer')}" for j in fresh_jobs[:3]]
                notify("New Jobs", f"Found {len(fresh_jobs)} new matching jobs")
                self._say(f"I found {len(fresh_jobs)} new matching jobs: " + ". ".join(details))

    # ── Schedule background tasks ────────────────────────────────────────────

    def _start_scheduler(self):
        intervals = self.cfg.scheduler.intervals
        
        self.scheduler.add_job(self._check_emails, "interval", minutes=intervals["email"], id="email")
        self.scheduler.add_job(self._check_whatsapp, "interval", minutes=intervals["whatsapp"], id="whatsapp")
        self.scheduler.add_job(self._check_instagram, "interval", minutes=intervals["instagram"], id="instagram")
        self.scheduler.add_job(self._check_telegram, "interval", minutes=intervals["telegram"], id="telegram")
        self.scheduler.add_job(self._check_calendar, "interval", minutes=intervals["calendar"], id="calendar")
        self.scheduler.add_job(self._check_tasks, "interval", minutes=intervals["tasks"], id="tasks")
        self.scheduler.add_job(self._search_jobs_background, "interval", minutes=intervals["jobs"], id="jobs")
        
        self.scheduler.start()
        console.print("[bold green]⏰ Background scheduler started![/bold green]")

    # ── Handle voice commands ────────────────────────────────────────────────

    def handle_command(self, text: str):
        """Route a voice command to the right handler."""
        normalized_text = text.casefold()
        
        # Exit
        if normalized_text in ("quit", "exit", "goodbye", "bye", "shut down jarvis", "stop jarvis"):
            self._say("Goodbye. Shutting down now.")
            self.shutdown()
            return
        if normalized_text in ("stop", "stop speaking", "quiet"):
            return

        # Status report
        if any(w in normalized_text for w in ("status", "report", "what's going on", "update me", "briefing")):
            self._give_status_report()
            return

        # Let the brain classify the action
        action = self.brain.decide_action(text)
        act = action.get("action", "general_chat")

        # Try plugins first
        if plugin_manager.handle_command(text, action):
            return

        if act == "quit":
            self._say("Goodbye. Shutting down now.")
            self.shutdown()

        elif act == "get_status":
            self._give_status_report()

        elif act == "check_email":
            self._check_emails(announce=False)
            gmail = modules.get("gmail")
            self._say(gmail.get_summary() if gmail else "Gmail not configured.")

        elif act == "check_whatsapp":
            self._check_whatsapp(announce=False)
            wa = modules.get("whatsapp")
            self._say(wa.get_summary() if wa else "WhatsApp not connected.")

        elif act == "reply_whatsapp":
            wa = modules.get("whatsapp")
            if wa:
                contact = action.get("contact", "")
                msg = action.get("message", "")
                if not msg:
                    self._send_message_flow("whatsapp", contact)
                else:
                    self._send_message_flow("whatsapp", contact, msg)
            else:
                self._say("WhatsApp is not connected.")

        elif act in {"send_message", "send_whatsapp", "send_email"}:
            channel = action.get("channel")
            if act == "send_whatsapp":
                channel = "whatsapp"
            elif act == "send_email":
                channel = "email"
            if channel not in {"email", "whatsapp"}:
                self._say("Would you like to send this by WhatsApp or email?")
                channel = self.voice.listen(timeout=10, phrase_limit=8)
                channel = (channel or "").strip().casefold()
                if "whatsapp" in channel:
                    channel = "whatsapp"
                elif "email" in channel or "mail" in channel:
                    channel = "email"
                else:
                    self._say("I couldn't determine the sending method.")
                    return
            self._send_message_flow(
                channel,
                action.get("contact") or action.get("recipient", ""),
                action.get("message", ""),
                action.get("subject", ""),
            )

        elif act == "check_instagram":
            self._check_instagram(announce=False)
            ig = modules.get("instagram")
            self._say(ig.get_summary() if ig else "Instagram not connected.")

        elif act == "reply_instagram":
            ig = modules.get("instagram")
            if ig:
                contact = action.get("contact", "")
                msg = action.get("message", "")
                if not msg:
                    self._say(f"What should I reply to {contact}?")
                    msg = self.voice.listen(timeout=10)
                if msg:
                    refined = self.brain.think(
                        f"Write a natural Instagram DM reply: {msg}",
                        response_language=self.voice.last_language,
                    )
                    ok = ig.send_dm(contact, refined)
                    self._say(f"{'Sent' if ok else 'Failed'} DM to {contact}.")
                else:
                    self._say("I didn't hear a message to send.")
            else:
                self._say("Instagram is not connected.")

        elif act == "reply_telegram":
            tg = modules.get("telegram")
            if tg:
                msg = action.get("message", "")
                if msg:
                    ok = tg.send_message(msg)
                    self._say(f"{'Sent' if ok else 'Failed'} Telegram message.")
                else:
                    self._say("I didn't hear a message to send.")
            else:
                self._say("Telegram is not connected.")

        elif act == "check_telegram":
            messages = self._check_telegram(announce=False)
            if not messages:
                self._say("There are no new Telegram messages.")
            else:
                details = [f"{m['from']} said: {m.get('text') or 'sent a message'}" for m in messages[:5]]
                self._say(f"You have {len(messages)} new Telegram messages. " + " ".join(details))

        elif act == "check_calendar":
            self._check_calendar(announce=False)
            cal = modules.get("calendar")
            self._say(cal.get_summary() if cal else "Calendar not configured.")

        elif act == "check_tasks":
            self._say(self.tasks.get_summary())

        elif act == "add_task":
            title = action.get("title", text)
            deadline = action.get("deadline")
            task = self.tasks.add_task(title, deadline)
            self._say(f"Task added: {task['title']}." + (f" Due: {deadline}." if deadline else ""))
            notify("Task Added", task["title"])

        elif act == "search_jobs":
            query = action.get("query", "")
            self._say(f"Searching for {query or 'your preferred'} jobs...")
            jobs_mod = modules.get("jobs")
            if jobs_mod:
                jobs = jobs_mod.search_all(query)
                if jobs:
                    self._latest_job_updates = jobs
                    self._say(f"Found {len(jobs)} jobs. Here are the top ones:")
                    for j in jobs[:3]:
                        self._say(f"{j['title']} at {j['company']}, {j['location']}.")
                else:
                    self._say("No matching jobs found right now.")
            else:
                self._say("The job search module is not available.")

        elif act == "send_job_updates":
            channel = str(action.get("channel", "both")).strip().lower()
            self._send_job_updates(channel)

        elif act == "open_app":
            app = action.get("app", "").lower()
            if app in APP_ALIASES:
                os.startfile(APP_ALIASES[app])
                self._say(f"Opening {app}.")
            else:
                os.system(f'start "" "search-ms:query={app}"')
                self._say(f"Searching for {app}.")

        elif act == "search_web":
            query = action.get("query", text)
            webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            self._say(f"Searching for {query}.")

        else:
            # General AI chat
            reply = self.brain.think(text, response_language=self.voice.last_language)
            self.voice.speak(reply)

    def _send_message_flow(
        self,
        channel: str,
        recipient: str = "",
        message: str = "",
        subject: str = "",
    ):
        """Collect missing message details, then confirm before sending."""
        channel = channel.strip().casefold()
        sender = modules.get("whatsapp" if channel == "whatsapp" else "gmail")
        if not sender:
            self._say(f"{channel.capitalize()} is not connected.")
            return

        if channel == "whatsapp" and not sender._logged_in:
            self._say("WhatsApp is not connected. Please log in first.")
            return
        if channel == "email" and not sender.service:
            self._say("Gmail is not connected. Please finish Gmail setup first.")
            return

        if not recipient:
            prompt = (
                "Who should I send it to? Say a WhatsApp contact name or phone "
                "number with country code."
                if channel == "whatsapp"
                else "What email address should I send it to?"
            )
            self._say(prompt)
            recipient = self.voice.listen(timeout=15, phrase_limit=20) or ""
        recipient = recipient.strip()
        if channel == "email":
            recipient = (
                recipient.replace(" at ", "@")
                .replace(" dot ", ".")
                .replace(" ", "")
            )
        if not recipient:
            self._say("I didn't get a recipient, so I cancelled.")
            return

        attachment_path = None
        temporary_audio_path = None
        body = message.strip()
        try:
            if not body:
                self._say(
                    "What should I send: a text message, a photo, or a voice recording?"
                )
                content_type = (
                    self.voice.listen(timeout=10, phrase_limit=10) or ""
                ).casefold()
                if any(word in content_type for word in ("photo", "image", "picture")):
                    attachment_path = self._choose_media_file("photo")
                    if not attachment_path:
                        self._say("No photo was selected. I cancelled.")
                        return
                    self._say("Would you like to add a caption? Say it now, or say none.")
                    body = self.voice.listen(timeout=8, phrase_limit=20) or ""
                    if body.strip().casefold() in {"none", "no", "skip"}:
                        body = ""
                elif any(
                    word in content_type
                    for word in ("voice", "audio", "recording", "record")
                ):
                    self._say("Please speak after the beep. I will record up to 30 seconds.")
                    audio_data = self.voice.record_audio(timeout=8, phrase_limit=30)
                    if not audio_data:
                        self._say("I couldn't record audio, so I cancelled.")
                        return
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as audio_file:
                        audio_file.write(audio_data)
                        temporary_audio_path = audio_file.name
                    attachment_path = temporary_audio_path
                    self._say("Would you like to add a caption? Say it now, or say none.")
                    body = self.voice.listen(timeout=8, phrase_limit=20) or ""
                    if body.strip().casefold() in {"none", "no", "skip"}:
                        body = ""
                else:
                    self._say("What message should I send?")
                    body = self.voice.listen(timeout=10, phrase_limit=30) or ""
                    if not body.strip():
                        self._say("I didn't hear a message, so I cancelled.")
                        return

            if channel == "email" and not subject:
                self._say("What should the email subject be?")
                subject = self.voice.listen(timeout=10, phrase_limit=15) or ""
                subject = subject.strip() or "Message from Jarvis"

            self._say(
                f"Ready to send to {recipient}. Say yes to send, or no to cancel."
            )
            confirmation = (
                self.voice.listen(timeout=8, phrase_limit=5) or ""
            ).strip().casefold()
            affirmative = (
                confirmation.split(maxsplit=1)[0].strip(".,!?;:")
                if confirmation
                else ""
            )
            if affirmative not in {
                "yes", "yeah", "yep", "send", "confirm",
                "હા", "હાં", "हाँ", "जी",
            }:
                self._say("Cancelled. Nothing was sent.")
                return

            if channel == "whatsapp":
                if attachment_path:
                    sent = sender.send_media(recipient, attachment_path, body)
                else:
                    sent = sender.send_message(recipient, body)
            else:
                sent = sender.send_email(
                    recipient, subject, body, attachment_path=attachment_path
                )
            self._say(
                f"{'Sent' if sent else 'Failed to send'} "
                f"{'WhatsApp message' if channel == 'whatsapp' else 'email'} "
                f"to {recipient}."
            )
        finally:
            if temporary_audio_path:
                try:
                    os.unlink(temporary_audio_path)
                except OSError as e:
                    console.print(f"[yellow]Could not remove temporary audio: {e}[/yellow]")

    def _choose_media_file(self, media_type: str) -> str:
        """Open a file picker for an image to attach to an outgoing message."""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            try:
                root.withdraw()
                root.attributes("-topmost", True)
                return filedialog.askopenfilename(
                    title="Choose a photo to send",
                    filetypes=[
                        ("Image files", "*.jpg *.jpeg *.png *.gif *.webp *.bmp"),
                        ("All files", "*.*"),
                    ],
                )
            finally:
                root.destroy()
        except Exception as e:
            console.print(f"[yellow]Could not open the {media_type} picker: {e}[/yellow]")
            return ""

    def _send_job_updates(self, channel: str):
        """Send cached job links through the explicitly requested channels."""
        if channel not in {"email", "whatsapp", "both"}:
            self._say("Please choose email, WhatsApp, or both.")
            return

        jobs_mod = modules.get("jobs")
        jobs = self._latest_job_updates or (getattr(jobs_mod, "found_jobs", []) if jobs_mod else [])

        linked_jobs = [j for j in jobs if str(j.get("url", "")).startswith(("https://", "http://"))][:10]
        if not linked_jobs:
            self._say("I couldn't find any job links to send yet.")
            return

        lines = ["Here are your latest job links:"]
        for job in linked_jobs:
            lines.append(
                f"{job.get('title', 'Job')} — {job.get('company', 'Company')} "
                f"({job.get('platform', 'Job site')}; {job.get('location', 'Location not listed')})\n{job['url']}"
            )
        message = "\n\n".join(lines)
        results = []

        if channel in {"email", "both"}:
            recipient = os.getenv("JOB_UPDATES_EMAIL", "").strip()
            gmail = modules.get("gmail")
            if recipient and gmail:
                sent = gmail.send_email(recipient, "Your latest job links", message)
                results.append(f"Email {'sent' if sent else 'could not be sent'}.")
            else:
                results.append("Email is not configured; set JOB_UPDATES_EMAIL and connect Gmail.")

        if channel in {"whatsapp", "both"}:
            recipient = os.getenv("JOB_UPDATES_WHATSAPP", "").strip()
            whatsapp = modules.get("whatsapp")
            if recipient and whatsapp and whatsapp._logged_in:
                sent = whatsapp.send_message(recipient, message)
                results.append(f"WhatsApp message {'sent' if sent else 'could not be sent'}.")
            else:
                results.append("WhatsApp is not ready; set JOB_UPDATES_WHATSAPP and log in.")

        self._say(" ".join(results))

    def _give_status_report(self):
        """Full status briefing."""
        self._say("Here's your status report.")
        parts = [self.tasks.get_summary()]
        
        for name, mod in modules.items():
            if hasattr(mod, "get_summary"):
                try:
                    parts.append(mod.get_summary())
                except Exception:
                    pass
        
        for plugin in plugin_manager.plugins.values():
            try:
                parts.append(plugin.get_summary())
            except Exception:
                pass

        report = "\n".join(parts)
        console.print(Panel(report, title="📊 Status Report", border_style="cyan"))

        # Speak condensed version
        summary = self.brain.think(
            f"Summarize this status report in a few natural spoken sentences:\n{report}",
            response_language=self.voice.last_language,
        )
        self.voice.speak(summary)

    # ── Startup & shutdown ───────────────────────────────────────────────────

    def start(self):
        """Boot Jarvis."""
        key = os.getenv("GROQ_API_KEY", "")
        if not key or key == "your_groq_api_key_here":
            console.print("[bold red]❌ Set GROQ_API_KEY in .env first![/bold red]")
            console.print("   Get a free key at https://console.groq.com")
            sys.exit(1)

        console.print(Panel(
            "[bold cyan]🤖 J.A.R.V.I.S.[/bold cyan]\n"
            "Just A Rather Very Intelligent System\n"
            "Personal AI Background Agent",
            border_style="cyan",
        ))

        # Load modules
        self._load_modules()
        
        # Start scheduler
        self._start_scheduler()
        
        # Start health monitor
        self.health_monitor = HealthMonitor(self)
        self._register_health_checks()
        self.health_monitor.start()
        
        # Start briefing manager
        self.briefing_manager = create_briefing_manager(self)
        self.briefing_manager.start()
        
        # Start API server
        self.api_thread = start_api_server(self, self.voice, self.brain, self.tasks)
        
        # Initial checks
        console.print("\n[bold]Running initial checks...[/bold]")
        threading.Thread(target=self._check_emails, daemon=True).start()
        threading.Thread(target=self._check_calendar, daemon=True).start()
        threading.Thread(target=self._check_tasks, daemon=True).start()

        # Auto-start setup if configured
        if self.cfg.auto_start.enabled and not self.autostart_manager.is_enabled(self.cfg.auto_start.method):
            console.print(f"[yellow]Auto-start enabled in config but not set up. Run 'python -m core.autostart' to configure.[/yellow]")

        console.print("\n[bold green]✅ Jarvis is online![/bold green]")
        console.print("[dim]Say 'Jarvis' followed by a command, or 'Jarvis' then wait for prompt.[/dim]")
        console.print("[dim]Say 'status' for a full report, 'quit' to exit.[/dim]\n")

        self.voice.speak("I'm ready whenever you need me.")
        
        self.running = True
        self._voice_loop()

    def _register_health_checks(self):
        """Register components for health monitoring."""
        checks = {
            "email": lambda: self._check_emails(announce=False),
            "whatsapp": lambda: self._check_whatsapp(announce=False),
            "instagram": lambda: self._check_instagram(announce=False),
            "telegram": lambda: self._check_telegram(announce=False),
            "calendar": lambda: self._check_calendar(announce=False),
            "tasks": lambda: self._check_tasks(announce=False),
            "jobs": self._search_jobs_background,
        }
        
        for name, check_func in checks.items():
            # Only register if module is loaded
            if name in modules and modules[name]:
                self.health_monitor.register_component(
                    name, 
                    check_func,
                    recovery_func=lambda n=name: self._recover_module(n)
                )

    def _recover_module(self, name: str):
        """Attempt to recover a failed module."""
        console.print(f"[yellow]🔄 Attempting recovery for {name}...[/yellow]")
        try:
            if name == "whatsapp":
                wa = modules.get("whatsapp")
                if wa:
                    wa.start()
            elif name == "instagram":
                ig = modules.get("instagram")
                if ig:
                    ig.start()
            # Other modules typically don't need explicit recovery
            console.print(f"[green]✅ Recovery attempted for {name}[/green]")
        except Exception as e:
            console.print(f"[red]❌ Recovery failed for {name}: {e}[/red]")

    def _voice_loop(self):
        """Listen for commands, including requests that interrupt Jarvis speaking."""
        while self.running:
            try:
                command = self.voice.consume_interrupted_command()
                if command is None:
                    command = self.voice.wait_for_wake_word()
                acknowledged = command == ""
                if command == "":
                    self._acknowledge_wake(waiting_for_command=True)
                    command = self.voice.listen(timeout=8, phrase_limit=20)
                if command and not acknowledged:
                    self._acknowledge_wake()
                if command:
                    self.handle_command(command)
            except KeyboardInterrupt:
                self.shutdown()
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                try:
                    self._say("Sorry, I couldn't complete that request.")
                except Exception as speech_error:
                    console.print(f"[red]Voice response error: {speech_error}[/red]")

    def shutdown(self):
        """Clean shutdown."""
        with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True

        console.print("[yellow]🛑 Shutting down...[/yellow]")
        self.running = False
        
        # Stop health monitor
        if self.health_monitor:
            self.health_monitor.stop()
        
        # Stop briefing manager
        if self.briefing_manager:
            self.briefing_manager.stop()
        
        # Stop scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        
        # Stop plugins
        plugin_manager.stop_all()
        
        # Stop modules
        for name, mod in modules.items():
            if hasattr(mod, "stop"):
                try:
                    mod.stop()
                except Exception:
                    pass
        console.print("[bold cyan]👋 Jarvis offline.[/bold cyan]")
        console.print("[bold cyan]👋 Jarvis offline.[/bold cyan]")


def setup_autostart():
    """CLI command to set up auto-start."""
    manager = AutoStartManager()
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS Auto-Start Setup")
    parser.add_argument("--enable", action="store_true", help="Enable auto-start")
    parser.add_argument("--disable", action="store_true", help="Disable auto-start")
    parser.add_argument("--method", choices=["task_scheduler", "startup_folder", "registry"], 
                       default="task_scheduler", help="Auto-start method")
    parser.add_argument("--admin", action="store_true", help="Run as admin (Task Scheduler only)")
    args = parser.parse_args()
    
    if args.enable:
        manager.enable(args.method, args.admin)
    elif args.disable:
        manager.disable(args.method)
    else:
        parser.print_help()


if __name__ == "__main__":
    # Check for auto-start CLI command
    if len(sys.argv) > 1 and sys.argv[1] == "autostart":
        sys.argv.pop(1)
        setup_autostart()
        sys.exit(0)
    
    jarvis = Jarvis()
    signal.signal(signal.SIGINT, lambda *_: jarvis.shutdown())
    signal.signal(signal.SIGTERM, lambda *_: jarvis.shutdown())
    atexit.register(jarvis.shutdown)
    jarvis.start()