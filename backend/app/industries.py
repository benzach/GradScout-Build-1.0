"""
Canonical industry taxonomy — the second finite-category filter
alongside location (see app/locations.py, which this deliberately
mirrors in structure).

categorize_industry() works from a job's TITLE and DESCRIPTION, not a
single structured field, since sources don't provide an "industry"
field. Title is checked first (a specific job title is a much stronger
signal than an incidental word in a longer description).

Rebuilt against real production data (2,901 live jobs) after the first
version showed 33% falling into "Other". The two single biggest gaps
were "Trainee Business Analyst" (98 jobs) and "Trainee Health And
Safety Officer" (94 jobs) — both genuinely common graduate role types
that simply had no category to belong to, not a keyword-tuning
problem. Added two new categories to cover them. Several other real
titles revealed genuine keyword gaps rather than missing categories:
"Tax Intern" never matched Accounting (the word "tax" was never
actually added despite being an obvious fit), and several Sales titles
("Graduate Sales Development Representative", "Graduate Sales &
Business Management Trainee") never matched because the original
patterns required exact multi-word phrases like "sales representative"
rather than the far more common bare word "sales".

Known limitation, same honesty as locations.py: keyword matching is not
true classification — a "Software Engineer" role at a bank might
arguably fit Finance as well as Technology. This picks the first
confident signal rather than attempting to weigh competing signals.
"""
import re

CANONICAL_INDUSTRIES = [
    "Law", "Finance", "Accounting", "Engineering", "Technology",
    "Consulting", "Marketing", "Sales", "Healthcare", "Charity & Nonprofit",
    "Education", "Retail", "Hospitality", "Media", "Public Sector",
    "Construction & Property", "Manufacturing", "Science & Research",
    "HR & Recruitment", "Logistics & Supply Chain", "Energy",
    "Business & Operations", "Health & Safety", "Other",
]

# Checked in order, first match wins. Ordering matters in a few
# deliberate places, called out inline below.
_INDUSTRY_PATTERNS = [
    ("Law", ["law", "legal", "solicitor", "barrister", "paralegal", "chambers", "litigation"]),
    ("Accounting", ["accounting", "accountant", "audit", "auditor", "acca", "aca", "cima",
                     "bookkeeping", "tax "]),  # "tax" was a real gap - "Tax Intern" matched nothing before this
    ("Finance", ["finance", "financial analyst", "banking", "investment bank", "asset management",
                 "wealth management", "trading", "equities", "hedge fund", "private equity"]),
    # Technology MUST come before Engineering: "Graduate Software
    # Engineer" contains both "software" (Technology) and "engineer"
    # (Engineering) — checking Engineering first would categorize the
    # single largest graduate tech role as traditional engineering.
    ("Technology", ["software", "developer", "programmer", "data scientist", "data analyst",
                     "cyber security", "cybersecurity", "devops", "front end", "back end",
                     "full stack", "machine learning", "artificial intelligence", "it support",
                     "systems analyst"]),
    ("Engineering", ["engineer", "engineering", "mechanical", "electrical engineer", "civil engineer",
                      "structural engineer", "aerospace"]),
    ("Consulting", ["consultant", "consulting", "advisory"]),
    # Construction & Property MUST come before Sales: "Estate Agent
    # Sales Negotiator" contains both "estate agent" (property) and,
    # once the Sales bare-word fix below is added, would also match
    # "sales" — property-specific phrasing should win.
    ("Construction & Property", ["construction", "quantity surveyor", "real estate", "architect",
                                  "surveyor", "property manager", "site manager", "viewing agent",
                                  "estate agent", "letting agent"]),
    ("Marketing", ["marketing", "advertising", "brand manager", "digital marketing", "seo ",
                    "social media manager", "content marketing"]),
    # Sales: originally required exact multi-word phrases like "sales
    # representative", which real titles like "Graduate Sales
    # Development Representative" and "Graduate Sales & Business
    # Management Trainee" didn't contain verbatim. Added the bare word
    # "sales" as a fallback — safe here since Construction & Property's
    # more specific property-sales phrasing is checked first, above.
    ("Sales", ["sales executive", "sales representative", "business development", "account manager",
               "account executive", "sales"]),
    ("Healthcare", ["nurse", "nursing", "healthcare", "clinical", "nhs", "pharmacist", "physiotherapist",
                     "paramedic", "midwife", "care worker", "support worker", "extra care"]),
    ("Charity & Nonprofit", ["charity", "charities", "nonprofit", "non-profit", "ngo", "fundraising",
                              "third sector", "voluntary sector"]),
    ("Education", ["teacher", "teaching", "education", "tutor", "lecturer", "teaching assistant",
                    "cover supervisor"]),
    ("Retail", ["retail", "store manager", "merchandiser", "shop assistant"]),
    ("Hospitality", ["hospitality", "hotel", "chef", "restaurant", "catering", "barista"]),
    ("Media", ["journalism", "journalist", "media", "broadcast", "publishing", "editor",
               "content writer", "copywriter"]),
    ("Public Sector", ["civil service", "government", "public sector", "policy", "parliamentary",
                        "council", "local authority", "police", "caseworker", "constituency"]),
    ("Manufacturing", ["manufacturing", "production line", "factory", "operations manager"]),
    ("Science & Research", ["research scientist", "laboratory", "biotech", "pharmaceutical",
                             "research assistant", "clinical research"]),
    ("HR & Recruitment", ["human resources", "hr advisor", "hr officer", "hr administrator",
                           "recruitment consultant", "recruiter", "talent acquisition"]),
    ("Logistics & Supply Chain", ["logistics", "supply chain", "warehouse", "procurement",
                                   "distribution centre"]),
    ("Energy", ["renewable energy", "oil and gas", "utilities", "power plant", "energy sector"]),
    # New category, added directly in response to real production data:
    # "Trainee Health And Safety Officer" was the single largest
    # miscategorized group (94 jobs) — a genuine, common graduate role
    # type that had no home in the original 21 categories.
    ("Health & Safety", ["health and safety", "health & safety", "hse officer", "hygiene"]),
    # New category, added directly in response to real production data:
    # "Trainee Business Analyst" was the single largest miscategorized
    # group overall (98 jobs). Also absorbs generic office/operations
    # titles (Administrator, Office Manager, Area Manager) that are
    # genuinely a function rather than an industry, and don't belong
    # forced into any of the more specific categories above. Checked
    # near the end, deliberately after everything more specific, so it
    # only catches titles that didn't match anything sharper first.
    ("Business & Operations", ["business analyst", "administrator", "administration", "operations",
                                 "office manager", "executive assistant", "area manager",
                                 "business management trainee"]),
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
            if re.search(rf"\b{re.escape(pattern.strip())}\b", title_text):
                return category

    description_text = (description or "").lower()
    for category, patterns in _INDUSTRY_PATTERNS:
        for pattern in patterns:
            if re.search(rf"\b{re.escape(pattern.strip())}\b", description_text):
                return category

    return "Other"
