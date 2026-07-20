"""
Tests for the full API surface: search criteria CRUD and the job feed
(the part that actually proves criteria filtering + the get-or-create
match pattern work correctly through real HTTP requests, not just
direct function calls).

Uses the same JWT-generation pattern as test_auth.py — a genuine ES256
key pair standing in for Supabase's, exercising the real auth flow
end-to-end rather than the old X-User-Id stub.
"""
import base64
import os
os.environ["DISABLE_SCHEDULER"] = "true"  # must be set before importing app.main
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_session
from app.models import Job, JobSource, SearchCriteria, User, UserJobMatch
import app.auth as auth_module

client = TestClient(app)


def _b64url(n: int, length: int = 32) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    kid = "test-key-id"
    jwk = {
        "kid": kid, "kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
        "x": _b64url(public_numbers.x), "y": _b64url(public_numbers.y),
    }
    return {"private_key": private_key, "kid": kid, "jwks": {"keys": [jwk]}}


def _make_token(key_pair, sub=None, email="test@example.com"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub or uuid4()), "email": email, "aud": "authenticated",
        "exp": now + timedelta(hours=1), "iat": now,
    }
    return jwt.encode(payload, key_pair["private_key"], algorithm="ES256", headers={"kid": key_pair["kid"]})


@pytest.fixture(autouse=True)
def mock_jwks(key_pair):
    """Every test in this file gets its Authorization Bearer tokens verified against the shared test key pair, not a real Supabase project."""
    auth_module._jwks_cache["keys_by_kid"] = {}
    auth_module._jwks_cache["fetched_at"] = 0.0
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = key_pair["jwks"]
    with patch("app.auth.requests.get", return_value=resp):
        yield


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
def auth_headers(session, key_pair):
    """A fresh user, provisioned automatically on their first authenticated request — exactly like a real new signup."""
    token = _make_token(key_pair)
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_missing_token_rejected(self, session):
        r = client.get("/criteria")
        assert r.status_code == 401  # HTTPBearer's actual default for a missing Authorization header

    def test_malformed_token_rejected(self, session):
        r = client.get("/criteria", headers={"Authorization": "Bearer not-a-real-jwt"})
        assert r.status_code == 401

    def test_token_signed_by_unknown_key_rejected(self, session, key_pair):
        forged_key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"sub": str(uuid4()), "aud": "authenticated", "exp": now + timedelta(hours=1), "iat": now},
            forged_key, algorithm="ES256", headers={"kid": key_pair["kid"]},
        )
        r = client.get("/criteria", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    def test_valid_token_auto_provisions_user(self, session, key_pair):
        token = _make_token(key_pair, email="brandnew@example.com")
        r = client.get("/criteria", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200  # succeeds even though this user never existed before
        assert session.query(User).filter_by(email="brandnew@example.com").count() == 1


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

    def test_cannot_access_another_users_criteria(self, session, auth_headers, key_pair):
        r = client.post("/criteria", json={"keywords": ["x"]}, headers=auth_headers)
        criteria_id = r.json()["id"]

        other_token = _make_token(key_pair, email="other@example.com")
        other_headers = {"Authorization": f"Bearer {other_token}"}

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

    def test_cannot_update_another_users_match(self, session, auth_headers, key_pair):
        self._seed_job(session, "Graduate Analyst", "Barclays", "London")
        client.post("/criteria", json={"keywords": ["analyst"]}, headers=auth_headers)
        feed = client.get("/feed", headers=auth_headers).json()
        match_id = feed["items"][0]["id"]

        other_token = _make_token(key_pair, email="other2@example.com")
        other_headers = {"Authorization": f"Bearer {other_token}"}

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
