"""
Instagram DM module — read & reply DMs via browser automation.
Uses Selenium with undetected-chromedriver.

First run: You'll need to log in manually. Session persists.
"""

import os
import time
from pathlib import Path
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from core.browser import CHROME_START_LOCK, browser_error_summary


DEFAULT_CHROME_USER_DATA_DIR = (
    Path(__file__).parent.parent / "data" / "instagram_profile"
)
CHROME_USER_DATA_DIR = Path(
    os.getenv("INSTAGRAM_CHROME_USER_DATA_DIR", str(DEFAULT_CHROME_USER_DATA_DIR))
)
CHROME_PROFILE = os.getenv("INSTAGRAM_CHROME_PROFILE", "Default")


class InstagramModule:
    def __init__(self):
        self.driver = None
        self._logged_in = False

    def start(self):
        """Launch Instagram in Chrome."""
        try:
            CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
            options.add_argument(f"--profile-directory={CHROME_PROFILE}")
            options.add_argument("--no-sandbox")

            with CHROME_START_LOCK:
                self.driver = uc.Chrome(options=options)
            self.driver.get("https://www.instagram.com/direct/inbox/")
            print("📸 Instagram: Waiting for login...")
            print("   Log in manually if this is the first time.")

            # Wait for DM inbox to load
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[aria-label="Direct"]'))
            )
            self._logged_in = True
            print("✅ Instagram: Logged in!")
        except TimeoutException:
            self._logged_in = False
            print(
                "⚠ Instagram did not reach its logged-in inbox within 60 seconds. "
                "Complete login if prompted; if already logged in, the page "
                "selector may need updating."
            )
        except Exception as e:
            self._logged_in = False
            print(f"⚠ Instagram startup failed: {browser_error_summary(e)}")

    def get_unread_dms(self) -> list[dict]:
        """Get unread DMs."""
        if not self._logged_in:
            return []

        unread = []
        try:
            self.driver.get("https://www.instagram.com/direct/inbox/")
            time.sleep(2)

            # Find conversation threads with unread indicators
            threads = self.driver.find_elements(
                By.CSS_SELECTOR, 'div[role="listitem"]'
            )
            for thread in threads[:10]:
                try:
                    # Check for unread dot indicator
                    dots = thread.find_elements(By.CSS_SELECTOR, '[aria-label*="unread"]')
                    if not dots:
                        continue

                    name_elem = thread.find_element(By.CSS_SELECTOR, "span")
                    name = name_elem.text

                    unread.append({
                        "contact": name,
                        "element": thread,
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠ Instagram DM read error: {e}")

        return unread

    def send_dm(self, contact: str, message: str) -> bool:
        """Send a DM to a user."""
        if not self._logged_in:
            return False

        try:
            self.driver.get("https://www.instagram.com/direct/inbox/")
            time.sleep(2)

            # Search for the contact in DM threads
            threads = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
            for thread in threads:
                try:
                    name = thread.find_element(By.CSS_SELECTOR, "span").text
                    if contact.lower() in name.lower():
                        thread.click()
                        time.sleep(1)

                        # Type message
                        msg_box = self.driver.find_element(
                            By.CSS_SELECTOR, 'textarea[placeholder="Message..."]'
                        )
                        msg_box.click()
                        msg_box.send_keys(message)
                        msg_box.send_keys(Keys.ENTER)
                        return True
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠ Instagram send error: {e}")
        return False

    def get_summary(self) -> str:
        if not self._logged_in:
            return "Instagram is not connected. Check Chrome startup and log in."
        dms = self.get_unread_dms()
        if not dms:
            return "📸 No unread Instagram DMs."
        lines = [f"📸 {len(dms)} unread Instagram DMs:"]
        for d in dms:
            lines.append(f"  • {d['contact']}")
        return "\n".join(lines)

    def stop(self):
        if self.driver:
            self.driver.quit()
