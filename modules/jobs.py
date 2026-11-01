"""
Job Auto-Apply module — searches & applies to jobs on LinkedIn, Naukri, Indeed.
Uses Selenium browser automation.

⚠️ Auto-applying to jobs via automation may violate platform ToS.
   Use responsibly. This module helps with SEARCHING and EASY APPLY only.
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


PROFILE_DIR = str(Path(__file__).parent.parent / "data" / "jobs_profile")
RESUME_PATH = os.getenv("RESUME_PATH", "config/resume.pdf")


class JobModule:
    def __init__(self):
        self.driver = None
        self.job_titles = [t.strip() for t in os.getenv("JOB_TITLES", "Software Engineer").split(",")]
        self.locations = [l.strip() for l in os.getenv("JOB_LOCATIONS", "Remote").split(",")]
        self.found_jobs: list[dict] = []

    def _get_driver(self):
        if not self.driver:
            options = uc.ChromeOptions()
            options.add_argument(f"--user-data-dir={PROFILE_DIR}")
            options.add_argument("--no-sandbox")
            with CHROME_START_LOCK:
                self.driver = uc.Chrome(options=options)
        return self.driver

    def search_linkedin(self, query: str = None) -> list[dict]:
        """Search LinkedIn jobs."""
        driver = self._get_driver()
        title = query or self.job_titles[0]
        location = self.locations[0]

        jobs = []
        try:
            url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_AL=true"
            driver.get(url)
            time.sleep(3)

            cards = driver.find_elements(By.CSS_SELECTOR, ".job-card-container")[:10]
            for card in cards:
                try:
                    job_title = card.find_element(By.CSS_SELECTOR, ".job-card-list__title").text
                    company = card.find_element(By.CSS_SELECTOR, ".job-card-container__company-name").text
                    location_text = card.find_element(By.CSS_SELECTOR, ".job-card-container__metadata-item").text
                    link = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")

                    job = {
                        "platform": "LinkedIn",
                        "title": job_title,
                        "company": company,
                        "location": location_text,
                        "url": link,
                        "easy_apply": "Easy Apply" in card.text,
                    }
                    jobs.append(job)
                except Exception:
                    continue

            self.found_jobs.extend(jobs)
        except Exception as e:
            print(f"⚠ LinkedIn search error: {e}")
        return jobs

    def search_naukri(self, query: str = None) -> list[dict]:
        """Search Naukri.com jobs."""
        driver = self._get_driver()
        title = query or self.job_titles[0]

        jobs = []
        try:
            url = f"https://www.naukri.com/{title.lower().replace(' ', '-')}-jobs"
            driver.get(url)
            time.sleep(3)

            cards = driver.find_elements(By.CSS_SELECTOR, ".srp-jobtuple-wrapper")[:10]
            for card in cards:
                try:
                    job_title = card.find_element(By.CSS_SELECTOR, ".title").text
                    company = card.find_element(By.CSS_SELECTOR, ".comp-name").text
                    location_text = card.find_element(By.CSS_SELECTOR, ".locWdth").text
                    link = card.find_element(By.CSS_SELECTOR, "a.title").get_attribute("href")

                    jobs.append({
                        "platform": "Naukri",
                        "title": job_title,
                        "company": company,
                        "location": location_text,
                        "url": link,
                    })
                except Exception:
                    continue

            self.found_jobs.extend(jobs)
        except Exception as e:
            print(f"⚠ Naukri search error: {e}")
        return jobs

    def search_indeed(self, query: str = None) -> list[dict]:
        """Search Indeed jobs."""
        driver = self._get_driver()
        title = query or self.job_titles[0]
        location = self.locations[0]

        jobs = []
        try:
            url = f"https://www.indeed.com/jobs?q={title.replace(' ', '+')}&l={location.replace(' ', '+')}"
            driver.get(url)
            time.sleep(3)

            cards = driver.find_elements(By.CSS_SELECTOR, ".job_seen_beacon")[:10]
            for card in cards:
                try:
                    job_title = card.find_element(By.CSS_SELECTOR, ".jobTitle span").text
                    company = card.find_element(By.CSS_SELECTOR, ".companyName").text
                    location_text = card.find_element(By.CSS_SELECTOR, ".companyLocation").text
                    link_elem = card.find_element(By.CSS_SELECTOR, "a")
                    link = link_elem.get_attribute("href")

                    jobs.append({
                        "platform": "Indeed",
                        "title": job_title,
                        "company": company,
                        "location": location_text,
                        "url": link,
                    })
                except Exception:
                    continue

            self.found_jobs.extend(jobs)
        except Exception as e:
            print(f"⚠ Indeed search error: {e}")
        return jobs

    def search_all(self, query: str = None) -> list[dict]:
        """Search all platforms."""
        all_jobs = []
        all_jobs.extend(self.search_linkedin(query))
        all_jobs.extend(self.search_naukri(query))
        all_jobs.extend(self.search_indeed(query))
        return all_jobs

    def get_summary(self) -> str:
        if not self.found_jobs:
            return "💼 No jobs searched yet."
        lines = [f"💼 {len(self.found_jobs)} jobs found:"]
        for j in self.found_jobs[-5:]:
            lines.append(f"  • [{j['platform']}] {j['title']} at {j['company']} — {j['location']}")
        return "\n".join(lines)

    def stop(self):
        if self.driver:
            self.driver.quit()
