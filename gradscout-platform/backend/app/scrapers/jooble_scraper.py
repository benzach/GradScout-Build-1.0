"""
Jooble API scraper. Verified against Jooble's official REST API docs.
Note the request pattern differs from Adzuna/Reed: it's a POST with a
JSON body, and the API key goes in the URL path itself.
Requires JOOBLE_API_KEY environment variable.
"""
import os

import requests

from app.scrapers.base import BaseScraper

JOOBLE_URL_TEMPLATE = "https://jooble.org/api/{api_key}"
TIMEOUT = 15


class JoobleScraper(BaseScraper):
    def scrape(self) -> list[dict]:
        api_key = os.environ.get("JOOBLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "JOOBLE_API_KEY must be set as an environment variable "
                "(register at https://jooble.org/api/about)"
            )

        keywords = self.config.get("keywords", "graduate")
        location = self.config.get("location", "United Kingdom")
        results_per_page = self.config.get("results_on_page", 50)
        max_pages = self.config.get("max_pages", 3)

        url = JOOBLE_URL_TEMPLATE.format(api_key=api_key)
        jobs = []

        for page in range(1, max_pages + 1):
            body = {
                "keywords": keywords, "location": location,
                "page": str(page), "ResultOnPage": str(results_per_page),
            }
            resp = requests.post(url, json=body, timeout=TIMEOUT)
            resp.raise_for_status()
            page_jobs = resp.json().get("jobs", [])

            if not page_jobs:
                break
            jobs.extend(self._parse_job(item) for item in page_jobs)
            if len(page_jobs) < results_per_page:
                break

        return jobs

    def _parse_job(self, item: dict) -> dict:
        return {
            "title": item.get("title", "").strip(),
            "url": item.get("link", "").strip(),
            "company": item.get("company", "") or "",
            "location": item.get("location", "") or "",
            "salary": item.get("salary", "") or "",
            "contract_type": item.get("type", "") or "",
            "description": item.get("snippet", "") or "",
            "posted_date": item.get("updated", "") or "",
        }
