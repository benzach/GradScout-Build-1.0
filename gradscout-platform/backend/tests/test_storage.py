"""
Tests for the storage layer — the DB-backed version of everything Phase
0 already proved works in pure Python. Each test runs inside a
transaction that's rolled back afterward, so tests never leave residue
in the dev database for the next test (or for you, poking around
manually) to trip over.
"""
import pytest

from app.db import get_session
from app.models import Job, JobSource
from app.storage import process_scraped_job


@pytest.fixture
def session():
    """
    Uses a real session against the dev database, with an explicit
    cleanup before each test — NOT the more common "wrap in a
    transaction and roll back" pattern, because process_scraped_job()
    calls session.commit() internally (correctly, for production use).
    A commit on a session ends the surrounding transaction regardless of
    what a test fixture wants, which silently breaks rollback-based
    isolation. Explicit truncation sidesteps that entirely and is easier
    to reason about.
    """
    s = get_session()
    s.query(JobSource).delete()
    s.query(Job).delete()
    s.commit()
    yield s
    s.close()


def test_new_job_creates_canonical_row_and_one_source(session):
    job = {
        "title": "Graduate Analyst", "url": "https://example.com/job/1",
        "company": "Barclays", "location": "London", "salary": "£35,000",
        "description": "Join our graduate scheme.", "posted_date": "2026-07-10",
        "contract_type": "Full-time",
    }
    result = process_scraped_job(session, "adzuna", job)
    assert result["action"] == "insert_new"
    assert session.query(Job).count() == 1
    assert session.query(JobSource).count() == 1


def test_same_job_different_source_merges_not_duplicates(session):
    """The core scenario: same job, different wording, different source, different URL."""
    adzuna_job = {
        "title": "Software Engineer - Remote", "url": "https://adzuna.example/1",
        "company": "Google LLC", "location": "London (Remote)",
        "salary": "£45,000 - £55,000",
        "description": "We are looking for a talented software engineer to join our growing team in London.",
        "posted_date": "2026-07-10", "contract_type": "Full-time",
    }
    reed_job = {
        "title": "Software Developer (Remote)", "url": "https://reed.example/2",
        "company": "Google", "location": "London (Remote)",
        "salary": "£46,000 - £54,000",
        "description": "We are looking for a talented software developer to join our growing team in London.",
        "posted_date": "2026-07-11", "contract_type": "Full-time",
    }
    r1 = process_scraped_job(session, "adzuna", adzuna_job)
    r2 = process_scraped_job(session, "reed", reed_job)

    assert r1["action"] == "insert_new"
    assert r2["action"] == "merge"
    assert r1["job_id"] == r2["job_id"]  # same canonical job
    assert session.query(Job).count() == 1
    assert session.query(JobSource).count() == 2


def test_rescraping_same_url_is_cheap_noop(session):
    job = {
        "title": "Graduate Analyst", "url": "https://example.com/job/1",
        "company": "Barclays", "location": "London", "salary": "£35,000",
        "description": "Join our graduate scheme.", "posted_date": "2026-07-10",
        "contract_type": "Full-time",
    }
    process_scraped_job(session, "adzuna", job)
    result = process_scraped_job(session, "adzuna", job)  # exact same posting again
    assert result["action"] == "already_seen"
    assert session.query(Job).count() == 1
    assert session.query(JobSource).count() == 1  # not duplicated


def test_different_companies_same_title_both_kept_distinct(session):
    """Every bank has a 'Graduate Analyst' - these must never merge."""
    barclays_job = {
        "title": "Graduate Analyst", "url": "https://example.com/barclays",
        "company": "Barclays", "location": "London", "salary": "£35,000",
        "description": "Join our graduate scheme working across investment banking.",
        "posted_date": "2026-07-10", "contract_type": "Full-time",
    }
    hsbc_job = {
        "title": "Graduate Analyst", "url": "https://example.com/hsbc",
        "company": "HSBC", "location": "London", "salary": "£34,000",
        "description": "Join our graduate scheme working across investment banking.",
        "posted_date": "2026-07-10", "contract_type": "Full-time",
    }
    process_scraped_job(session, "adzuna", barclays_job)
    result = process_scraped_job(session, "reed", hsbc_job)

    assert result["action"] == "insert_new"
    assert session.query(Job).count() == 2


def test_ambiguous_case_flagged_with_link_preserved(session):
    existing = {
        "title": "Graduate Marketing Executive", "url": "https://example.com/unilever1",
        "company": "Unilever", "location": "London", "salary": "£28,000",
        "description": "Join our fast-paced marketing team working on some of the biggest consumer brands in the world today.",
        "posted_date": "2026-07-01", "contract_type": "Full-time",
    }
    ambiguous = {
        "title": "Graduate Marketing Executive", "url": "https://example.com/unilever2",
        "company": "Unilever", "location": "London", "salary": "£30,000",
        "description": "An exciting opportunity has arisen for a graduate to join our brand management division working on household names.",
        "posted_date": "2026-07-12", "contract_type": "Full-time",
    }
    process_scraped_job(session, "adzuna", existing)
    result = process_scraped_job(session, "reed", ambiguous)

    assert result["action"] == "flag_for_review"
    assert session.query(Job).count() == 2  # kept as separate rows
    flagged_job = session.query(Job).filter_by(id=result["job_id"]).first()
    assert flagged_job.possible_duplicate_of is not None  # but linked
