"""
Real authentication — verifies a Supabase-issued JWT via JWKS (the
current recommended approach; Supabase explicitly advises against the
older shared-secret method). Replaces the stub from earlier phases.

Deliberately keeps get_current_user()'s signature and return type
(still just `-> User`) identical to the stub it replaces — every router
in this codebase depends on `Depends(get_current_user)` and none of them
needed to change for this. That was the entire point of building the
stub as its own isolated file back in Phase 3.

How it works:
  1. Frontend authenticates with Supabase directly (magic link, email/
     password, etc.) and gets back a JWT.
  2. Frontend sends that JWT as a standard `Authorization: Bearer <token>`
     header on every API request — no more custom X-User-Id header.
  3. This module verifies the token's signature against Supabase's
     public keys (fetched from the project's JWKS endpoint, cached in
     memory, refreshed only when an unrecognized key id shows up — e.g.
     after Supabase rotates keys), confirms it hasn't expired, and reads
     the verified `sub` claim as the user's ID.
  4. First time a given Supabase user hits this API, there's no
     matching row in our own `users` table yet — one is created
     automatically (same UUID as Supabase's, so the two stay in sync
     with no separate signup step to keep consistent). Every request
     after that just looks the row up.

Requires SUPABASE_URL (e.g. https://abcdefgh.supabase.co) as an
environment variable — used to build the JWKS endpoint URL.
"""
import os
import time
from uuid import UUID

import jwt
import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
JWKS_CACHE_TTL_SECONDS = 600  # matches Supabase's own edge cache for this endpoint

_jwks_cache: dict = {"keys_by_kid": {}, "fetched_at": 0.0}

security = HTTPBearer()


def _fetch_jwks() -> dict:
    """Fetches and caches Supabase's public signing keys, keyed by `kid`."""
    resp = requests.get(JWKS_URL, timeout=10)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    return {k["kid"]: k for k in keys if "kid" in k}


def _get_signing_key(kid: str):
    """
    Returns the public key matching a token's `kid`, using the cache
    unless it's stale or the kid isn't in it yet (handles Supabase
    rotating keys without needing a deploy on our end — the next
    request with a new kid just triggers a fresh fetch).
    """
    now = time.time()
    cache_stale = (now - _jwks_cache["fetched_at"]) > JWKS_CACHE_TTL_SECONDS
    if kid not in _jwks_cache["keys_by_kid"] or cache_stale:
        _jwks_cache["keys_by_kid"] = _fetch_jwks()
        _jwks_cache["fetched_at"] = now

    jwk_dict = _jwks_cache["keys_by_kid"].get(kid)
    if not jwk_dict:
        raise HTTPException(status_code=401, detail="Token signed with an unrecognized key")
    return jwt.PyJWK(jwk_dict).key


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_db),
) -> User:
    if not JWKS_URL:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured on the server")

    token = credentials.credentials
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Token missing key id")

        signing_key = _get_signing_key(kid)
        claims = jwt.decode(
            token, signing_key,
            algorithms=["ES256", "RS256"],  # Supabase's current asymmetric options
            audience="authenticated",  # Supabase's standard audience for logged-in users
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    user_id = UUID(claims["sub"])
    user = session.get(User, user_id)
    if not user:
        # First time this Supabase user has hit the API — provision
        # their app-side profile row now, same UUID as Supabase's own,
        # so no separate signup endpoint is needed.
        user = User(id=user_id, email=claims.get("email", ""))
        session.add(user)
        session.commit()
        session.refresh(user)

    return user
