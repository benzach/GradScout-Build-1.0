"""
Tests for real Supabase JWT authentication (app/auth.py).

Since this sandbox has no real Supabase project to authenticate against,
these tests generate a genuine ES256 key pair (the same algorithm
Supabase uses) and simulate its JWKS endpoint — proving the actual
verification MECHANISM works correctly (signature checking, kid
matching, expiry, claims extraction, auto-provisioning) without needing
real Supabase credentials. Only the network fetch of the JWKS is mocked;
every line of cryptographic verification logic is genuinely exercised.
"""
import base64
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.security import HTTPAuthorizationCredentials

os.environ["SUPABASE_URL"] = "https://test-project.supabase.co"

from app.db import get_session
from app.models import User
import app.auth as auth_module
from app.auth import get_current_user


def _b64url(n: int, length: int = 32) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


@pytest.fixture
def key_pair():
    """A genuine ES256 key pair, playing the role of Supabase's signing keys for this test run."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    kid = "test-key-id"
    jwk = {
        "kid": kid, "kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
        "x": _b64url(public_numbers.x), "y": _b64url(public_numbers.y),
    }
    return {"private_key": private_key, "kid": kid, "jwks": {"keys": [jwk]}}


def _make_token(key_pair, sub=None, email="test@example.com", expired=False, aud="authenticated"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub or uuid4()), "email": email, "aud": aud,
        "exp": now - timedelta(minutes=5) if expired else now + timedelta(hours=1),
        "iat": now,
    }
    return jwt.encode(payload, key_pair["private_key"], algorithm="ES256", headers={"kid": key_pair["kid"]})


@pytest.fixture
def session():
    s = get_session()
    s.query(User).delete()
    s.commit()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def reset_jwks_cache():
    """Each test gets a clean JWKS cache — otherwise one test's mocked keys leak into the next."""
    auth_module._jwks_cache["keys_by_kid"] = {}
    auth_module._jwks_cache["fetched_at"] = 0.0
    yield


def _mock_jwks_response(key_pair):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = key_pair["jwks"]
    return resp


class TestAuth:
    def test_valid_token_creates_new_user(self, session, key_pair):
        user_id = uuid4()
        token = _make_token(key_pair, sub=user_id, email="new@example.com")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            user = get_current_user(credentials=creds, session=session)

        assert user.id == user_id
        assert user.email == "new@example.com"
        assert session.query(User).filter_by(id=user_id).count() == 1

    def test_second_request_reuses_existing_user_not_duplicate(self, session, key_pair):
        user_id = uuid4()
        token = _make_token(key_pair, sub=user_id)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            get_current_user(credentials=creds, session=session)
            get_current_user(credentials=creds, session=session)

        assert session.query(User).filter_by(id=user_id).count() == 1

    def test_expired_token_rejected(self, session, key_pair):
        from fastapi import HTTPException
        token = _make_token(key_pair, expired=True)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(credentials=creds, session=session)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_wrong_signing_key_rejected(self, session, key_pair):
        """A token signed by a DIFFERENT private key than the one in our JWKS must be rejected — this is the actual forgery-prevention check."""
        from fastapi import HTTPException

        forged_private_key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        forged_token = jwt.encode(
            {"sub": str(uuid4()), "email": "attacker@example.com", "aud": "authenticated",
             "exp": now + timedelta(hours=1), "iat": now},
            forged_private_key, algorithm="ES256",
            headers={"kid": key_pair["kid"]},  # claims to use our real key id, but signed with a different key
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged_token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(credentials=creds, session=session)
        assert exc_info.value.status_code == 401

    def test_wrong_audience_rejected(self, session, key_pair):
        from fastapi import HTTPException
        token = _make_token(key_pair, aud="something-else")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(credentials=creds, session=session)
        assert exc_info.value.status_code == 401

    def test_unrecognized_kid_rejected(self, session, key_pair):
        """A token whose kid isn't in our JWKS at all (e.g. a stale/bogus token) must be rejected, not crash."""
        from fastapi import HTTPException
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"sub": str(uuid4()), "aud": "authenticated", "exp": now + timedelta(hours=1), "iat": now},
            key_pair["private_key"], algorithm="ES256",
            headers={"kid": "totally-unknown-key-id"},
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(credentials=creds, session=session)
        assert exc_info.value.status_code == 401

    def test_jwks_cache_avoids_refetching_on_every_request(self, session, key_pair):
        """Proves the cache actually works — repeated requests with a known kid shouldn't hit the network again."""
        token = _make_token(key_pair)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch("app.auth.requests.get", return_value=_mock_jwks_response(key_pair)) as mock_get:
            get_current_user(credentials=creds, session=session)
            get_current_user(credentials=creds, session=session)
            get_current_user(credentials=creds, session=session)

        assert mock_get.call_count == 1  # cached after the first fetch
