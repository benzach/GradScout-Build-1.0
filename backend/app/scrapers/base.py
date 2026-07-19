"""
Every scraper — static, RSS, or API-based — implements this same
interface. Unchanged from the prototype; the contract didn't need to
change, only how scrapers get their config (see registry.py — now reads
from the sources DB table instead of sites.yaml) and what happens to
their output (now flows into app/storage.py instead of SQLite directly).
"""
from abc import ABC, abstractmethod


class BaseScraper(ABC):
    def __init__(self, site_config: dict):
        self.config = site_config
        self.name = site_config["name"]
        self.url = site_config.get("url", "")  # optional — API scrapers build their own request URLs

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Fetch and parse job listings. Must return a list of plain dicts
        (not JobListing objects — see note in registry.py about why),
        each with: title, url, company, location, salary, contract_type,
        description, posted_date. Missing fields should be "", not
        omitted, since storage.py accesses them with .get(key, "").
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} site={self.name!r}>"
