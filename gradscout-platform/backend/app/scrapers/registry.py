"""
Maps a source's scraper_type (stored in the sources DB table) to the
Python class that handles it, and builds scraper instances from a
Source row's config.

This replaces sites.yaml entirely — the registry itself (this mapping of
type -> class) is still code, but WHICH sources exist and how they're
configured is now data (see migrations/0002_seed_sources.sql and the
"adding a new source" note in backend/README.md).
"""
from sqlalchemy.orm import Session

from app.models import Source
from app.scrapers.base import BaseScraper
from app.scrapers.static_scraper import StaticScraper
from app.scrapers.rss_scraper import RSSScraper
from app.scrapers.adzuna_scraper import AdzunaScraper
from app.scrapers.reed_scraper import ReedScraper
from app.scrapers.jooble_scraper import JoobleScraper

SCRAPER_TYPES: dict[str, type[BaseScraper]] = {
    "static": StaticScraper,
    "rss": RSSScraper,
    "adzuna": AdzunaScraper,
    "reed": ReedScraper,
    "jooble": JoobleScraper,
}


def load_enabled_sources(session: Session) -> list[Source]:
    return session.query(Source).filter_by(enabled=True).all()


def build_scraper(source: Source) -> BaseScraper:
    scraper_cls = SCRAPER_TYPES.get(source.scraper_type)
    if not scraper_cls:
        raise ValueError(
            f"Unknown scraper_type '{source.scraper_type}' for source '{source.name}' "
            f"(known types: {', '.join(SCRAPER_TYPES)})"
        )
    # Merge the source's name into its config dict — scrapers expect
    # config['name'] per the BaseScraper contract, and this way each
    # scraper class doesn't need to know it came from a DB row at all.
    config = {"name": source.name, **(source.config or {})}
    return scraper_cls(config)
