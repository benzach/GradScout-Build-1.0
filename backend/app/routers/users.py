"""
User creation. In Phase 4, real signup happens through Supabase Auth
(email/magic-link/etc.) and this endpoint likely goes away entirely, or
becomes an internal-only "create app profile after Supabase signup"
step. For now, it exists purely so you can create a test user through
the interactive API docs without needing real auth built yet.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_db
from app.models import User
from app.schemas import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, session: Session = Depends(get_db)):
    existing = session.query(User).filter_by(email=payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    user = User(email=payload.email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
