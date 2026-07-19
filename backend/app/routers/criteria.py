"""
Search criteria CRUD. A user can save multiple criteria sets — see the
schema note in migrations/0001_initial_schema.sql for why (e.g. separate
"software grad roles" and "marketing grad roles" searches).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_db
from app.models import SearchCriteria, User
from app.schemas import SearchCriteriaCreate, SearchCriteriaOut, SearchCriteriaUpdate

router = APIRouter(prefix="/criteria", tags=["search criteria"])


@router.post("", response_model=SearchCriteriaOut, status_code=201)
def create_criteria(
    payload: SearchCriteriaCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    criteria = SearchCriteria(user_id=user.id, **payload.model_dump())
    session.add(criteria)
    session.commit()
    session.refresh(criteria)
    return criteria


@router.get("", response_model=list[SearchCriteriaOut])
def list_criteria(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    return session.query(SearchCriteria).filter_by(user_id=user.id).all()


@router.get("/{criteria_id}", response_model=SearchCriteriaOut)
def get_criteria(
    criteria_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    criteria = _get_owned_criteria(session, criteria_id, user.id)
    return criteria


@router.patch("/{criteria_id}", response_model=SearchCriteriaOut)
def update_criteria(
    criteria_id: UUID,
    payload: SearchCriteriaUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    criteria = _get_owned_criteria(session, criteria_id, user.id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(criteria, field, value)
    session.commit()
    session.refresh(criteria)
    return criteria


@router.delete("/{criteria_id}", status_code=204)
def delete_criteria(
    criteria_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    criteria = _get_owned_criteria(session, criteria_id, user.id)
    session.delete(criteria)
    session.commit()


def _get_owned_criteria(session: Session, criteria_id: UUID, user_id: UUID) -> SearchCriteria:
    """
    Looks up a criteria row AND confirms it belongs to the requesting
    user — a 404 either way (not found, or belongs to someone else)
    rather than a 403, so requests can't be used to probe which IDs
    exist for other users.
    """
    criteria = session.get(SearchCriteria, criteria_id)
    if not criteria or criteria.user_id != user_id:
        raise HTTPException(status_code=404, detail="Search criteria not found")
    return criteria
