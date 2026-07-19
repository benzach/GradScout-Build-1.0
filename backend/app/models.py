"""
SQLAlchemy models — one class per table in migrations/0001_initial_schema.sql.

These are a direct mirror of the SQL schema, not a separate source of
truth. If you ever change one, change the other and write a new
migration file (numbered, e.g. 0003_...) rather than editing 0001 in
place — that's how real schema evolution works once there's live data
to preserve.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Source(Base):
    """A scrapeable job source — see the extensive comment in the migration file."""
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    scraper_type = Column(Text, nullable=False)
    config = Column(JSONB, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    last_scraped_at = Column(DateTime(timezone=True))
    last_scrape_status = Column(Text)
    last_scrape_error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    subscription_tier = Column(Text, nullable=False, default="free")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    search_criteria = relationship("SearchCriteria", back_populates="user", cascade="all, delete-orphan")
    matches = relationship("UserJobMatch", back_populates="user", cascade="all, delete-orphan")


class SearchCriteria(Base):
    __tablename__ = "search_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = Column(Text)
    keywords = Column(ARRAY(Text), nullable=False, default=list)
    locations = Column(ARRAY(Text), nullable=False, default=list)
    salary_min = Column(Integer)
    contract_types = Column(ARRAY(Text), nullable=False, default=list)
    sources_enabled = Column(ARRAY(Text))  # NULL = all sources
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="search_criteria")


class Job(Base):
    """Canonical, deduplicated job record — the output of the dedup engine."""
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    normalized_title = Column(Text, nullable=False)
    company = Column(Text, nullable=False)
    normalized_company = Column(Text, nullable=False)
    location = Column(Text)
    normalized_location = Column(Text)
    remote_type = Column(Text)
    salary_text = Column(Text)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    contract_type = Column(Text)
    description = Column(Text)
    posted_date = Column(DateTime(timezone=True))
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    possible_duplicate_of = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    sources = relationship("JobSource", back_populates="job", cascade="all, delete-orphan")


class JobSource(Base):
    """Every original posting for a canonical job — preserves all apply links."""
    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("site", "source_url", name="uq_job_sources_site_url"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    site = Column(Text, ForeignKey("sources.name"), nullable=False)
    source_url = Column(Text, nullable=False)
    source_job_id = Column(Text)
    raw_title = Column(Text, nullable=False)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="sources")


class UserJobMatch(Base):
    __tablename__ = "user_job_matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_matches_user_job"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    matched_criteria_id = Column(UUID(as_uuid=True), ForeignKey("search_criteria.id", ondelete="SET NULL"))
    matched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    notified_at = Column(DateTime(timezone=True))
    status = Column(Text, nullable=False, default="new")

    user = relationship("User", back_populates="matches")
    job = relationship("Job")
