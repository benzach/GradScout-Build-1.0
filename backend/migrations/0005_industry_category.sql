-- Migration 0005: industry categorization + expanded location taxonomy.
--
-- Adds industry_category to jobs (populated at storage time by
-- app/industries.py's categorize_industry(), mirroring how
-- location_category works). Also adds `industries` to search_criteria,
-- the new filter dimension alongside keywords/locations/contract_types.
--
-- The expanded location list itself (52 locations, up from 20) needed
-- no schema change — location_category was always a plain TEXT column,
-- so new category values are just new possible strings in the same
-- column. Existing jobs categorized under the old 20-location taxonomy
-- should be re-backfilled (see scripts/backfill_categories.py) so they
-- can benefit from the new, more specific categories where applicable.

ALTER TABLE jobs ADD COLUMN industry_category TEXT;
CREATE INDEX idx_jobs_industry_category ON jobs(industry_category);

ALTER TABLE search_criteria ADD COLUMN industries TEXT[] NOT NULL DEFAULT '{}';
