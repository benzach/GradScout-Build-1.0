"""
Canonical industry taxonomy — the second finite-category filter
alongside location (see app/locations.py, which this deliberately
mirrors in structure).

One real difference from location: categorize_industry() works from a
job's TITLE and DESCRIPTION, not a single structured field. Sources
don't provide an "industry" field the way they provide "location" — so
this infers industry from content, using the same word-boundary keyword
matching approach, checked against title first (higher-confidence
signal — a job titled "Trainee Solicitor" is unambiguous) then falling
through to description if the title alone doesn't indicate anything.

Called once, at job-storage time (see app/storage.py), same lifecycle
as location categorization.

Known limitation, same honesty as locations.py: keyword matching is not
true classification. A "Software Engineer" role at a bank might get
categorized as Technology when Finance would arguably be equally valid
— this picks the first confident signal rather than attempting to
weigh competing signals, which keeps the logic simple and predictable
rather than silently guessing at nuance it can't actually resolve.
"""
import re

CANONICAL_INDUSTRIES = [
    "Law", "Finance", "Accounting", "Engineering", "Technology",
    "Consulting", "Marketing", "Sales", "Healthcare", "Charity & Nonprofit",
    "Education", "Retail", "Hospitality", "Media", "Public Sector",
    "Construction & Property", "Manufacturing", "Science & Research",
    "HR & Recruitment", "Logistics & Supply Chain", "Energy", "Other",
]

# Checked in order, first match wins. More specific/unambiguous terms
# are placed earlier where two industries could plausibly share a
# generic word (e.g. "analyst" alone is too generic to gate on, so it's
# deliberately absent — only used in compound terms like "financial
# analyst" that are unambiguous on their own).
_INDUSTRY_PATTERNS = [
    ("Law", ["law", "legal", "solicitor", "barrister", "paralegal", "chambers", "litigation"]),
    ("Accounting", ["accounting", "accountant", "audit", "auditor", "acca", "aca", "cima", "bookkeeping"]),
    ("Finance", ["finance", "financial analyst", "banking", "investment bank", "asset management",
                 "wealth management", "trading", "equities", "hedge fund", "private equity"]),
    # Technology MUST come before Engineering: "Graduate Software
    # Engineer" contains both "software" (Technology) and "engineer"
    # (Engineering) — checking Engineering first would categorize the
    # single largest graduate tech role as traditional engineering,
    # which is exactly the bug this ordering fixes. Caught by testing
    # against a realistic title before this shipped, not by luck.
    ("Technology", ["software", "developer", "programmer", "data scientist", "data analyst",
                     "cyber security", "cybersecurity", "devops", "front end", "back end",
                     "full stack", "machine learning", "artificial intelligence", "it support",
                     "systems analyst"]),
    ("Engineering", ["engineer", "engineering", "mechanical", "electrical engineer", "civil engineer",
                      "structural engineer", "aerospace"]),
    ("Consulting", ["consultant", "consulting", "advisory"]),
    ("Marketing", ["marketing", "advertising", "brand manager", "digital marketing", "seo ",
                    "social media manager", "content marketing"]),
    ("Sales", ["sales executive", "sales representative", "business development", "account manager",
               "account executive"]),
    ("Healthcare", ["nurse", "nursing", "healthcare", "clinical", "nhs", "pharmacist", "physiotherapist",
                     "paramedic", "midwife"]),
    ("Charity & Nonprofit", ["charity", "charities", "nonprofit", "non-profit", "ngo", "fundraising",
                              "third sector", "voluntary sector"]),
    ("Education", ["teacher", "teaching", "education", "tutor", "lecturer", "teaching assistant"]),
    ("Retail", ["retail", "store manager", "merchandiser", "shop assistant"]),
    ("Hospitality", ["hospitality", "hotel", "chef", "restaurant", "catering", "barista"]),
    ("Media", ["journalism", "journalist", "media", "broadcast", "publishing", "editor",
               "content writer", "copywriter"]),
    ("Public Sector", ["civil service", "government", "public sector", "policy officer",
                        "parliamentary", "council", "local authority"]),
    ("Construction & Property", ["construction", "quantity surveyor", "real estate", "architect",
                                  "surveyor", "property manager", "site manager"]),
    ("Manufacturing", ["manufacturing", "production line", "factory", "operations manager"]),
    ("Science & Research", ["research scientist", "laboratory", "biotech", "pharmaceutical",
                             "research assistant", "clinical research"]),
    ("HR & Recruitment", ["human resources", "hr advisor", "hr officer", "recruitment consultant",
                           "recruiter", "talent acquisition"]),
    ("Logistics & Supply Chain", ["logistics", "supply chain", "warehouse", "procurement",
                                   "distribution centre"]),
    ("Energy", ["renewable energy", "oil and gas", "utilities", "power plant", "energy sector"]),
]


def categorize_industry(title: str, description: str = "") -> str:
    """
    Maps a job's title and description onto exactly one of
    CANONICAL_INDUSTRIES. Title is checked first (unambiguous signals
    like a specific job title outweigh incidental word matches in a
    longer description); description is only consulted if nothing in
    the title matched.
    """
    title_text = (title or "").lower()
    for category, patterns in _INDUSTRY_PATTERNS:
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern)}\b", title_text):
                return category

    description_text = (description or "").lower()
    for category, patterns in _INDUSTRY_PATTERNS:
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern)}\b", description_text):
                return category

    return "Other"
