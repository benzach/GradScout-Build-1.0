-- Migration 0003: add w4mpjobs, mistakenly omitted from the original
-- seed (0002) — my own recap message miscounted "6 live sources" when
-- it was actually 7. Written as a new migration rather than editing
-- 0002 in place, per the rule in backend/README.md: once a migration
-- has been applied against real data, it's a historical record, not
-- something to rewrite.

INSERT INTO sources (name, scraper_type, config, enabled) VALUES
('w4mpjobs', 'rss', '{"url": "https://www.w4mpjobs.org/RSS.aspx", "fetch_details": true, "detail_fetch_limit": 50}', true);
