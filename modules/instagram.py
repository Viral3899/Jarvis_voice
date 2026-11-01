"""
Instagram DM module — read & reply DMs via browser automation.
Uses Selenium with undetected-chromedriver.

First run: You'll need to log in manually. Session persists.
"""

import os
import time
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from core.browser import CHROME_START_LOCK


DEFAULT_CHROME_USER_DATA_DIR = (
    Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "Google"
    / "Chrome"
    / "User Data"
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
            profile_dir = CHROME_USER_DATA_DIR / CHROME_PROFILE
            if not profile_dir.is_dir():
                raise FileNotFoundError(
                    f"Chrome profile not found: {profile_dir}. "
                    "Set INSTAGRAM_CHROME_USER_DATA_DIR and INSTAGRAM_CHROME_PROFILE."
                )

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
        except Exception as e:
            print(f"⚠ Instagram start error: {e}")

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
