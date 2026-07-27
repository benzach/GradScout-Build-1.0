"""
Tests for the location categorization taxonomy (app/locations.py) — the
function every scraped job's location gets run through exactly once, at
storage time, before it's usable by the finite-dropdown filter.
"""
from app.locations import categorize_location, CANONICAL_LOCATIONS


def test_remote_takes_priority_over_city_mentioned_in_text():
    """A listing saying 'London (Remote)' should categorize as Remote, not London — more useful for someone specifically filtering for remote work."""
    assert categorize_location("London (Remote)", remote_type="remote") == "Remote"


def test_remote_keyword_detected_even_without_remote_type_field():
    assert categorize_location("Remote - UK wide") == "Remote"
    assert categorize_location("Work from home") == "Remote"


def test_real_world_location_strings_categorize_correctly():
    cases = [
        ("Central London, Greater London", "London"),
        ("Manchester, Greater Manchester", "Manchester"),
        ("Newcastle upon Tyne", "Newcastle"),
        ("Tyne and Wear", "Newcastle"),
        ("Edinburgh, Scotland", "Edinburgh"),
        ("Cardiff, Wales", "Cardiff"),
        ("Belfast, Northern Ireland", "Belfast"),
    ]
    for raw, expected in cases:
        assert categorize_location(raw) == expected, f"{raw!r} should categorize as {expected!r}"


def test_word_boundary_prevents_substring_false_positive():
    """'Londonderry' is a real, different NI city — must NOT match 'London' just because the substring is present."""
    assert categorize_location("Londonderry") != "London"
    assert categorize_location("Londonderry") == "Other UK"


def test_unrecognized_or_empty_location_falls_back_to_other_uk():
    assert categorize_location("") == "Other UK"
    assert categorize_location("Somewhere Vague") == "Other UK"
    assert categorize_location("Slough, Berkshire") == "Other UK"  # known limitation, documented in module docstring


def test_every_canonical_location_is_reachable():
    """Sanity check: every category in the taxonomy has at least one real input that produces it, so none are silently dead/unreachable."""
    from app.locations import _LOCATION_PATTERNS

    reachable = {categorize_location("Remote job"), categorize_location("Nowhere Real")}
    for category, patterns in _LOCATION_PATTERNS:
        reachable.add(categorize_location(patterns[0]))

    assert reachable == set(CANONICAL_LOCATIONS)


def test_expanded_location_list_has_52_categories():
    """Sanity check the list didn't accidentally shrink or duplicate during expansion."""
    assert len(CANONICAL_LOCATIONS) == 52
    assert len(CANONICAL_LOCATIONS) == len(set(CANONICAL_LOCATIONS))  # no duplicates


def test_newly_added_locations_categorize_correctly():
    cases = [
        ("Brighton, East Sussex", "Brighton"),
        ("Stoke-on-Trent, Staffordshire", "Stoke-on-Trent"),
        ("Stoke on Trent", "Stoke-on-Trent"),  # non-hyphenated variant also matches
        ("Milton Keynes, Buckinghamshire", "Milton Keynes"),
        ("Aberdeen, Scotland", "Aberdeen"),
        ("Swansea, Wales", "Swansea"),
        ("Kingston upon Hull", "Hull"),
    ]
    for raw, expected in cases:
        assert categorize_location(raw) == expected, f"{raw!r} should categorize as {expected!r}"


def test_derby_not_falsely_matched_inside_derbyshire():
    """Same word-boundary protection as the Londonderry case, applied to a new pattern."""
    assert categorize_location("Derbyshire") == "Other UK"
    assert categorize_location("Derby, Derbyshire") == "Derby"
