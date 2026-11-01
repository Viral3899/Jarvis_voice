"""
Gmail module — check inbox, read emails, send replies.
Uses Google API with OAuth2.

Setup:
1. Go to https://console.cloud.google.com
2. Create project → Enable Gmail API
3. Create OAuth2 credentials (Desktop app)
4. Download as config/gmail_credentials.json
5. First run will open browser for auth
"""

import os
import base64
import json
import time
from pathlib import Path
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
CREDS_FILE = Path(__file__).parent.parent / "config" / "gmail_credentials.json"
TOKEN_FILE = Path(__file__).parent.parent / "config" / "gmail_token.json"


class GmailModule:
    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None
        if TOKEN_FILE.exists():
            # Load the scopes actually granted in the saved token so newly
            # requested permissions trigger OAuth consent instead of appearing present.
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))

        if creds and creds.expired and creds.refresh_token and creds.has_scopes(SCOPES):
            creds.refresh(Request())

        if not creds or not creds.valid or not creds.has_scopes(SCOPES):
            if not CREDS_FILE.exists():
                print("⚠ Gmail: Place gmail_credentials.json in config/ folder")
                print("  Get it from https://console.cloud.google.com")
                return
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            if not creds.has_scopes(SCOPES):
                raise RuntimeError(
                    "Gmail authorization must include read/modify and send permissions."
                )

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        self.service = build("gmail", "v1", credentials=creds)

    def get_unread(self, max_results: int = 10) -> list[dict]:
        """Get unread emails received within the last 30 minutes."""
        if not self.service:
            return []

        try:
            received_after = int(time.time()) - 30 * 60
            results = self.service.users().messages().list(
                userId="me",
                q=f"is:unread after:{received_after}",
                maxResults=max_results,
            ).execute()

            messages = results.get("messages", [])
            emails = []
            for msg in messages:
                detail = self.service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()

                headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
                emails.append({
                    "id": msg["id"],
                    "from": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date": headers.get("Date", ""),
                    "snippet": detail.get("snippet", ""),
                })
            return emails
        except Exception as e:
            print(f"⚠ Gmail error: {e}")
            return []

    def send_reply(self, message_id: str, reply_text: str) -> bool:
        """Reply to an email."""
        if not self.service:
            return False

        try:
            original = self.service.users().messages().get(
                userId="me", id=message_id, format="metadata",
                metadataHeaders=["From", "Subject", "Message-ID"]
            ).execute()

            headers = {h["name"]: h["value"] for h in original["payload"]["headers"]}
            msg = MIMEText(reply_text)
            msg["to"] = headers.get("From", "")
            msg["subject"] = "Re: " + headers.get("Subject", "")
            msg["In-Reply-To"] = headers.get("Message-ID", "")

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": original["threadId"]}
            ).execute()
            return True
        except Exception as e:
            print(f"⚠ Gmail reply error: {e}")
            return False

    def send_email(self, recipient: str, subject: str, body: str) -> bool:
        """Send a plain-text email."""
        if not self.service:
            return False

        try:
            msg = MIMEText(body, _charset="utf-8")
            msg["to"] = recipient
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return True
        except Exception as e:
            print(f"⚠ Gmail send error: {e}")
            return False

    def get_summary(self) -> str:
        emails = self.get_unread(5)
        if not emails:
            return "📧 No unread emails from the last 30 minutes."
        lines = [f"📧 {len(emails)} unread emails from the last 30 minutes:"]
        for e in emails:
            lines.append(f"  • From: {e['from'][:30]} — {e['subject'][:50]}")
        return "\n".join(lines)
