import logging
import random
import time
from html.parser import HTMLParser

import requests

from .models import Job, SearchQuery

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class JobCardParser(HTMLParser):
    """Parse LinkedIn job card HTML fragments."""

    def __init__(self):
        super().__init__()
        self.jobs: list[dict] = []
        self._current_job: dict = {}
        self._capture_text = False
        self._capture_field: str | None = None
        self._text_buffer: str = ""

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = attr_dict.get("class", "")

        if tag == "div" and "base-card" in classes and "job-search-card" in classes:
            urn = attr_dict.get("data-entity-urn", "")
            job_id = urn.split(":")[-1] if urn else ""
            self._current_job = {"job_id": job_id, "title": "", "company": "", "location": "", "url": "", "date_posted": ""}

        if tag == "h3" and "base-search-card__title" in classes:
            self._capture_text = True
            self._capture_field = "title"
            self._text_buffer = ""

        if tag == "h4" and "base-search-card__subtitle" in classes:
            self._capture_text = True
            self._capture_field = "company"
            self._text_buffer = ""

        if tag == "span" and "job-search-card__location" in classes:
            self._capture_text = True
            self._capture_field = "location"
            self._text_buffer = ""

        if tag == "a" and "base-card__full-link" in classes:
            url = attr_dict.get("href", "")
            if self._current_job:
                self._current_job["url"] = url.split("?")[0]

        if tag == "time" and "job-search-card__listdate" in classes:
            self._capture_text = True
            self._capture_field = "date_posted"
            self._text_buffer = ""

    def handle_data(self, data):
        if self._capture_text:
            self._text_buffer += data

    def handle_endtag(self, tag):
        if self._capture_text and self._capture_field:
            if tag in ("h3", "h4", "span", "time"):
                text = self._text_buffer.strip()
                if self._current_job and text:
                    self._current_job[self._capture_field] = text
                self._capture_text = False
                self._capture_field = None
                self._text_buffer = ""

        if tag == "li" and self._current_job and self._current_job.get("job_id"):
            self.jobs.append(self._current_job)
            self._current_job = {}


def parse_jobs(html: str) -> list[Job]:
    parser = JobCardParser()
    parser.feed(html)
    return [
        Job(
            job_id=j["job_id"],
            title=j.get("title", "Unknown"),
            company=j.get("company", "Unknown"),
            location=j.get("location", "Unknown"),
            url=j.get("url", ""),
            date_posted=j.get("date_posted", ""),
        )
        for j in parser.jobs
        if j.get("job_id")
    ]


def scrape_jobs(query: SearchQuery, delay_range: tuple[int, int] = (3, 7)) -> list[Job]:
    """Scrape LinkedIn public guest API for jobs matching the query."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })

    all_jobs: list[Job] = []

    for page in range(query.max_pages):
        params = {
            "keywords": query.keywords,
            "location": query.location,
            "f_TPR": query.time_filter,
            "sortBy": "DD",
            "start": page * query.results_per_page,
        }
        if query.geo_id:
            params["geoId"] = query.geo_id
        if query.work_type:
            params["f_WT"] = query.work_type

        try:
            resp = session.get(BASE_URL, params=params, timeout=15)

            if resp.status_code == 429:
                logger.warning("Rate limited by LinkedIn. Backing off.")
                time.sleep(30)
                resp = session.get(BASE_URL, params=params, timeout=15)
                if resp.status_code == 429:
                    logger.error("Still rate limited after backoff. Stopping this search.")
                    break

            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} on page {page}. Skipping.")
                break

            jobs = parse_jobs(resp.text)
            if not jobs:
                logger.debug(f"No more jobs on page {page}. Done.")
                break

            all_jobs.extend(jobs)
            logger.info(f"Page {page}: found {len(jobs)} jobs")

            if page < query.max_pages - 1:
                delay = random.uniform(*delay_range)
                time.sleep(delay)

        except requests.RequestException as e:
            logger.error(f"Request failed on page {page}: {e}")
            break

    seen_ids = set()
    unique_jobs = []
    for job in all_jobs:
        if job.job_id not in seen_ids:
            seen_ids.add(job.job_id)
            unique_jobs.append(job)

    return unique_jobs
