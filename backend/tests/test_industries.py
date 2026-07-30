"""
Tests for the industry taxonomy (app/industries.py). Rebuilt against
real production data after the first version showed 33% falling into
"Other" — see the module docstring for the two missing categories
(Business & Operations, Health & Safety) and keyword gaps this fixed.
"""
from app.industries import categorize_industry, CANONICAL_INDUSTRIES, _INDUSTRY_PATTERNS


class TestNewCategories:
    """The two single biggest real gaps: genuinely common graduate role types with nowhere to go."""

    def test_business_analyst_no_longer_falls_to_engineering_or_other(self):
        """98 real jobs titled this way, the single largest miscategorized group."""
        assert categorize_industry("Trainee Business Analyst") == "Business & Operations"

    def test_health_and_safety_officer_gets_its_own_category(self):
        """94 real jobs titled this way, the second largest miscategorized group."""
        assert categorize_industry("Trainee Health And Safety Officer") == "Health & Safety"

    def test_business_and_operations_absorbs_generic_office_titles(self):
        cases = ["Administrator", "Office Manager", "Executive Assistant", "Area Manager",
                  "Administration Assistant", "Business Analyst"]
        for title in cases:
            assert categorize_industry(title) == "Business & Operations", f"{title!r} should be Business & Operations"


class TestRealKeywordGaps:
    """Specific real titles that matched nothing before, found by reviewing actual production data."""

    def test_tax_intern_matches_accounting(self):
        """'tax' was never actually added as a keyword despite being an obvious fit."""
        assert categorize_industry("Tax Intern") == "Accounting"

    def test_sales_titles_match_via_bare_sales_keyword(self):
        """Original patterns required exact phrases like 'sales representative' - real titles didn't contain them verbatim."""
        cases = [
            "Graduate Sales Development Representative",
            "Graduate Sales & Business Management Trainee",
            "Graduate Trainee Sales Manager",
            "Sales Administrator",
        ]
        for title in cases:
            assert categorize_industry(title) == "Sales", f"{title!r} should be Sales"

    def test_public_sector_expanded_patterns(self):
        cases = ["Caseworker", "Constituency Assistant", "Police Officer (National Graduate Programme)",
                  "Policy and Public Affairs Officer"]
        for title in cases:
            assert categorize_industry(title) == "Public Sector", f"{title!r} should be Public Sector"

    def test_healthcare_expanded_patterns(self):
        cases = ["Female Extra Care Support Worker", "Extra Care Team Manager"]
        for title in cases:
            assert categorize_industry(title) == "Healthcare", f"{title!r} should be Healthcare"

    def test_cover_supervisor_matches_education(self):
        assert categorize_industry("Cover Supervisor") == "Education"


class TestOrderingPrecision:
    """Cases where two categories could plausibly match - confirms the more specific one wins."""

    def test_hr_administrator_matches_hr_not_generic_business_operations(self):
        assert categorize_industry("HR Administrator") == "HR & Recruitment"

    def test_estate_agent_sales_negotiator_matches_property_not_sales(self):
        """Construction & Property is checked before Sales specifically for this case."""
        assert categorize_industry("Estate Agent Sales Negotiator") == "Construction & Property"

    def test_software_engineer_matches_technology_not_engineering(self):
        """Regression guard for the ordering bug caught during initial development."""
        assert categorize_industry("Graduate Software Engineer") == "Technology"

    def test_generic_engineer_titles_without_tech_signal_stay_engineering(self):
        assert categorize_industry("Mechanical Engineer") == "Engineering"
        assert categorize_industry("Civil Engineer") == "Engineering"


class TestNoRegression:
    def test_original_unambiguous_titles_still_correct(self):
        cases = [
            ("Trainee Solicitor", "Law"), ("Graduate Accountant", "Accounting"),
            ("Investment Banking Analyst", "Finance"), ("Graduate Management Consultant", "Consulting"),
            ("Marketing Executive", "Marketing"), ("Staff Nurse", "Healthcare"),
            ("Graduate Teacher", "Education"), ("Trainee Quantity Surveyor", "Construction & Property"),
        ]
        for title, expected in cases:
            assert categorize_industry(title) == expected

    def test_title_still_takes_priority_over_description(self):
        result = categorize_industry("Marketing Executive", "You will use our internal software tools daily")
        assert result == "Marketing"

    def test_no_signal_anywhere_still_falls_back_to_other(self):
        assert categorize_industry("Graduate Scheme", "Generic description with no clear signal") == "Other"
        assert categorize_industry("", "") == "Other"
        # genuinely ambiguous/niche real titles - acceptable to stay Other
        assert categorize_industry("Customer Service Advisor") == "Other"
        assert categorize_industry("Receptionist") == "Other"


def test_no_duplicate_categories():
    assert len(CANONICAL_INDUSTRIES) == len(set(CANONICAL_INDUSTRIES))


def test_every_canonical_industry_is_reachable():
    reachable = {categorize_industry("some generic title", "")}
    for category, patterns in _INDUSTRY_PATTERNS:
        reachable.add(categorize_industry(patterns[0].strip()))
    assert reachable == set(CANONICAL_INDUSTRIES)
