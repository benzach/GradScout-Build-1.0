"""
Tests for the full API surface: users, search criteria CRUD, and the
job feed (the part that actually proves criteria filtering + the
get-or-create match pattern work correctly through real HTTP requests,
not just direct function calls).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_session
from app.models import Job, JobSource, SearchCriteria, User, UserJobMatch

client = TestClient(app)


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
def user(session):
    r = client.post("/users", json={"email": "test@example.com"})
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def auth_headers(user):
    return {"X-User-Id": user["id"]}


class TestAuth:
    def test_missing_header_rejected(self, session):
        r = client.get("/criteria")
        assert r.status_code == 422  # FastAPI's required-header validation

    def test_invalid_uuid_rejected(self, session):
        r = client.get("/criteria", headers={"X-User-Id": "not-a-uuid"})
        assert r.status_code == 401

    def test_unknown_user_rejected(self, session):
        r = client.get("/criteria", headers={"X-User-Id": "00000000-0000-0000-0000-000000000000"})
        assert r.status_code == 401


class TestUsers:
    def test_create_user(self, session):
        r = client.post("/users", json={"email": "new@example.com"})
        assert r.status_code == 201
        assert r.json()["email"] == "new@example.com"
        assert r.json()["subscription_tier"] == "free"

    def test_duplicate_email_rejected(self, session, user):
        r = client.post("/users", json={"email": user["email"]})
        assert r.status_code == 409


class TestCriteria:
    def test_create_and_list(self, auth_headers):
        r = client.post("/criteria", json={
            "label": "Software grad roles", "keywords": ["software", "engineer"],
            "locations": ["london"], "salary_min": 25000,
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["label"] == "Software grad roles"

        r = client.get("/criteria", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_cannot_access_another_users_criteria(self, session, auth_headers):
        r = client.post("/criteria", json={"keywords": ["x"]}, headers=auth_headers)
        criteria_id = r.json()["id"]

        other_user = client.post("/users", json={"email": "other@example.com"}).json()
        other_headers = {"X-User-Id": other_user["id"]}

        r = client.get(f"/criteria/{criteria_id}", headers=other_headers)
        assert r.status_code == 404  # not 403 - see _get_owned_criteria's docstring

    def test_update_is_partial(self, auth_headers):
        r = client.post("/criteria", json={"keywords": ["a"], "locations": ["london"]}, headers=auth_headers)
        criteria_id = r.json()["id"]

        r = client.patch(f"/criteria/{criteria_id}", json={"keywords": ["b"]}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["keywords"] == ["b"]
        assert r.json()["locations"] == ["london"]  # untouched by the partial update

    def test_delete(self, auth_headers):
        r = client.post("/criteria", json={"keywords": ["a"]}, headers=auth_headers)
        criteria_id = r.json()["id"]

        r = client.delete(f"/criteria/{criteria_id}", headers=auth_headers)
        assert r.status_code == 204

        r = client.get(f"/criteria/{criteria_id}", headers=auth_headers)
        assert r.status_code == 404


class TestFeed:
    def _seed_job(self, session, title, company, location, description="", salary_min=None):
        job = Job(
            title=title, normalized_title=title.lower(),
            company=company, normalized_company=company.lower(),
            location=location, normalized_location=location.lower(),
            description=description, salary_min=salary_min,
        )
        session.add(job)
        session.flush()
        session.add(JobSource(job_id=job.id, site="adzuna", source_url=f"https://example.com/{job.id}", raw_title=title))
        session.commit()
        return job

    def test_no_active_criteria_gives_empty_feed(self, auth_headers):
        r = client.get("/feed", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}

    def test_feed_only_returns_matching_jobs(self, session, auth_headers):
        self._seed_job(session, "Graduate Software Engineer", "Google", "London",
                        description="Join our engineering team")
        self._seed_job(session, "Graduate Chef", "Ritz Hotel", "London",
                        description="Join our kitchen team")

        client.post("/criteria", json={"keywords": ["software"], "locations": ["london"]}, headers=auth_headers)

        r = client.get("/feed", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["job"]["title"] == "Graduate Software Engineer"
        assert body["items"][0]["job"]["sources"][0]["site"] == "adzuna"
        assert body["items"][0]["status"] == "new"

    def test_feed_materializes_matches_idempotently(self, session, auth_headers):
        """Calling /feed twice shouldn't create duplicate match rows for the same job."""
        self._seed_job(session, "Graduate Analyst", "Barclays", "London")
        client.post("/criteria", json={"keywords": ["analyst"]}, headers=auth_headers)

        client.get("/feed", headers=auth_headers)
        client.get("/feed", headers=auth_headers)

        user_row = session.query(User).first()
        assert session.query(UserJobMatch).filter_by(user_id=user_row.id).count() == 1

    def test_match_status_update(self, session, auth_headers):
        self._seed_job(session, "Graduate Analyst", "Barclays", "London")
        client.post("/criteria", json={"keywords": ["analyst"]}, headers=auth_headers)

        feed = client.get("/feed", headers=auth_headers).json()
        match_id = feed["items"][0]["id"]

        r = client.patch(f"/matches/{match_id}", json={"status": "applied"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "applied"

    def test_cannot_update_another_users_match(self, session, auth_headers):
        self._seed_job(session, "Graduate Analyst", "Barclays", "London")
        client.post("/criteria", json={"keywords": ["analyst"]}, headers=auth_headers)
        feed = client.get("/feed", headers=auth_headers).json()
        match_id = feed["items"][0]["id"]

        other_user = client.post("/users", json={"email": "other2@example.com"}).json()
        other_headers = {"X-User-Id": other_user["id"]}

        r = client.patch(f"/matches/{match_id}", json={"status": "applied"}, headers=other_headers)
        assert r.status_code == 404

    def test_salary_min_excludes_lower_but_keeps_unparsed(self, session, auth_headers):
        self._seed_job(session, "Grad Role A", "Co A", "London", salary_min=20000)
        self._seed_job(session, "Grad Role B", "Co B", "London", salary_min=35000)
        self._seed_job(session, "Grad Role C", "Co C", "London", salary_min=None)  # unparsed

        client.post("/criteria", json={"salary_min": 30000}, headers=auth_headers)
        r = client.get("/feed", headers=auth_headers)
        titles = {item["job"]["title"] for item in r.json()["items"]}
        assert titles == {"Grad Role B", "Grad Role C"}  # A excluded, C kept despite missing data
