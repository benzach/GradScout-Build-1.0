"""
Test suite for the dedup engine. Each test captures a scenario that
matters for a real graduate job platform — not just "does the code run"
but "does it make the right call on cases that actually come up."
"""
from app.dedup.engine import dedup_against_existing
from app.dedup.normalize import normalize_title, normalize_company, normalize_location


class TestNormalization:
    def test_title_strips_remote_tag_both_formats(self):
        assert normalize_title("Software Engineer - Remote") == ("software engineer", "remote")
        assert normalize_title("Software Developer (Remote)") == ("software developer", "remote")

    def test_company_normalizes_legal_suffixes(self):
        assert normalize_company("Google LLC") == normalize_company("Google") == "google"
        assert normalize_company("Foo Group Ltd") == "foo"

    def test_company_keeps_meaningful_regional_qualifiers(self):
        # "UK" is not a legal suffix - stripping it could conflate
        # distinct regional entities of the same parent company.
        assert normalize_company("Deloitte UK") == "deloitte uk"

    def test_location_extracts_remote_signal(self):
        assert normalize_location("London (Remote)") == ("london", "remote")
        assert normalize_location("Leeds - Hybrid") == ("leeds", "hybrid")


class TestDedupEngine:
    def test_same_job_different_wording_merges(self):
        """The core case this system exists to catch: same job, described differently by two sources."""
        existing = [{
            "title": "Software Engineer - Remote",
            "company": "Google LLC",
            "location": "London (Remote)",
            "salary": "£45,000 - £55,000",
            "description": "We are looking for a talented software engineer to join our growing team in London. You will work on scalable backend systems.",
            "posted_date": "2026-07-10",
        }]
        new_job = {
            "title": "Software Developer (Remote)",
            "company": "Google",
            "location": "London (Remote)",
            "salary": "£46,000 - £54,000",
            "description": "We are looking for a talented software developer to join our growing team in London. You will work on scalable backend systems.",
            "posted_date": "2026-07-11",
        }
        outcome = dedup_against_existing(new_job, existing)
        assert outcome.action == "merge"

    def test_different_seniority_same_company_stays_distinct(self):
        """Guards against false positives: similar titles, same company, but genuinely different roles."""
        existing = [{
            "title": "Graduate Software Engineer",
            "company": "Google",
            "location": "London",
            "salary": "£45,000",
            "description": "Join our infrastructure team building distributed systems that power search at massive scale across the globe.",
            "posted_date": "2026-07-10",
        }]
        new_job = {
            "title": "Senior Software Engineer",
            "company": "Google",
            "location": "London",
            "salary": "£85,000",
            "description": "Lead a team of engineers developing our advertising platform, working closely with product managers on strategy.",
            "posted_date": "2026-07-10",
        }
        outcome = dedup_against_existing(new_job, existing)
        assert outcome.action == "insert_new"

    def test_identical_title_different_companies_never_compared(self):
        """Common for grad roles - every bank has a 'Graduate Analyst'. Blocking should reject before scoring."""
        existing = [{
            "title": "Graduate Analyst",
            "company": "Barclays",
            "location": "London",
            "salary": "£35,000",
            "description": "Join our graduate scheme working across our investment banking division.",
            "posted_date": "2026-07-10",
        }]
        new_job = {
            "title": "Graduate Analyst",
            "company": "HSBC",
            "location": "London",
            "salary": "£34,000",
            "description": "Join our graduate scheme working across our investment banking division.",
            "posted_date": "2026-07-10",
        }
        outcome = dedup_against_existing(new_job, existing)
        assert outcome.action == "insert_new"
        assert outcome.match_result is None  # never scored - blocked out entirely

    def test_ambiguous_case_flagged_not_guessed(self):
        """Genuinely uncertain cases should be flagged for review, never silently auto-decided either way."""
        existing = [{
            "title": "Graduate Marketing Executive",
            "company": "Unilever",
            "location": "London",
            "salary": "£28,000",
            "description": "Join our fast-paced marketing team working on some of the biggest consumer brands in the world today.",
            "posted_date": "2026-07-01",
        }]
        new_job = {
            "title": "Graduate Marketing Executive",
            "company": "Unilever",
            "location": "London",
            "salary": "£30,000",
            "description": "An exciting opportunity has arisen for a graduate to join our brand management division working on household names.",
            "posted_date": "2026-07-12",
        }
        outcome = dedup_against_existing(new_job, existing)
        assert outcome.action == "flag_for_review"

    def test_no_existing_jobs_always_inserts_new(self):
        outcome = dedup_against_existing({"title": "X", "company": "Y", "location": "Z"}, [])
        assert outcome.action == "insert_new"
        assert outcome.match_result is None


def test_parse_salary_range_handles_comma_only_match_without_crashing():
    """
    Regression test for a real production crash: the salary-number regex
    used to allow a match made entirely of commas with zero actual
    digits (comma was in the character class, `+` didn't require a
    digit specifically). Some job's salary text apparently contained a
    stray/malformed comma with no number attached — after stripping
    commas, int("") crashed the whole scheduler cycle. The fix requires
    every match to START with a real digit, so a comma-only match can
    never occur.
    """
    from app.dedup.scoring import parse_salary_range

    assert parse_salary_range(", ") == (None, None)
    assert parse_salary_range("£,") == (None, None)
    assert parse_salary_range(",,") == (None, None)
    assert parse_salary_range("Salary: ,") == (None, None)
    # normal values still parse correctly
    assert parse_salary_range("£28,000 - £32,000") == (28000, 32000)
    assert parse_salary_range("£30,000") == (30000, 30000)
