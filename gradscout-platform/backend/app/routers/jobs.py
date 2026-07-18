"""
Job feed: the endpoint that turns "a database full of jobs" into "jobs
this specific user actually cares about."

Design note worth understanding: this computes matches LIVE, at request
time, rather than waiting for Phase 5's scheduler to exist. It reuses
app/matching.py's pure filtering logic and "get-or-create" a
user_job_matches row for anything it finds — so a status update (mark as
seen/applied) always has a real row to attach to, and Phase 5 can later
call this exact same matching logic from a background job instead of a
request handler, without changing the underlying data model at all.

The tradeoff being made here, deliberately: recomputing matches on every
feed request is more work per request than reading pre-computed matches
would be. That's fine for now — correctness and a working end-to-end
loop first, matching the same philosophy as everything before this. Once
Phase 5's scheduler exists, it does this same computation in the
background on a timer, and this endpoint becomes a fast read of
already-materialized rows instead. That shift also matters for push
notifications specifically — you can't notify someone about something
that's only ever computed when they happen to open the app.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_db
from app.matching import compute_and_materialize_matches
from app.models import SearchCriteria, User, UserJobMatch
from app.routers.criteria import _get_owned_criteria
from app.schemas import MatchOut, MatchStatus, MatchStatusUpdate, PaginatedFeed

router = APIRouter(tags=["jobs"])


@router.get("/feed", response_model=PaginatedFeed)
def get_feed(
    limit: int = Query(20, le=100),
    offset: int = 0,
    status: MatchStatus | None = None,
    criteria_id: UUID | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if criteria_id:
        criteria_list = [_get_owned_criteria(session, criteria_id, user.id)]
    else:
        criteria_list = session.query(SearchCriteria).filter_by(user_id=user.id, active=True).all()

    if not criteria_list:
        return PaginatedFeed(items=[], total=0, limit=limit, offset=offset)

    matched_job_ids = compute_and_materialize_matches(session, user, criteria_list)

    query = (
        session.query(UserJobMatch)
        .filter_by(user_id=user.id)
        .filter(UserJobMatch.job_id.in_(matched_job_ids))
    )
    if status:
        query = query.filter_by(status=status)

    total = query.count()
    items = (
        query.order_by(UserJobMatch.matched_at.desc())
        .offset(offset).limit(limit).all()
    )

    return PaginatedFeed(items=items, total=total, limit=limit, offset=offset)


@router.patch("/matches/{match_id}", response_model=MatchOut)
def update_match_status(
    match_id: UUID,
    payload: MatchStatusUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    match = session.get(UserJobMatch, match_id)
    if not match or match.user_id != user.id:
        raise HTTPException(status_code=404, detail="Match not found")

    match.status = payload.status
    session.commit()
    session.refresh(match)
    return match
