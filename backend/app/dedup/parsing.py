"""
Shared parsing helper used by multiple scrapers: detects contract-type
terms (Full-time, Part-time, etc.) from free text, since sites rarely
expose this as a clean structured field.

Ported unchanged from the prototype, including the fix for matching both
"Full-time" (hyphenated) and "Full Time" (space-separated) — sites are
genuinely inconsistent about this, and the fix matters for real data
(Third Sector Jobs specifically uses the space variant).
"""
import re

CONTRACT_TYPE_TERMS = [
    "Full-time", "Part-time", "Permanent", "Contract", "Temporary",
    "Internship", "Remote", "Hybrid", "On-site",
]


def detect_contract_type(*text_fragments: str) -> str:
    combined = " ".join(f for f in text_fragments if f).lower()
    if not combined:
        return ""

    found = []
    for term in CONTRACT_TYPE_TERMS:
        # word-boundary match so "Contract" doesn't match inside "Contractor";
        # allow a hyphen OR a space between compound terms
        pattern = re.escape(term.lower()).replace(r"\-", r"[\s\-]")
        if re.search(rf"\b{pattern}\b", combined):
            found.append(term)
    return ", ".join(found)
