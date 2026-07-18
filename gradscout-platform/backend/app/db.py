"""
Database connection. Reads DATABASE_URL from environment; falls back to
the local dev database for testing.

In Phase 4, DATABASE_URL points at your real Supabase Postgres instance.
One gotcha worth knowing: Supabase (like Heroku and several other
hosts) hands you a connection string starting with `postgres://`, but
SQLAlchemy 1.4+ requires `postgresql://` — the two-character difference
is a real, common source of a deploy silently failing with a confusing
error. Handled here once, so it's never a surprise later.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://gradscout:localdev@localhost/gradscout_dev"
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    return SessionLocal()
