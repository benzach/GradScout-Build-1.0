-- GradScout initial schema
-- Migration 0001

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- ============================================================
-- sources: registry of scrapeable job sources.
--
-- Deliberately data-driven rather than hardcoded, so new sources that
-- fit an EXISTING scraper_type (another RSS feed, another static HTML
-- board, another Adzuna-style API) can be added with an INSERT here —
-- no code deploy required. A genuinely new source TYPE (a new API
-- shape we've never seen) still needs one new scraper class in code,
-- but that's the only case that does.
-- ============================================================
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,              -- e.g. 'adzuna', 'reed', 'acca'
    scraper_type TEXT NOT NULL,             -- maps to a Python scraper class in the registry
    config JSONB NOT NULL DEFAULT '{}',     -- per-source settings: keywords, URL, selectors, etc.
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_scraped_at TIMESTAMPTZ,
    last_scrape_status TEXT,                -- 'success' | 'failed' | NULL (never run)
    last_scrape_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- users: for local dev, self-contained. In Phase 4 (Supabase) this
-- becomes a 'profiles' table with id referencing Supabase's own
-- auth.users(id) instead — Supabase manages authentication, we manage
-- everything app-specific about a user.
-- ============================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    subscription_tier TEXT NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- search_criteria: a user can save multiple criteria sets
-- (e.g. "software grad roles" and "marketing grad roles" separately)
-- ============================================================
CREATE TABLE search_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label TEXT,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    locations TEXT[] NOT NULL DEFAULT '{}',
    salary_min INTEGER,
    contract_types TEXT[] NOT NULL DEFAULT '{}',
    sources_enabled TEXT[],                 -- NULL = all sources; else restrict to named sources
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_search_criteria_user_id ON search_criteria(user_id);

-- ============================================================
-- jobs: CANONICAL, deduplicated job records — the output of the dedup
-- engine (Phase 0). One row here can represent multiple original
-- postings (see job_sources below).
-- ============================================================
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    company TEXT NOT NULL,
    normalized_company TEXT NOT NULL,
    location TEXT,
    normalized_location TEXT,
    remote_type TEXT,                       -- 'remote' | 'hybrid' | 'on-site' | ''
    salary_text TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    contract_type TEXT,
    description TEXT,
    posted_date TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Set when the dedup engine's decision was "flag_for_review": the
    -- job stays as its own row (never silently merged on a guess) but
    -- is linked to what it might be a duplicate of, for a future admin
    -- review view.
    possible_duplicate_of UUID REFERENCES jobs(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_normalized_company ON jobs(normalized_company);
CREATE INDEX idx_jobs_posted_date ON jobs(posted_date);
CREATE INDEX idx_jobs_possible_duplicate_of ON jobs(possible_duplicate_of);
CREATE INDEX idx_jobs_salary_min ON jobs(salary_min);

-- ============================================================
-- job_sources: every ORIGINAL posting, many-to-one to a canonical job.
-- This is what preserves every apply link after a merge, and enables a
-- cheap EXACT-duplicate check (same site, same URL) before the fuzzy
-- dedup engine ever needs to run — most re-scrapes of an already-seen
-- posting get caught here for free.
-- ============================================================
CREATE TABLE job_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    site TEXT NOT NULL REFERENCES sources(name),
    source_url TEXT NOT NULL,
    source_job_id TEXT,                     -- the source's own internal ID, if it has one
    raw_title TEXT NOT NULL,                -- original unnormalized title, kept for transparency
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site, source_url)
);
CREATE INDEX idx_job_sources_job_id ON job_sources(job_id);

-- ============================================================
-- user_job_matches: which canonical jobs matched which user's criteria
-- ============================================================
CREATE TABLE user_job_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    matched_criteria_id UUID REFERENCES search_criteria(id) ON DELETE SET NULL,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notified_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'new',     -- 'new' | 'seen' | 'applied' | 'dismissed'
    UNIQUE (user_id, job_id)
);
CREATE INDEX idx_user_job_matches_user_id ON user_job_matches(user_id);
CREATE INDEX idx_user_job_matches_status ON user_job_matches(status);
