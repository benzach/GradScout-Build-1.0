"""
Stage 2 of the dedup pipeline: blocking.

Narrows down which existing jobs a new job should even be compared
against, BEFORE running the expensive fuzzy scoring in scoring.py. This
is the standard technique in record-linkage/entity-resolution systems
for making dedup tractable at scale — without it, adding one new job
means comparing it against every job ever stored, which is fine at 100
jobs and unworkable at 100,000.

In production this becomes a database query (WHERE normalized_company =
... AND posted_date BETWEEN ...) rather than an in-memory loop — the
function signature here is written so that swap is straightforward: it
takes a list of candidates and returns the filtered subset, so the
caller can decide whether that list came from a DB query or memory.
"""
from datetime import datetime, timedelta

from app.dedup.normalize import normalize_company
from app.dedup.scoring import fuzz, _try_parse_date

# How many days apart two postings can be and still be considered
# possibly-the-same-job. Wider than you might expect on purpose: a
# repost or an aggregator picking up a listing a week late is common,
# and blocking is meant to be a wide net — precision comes from the
# fuzzy scoring stage after this, not from being strict here.
DATE_WINDOW_DAYS = 14

# Company names don't always normalize identically even after
# normalize_company() (e.g. genuine typos, or one source using a
# subsidiary name) — so blocking uses a fuzzy company match above this
# threshold rather than requiring an exact string match.
COMPANY_BLOCK_THRESHOLD = 80


def find_candidates(new_job: dict, existing_jobs: list[dict]) -> list[dict]:
    """
    Returns the subset of existing_jobs worth running full fuzzy scoring
    against for new_job — same (fuzzy-matched) company, posted within
    DATE_WINDOW_DAYS of each other.
    """
    new_company_norm = normalize_company(new_job.get("company", ""))
    new_date = _try_parse_date(new_job.get("posted_date", ""))

    candidates = []
    for existing in existing_jobs:
        existing_company_norm = normalize_company(existing.get("company", ""))

        if not new_company_norm or not existing_company_norm:
            continue

        company_similarity = fuzz.ratio(new_company_norm, existing_company_norm)
        if company_similarity < COMPANY_BLOCK_THRESHOLD:
            continue

        # Date window check — only applied if both dates are actually
        # parseable. If either is missing, we don't exclude on that
        # basis alone (better to pass an extra candidate to fuzzy
        # scoring than to silently miss a real duplicate over a missing
        # date field).
        existing_date = _try_parse_date(existing.get("posted_date", ""))
        if new_date and existing_date:
            if abs((new_date - existing_date).days) > DATE_WINDOW_DAYS:
                continue

        candidates.append(existing)

    return candidates
