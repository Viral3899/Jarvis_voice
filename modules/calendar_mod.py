"""
Google Calendar module — check upcoming events, get reminders.
Uses Google Calendar API with OAuth2.

Setup: Same Google Cloud project as Gmail.
Enable Google Calendar API in the console.
"""

import os
import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDS_FILE = Path(__file__).parent.parent / "config" / "gmail_credentials.json"
TOKEN_FILE = Path(__file__).parent.parent / "config" / "calendar_token.json"


class CalendarModule:
    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDS_FILE.exists():
                    print("⚠ Calendar: Place gmail_credentials.json in config/")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

        self.service = build("calendar", "v3", credentials=creds)

    def get_upcoming_events(self, max_results: int = 10) -> list[dict]:
        """Get upcoming calendar events."""
        if not self.service:
            return []

        try:
            now = datetime.datetime.utcnow().isoformat() + "Z"
            end = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + "Z"

            result = self.service.events().list(
                calendarId="primary",
                timeMin=now,
                timeMax=end,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = []
            for event in result.get("items", []):
                start = event["start"].get("dateTime", event["start"].get("date"))
                events.append({
                    "summary": event.get("summary", "(no title)"),
                    "start": start,
                    "location": event.get("location", ""),
                    "description": event.get("description", "")[:100],
                })
            return events
        except Exception as e:
            print(f"⚠ Calendar error: {e}")
            return []

    def get_summary(self) -> str:
        events = self.get_upcoming_events(5)
        if not events:
            return "📅 No upcoming events today."
        lines = [f"📅 {len(events)} upcoming events:"]
        for e in events:
            lines.append(f"  • {e['start']}: {e['summary']}")
            if e["location"]:
                lines.append(f"    📍 {e['location']}")
        return "\n".join(lines)
