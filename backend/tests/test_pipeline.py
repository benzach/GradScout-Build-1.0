"""
Full pipeline integration test: real `sources` DB rows (the same ones
your actual deployment will use) -> real scraper classes -> mocked HTTP
layer (since this sandbox can't reach the live internet) -> REAL
storage.process_scraped_job -> REAL Postgres -> REAL dedup engine.

This is the strongest proof available without actually hitting live
sites: every layer except the network call itself is the genuine
production code path, not a simulation of it.
"""
import os
from unittest.mock import patch, MagicMock

import pytest

from app.db import get_session
from app.models import Job, JobSource, Source
from app.pipeline import run_pipeline


@pytest.fixture
def session():
    s = get_session()
    s.query(JobSource).delete()
    s.query(Job).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def api_keys():
    os.environ["ADZUNA_APP_ID"] = "test_id"
    os.environ["ADZUNA_APP_KEY"] = "test_key"
    os.environ["REED_API_KEY"] = "test_key"
    os.environ["JOOBLE_API_KEY"] = "test_key"


def _mock_adzuna_response(*args, **kwargs):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": [{
            "title": "Software Engineer - Remote",
            "redirect_url": "https://adzuna.example/jobs/123",
            "company": {"display_name": "Google LLC"},
            "location": {"display_name": "London (Remote)"},
            "salary_min": 45000, "salary_max": 55000,
            "description": "We are looking for a talented software engineer to join our growing team in London.",
            "created": "2026-07-10T09:00:00Z",
            "contract_type": "permanent", "contract_time": "full_time",
        }]
    }
    return resp


def _mock_reed_response(*args, **kwargs):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": [{
            "jobTitle": "Software Developer (Remote)",
            "jobUrl": "https://reed.example/jobs/456",
            "employerName": "Google",
            "locationName": "London (Remote)",
            "minimumSalary": 46000, "maximumSalary": 54000,
            "jobDescription": "We are looking for a talented software developer to join our growing team in London.",
            "date": "11/07/2026",
            "fullTime": True, "contractType": "Permanent",
        }]
    }
    return resp


def _mock_requests_get(url, *args, **kwargs):
    """
    Single dispatching mock, routing by URL. Necessary because
    adzuna_scraper.py and reed_scraper.py both do a plain `import
    requests`, meaning they share the exact same underlying module
    object in memory — patching app.scrapers.adzuna_scraper.requests.get
    and app.scrapers.reed_scraper.requests.get as two SEPARATE mocks
    doesn't give two independent mocks, it patches the same shared
    attribute twice, and whichever patch is applied last silently wins
    for the whole test. Routing on the URL within one shared mock avoids
    that trap and mirrors how the real requests.get behaves anyway.
    """
    if "adzuna" in url:
        return _mock_adzuna_response()
    elif "reed" in url:
        return _mock_reed_response()
    raise ValueError(f"Unexpected URL in test: {url}")


def test_two_real_sources_same_job_merges_through_full_pipeline(session):
    """
    Disables everything except adzuna+reed, mocks their HTTP layer to
    return the SAME underlying job worded differently (the exact
    scenario Phase 0/1 proved works), and runs the ACTUAL pipeline
    orchestrator end to end.
    """
    # Temporarily disable the other 5 sources so this test is focused
    other_sources = session.query(Source).filter(Source.name.notin_(["adzuna", "reed"])).all()
    original_states = {s.name: s.enabled for s in other_sources}
    for s in other_sources:
        s.enabled = False
    session.commit()

    try:
        with patch("app.scrapers.adzuna_scraper.requests.get", side_effect=_mock_requests_get), \
             patch("app.scrapers.reed_scraper.requests.get", side_effect=_mock_requests_get):
            summary = run_pipeline(session)

        assert summary["sources_run"] == 2
        assert summary["sources_failed"] == 0
        assert summary["jobs"]["insert_new"] == 1
        assert summary["jobs"]["merge"] == 1

        assert session.query(Job).count() == 1
        assert session.query(JobSource).count() == 2

        job = session.query(Job).first()
        sources_linked = {s.site for s in session.query(JobSource).filter_by(job_id=job.id).all()}
        assert sources_linked == {"adzuna", "reed"}
    finally:
        for s in other_sources:
            s.enabled = original_states[s.name]
        session.commit()


def test_one_source_failing_does_not_stop_the_others(session):
    other_sources = session.query(Source).filter(Source.name.notin_(["adzuna", "reed"])).all()
    original_states = {s.name: s.enabled for s in other_sources}
    for s in other_sources:
        s.enabled = False
    session.commit()

    def _mock_with_adzuna_broken(url, *args, **kwargs):
        if "adzuna" in url:
            raise ConnectionError("simulated network failure")
        elif "reed" in url:
            return _mock_reed_response()
        raise ValueError(f"Unexpected URL in test: {url}")

    try:
        with patch("app.scrapers.adzuna_scraper.requests.get", side_effect=_mock_with_adzuna_broken), \
             patch("app.scrapers.reed_scraper.requests.get", side_effect=_mock_with_adzuna_broken):
            summary = run_pipeline(session)

        assert summary["sources_run"] == 1  # reed succeeded
        assert summary["sources_failed"] == 1  # adzuna failed
        assert summary["failures"][0]["source"] == "adzuna"
        assert session.query(Job).count() == 1  # reed's job still got stored

        adzuna_source = session.query(Source).filter_by(name="adzuna").first()
        assert adzuna_source.last_scrape_status == "failed"
        assert "simulated network failure" in adzuna_source.last_scrape_error
    finally:
        for s in other_sources:
            s.enabled = original_states[s.name]
        session.commit()


def test_one_bad_job_does_not_lose_the_rest_of_the_batch(session):
    """
    Regression test for a real production incident: one job with
    malformed salary data crashed process_scraped_job, which took down
    the ENTIRE run_pipeline call — losing every other job from that
    source (including ones already fetched but not yet processed) and
    every source after it in the loop, since the try/except only
    wrapped scraper.scrape(), not the per-job processing inside it.
    """
    other_sources = session.query(Source).filter(Source.name != "adzuna").all()
    original_states = {s.name: s.enabled for s in other_sources}
    for s in other_sources:
        s.enabled = False
    session.commit()

    def mock_scrape(self):
        return [
            {"title": "Good Job A", "url": "https://x.example/a", "company": "Co A",
             "location": "London", "salary": "£30,000", "description": "d", "posted_date": "", "contract_type": ""},
            {"title": "Bad Job", "url": "https://x.example/bad", "company": "Co Bad",
             "location": "London", "salary": ",,,", "description": "d", "posted_date": "", "contract_type": ""},
            {"title": "Good Job B", "url": "https://x.example/b", "company": "Co B",
             "location": "London", "salary": "£40,000", "description": "d", "posted_date": "", "contract_type": ""},
        ]

    # Deliberately reinstate the OLD buggy regex pattern to prove this
    # is real defense-in-depth, independent of the regex fix itself —
    # this test protects against ANY future per-job data quirk, not
    # just the one that actually occurred in production.
    import re
    try:
        with patch("app.scrapers.adzuna_scraper.AdzunaScraper.scrape", mock_scrape), \
             patch("app.dedup.scoring.SALARY_NUMBER_PATTERN", re.compile(r"£?\s?([\d,]+)")):
            run_pipeline(session)

        titles = {j.title for j in session.query(Job).all()}
        assert titles == {"Good Job A", "Good Job B"}  # bad one skipped, neighbors survive

        source = session.query(Source).filter_by(name="adzuna").first()
        assert source.last_scrape_status == "partial"
    finally:
        for s in other_sources:
            s.enabled = original_states[s.name]
        session.commit()
