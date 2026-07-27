"""
Exposes the canonical industry list (app/industries.py) to the frontend.
Mirrors app/routers/locations.py — same reasoning, same "fetch from
here rather than hardcode a copy" principle.
"""
from fastapi import APIRouter

from app.industries import CANONICAL_INDUSTRIES

router = APIRouter(tags=["industries"])


@router.get("/industries", response_model=list[str])
def list_industries():
    return CANONICAL_INDUSTRIES
