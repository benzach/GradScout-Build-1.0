"""
Pipeline orchestrator — the thing that will eventually be called by
Phase 5's scheduler every 15-30 minutes. For now, callable directly
(see the __main__ block) for manual runs and testing.

Same failure-isolation principle as the prototype's main.py: one source
failing (bad credentials, site down, changed HTML) shouldn't stop the
others from running. Each source's outcome — success or failure — gets
recorded on its own `sources` row, so failures are visible in the
database itself, not just in logs that scroll away.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.scrapers.registry import load_enabled_sources, build_scraper
from app.storage import process_scraped_job


def run_pipeline(session: Session) -> dict:
    """
    Runs every enabled source once: scrape -> dedup -> store. Returns a
    summary dict for logging/testing:
        {"sources_run": N, "sources_failed": N,
         "jobs": {"insert_new": N, "merge": N, "flag_for_review": N, "already_seen": N},
         "failures": [{"source": name, "error": str}, ...]}
    """
    sources = load_enabled_sources(session)
    summary = {
        "sources_run": 0, "sources_failed": 0,
        "jobs": {"insert_new": 0, "merge": 0, "flag_for_review": 0, "already_seen": 0},
        "failures": [],
    }

    for source in sources:
        print(f"Scraping {source.name}...")
        try:
            scraper = build_scraper(source)
            scraped_jobs = scraper.scrape()
        except Exception as e:
            print(f"  -> FAILED: {e}")
            source.last_scrape_status = "failed"
            source.last_scrape_error = str(e)
            source.last_scraped_at = datetime.now(timezone.utc)
            session.commit()
            summary["sources_failed"] += 1
            summary["failures"].append({"source": source.name, "error": str(e)})
            continue

        print(f"  -> found {len(scraped_jobs)} listing(s)")
        for job in scraped_jobs:
            result = process_scraped_job(session, source.name, job)
            summary["jobs"][result["action"]] += 1

        source.last_scrape_status = "success"
        source.last_scrape_error = None
        source.last_scraped_at = datetime.now(timezone.utc)
        session.commit()
        summary["sources_run"] += 1

    return summary


if __name__ == "__main__":
    from app.db import get_session

    session = get_session()
    result = run_pipeline(session)
    session.close()

    print("\n=== Pipeline summary ===")
    print(f"Sources run: {result['sources_run']}, failed: {result['sources_failed']}")
    print(f"Jobs: {result['jobs']}")
    if result["failures"]:
        print("Failures:")
        for f in result["failures"]:
            print(f"  {f['source']}: {f['error']}")
