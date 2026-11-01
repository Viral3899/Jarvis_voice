"""
🤖 JARVIS — Personal AI Background Agent
==========================================
Main orchestrator: runs all modules in background threads,
listens for voice commands, manages the task loop.

Say "Jarvis" to wake, then give a command.

Architecture:
  ┌──────────────────────────────────────────┐
  │              JARVIS MAIN                 │
  │  ┌─────────┐  ┌──────────────────────┐   │
  │  │  Voice   │  │  Background Scheduler│   │
  │  │  Loop    │  │  ┌─ Email check     ││   │
  │  │ (listen) │  │  ├─ WhatsApp check  ││   │
  │  │          │  │  ├─ Instagram check ││   │
  │  └────┬─────┘  │  ├─ Telegram check  ││   │
  │       │        │  ├─ Calendar check  ││   │
  │       ▼        │  ├─ Job search      ││   │
  │  ┌─────────┐   │  └─ Task reminders  ││   │
  │  │  Brain   │   └──────────────────────┘   │
  │  │ (Groq)  │   ┌──────────────────────┐   │
  │  └─────────┘   │  Notifier (toasts)   │   │
  │                └──────────────────────┘   │
  └──────────────────────────────────────────┘
"""

import os
import sys
import time
import threading
import webbrowser
import datetime
import json
import signal

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

console = Console()

# ── Module loading (graceful — each module can fail independently) ───────
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
        self.brain = JarvisBrain()
        self.voice = VoiceEngine()
        self.tasks = TaskManager()
        self.scheduler = BackgroundScheduler()
        self.running = False

        self._last_email_ids = set()
        self._last_wa_messages = {}
        self._last_ig_contacts = set()
        self._last_calendar_events = set()
        self._last_overdue_task_ids = set()
        self._last_job_ids = set()
        self._latest_job_updates = []

    def _load_modules(self):
        console.print("\n[bold cyan]Loading modules...[/bold cyan]")
        load_module("gmail", "modules.email_gmail.GmailModule")
        load_module("calendar", "modules.calendar_mod.CalendarModule")
        load_module("telegram", "modules.telegram_bot.TelegramModule")

        # Browser-based modules start their own driver
        wa = load_module("whatsapp", "modules.whatsapp.WhatsAppModule")
        if wa:
            threading.Thread(
                target=self._start_whatsapp, args=(wa,), daemon=True
            ).start()

        ig = load_module("instagram", "modules.instagram.InstagramModule")
        if ig:
            threading.Thread(target=ig.start, daemon=True).start()

        load_module("jobs", "modules.jobs.JobModule")

    def _start_whatsapp(self, whatsapp):
        """Check unread WhatsApp chats as soon as the Web session logs in."""
        whatsapp.start()
        if whatsapp._logged_in:
            self._check_whatsapp()

    # ── Background check functions ───────────────────────────────────────

    def _say(self, text: str):
        """Speak a natural update in the most recently detected language."""
        text = sanitize_speech_text(text, self.voice.last_language_code)
        spoken_text = self.brain.phrase_for_speech(
            text, self.voice.last_language, self.voice.last_transcript
        )
        spoken_text = sanitize_speech_text(
            spoken_text, self.voice.last_language_code
        )
        self.voice.speak(spoken_text)

    def _acknowledge_wake(self, waiting_for_command=False):
        """Acknowledge the wake word in English without changing reply language."""
        text = (
            "Yes sir, I'm listening. Tell me what you need."
            if waiting_for_command
            else "Yes sir, I hear you."
        )
        self.voice.speak(text, language_code="en")

    def _check_emails(self, announce=True):
        """Background: check Gmail for new mail."""
        mod = modules.get("gmail")
        if mod:
            emails = mod.get_unread(5) if hasattr(mod, "get_unread") else []
            if emails:
                lines = [
                    f"{len(emails)} unread emails from the last 30 minutes:"
                ]
                lines.extend(
                    f"From {email['from']}: {email['subject']}" for email in emails
                )
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
                    {
                        "contact": chat.get("contact", ""),
                        "message": chat.get("last_message", ""),
                    }
                    for chat in chats
                ],
            })
            current_messages = {
                chat["contact"]: chat.get("last_message", "")
                for chat in chats
                if chat.get("contact")
            }
            updates = [
                chat for chat in chats
                if chat.get("contact")
                and self._last_wa_messages.get(chat["contact"])
                != chat.get("last_message", "")
            ]
            if announce and updates:
                details = []
                for chat in updates[:3]:
                    message = " ".join(chat.get("last_message", "").split())[:160]
                    details.append(
                        f"{chat['contact']} said: {message}"
                        if message
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
                self._say(
                    f"You have {len(new_contacts)} new unread Instagram messages "
                    f"from {names}."
                )
            self._last_ig_contacts = contacts

    def _check_telegram(self, announce=True):
        tg = modules.get("telegram")
        if tg:
            msgs = tg.get_new_messages()
            self.brain.update_context("telegram", {
                "new": len(msgs),
                "messages": [
                    {"from": message["from"], "text": message.get("text", "")}
                    for message in msgs
                ],
            })
            if announce and msgs:
                details = [
                    f"{message['from']} said: {message.get('text') or 'sent a message'}"
                    for message in msgs[:3]
                ]
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
                    f"{event.get('start', 'Unknown time')}: "
                    f"{event.get('summary', '(no title)')}"
                    for event in events[:5]
                )
            else:
                summary = "No upcoming events today."
            self.brain.update_context("calendar", {"summary": summary})
            event_keys = {
                (event.get("summary", ""), event.get("start", ""))
                for event in events
            }
            new_events = [
                event for event in events
                if (event.get("summary", ""), event.get("start", ""))
                not in self._last_calendar_events
            ]
            if announce and new_events:
                details = [
                    f"{event.get('summary', 'An event')} at {event.get('start', 'an unknown time')}"
                    + (f", at {event['location']}" if event.get("location") else "")
                    for event in new_events[:3]
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
            titles = ", ".join(
                task["title"] for task in overdue if task["id"] in new_overdue
            )
            notify("Overdue Tasks!", f"{len(new_overdue)} overdue: {titles}")
            self._say(f"You have {len(new_overdue)} overdue tasks: {titles}.")
        self._last_overdue_task_ids = overdue_ids
        self.brain.update_context("tasks", {
            "pending": len(pending),
            "overdue": len(overdue),
            "summary": self.tasks.get_summary(),
        })

    def _search_jobs_background(self):
        """Periodically search for new jobs matching preferences."""
        jobs_mod = modules.get("jobs")
        if jobs_mod:
            new_jobs = []
            for title in jobs_mod.job_titles[:2]:  # Limit to avoid too much scraping
                new_jobs.extend(jobs_mod.search_linkedin(title))
            self.brain.update_context("jobs", {
                "found": len(jobs_mod.found_jobs),
                "recent": jobs_mod.found_jobs[-5:],
            })
            fresh_jobs = []
            for job in new_jobs:
                job_key = (
                    job.get("url")
                    or f"{job.get('title', '')}|{job.get('company', '')}"
                )
                if job_key not in self._last_job_ids:
                    fresh_jobs.append(job)
                    self._last_job_ids.add(job_key)
            if fresh_jobs:
                self._latest_job_updates = fresh_jobs
            if fresh_jobs:
                details = [
                    f"{job.get('title', 'A job')} at {job.get('company', 'an employer')}"
                    for job in fresh_jobs[:3]
                ]
                notify("New Jobs", f"Found {len(fresh_jobs)} new matching jobs")
                self._say(
                    f"I found {len(fresh_jobs)} new matching jobs: "
                    + ". ".join(details)
                )

    # ── Schedule background tasks ────────────────────────────────────────

    def _start_scheduler(self):
        intervals = {
            "email": int(os.getenv("CHECK_EMAIL_INTERVAL", 5)),
            "whatsapp": int(os.getenv("CHECK_WHATSAPP_INTERVAL", 3)),
            "instagram": int(os.getenv("CHECK_INSTAGRAM_INTERVAL", 10)),
            "telegram": int(os.getenv("CHECK_TELEGRAM_INTERVAL", 2)),
            "calendar": int(os.getenv("CHECK_CALENDAR_INTERVAL", 5)),
            "tasks": int(os.getenv("TASK_REMINDER_INTERVAL", 15)),
            "jobs": int(os.getenv("CHECK_JOBS_INTERVAL", 60)),
        }

        self.scheduler.add_job(self._check_emails, "interval", minutes=intervals["email"], id="email")
        self.scheduler.add_job(self._check_whatsapp, "interval", minutes=intervals["whatsapp"], id="whatsapp")
        self.scheduler.add_job(self._check_instagram, "interval", minutes=intervals["instagram"], id="instagram")
        self.scheduler.add_job(self._check_telegram, "interval", minutes=intervals["telegram"], id="telegram")
        self.scheduler.add_job(self._check_calendar, "interval", minutes=intervals["calendar"], id="calendar")
        self.scheduler.add_job(self._check_tasks, "interval", minutes=intervals["tasks"], id="tasks")
        self.scheduler.add_job(self._search_jobs_background, "interval", minutes=intervals["jobs"], id="jobs")

        self.scheduler.start()
        console.print("[bold green]⏰ Background scheduler started![/bold green]")

    # ── Handle voice commands ────────────────────────────────────────────

    def handle_command(self, text: str):
        """Route a voice command to the right handler."""
        normalized_text = text.casefold()
        # Exit
        if normalized_text in (
            "quit", "exit", "goodbye", "bye", "shut down jarvis",
            "stop jarvis",
        ):
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

        if act == "quit":
            self._say("Goodbye. Shutting down now.")
            self.shutdown()

        elif act == "get_status":
            self._give_status_report()

        elif act == "check_email":
            self._check_emails(announce=False)
            gmail = modules.get("gmail")
            reply = gmail.get_summary() if gmail else "Gmail not configured."
            self._say(reply)

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
                    self._say(f"What should I say to {contact}?")
                    msg = self.voice.listen(timeout=10)
                if msg:
                    # Let AI refine the reply
                    refined = self.brain.think(
                        f"Write a natural WhatsApp reply: {msg}",
                        response_language=self.voice.last_language,
                    )
                    ok = wa.send_message(contact, refined)
                    self._say(
                        f"{'Sent' if ok else 'Failed to send'} message to {contact}."
                    )
                else:
                    self._say("I didn't hear a message to send.")
            else:
                self._say("WhatsApp is not connected.")

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
                details = [
                    f"{message['from']} said: {message.get('text') or 'sent a message'}"
                    for message in messages[:5]
                ]
                self._say(
                    f"You have {len(messages)} new Telegram messages. "
                    + " ".join(details)
                )

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
            self._say(
                f"Task added: {task['title']}."
                + (f" Due: {deadline}." if deadline else "")
            )
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
                        self._say(
                            f"{j['title']} at {j['company']}, {j['location']}."
                        )
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
            reply = self.brain.think(
                text, response_language=self.voice.last_language
            )
            self.voice.speak(reply)

    def _send_job_updates(self, channel: str):
        """Send cached job links through the explicitly requested channels."""
        if channel not in {"email", "whatsapp", "both"}:
            self._say("Please choose email, WhatsApp, or both.")
            return

        jobs_mod = modules.get("jobs")
        jobs = self._latest_job_updates or (
            getattr(jobs_mod, "found_jobs", []) if jobs_mod else []
        )

        linked_jobs = [
            job for job in jobs
            if str(job.get("url", "")).startswith(("https://", "http://"))
        ][:10]
        if not linked_jobs:
            self._say("I couldn't find any job links to send yet.")
            return

        lines = ["Here are your latest job links:"]
        for job in linked_jobs:
            lines.append(
                f"{job.get('title', 'Job')} — {job.get('company', 'Company')} "
                f"({job.get('platform', 'Job site')}; "
                f"{job.get('location', 'Location not listed')})\n{job['url']}"
            )
        message = "\n\n".join(lines)
        results = []

        if channel in {"email", "both"}:
            recipient = os.getenv("JOB_UPDATES_EMAIL", "").strip()
            gmail = modules.get("gmail")
            if recipient and gmail:
                sent = gmail.send_email(
                    recipient, "Your latest job links", message
                )
                results.append(f"Email {'sent' if sent else 'could not be sent'}.")
            else:
                results.append(
                    "Email is not configured; set JOB_UPDATES_EMAIL and connect Gmail."
                )

        if channel in {"whatsapp", "both"}:
            recipient = os.getenv("JOB_UPDATES_WHATSAPP", "").strip()
            whatsapp = modules.get("whatsapp")
            if recipient and whatsapp and whatsapp._logged_in:
                sent = whatsapp.send_message(recipient, message)
                results.append(
                    f"WhatsApp message {'sent' if sent else 'could not be sent'}."
                )
            else:
                results.append(
                    "WhatsApp is not ready; set JOB_UPDATES_WHATSAPP and log in."
                )

        self._say(" ".join(results))

    def _give_status_report(self):
        """Full status briefing."""
        self._say("Here's your status report.")
        parts = []

        # Tasks
        parts.append(self.tasks.get_summary())

        # Each module summary
        for name, mod in modules.items():
            if hasattr(mod, "get_summary"):
                try:
                    parts.append(mod.get_summary())
                except Exception:
                    pass

        report = "\n".join(parts)
        console.print(Panel(report, title="📊 Status Report", border_style="cyan"))

        # Speak a condensed version
        summary = self.brain.think(
            f"Summarize this status report in a few natural spoken sentences:\n{report}",
            response_language=self.voice.last_language,
        )
        self.voice.speak(summary)

    # ── Startup & shutdown ───────────────────────────────────────────────

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

        self._load_modules()
        self._start_scheduler()

        # Initial checks
        console.print("\n[bold]Running initial checks...[/bold]")
        threading.Thread(target=self._check_emails, daemon=True).start()
        threading.Thread(target=self._check_calendar, daemon=True).start()
        threading.Thread(target=self._check_tasks, daemon=True).start()

        console.print("\n[bold green]✅ Jarvis is online![/bold green]")
        console.print("[dim]Say 'Jarvis' followed by a command, or 'Jarvis' then wait for prompt.[/dim]")
        console.print("[dim]Say 'status' for a full report, 'quit' to exit.[/dim]\n")

        self.voice.speak("I'm ready whenever you need me.")

        self.running = True
        self._voice_loop()

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
        self.running = False
        self.scheduler.shutdown(wait=False)

        for name, mod in modules.items():
            if hasattr(mod, "stop"):
                try:
                    mod.stop()
                except Exception:
                    pass

        console.print("[bold cyan]👋 Jarvis offline.[/bold cyan]")
        sys.exit(0)


if __name__ == "__main__":
    jarvis = Jarvis()
    signal.signal(signal.SIGINT, lambda *_: jarvis.shutdown())
    jarvis.start()
