"""
Tests for the location taxonomy (app/locations.py). Rebuilt against
real production data after the first version showed 69% falling into
"Other UK" — see the module docstring for the three real patterns that
drove this rewrite (postcodes, missing towns, non-UK jobs).
"""
from app.locations import categorize_location, CANONICAL_LOCATIONS, _LOCATION_PATTERNS


class TestPostcodeDecoding:
    """The single biggest fix: several sources return raw postcodes, not city names."""

    def test_real_production_postcodes_decode_correctly(self):
        cases = [
            ("EC3M6BL", "London"), ("M13LD", "Manchester"), ("NN157JU", "Northampton"),
            ("B32HB", "Birmingham"), ("NN114XF", "Northampton"), ("EC4N6EU", "London"),
            ("RG11AF", "Reading"), ("EC1N8JG", "London"), ("DE43QZ", "Derby"),
            ("SW1A2DX", "London"), ("S601LB", "Sheffield"), ("HU13DX", "Hull"),
        ]
        for raw, expected in cases:
            assert categorize_location(raw) == expected, f"{raw!r} should decode to {expected!r}"

    def test_postcode_with_no_known_area_mapping_falls_back_honestly(self):
        """WF (Wakefield) isn't mapped to any canonical city - should fall to Other UK, not guess wrong."""
        assert categorize_location("WF12DH") == "Other UK"

    def test_non_postcode_text_never_falsely_triggers_postcode_matching(self):
        assert categorize_location("London") == "London"
        assert categorize_location("Somewhere Vague") == "Other UK"


class TestInternational:
    """Non-UK jobs showed up in real data despite sources being configured for UK results - see module docstring."""

    def test_real_international_cities_categorized_honestly_not_as_uk(self):
        cases = ["Kuala Lumpur", "Madrid", "Dublin", "Kathmandu (NP)", "Singapore-SGP",
                  "Lahore (PK)", "Hong Kong", "Singapore, SGP"]
        for raw in cases:
            assert categorize_location(raw) == "International", f"{raw!r} should be International, not silently mislabeled UK"

    def test_northern_ireland_is_not_miscategorized_as_international(self):
        """
        Regression test for a real bug caught during development: an
        earlier version included the generic country name "ireland" in
        the International list. Since "Ireland" appears as a standalone
        word inside "Northern Ireland" too, "Belfast, Northern Ireland"
        (genuinely UK territory) was being miscategorized as
        International. Fixed by limiting International matching to
        specific observed cities rather than broader country names.
        """
        assert categorize_location("Belfast, Northern Ireland") == "Belfast"
        assert categorize_location("Northern Ireland") != "International"

    def test_generalized_suffix_code_catches_unseen_countries(self):
        """
        Real data showed a repeatable pattern: non-UK listings suffix a
        short country code set off by a comma/hyphen/paren. This
        generalizes to any country using that pattern, not just the
        specific cities already hardcoded above.
        """
        cases = ["Warsaw (PL)", "Berlin-DEU", "Toronto, CAN", "Cambridge, MA"]
        for raw in cases:
            assert categorize_location(raw) == "International", f"{raw!r} should be caught by the general suffix-code pattern"

    def test_uk_and_gb_suffix_do_not_trigger_international(self):
        """The general suffix-code pattern must not fire on the UK's own country codes."""
        assert categorize_location("Manchester, UK") == "Manchester"
        assert categorize_location("London, GB") == "London"

    def test_cambridge_massachusetts_not_confused_with_uk_cambridge(self):
        """
        Ordering matters: the suffix-code check runs BEFORE the UK city
        name loop specifically so a US city sharing a name with a UK one
        doesn't get miscategorized as the UK city.
        """
        assert categorize_location("Cambridge, MA") == "International"
        assert categorize_location("Cambridge, Cambridgeshire") == "Cambridge"  # genuine UK Cambridge unaffected


class TestNewTowns:
    def test_towns_added_from_real_production_data(self):
        cases = ["Stockport", "Warrington", "Doncaster", "Blackpool",
                  "Chesterfield", "Burnley", "Woking", "Basingstoke"]
        for town in cases:
            assert categorize_location(town) == town


class TestRemote:
    def test_internet_keyword_recognized_as_remote(self):
        """'Internet' seen in real data as a placeholder location for fully-remote roles."""
        assert categorize_location("Internet") == "Remote"

    def test_remote_still_takes_priority_over_city_mentioned_in_text(self):
        assert categorize_location("London (Remote)", remote_type="remote") == "Remote"


class TestNoRegression:
    """Everything that worked before this rewrite must still work."""

    def test_original_cities_still_categorize_correctly(self):
        cases = [
            ("Central London, Greater London", "London"),
            ("Manchester, Greater Manchester", "Manchester"),
            ("Newcastle upon Tyne", "Newcastle"),
            ("Edinburgh, Scotland", "Edinburgh"),
            ("Cardiff, Wales", "Cardiff"),
            ("Belfast, Northern Ireland", "Belfast"),
        ]
        for raw, expected in cases:
            assert categorize_location(raw) == expected

    def test_word_boundary_protection_still_works(self):
        assert categorize_location("Londonderry") == "Other UK"
        assert categorize_location("Derbyshire") == "Other UK"
        assert categorize_location("Derby, Derbyshire") == "Derby"

    def test_genuine_unknowns_still_fall_back_honestly(self):
        assert categorize_location("") == "Other UK"
        assert categorize_location("Somewhere Vague") == "Other UK"
        assert categorize_location("Slough, Berkshire") == "Other UK"  # documented known gap


def test_no_duplicate_categories():
    assert len(CANONICAL_LOCATIONS) == len(set(CANONICAL_LOCATIONS))


def test_every_canonical_location_is_reachable():
    reachable = {categorize_location("Remote job"), categorize_location("Madrid"), categorize_location("Nowhere Real")}
    for category, patterns in _LOCATION_PATTERNS:
        reachable.add(categorize_location(patterns[0]))
    assert reachable == set(CANONICAL_LOCATIONS)
