"""
Top-level dedup engine — orchestrates normalize -> block -> score -> decide.

This is the single entry point the rest of the backend calls. Everything
in normalize.py / blocking.py / scoring.py is an implementation detail
this module composes.
"""
from dataclasses import dataclass

from app.dedup.blocking import find_candidates
from app.dedup.scoring import compute_match, MatchResult


@dataclass
class DedupOutcome:
    new_job: dict
    best_match: dict | None
    match_result: MatchResult | None
    action: str  # "insert_new" | "merge" | "flag_for_review"


def dedup_against_existing(new_job: dict, existing_jobs: list[dict]) -> DedupOutcome:
    """
    Checks a newly-scraped job against the pool of existing jobs and
    decides what to do with it.

    Returns a DedupOutcome describing the action to take:
      - "insert_new": no meaningful match found, store as a new canonical job
      - "merge": high-confidence match found, link as another source on
                 the existing canonical job rather than creating a new one
      - "flag_for_review": medium-confidence match — kept as its own
                 record for now, but linked for a human/admin view to
                 confirm later. Never silently guesses on ambiguous cases.
    """
    candidates = find_candidates(new_job, existing_jobs)

    best_match = None
    best_result = None

    for candidate in candidates:
        result = compute_match(new_job, candidate)
        if best_result is None or result.composite_score > best_result.composite_score:
            best_match = candidate
            best_result = result

    if best_result is None:
        return DedupOutcome(new_job=new_job, best_match=None, match_result=None, action="insert_new")

    if best_result.decision == "auto_merge":
        return DedupOutcome(new_job=new_job, best_match=best_match, match_result=best_result, action="merge")
    elif best_result.decision == "possible_duplicate":
        return DedupOutcome(new_job=new_job, best_match=best_match, match_result=best_result, action="flag_for_review")
    else:
        return DedupOutcome(new_job=new_job, best_match=None, match_result=best_result, action="insert_new")
