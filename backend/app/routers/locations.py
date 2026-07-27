"""
Exposes the canonical location list (app/locations.py) to the frontend.

Deliberately a real endpoint rather than a value the frontend hardcodes
separately — the whole point of a finite-choice location filter is that
the options shown to a user must correspond exactly to values the
backend actually categorizes real jobs into. Fetching from here means
the two can never silently drift out of sync.

No auth required — this is static, non-sensitive reference data, useful
even on the login/signup screen before a user has a session yet.
"""
from fastapi import APIRouter

from app.locations import CANONICAL_LOCATIONS

router = APIRouter(tags=["locations"])


@router.get("/locations", response_model=list[str])
def list_locations():
    return CANONICAL_LOCATIONS
