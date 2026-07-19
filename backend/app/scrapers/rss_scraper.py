"""
RSS scraper — for sites that publish an official feed. Currently just
w4mpjobs, but the pattern (and this class) applies to any future RSS
source with an INSERT into the sources table, same scraper_type='rss'.

Ported from the prototype with verified real feed structure preserved:
location comes from <category>, organisation (now: company) from
<author>, salary is only occasionally present in the feed text itself
and extracted with a best-effort regex when it is.
"""
import html
import re
import time

import feedparser
import requests
from bs4 import BeautifulSoup

from app.dedup.parsing import detect_contract_type
from app.scrapers.base import BaseScraper

SALARY_PATTERN = re.compile(
    r"Salary\s*:?\s*([£$]?[\d][\d,\.]*(?:\s*-\s*[£$]?[\d][\d,\.]*)?(?:\s*per\s+\w+)?)",
    re.IGNORECASE,
)
ORG_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

# Detail-page field extraction (for w4mpjobs's JobDetails.aspx pages,
# where salary is far more often present than in the RSS feed itself).
# Only searched within the structured header block, before the free-text
# description, to avoid false-matching similar words in the job body.
DETAIL_LOCATION_PATTERN = re.compile(r"Location\s*:\s*([^\n]+)", re.IGNORECASE)
DETAIL_SALARY_PATTERN = re.compile(r"Salary\s*:\s*([^\n]+)", re.IGNORECASE)
DETAIL_ORG_PATTERN = re.compile(r"Working For\s*:\s*([^\n]+)", re.IGNORECASE)
DETAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
DETAIL_TIMEOUT = 15
DETAIL_FETCH_DELAY_SECONDS = 0.5  # be polite — don't hammer the source site


def _clean_description(raw_html: str) -> str:
    if not raw_html:
        return ""
    unescaped = html.unescape(raw_html)
    return BeautifulSoup(unescaped, "lxml").get_text(separator=" ", strip=True)


def _extract_salary_from_text(clean_text: str) -> str:
    match = SALARY_PATTERN.search(clean_text)
    return match.group(1).strip() if match else ""


def _clean_company(author: str) -> str:
    if not author:
        return ""
    return ORG_TRAILING_PAREN.sub("", author).strip()


def _fetch_job_detail_fields(url: str) -> dict:
    """
    Fetches a job's full detail page and extracts location/salary/company
    from the structured header block. Empty strings for anything not
    found — callers should only overwrite existing data with non-empty
    results, since a miss here isn't necessarily a real absence.
    """
    resp = requests.get(url, headers=DETAIL_HEADERS, timeout=DETAIL_TIMEOUT)
    resp.raise_for_status()
    full_text = BeautifulSoup(resp.text, "lxml").get_text(separator="\n")
    header_block = full_text.split("Job Details")[0]

    def _extract(pattern):
        m = pattern.search(header_block)
        return m.group(1).strip() if m else ""

    return {
        "location": _extract(DETAIL_LOCATION_PATTERN),
        "salary": _extract(DETAIL_SALARY_PATTERN),
        "company": _extract(DETAIL_ORG_PATTERN),
    }


class RSSScraper(BaseScraper):
    def scrape(self) -> list[dict]:
        # Deliberately NOT feedparser.parse(self.url) for real HTTP(S)
        # URLs — that lets feedparser make the network call itself, with
        # no timeout at all (a real gap: every other network call in
        # this codebase sets timeout=15, this was the one exception). If
        # the source site is slow or silently drops the connection, that
        # call can hang indefinitely; if it hangs long enough for the
        # host to kill and restart the process, our own failure-recording
        # code in app/pipeline.py's except block never even runs, since
        # nothing was ever raised — the source's last_scrape_status stays
        # NULL forever instead of showing a real error. Fetching
        # explicitly first, with the same timeout/headers pattern every
        # other scraper uses, closes that gap.
        #
        # Local file paths (used by tests to avoid real network calls
        # entirely) skip this and go straight to feedparser, since
        # there's no network request to time out on in the first place.
        if self.url.startswith("http://") or self.url.startswith("https://"):
            resp = requests.get(self.url, headers=DETAIL_HEADERS, timeout=DETAIL_TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        else:
            feed = feedparser.parse(self.url)

        if feed.bozo and not feed.entries:
            raise ValueError(f"Failed to parse RSS feed for {self.name}: {feed.bozo_exception}")

        # Config-driven: fetch_details enables following each job link for
        # accurate salary; detail_fetch_limit bounds how many of the most
        # recent listings get this treatment per run (feed is newest-first,
        # and most older ones are already in the DB from previous runs).
        fetch_details = self.config.get("fetch_details", False)
        detail_fetch_limit = self.config.get("detail_fetch_limit", 50)

        jobs = []
        for i, entry in enumerate(feed.entries):
            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            posted = entry.get("published", "")

            if not title or not url:
                continue

            description = _clean_description(entry.get("summary", ""))
            location = entry.get("category", "").strip()
            company = _clean_company(entry.get("author", ""))
            salary = _extract_salary_from_text(description)

            if fetch_details and i < detail_fetch_limit:
                try:
                    detail_fields = _fetch_job_detail_fields(url)
                    location = detail_fields["location"] or location
                    salary = detail_fields["salary"] or salary
                    company = detail_fields["company"] or company
                except Exception as e:
                    # One job's detail page failing shouldn't lose the
                    # whole listing — fall back to whatever the feed gave us.
                    print(f"  (detail fetch failed for {url}: {e})")
                finally:
                    time.sleep(DETAIL_FETCH_DELAY_SECONDS)

            jobs.append({
                "title": title,
                "url": url,
                "company": company,
                "location": location,
                "salary": salary,
                "description": description,
                "posted_date": posted,
                "contract_type": detect_contract_type(title, description),
            })
        return jobs
