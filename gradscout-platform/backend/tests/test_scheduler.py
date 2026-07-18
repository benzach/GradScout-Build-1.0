"""
Tests for the scheduler's actual cycle logic (run_scheduled_cycle) —
NOT for APScheduler's timing mechanism itself, which is a well-established
third-party library not worth re-testing. What matters here is proving
OUR code correctly orchestrates: scrape all sources, then materialize
matches for every user with active criteria, with failure isolation at
both levels.
"""
import os
os.environ["DISABLE_SCHEDULER"] = "true"
os.environ.setdefault("ADZUNA_APP_ID", "test")
os.environ.setdefault("ADZUNA_APP_KEY", "test")
os.environ.setdefault("REED_API_KEY", "test")
os.environ.setdefault("JOOBLE_API_KEY", "test")

from unittest.mock import patch, MagicMock

import pytest

from app.db import get_session
from app.models import Job, JobSource, SearchCriteria, Source, User, UserJobMatch
from app.scheduler import run_scheduled_cycle


@pytest.fixture
def session():
    s = get_session()
    s.query(UserJobMatch).delete()
    s.query(JobSource).delete()
    s.query(Job).delete()
    s.query(SearchCriteria).delete()
    s.query(User).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture
def disabled_sources(session):
    """Disable all real sources so run_pipeline finds nothing to scrape — these tests are about the ORCHESTRATION, not re-testing Phase 2's scraping."""
    sources = session.query(Source).all()
    original = {s.name: s.enabled for s in sources}
    for s in sources:
        s.enabled = False
    session.commit()
    yield
    for s in sources:
        s.enabled = original[s.name]
    session.commit()


def test_cycle_computes_matches_for_users_with_active_criteria(session, disabled_sources):
    user = User(email="cycle-test@example.com")
    session.add(user)
    session.flush()

    job = Job(
        title="Graduate Analyst", normalized_title="graduate analyst",
        company="Barclays", normalized_company="barclays",
        location="London", normalized_location="london",
    )
    session.add(job)
    session.flush()
    session.add(JobSource(job_id=job.id, site="adzuna", source_url="https://example.com/1", raw_title=job.title))

    criteria = SearchCriteria(user_id=user.id, keywords=["analyst"], active=True)
    session.add(criteria)
    session.commit()

    summary = run_scheduled_cycle()

    assert summary["users_processed"] == 1
    assert summary["match_errors"] == []
    assert "fatal_error" not in summary

    match_count = session.query(UserJobMatch).filter_by(user_id=user.id).count()
    assert match_count == 1


def test_cycle_skips_users_with_no_active_criteria(session, disabled_sources):
    user = User(email="no-criteria@example.com")
    session.add(user)
    session.commit()

    summary = run_scheduled_cycle()

    assert summary["users_processed"] == 0  # never even considered - no active criteria


def test_one_users_match_failure_does_not_stop_others(session, disabled_sources):
    user_a = User(email="a@example.com")
    user_b = User(email="b@example.com")
    session.add_all([user_a, user_b])
    session.flush()

    session.add(SearchCriteria(user_id=user_a.id, keywords=["x"], active=True))
    session.add(SearchCriteria(user_id=user_b.id, keywords=["y"], active=True))
    session.commit()

    real_fn = __import__("app.matching", fromlist=["compute_and_materialize_matches"]).compute_and_materialize_matches

    def flaky(session_arg, user_arg, criteria_list):
        if user_arg.id == user_a.id:
            raise RuntimeError("simulated failure for user A")
        return real_fn(session_arg, user_arg, criteria_list)

    with patch("app.scheduler.compute_and_materialize_matches", side_effect=flaky):
        summary = run_scheduled_cycle()

    assert summary["users_processed"] == 1  # user B still succeeded
    assert len(summary["match_errors"]) == 1
    assert summary["match_errors"][0]["user_id"] == str(user_a.id)


def test_pipeline_failure_is_captured_not_raised(session):
    """If run_pipeline itself blows up entirely, the cycle should report it, not crash the scheduler thread."""
    with patch("app.scheduler.run_pipeline", side_effect=RuntimeError("simulated total pipeline failure")):
        summary = run_scheduled_cycle()

    assert summary["fatal_error"] == "simulated total pipeline failure"
