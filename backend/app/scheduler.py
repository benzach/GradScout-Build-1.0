"""
The scheduler — this is what turns "an API that answers when asked"
into "a system that watches constantly," which was the original point
of moving off the prototype's once-a-day GitHub Actions cron.

Runs INSIDE the same process as the FastAPI app (via APScheduler's
BackgroundScheduler, a thread, not a separate service) — so deploying
this is just deploying the API as normal; there's no second Railway
service to configure. It wakes up on an interval and does exactly two
things, using logic that already exists and is already tested:

  1. app.pipeline.run_pipeline() — scrape every enabled source, dedup,
     store (Phase 2, unchanged).
  2. app.matching.compute_and_materialize_matches() — for every user
     with at least one active criteria set, check their criteria against
     recent jobs and materialize any new matches (Phase 3, unchanged,
     now called by a timer instead of only by someone loading the feed).

Nothing about the underlying data model changes for this phase — the
scheduler is a new CALLER of code that already exists, not new business
logic. That's deliberate: it's the payoff of building compute_and_materialize_matches
as a shared, reusable function back in Phase 3/the jobs.py refactor.
"""
import os
import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import get_session
from app.matching import compute_and_materialize_matches
from app.models import SearchCriteria, User
from app.pipeline import run_pipeline

SCRAPE_INTERVAL_MINUTES = int(os.environ.get("SCRAPE_INTERVAL_MINUTES", "20"))

_scheduler: BackgroundScheduler | None = None


def run_scheduled_cycle() -> dict:
    """
    One full cycle: scrape -> dedup -> store -> materialize matches for
    every user. Returns a summary dict — used directly by tests, and
    printed (Railway captures stdout as logs) so failures are visible,
    not silent, per the roadmap's explicit requirement for this phase.
    """
    started_at = datetime.now(timezone.utc)
    session = get_session()
    summary = {"started_at": started_at.isoformat(), "pipeline": None, "users_processed": 0, "match_errors": []}

    try:
        summary["pipeline"] = run_pipeline(session)
        print(f"[scheduler] pipeline: {summary['pipeline']}")

        # Every user with at least one active criteria set gets checked.
        # A single query for "which user_ids have an active criteria row"
        # rather than looping all users, since most of the work (the
        # actual matching) is per-criteria-set anyway.
        user_ids_with_active_criteria = {
            row[0] for row in session.query(SearchCriteria.user_id).filter_by(active=True).distinct()
        }

        for user_id in user_ids_with_active_criteria:
            user = session.get(User, user_id)
            if not user:
                continue
            criteria_list = session.query(SearchCriteria).filter_by(user_id=user_id, active=True).all()
            try:
                compute_and_materialize_matches(session, user, criteria_list)
                summary["users_processed"] += 1
            except Exception as e:
                # One user's matching logic failing (e.g. a data
                # oddity in their criteria) shouldn't stop everyone
                # else's matches from being computed — same
                # failure-isolation principle as run_pipeline's
                # per-source handling in Phase 2.
                print(f"[scheduler] match computation failed for user {user_id}: {e}")
                summary["match_errors"].append({"user_id": str(user_id), "error": str(e)})

    except Exception as e:
        print(f"[scheduler] cycle failed entirely: {e}")
        traceback.print_exc()
        summary["fatal_error"] = str(e)
    finally:
        session.close()

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(f"[scheduler] cycle complete: {summary}")
    return summary


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler  # already running — don't start a second one

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_scheduled_cycle,
        trigger=IntervalTrigger(minutes=SCRAPE_INTERVAL_MINUTES),
        id="scrape_and_match_cycle",
        next_run_time=datetime.now(timezone.utc),  # run once immediately on startup, then on the interval
        max_instances=1,  # never let two cycles overlap if one runs long
    )
    _scheduler.start()
    print(f"[scheduler] started — running every {SCRAPE_INTERVAL_MINUTES} minute(s)")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print("[scheduler] stopped")
