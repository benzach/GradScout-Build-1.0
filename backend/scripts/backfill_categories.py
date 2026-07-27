"""
One-off backfill: sets location_category AND industry_category on every
existing job row.

Needed because migrations only add columns — they can't populate them,
since both categorization functions are Python logic (regex/keyword
matching), not expressible as plain SQL UPDATEs. Run this once, after
applying migrations 0004 and 0005, against whichever database has real
data that predates these features (your Supabase production database,
most likely).

Also worth re-running after the location taxonomy expanded from 20 to
52 categories — existing jobs categorized under the old, coarser
taxonomy (e.g. a Brighton job that fell into "Other UK" because
"Brighton" wasn't a category yet) benefit from being recategorized
under the new, more specific one.

Usage:
    DATABASE_URL=<your real Supabase connection string> python -m scripts.backfill_categories

Safe to re-run — recomputes and overwrites both category columns for
every job each time, so running it twice just does redundant work, not
harm.
"""
from app.db import get_session
from app.locations import categorize_location
from app.industries import categorize_industry
from app.models import Job


def backfill():
    session = get_session()
    jobs = session.query(Job).all()
    print(f"Found {len(jobs)} job(s) to categorize...")

    location_counts: dict[str, int] = {}
    industry_counts: dict[str, int] = {}

    for job in jobs:
        location_cat = categorize_location(job.location or "", job.remote_type or "")
        industry_cat = categorize_industry(job.title or "", job.description or "")
        job.location_category = location_cat
        job.industry_category = industry_cat
        location_counts[location_cat] = location_counts.get(location_cat, 0) + 1
        industry_counts[industry_cat] = industry_counts.get(industry_cat, 0) + 1

    session.commit()
    session.close()

    print("\nDone. Location breakdown:")
    for category, count in sorted(location_counts.items(), key=lambda x: -x[1]):
        print(f"  {category:18} {count}")

    print("\nIndustry breakdown:")
    for category, count in sorted(industry_counts.items(), key=lambda x: -x[1]):
        print(f"  {category:26} {count}")


if __name__ == "__main__":
    backfill()
