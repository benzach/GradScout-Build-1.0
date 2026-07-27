"""
Canonical location taxonomy.

This is the single source of truth for "which finite set of locations
does GradScout recognize" — the frontend's location picker fetches this
list from GET /locations (see app/routers/locations.py) rather than
hardcoding its own copy, specifically to prevent the frontend and
backend drifting out of sync over time.

categorize_location() is called once, at job-storage time (see
app/storage.py), converting whatever free-text location a scraper
happened to produce ("Central London, Greater London", "Manchester
(Hybrid)", "Remote - UK wide") into exactly one of these buckets. This
is what makes a finite dropdown filter possible at all — matching.py's
location filter can then do simple exact-membership checking instead of
fuzzy substring matching against arbitrary free text.

Known limitations, worth being upfront about:
  - This is substring/keyword matching against the job's structured
    location field (not the full description), not a real geocoding
    service. A location like "Slough" or "Guildford" — genuinely
    commutable to London — falls into "Other UK" rather than "London",
    since there's no keyword match for either name in the London
    pattern. A real postcode/geocoding-based approach would be the
    natural upgrade if this proves too coarse in practice.
  - "York" vs "New York": word-boundary matching means "New York" (a US
    city) would match the "York" pattern, same as "New London,
    Connecticut" matching "London" — accepted as effectively irrelevant
    for a UK-only graduate platform rather than engineered around.
"""
import re

CANONICAL_LOCATIONS = [
    # England — major/mid-size cities and towns
    "London", "Manchester", "Birmingham", "Leeds", "Bristol", "Liverpool",
    "Sheffield", "Newcastle", "Nottingham", "Leicester", "Southampton",
    "Oxford", "Cambridge", "Reading", "Brighton", "York", "Bath",
    "Coventry", "Derby", "Hull", "Plymouth", "Norwich", "Exeter",
    "Milton Keynes", "Portsmouth", "Bournemouth", "Sunderland",
    "Wolverhampton", "Stoke-on-Trent", "Preston", "Bradford", "Ipswich",
    "Northampton", "Swindon", "Peterborough", "Luton", "Watford",
    "Guildford", "Chester", "Lincoln", "Gloucester", "Cheltenham",
    "Middlesbrough",
    # Scotland
    "Edinburgh", "Glasgow", "Aberdeen", "Dundee",
    # Wales
    "Cardiff", "Swansea",
    # Northern Ireland
    "Belfast",
    # Catch-alls
    "Remote", "Other UK",
]

# Substrings (lowercase) that, if found anywhere in the raw location
# text, map to that canonical category. Checked in the order below;
# first match wins. Compound names include both hyphenated and
# spaced variants since sources are inconsistent about which they use.
_LOCATION_PATTERNS = [
    ("London", ["london"]),
    ("Manchester", ["manchester"]),
    ("Birmingham", ["birmingham"]),
    ("Leeds", ["leeds"]),
    ("Bristol", ["bristol"]),
    ("Liverpool", ["liverpool"]),
    ("Sheffield", ["sheffield"]),
    ("Newcastle", ["newcastle", "tyne and wear", "tyneside"]),
    ("Nottingham", ["nottingham"]),
    ("Leicester", ["leicester"]),
    ("Southampton", ["southampton"]),
    ("Oxford", ["oxford"]),
    ("Cambridge", ["cambridge"]),
    ("Reading", ["reading"]),
    ("Brighton", ["brighton"]),
    ("York", ["york"]),
    ("Bath", ["bath"]),
    ("Coventry", ["coventry"]),
    ("Derby", ["derby"]),
    ("Hull", ["hull", "kingston upon hull"]),
    ("Plymouth", ["plymouth"]),
    ("Norwich", ["norwich"]),
    ("Exeter", ["exeter"]),
    ("Milton Keynes", ["milton keynes"]),
    ("Portsmouth", ["portsmouth"]),
    ("Bournemouth", ["bournemouth"]),
    ("Sunderland", ["sunderland"]),
    ("Wolverhampton", ["wolverhampton"]),
    ("Stoke-on-Trent", ["stoke-on-trent", "stoke on trent"]),
    ("Preston", ["preston"]),
    ("Bradford", ["bradford"]),
    ("Ipswich", ["ipswich"]),
    ("Northampton", ["northampton"]),
    ("Swindon", ["swindon"]),
    ("Peterborough", ["peterborough"]),
    ("Luton", ["luton"]),
    ("Watford", ["watford"]),
    ("Guildford", ["guildford"]),
    ("Chester", ["chester"]),
    ("Lincoln", ["lincoln"]),
    ("Gloucester", ["gloucester"]),
    ("Cheltenham", ["cheltenham"]),
    ("Middlesbrough", ["middlesbrough"]),
    ("Edinburgh", ["edinburgh"]),
    ("Glasgow", ["glasgow"]),
    ("Aberdeen", ["aberdeen"]),
    ("Dundee", ["dundee"]),
    ("Cardiff", ["cardiff"]),
    ("Swansea", ["swansea"]),
    ("Belfast", ["belfast"]),
]

_REMOTE_KEYWORDS = ["remote", "work from home", "wfh", "anywhere", "home based", "home-based"]


def categorize_location(raw_location: str, remote_type: str = "") -> str:
    """
    Maps a raw, free-text location string (plus the already-extracted
    remote_type signal from normalize.py, if available) onto exactly
    one of CANONICAL_LOCATIONS.

    Remote is checked first and takes priority over any city mentioned
    in the text — a listing that says "London (Remote)" is categorized
    as Remote, since that's the more useful bucket for someone
    specifically filtering for remote work regardless of which city the
    employer happens to be headquartered in.
    """
    text = (raw_location or "").lower()

    if remote_type == "remote" or any(kw in text for kw in _REMOTE_KEYWORDS):
        return "Remote"

    for category, patterns in _LOCATION_PATTERNS:
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern)}\b", text):
                return category

    return "Other UK"
