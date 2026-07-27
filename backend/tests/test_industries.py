"""
Tests for the industry categorization taxonomy (app/industries.py) —
the second finite-category filter, mirroring app/locations.py's design
and test rigor.
"""
from app.industries import categorize_industry, CANONICAL_INDUSTRIES, _INDUSTRY_PATTERNS


def test_unambiguous_titles_categorize_correctly():
    cases = [
        ("Trainee Solicitor", "Law"),
        ("Graduate Accountant", "Accounting"),
        ("Investment Banking Analyst", "Finance"),
        ("Graduate Management Consultant", "Consulting"),
        ("Marketing Executive", "Marketing"),
        ("Staff Nurse", "Healthcare"),
        ("Graduate Teacher", "Education"),
        ("Trainee Quantity Surveyor", "Construction & Property"),
        ("Policy Officer", "Public Sector"),
    ]
    for title, expected in cases:
        assert categorize_industry(title) == expected, f"{title!r} should categorize as {expected!r}"


def test_software_engineer_categorizes_as_technology_not_engineering():
    """
    Regression test for a real bug caught during development: Technology
    MUST be checked before Engineering in the pattern list, since
    "Software Engineer" contains both "software" (Technology) and
    "engineer" (Engineering) — checking Engineering first miscategorized
    the single largest graduate tech job title as traditional
    engineering.
    """
    assert categorize_industry("Graduate Software Engineer") == "Technology"
    assert categorize_industry("Software Engineer", "Join our engineering team") == "Technology"


def test_generic_engineer_titles_without_tech_signal_stay_engineering():
    assert categorize_industry("Mechanical Engineer") == "Engineering"
    assert categorize_industry("Civil Engineer") == "Engineering"


def test_title_takes_priority_over_description():
    """An unambiguous title shouldn't be overridden by an incidental word match in the description."""
    result = categorize_industry("Marketing Executive", "You will use our internal software tools daily")
    assert result == "Marketing"


def test_description_used_as_fallback_when_title_has_no_signal():
    result = categorize_industry("Graduate Scheme", "Join our fundraising and charity outreach team")
    assert result == "Charity & Nonprofit"


def test_no_signal_anywhere_falls_back_to_other():
    assert categorize_industry("Graduate Scheme", "Generic description with no clear signal") == "Other"
    assert categorize_industry("", "") == "Other"


def test_every_canonical_industry_is_reachable():
    """Sanity check: every category has at least one real input that produces it, so none are silently dead/unreachable."""
    reachable = {categorize_industry("some generic title", "")}  # "Other"
    for category, patterns in _INDUSTRY_PATTERNS:
        reachable.add(categorize_industry(patterns[0]))

    assert reachable == set(CANONICAL_INDUSTRIES)


def test_no_duplicate_categories():
    assert len(CANONICAL_INDUSTRIES) == len(set(CANONICAL_INDUSTRIES))
