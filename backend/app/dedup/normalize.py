"""
Stage 1 of the dedup pipeline: normalization.

Cleans individual job fields so that pure formatting differences (case,
punctuation, "- Remote" tags, legal company suffixes) don't get mistaken
for real differences at the comparison stage. This module never compares
two jobs to each other — it only cleans one job at a time.

Deliberately does NOT do synonym merging (e.g. "Developer" -> "Engineer").
That's tempting but dangerous: it risks silently merging genuinely
different roles. Real title differences are resolved later by fuzzy
scoring (see scoring.py), which produces a confidence number we can
reason about, rather than a blind hard-coded rule.
"""
import re

# Legal suffixes stripped from company names so "Google LLC" and "Google"
# normalize identically. Ordered longest-first so multi-word suffixes
# match before their shorter substrings do.
COMPANY_SUFFIXES = [
    "limited liability company", "incorporated", "corporation",
    "public limited company", "llc", "l.l.c.", "plc", "ltd.", "ltd",
    "limited", "inc.", "inc", "corp.", "corp", "group", "co.", "co",
]

# Tags that appear at the end of a title (after a dash or in parens)
# indicating work arrangement, not part of the actual job title.
REMOTE_TAG_PATTERN = re.compile(
    r"[\-\(]\s*(remote|hybrid|on[\s\-]?site|wfh)\s*\)?\s*$", re.IGNORECASE
)

WHITESPACE_PATTERN = re.compile(r"\s+")
PUNCTUATION_PATTERN = re.compile(r"[^\w\s]")


def _collapse_whitespace(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_title(title: str) -> tuple[str, str]:
    """
    Cleans a job title and extracts any remote-work tag from it.

    Returns (normalized_title, remote_type) where remote_type is one of
    "remote", "hybrid", "on-site", or "" if no tag was found.

    Example:
        "Software Engineer - Remote"   -> ("software engineer", "remote")
        "Software Developer (Remote)"  -> ("software developer", "remote")
    """
    if not title:
        return "", ""

    remote_match = REMOTE_TAG_PATTERN.search(title)
    remote_type = ""
    if remote_match:
        tag = remote_match.group(1).lower().replace(" ", "").replace("wfh", "remote")
        remote_type = "on-site" if "onsite" in tag or "on-site" in tag else tag
        title = title[: remote_match.start()]

    clean = title.lower().strip()
    clean = PUNCTUATION_PATTERN.sub(" ", clean)
    clean = _collapse_whitespace(clean)
    return clean, remote_type


def normalize_company(company: str) -> str:
    """
    Strips legal suffixes and punctuation so "Google LLC" and "Google"
    normalize to the same string.

    Example:
        "Google LLC"  -> "google"
        "Google"      -> "google"
        "Deloitte UK" -> "deloitte uk"   (not stripped - "UK" isn't a
                                            legal suffix, it's meaningful
                                            when a company has distinct
                                            regional entities)
    """
    if not company:
        return ""

    clean = company.lower().strip()
    clean = PUNCTUATION_PATTERN.sub(" ", clean)
    clean = _collapse_whitespace(clean)

    # Strip trailing legal suffixes (may need to strip more than one,
    # e.g. "Foo Group Ltd" has two)
    changed = True
    while changed:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            pattern = rf"\b{re.escape(suffix)}$"
            new_clean = re.sub(pattern, "", clean).strip()
            if new_clean != clean:
                clean = new_clean
                changed = True

    return _collapse_whitespace(clean)


def normalize_location(location: str) -> tuple[str, str]:
    """
    Cleans a location string and extracts any remote-work signal from it.

    Returns (normalized_location, remote_type) — same remote_type values
    as normalize_title, since sites inconsistently put this signal in
    either field.

    Example:
        "London (Remote)"       -> ("london", "remote")
        "Manchester, UK"        -> ("manchester, uk", "")
    """
    if not location:
        return "", ""

    remote_match = REMOTE_TAG_PATTERN.search(location)
    remote_type = ""
    if remote_match:
        tag = remote_match.group(1).lower().replace(" ", "").replace("wfh", "remote")
        remote_type = "on-site" if "onsite" in tag or "on-site" in tag else tag
        location = location[: remote_match.start()]

    clean = location.lower().strip()
    clean = _collapse_whitespace(clean)
    # Note: keep commas here (unlike title/company) since "London, UK"
    # vs "London" is a meaningful distinction worth preserving for now —
    # collapsing it is a call for the location-matching stage, not here.
    return clean, remote_type
