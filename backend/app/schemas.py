"""
Pydantic schemas — the API's request/response contract.

Deliberately separate from app/models.py (the SQLAlchemy/database
models), even though they overlap a lot in fields. This separation
matters: the database schema can evolve (new internal columns, renamed
fields) without automatically changing what the API exposes to a
frontend, and vice versa — the API contract can add computed/derived
fields that don't exist as real columns at all.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

MatchStatus = Literal["new", "seen", "applied", "dismissed"]


# ---------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    subscription_tier: str
    created_at: datetime


# ---------------------------------------------------------------------
# Search criteria
# ---------------------------------------------------------------------

class SearchCriteriaCreate(BaseModel):
    label: str | None = None
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    contract_types: list[str] = Field(default_factory=list)
    sources_enabled: list[str] | None = None  # None = all sources
    active: bool = True


class SearchCriteriaUpdate(BaseModel):
    """All fields optional — PATCH semantics, only provided fields change."""
    label: str | None = None
    keywords: list[str] | None = None
    locations: list[str] | None = None
    salary_min: int | None = None
    contract_types: list[str] | None = None
    sources_enabled: list[str] | None = None
    active: bool | None = None


class SearchCriteriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    label: str | None
    keywords: list[str]
    locations: list[str]
    salary_min: int | None
    contract_types: list[str]
    sources_enabled: list[str] | None
    active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------

class JobSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site: str
    source_url: str
    scraped_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str
    location: str | None
    remote_type: str | None
    salary_text: str | None
    salary_min: int | None
    salary_max: int | None
    contract_type: str | None
    description: str | None
    posted_date: datetime | None
    first_seen_at: datetime
    sources: list[JobSourceOut] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Matches (a job matched against a user's criteria)
# ---------------------------------------------------------------------

class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job: JobOut
    status: MatchStatus
    matched_at: datetime
    notified_at: datetime | None


class MatchStatusUpdate(BaseModel):
    status: MatchStatus


class PaginatedFeed(BaseModel):
    items: list[MatchOut]
    total: int
    limit: int
    offset: int
