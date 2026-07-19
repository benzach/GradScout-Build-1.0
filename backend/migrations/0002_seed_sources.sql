-- Seed data: the 6 sources already built and working from the prototype.
-- Adding a 7th source later that fits one of these scraper_types is
-- just another INSERT here — no migration needed.

INSERT INTO sources (name, scraper_type, config, enabled) VALUES
('adzuna', 'adzuna', '{"what": "graduate", "where": "uk", "results_per_page": 50, "max_pages": 3}', true),
('reed', 'reed', '{"graduate_only": true, "results_to_take": 100}', true),
('jooble', 'jooble', '{"keywords": "graduate", "location": "United Kingdom", "results_on_page": 50, "max_pages": 3}', true),
('charityjob', 'static', '{"url": "https://www.charityjob.co.uk/project-officer-jobs-in-london", "parser": "parse_charityjob"}', true),
('acca', 'static', '{"url": "https://jobs.accaglobal.com/jobs/entry-level/", "parser": "parse_acca"}', true),
('thirdsector', 'static', '{"url": "https://jp.thirdsector.co.uk/jobs", "parser": "parse_thirdsector"}', true);
