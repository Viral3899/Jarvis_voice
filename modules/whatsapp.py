"""
WhatsApp module — read & reply messages via WhatsApp Web automation.
Uses Selenium with undetected-chromedriver to avoid detection.

First run: You'll need to scan the QR code to log in.
Session persists in data/whatsapp_profile/ so you only scan once.
"""

import re
import time
from pathlib import Path
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from core.browser import CHROME_START_LOCK, browser_error_summary


PROFILE_DIR = str(Path(__file__).parent.parent / "data" / "whatsapp_profile")
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
CHAT_LIST_SELECTOR = (
    '[data-testid="chat-list"], [aria-label="Chat list"], '
    '#pane-side, [data-icon="chat"]'
)


def _spoken_preview(message: str) -> str:
    """Keep WhatsApp previews concise without reading out shared URLs."""
    preview = URL_PATTERN.sub("a link", message)
    preview = " ".join(preview.split()).strip(" .,:;")
    return preview[:200]


class WhatsAppModule:
    def __init__(self):
        self.driver = None
        self._logged_in = False

    def start(self):
        """Launch WhatsApp Web in a Chrome session."""
        try:
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={PROFILE_DIR}")
            options.add_argument("--start-maximized")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-gpu")

            with CHROME_START_LOCK:
                self.driver = uc.Chrome(options=options)
            self.driver.get("https://web.whatsapp.com")
            print("📱 WhatsApp Web: Waiting for login...")
            print("   Scan the QR code if this is the first time.")

            # Wait for the main chat screen to load (up to 60s for QR scan)
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, CHAT_LIST_SELECTOR)
                )
            )
            self._logged_in = True
            print("✅ WhatsApp Web: Logged in!")
        except TimeoutException:
            self._logged_in = False
            print(
                "⚠ WhatsApp Web did not reach its logged-in screen within "
                "60 seconds. Scan the QR code if prompted and keep this "
                "window open; Jarvis will keep checking for login."
            )
        except Exception as e:
            self._logged_in = False
            print(f"⚠ WhatsApp startup failed: {browser_error_summary(e)}")

    def refresh_login_status(self) -> bool:
        """Detect a login completed after the initial QR wait timed out."""
        if self._logged_in:
            return True
        if self.driver is None:
            return False

        try:
            self._logged_in = bool(
                self.driver.find_elements(By.CSS_SELECTOR, CHAT_LIST_SELECTOR)
            )
        except WebDriverException as e:
            print(f"⚠ WhatsApp login check failed: {browser_error_summary(e)}")
            return False

        if self._logged_in:
            print("✅ WhatsApp Web: Login detected!")
        return self._logged_in

    def get_unread_chats(self) -> list[dict]:
        """Get list of chats with unread messages."""
        if not self._logged_in:
            return []

        unread = []
        try:
            # Find chat list items with unread badges
            chat_elements = self.driver.find_elements(
                By.CSS_SELECTOR, '[aria-label*="unread"]'
            )
            for elem in chat_elements[:10]:
                try:
                    # Get contact name and last message
                    parent = elem.find_element(By.XPATH, "./ancestor::div[@data-id]")
                    name_elem = parent.find_element(By.CSS_SELECTOR, "span[title]")
                    name = name_elem.get_attribute("title")

                    msg_elem = parent.find_elements(By.CSS_SELECTOR, "span.selectable-text")
                    last_msg = _spoken_preview(msg_elem[-1].text) if msg_elem else ""

                    unread.append({
                        "contact": name,
                        "last_message": last_msg[:200],
                        "element": parent,
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠ WhatsApp read error: {e}")

        return unread

    def send_message(self, contact: str, message: str) -> bool:
        """Send a message to a contact."""
        if not self._logged_in or not contact.strip() or not message.strip():
            return False

        try:
            # Click search box
            search = self.driver.find_element(
                By.CSS_SELECTOR, '[data-icon="search"]'
            )
            search.click()
            time.sleep(0.5)

            # Type contact name
            search_input = self.driver.find_element(
                By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="3"]'
            )
            search_input.clear()
            search_input.send_keys(contact)
            time.sleep(1.5)

            # Click first matching contact
            contact_key = contact.strip().casefold()
            contact_digits = re.sub(r"\D", "", contact)
            candidates = self.driver.find_elements(By.CSS_SELECTOR, "span[title]")
            contacts = []
            for candidate in candidates:
                title = candidate.get_attribute("title") or ""
                if contact_digits:
                    if contact_digits in re.sub(r"\D", "", title):
                        contacts.append(candidate)
                elif contact_key in title.casefold():
                    contacts.append(candidate)
            if contacts:
                contacts[0].click()
                time.sleep(0.5)

                # Type and send message
                msg_box = self.driver.find_element(
                    By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]'
                )
                msg_box.click()
                msg_box.send_keys(message)
                msg_box.send_keys(Keys.ENTER)
                return True
        except Exception as e:
            print(f"⚠ WhatsApp send error: {e}")
        return False

    def get_summary(self) -> str:
        if not self._logged_in:
            return (
                "WhatsApp Web is not connected. Check Chrome startup and "
                "scan the QR code if prompted."
            )
        chats = self.get_unread_chats()
        if not chats:
            return "📱 No unread WhatsApp messages."
        lines = [f"📱 {len(chats)} unread WhatsApp chats:"]
        for c in chats:
            message = " ".join(c["last_message"].split())[:120]
            preview = message or "Message preview is unavailable."
            lines.append(f"  • {c['contact']}: {preview}")
        return "\n".join(lines)

    def stop(self):
        if self.driver:
            self.driver.quit()
