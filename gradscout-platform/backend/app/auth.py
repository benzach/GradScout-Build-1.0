"""
STUB authentication — deliberately simple, deliberately temporary.

Real auth (verifying a Supabase-issued JWT, extracting the user ID from
it) is Phase 4's job, once you have a real Supabase project to verify
tokens against. Building that now would mean mocking a cloud service
that doesn't exist yet in this sandbox.

What matters is that get_current_user() is the ONLY place in the entire
API that knows how "who is this request from" gets decided. Every
endpoint depends on this function, not on header-reading logic of its
own — so when Phase 4 arrives, this file is the only thing that changes.
No endpoint, no route, no business logic elsewhere needs to be touched.

For now: pass a real user's UUID in an `X-User-Id` header. Missing or
unknown IDs get a 401, same as real auth would give for an invalid
token — so callers of this API (including the future frontend) don't
need to know or care that this is a stub.
"""
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    x_user_id: str = Header(..., description="STUB AUTH: pass a user's UUID directly. Replaced by real JWT auth in Phase 4."),
    session: Session = Depends(get_db),
) -> User:
    try:
        user_id = UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="X-User-Id must be a valid UUID")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user
