"""
Storage layer — where the dedup engine (Phase 0, pure Python, no DB
knowledge) meets real persistence.

This module does two dedup checks, in order, and it's worth understanding
why there are two rather than one:

1. EXACT check (cheap): has this exact URL from this exact site been
   scraped before? A unique constraint on job_sources(site, source_url)
   makes this a single indexed lookup. Every re-scrape of a posting we
   already know about gets caught HERE, for almost no cost — this matters
   because a scheduler polling every 15-30 minutes will re-fetch mostly
   the same jobs over and over; without this check, every single one of
   them would run through the expensive fuzzy engine every single cycle.

2. FUZZY check (only for genuinely new URLs): is this a new posting for
   a job we've already seen from a DIFFERENT source? This is Phase 0's
   dedup engine, unchanged — normalize -> block -> score -> decide.

On the fuzzy check's candidate pool: rather than re-implementing the
blocking company-match logic in SQL, we fetch a coarse pool from the
database (jobs posted within the last 30 days — a plain indexed range
query) and hand it to the ALREADY-TESTED Python blocking/scoring logic
from Phase 0 unchanged. This preserves exact fidelity with everything we
validated in Phase 0's test suite, at the cost of fetching a wider pool
than strictly necessary. At real scale (many thousands of jobs/day) the
known next optimization is adding a Postgres trigram index (pg_trgm
extension) so the company-fuzzy-match narrowing happens in SQL too — not
needed yet, and deliberately deferred rather than built speculatively.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Job, JobSource
from app.dedup.engine import dedup_against_existing
from app.dedup.normalize import normalize_title, normalize_company, normalize_location
from app.dedup.scoring import parse_salary_range

CANDIDATE_POOL_WINDOW_DAYS = 30


def _job_row_to_dict(job: Job) -> dict:
    """Converts a Job ORM row into the plain dict shape the (DB-agnostic) dedup engine expects."""
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company,
        "location": job.location or "",
        "salary": job.salary_text or "",
        "description": job.description or "",
        "posted_date": job.posted_date.isoformat() if job.posted_date else "",
    }


def _fetch_candidate_pool(session: Session) -> list[dict]:
    """Coarse pre-filter: jobs posted recently, or with no parseable date at all."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=CANDIDATE_POOL_WINDOW_DAYS)
    rows = (
        session.query(Job)
        .filter((Job.posted_date == None) | (Job.posted_date >= cutoff))  # noqa: E711
        .all()
    )
    return [_job_row_to_dict(r) for r in rows]


def _build_job_row(scraped_job: dict, possible_duplicate_of=None) -> Job:
    norm_title, remote_from_title = normalize_title(scraped_job.get("title", ""))
    norm_location, remote_from_location = normalize_location(scraped_job.get("location", ""))
    salary_min, salary_max = parse_salary_range(scraped_job.get("salary", ""))

    return Job(
        title=scraped_job.get("title", ""),
        normalized_title=norm_title,
        company=scraped_job.get("company", ""),
        normalized_company=normalize_company(scraped_job.get("company", "")),
        location=scraped_job.get("location", ""),
        normalized_location=norm_location,
        remote_type=remote_from_title or remote_from_location,
        salary_text=scraped_job.get("salary", ""),
        salary_min=salary_min,
        salary_max=salary_max,
        contract_type=scraped_job.get("contract_type", ""),
        description=scraped_job.get("description", ""),
        posted_date=_try_parse_date(scraped_job.get("posted_date", "")),
        possible_duplicate_of=possible_duplicate_of,
    )


def _try_parse_date(date_str: str):
    if not date_str:
        return None
    from app.dedup.scoring import _try_parse_date as parse_fn
    return parse_fn(date_str)


def process_scraped_job(session: Session, site_name: str, scraped_job: dict) -> dict:
    """
    The main entry point this module exposes. Takes one freshly-scraped
    job (plain dict — title, url, company, location, salary, description,
    posted_date, contract_type) plus which source it came from, and
    persists it correctly: as a new canonical job, merged into an
    existing one, or flagged for review.

    Returns a dict describing what happened, for logging/testing:
        {"action": "already_seen" | "insert_new" | "merge" | "flag_for_review",
         "job_id": "...", "match_score": <float, if applicable>}
    """
    source_url = scraped_job.get("url", "")

    # Layer 1: exact-URL check — cheap, catches most re-scrapes for free.
    existing_source = (
        session.query(JobSource)
        .filter_by(site=site_name, source_url=source_url)
        .first()
    )
    if existing_source:
        return {"action": "already_seen", "job_id": str(existing_source.job_id)}

    # Layer 2: fuzzy cross-source check — only reached for genuinely new URLs.
    candidates = _fetch_candidate_pool(session)
    outcome = dedup_against_existing(scraped_job, candidates)

    if outcome.action == "insert_new":
        job = _build_job_row(scraped_job)
        session.add(job)
        session.flush()  # assigns job.id without committing yet
        session.add(JobSource(
            job_id=job.id, site=site_name, source_url=source_url,
            raw_title=scraped_job.get("title", ""),
        ))
        session.commit()
        return {"action": "insert_new", "job_id": str(job.id)}

    elif outcome.action == "merge":
        job_id = outcome.best_match["id"]
        job = session.get(Job, job_id)
        job.last_updated_at = datetime.now(timezone.utc)
        session.add(JobSource(
            job_id=job.id, site=site_name, source_url=source_url,
            raw_title=scraped_job.get("title", ""),
        ))
        session.commit()
        return {
            "action": "merge", "job_id": str(job_id),
            "match_score": outcome.match_result.composite_score,
        }

    else:  # flag_for_review
        possible_dup_id = outcome.best_match["id"]
        job = _build_job_row(scraped_job, possible_duplicate_of=possible_dup_id)
        session.add(job)
        session.flush()
        session.add(JobSource(
            job_id=job.id, site=site_name, source_url=source_url,
            raw_title=scraped_job.get("title", ""),
        ))
        session.commit()
        return {
            "action": "flag_for_review", "job_id": str(job.id),
            "possible_duplicate_of": possible_dup_id,
            "match_score": outcome.match_result.composite_score,
        }
