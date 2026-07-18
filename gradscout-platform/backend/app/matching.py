"""
Matching logic: does a given job satisfy a user's saved search criteria?

Worth noting how this differs from the dedup engine (app/dedup/): that
was deliberately pure, DB-independent Python because it was the riskiest,
most novel piece of the whole system and needed to be testable in total
isolation. This module is simpler, well-understood business logic
(keyword/location/salary filtering — the same shape of logic the
original prototype's core/filters.py already proved out), so it's fine
for it to operate directly on SQLAlchemy objects rather than maintaining
that same strict separation. Not every module needs the same rigor —
matching the level of caution to the level of actual risk/novelty.

Matching semantics (see conversation for the product-decision framing):
  - keywords: ANY match (OR), checked against title + description
  - locations: ANY match (OR), checked against the job's location string
  - contract_types: ANY match (OR), checked against the job's contract_type tags
  - salary_min: job's salary must meet the threshold IF it has a parsed
    salary at all — jobs with no parseable salary are KEPT, not excluded,
    since missing data shouldn't count against a job (same philosophy as
    the prototype's filter engine)
  - sources_enabled: if set, only jobs from one of those specific sites
    match; if None (the default), all sources are eligible
"""
from app.models import Job, SearchCriteria, User, UserJobMatch


def job_matches_criteria(job: Job, criteria: SearchCriteria) -> bool:
    haystack = f"{job.title} {job.description or ''}".lower()

    if criteria.keywords:
        if not any(kw.lower() in haystack for kw in criteria.keywords):
            return False

    if criteria.locations:
        location = (job.location or "").lower()
        if not any(loc.lower() in location for loc in criteria.locations):
            return False

    if criteria.contract_types:
        job_contract = (job.contract_type or "").lower()
        if not any(ct.lower() in job_contract for ct in criteria.contract_types):
            return False

    if criteria.salary_min:
        # Use whichever of min/max the job actually has; if genuinely
        # unparseable, don't exclude — see module docstring.
        job_salary = job.salary_min or job.salary_max
        if job_salary is not None and job_salary < criteria.salary_min:
            return False

    if criteria.sources_enabled:
        job_sites = {s.site for s in job.sources}
        if not job_sites & set(criteria.sources_enabled):
            return False

    return True


def filter_jobs_for_criteria(jobs: list[Job], criteria: SearchCriteria) -> list[Job]:
    return [j for j in jobs if job_matches_criteria(j, criteria)]


def filter_jobs_for_any_active_criteria(jobs: list[Job], criteria_list: list[SearchCriteria]) -> dict:
    """
    For the aggregated "your whole feed" view: returns a dict mapping
    job.id -> the FIRST criteria that matched it (used to record
    matched_criteria_id), for every job that matches at least one of the
    user's active criteria sets. A job matching multiple criteria sets
    still only needs one user_job_matches row — the user only needs to
    see it once.
    """
    matches: dict = {}
    for job in jobs:
        for criteria in criteria_list:
            if job_matches_criteria(job, criteria):
                matches[job.id] = criteria
                break
    return matches


CANDIDATE_POOL_WINDOW_DAYS = 60


def compute_and_materialize_matches(session, user: User, criteria_list: list[SearchCriteria]) -> list:
    """
    Runs matching against recent jobs, ensures a user_job_matches row
    exists for every hit. Returns the matched job IDs.

    Moved here (from app/routers/jobs.py, where it started life) once a
    second caller needed it: the Phase 5 scheduler calls this for every
    user with active criteria on a timer, and the live /feed endpoint
    still calls it too, for whoever happens to load the app between
    scheduler runs. Same function, same behavior, two different
    triggers — which is exactly the point of building it this way from
    the start (see the module docstring in app/routers/jobs.py history).
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=CANDIDATE_POOL_WINDOW_DAYS)
    candidate_jobs = (
        session.query(Job)
        .filter((Job.posted_date == None) | (Job.posted_date >= cutoff))  # noqa: E711
        .all()
    )

    matched = filter_jobs_for_any_active_criteria(candidate_jobs, criteria_list)

    existing_job_ids = {
        m.job_id for m in session.query(UserJobMatch.job_id).filter_by(user_id=user.id).all()
    }
    for job_id, matched_criteria in matched.items():
        if job_id not in existing_job_ids:
            session.add(UserJobMatch(
                user_id=user.id, job_id=job_id,
                matched_criteria_id=matched_criteria.id, status="new",
            ))
    session.commit()

    return list(matched.keys())
