"""
Stage 3 of the dedup pipeline: fuzzy scoring.

Takes two ALREADY-NORMALIZED jobs (see normalize.py) that blocking (see
blocking.py) has decided are worth comparing, and produces a confidence
score for whether they're the same underlying job posting.

Uses rapidfuzz for text similarity rather than TF-IDF + cosine similarity.
Both answer the same question ("how alike are these two texts?") — the
choice here is about the frontier of compare-two-strings vs
compare-against-a-corpus: rapidfuzz needs no fitting step and is very
fast for pairwise comparison, which is what we're doing here (one new
job against a handful of blocked candidates, not searching a whole
corpus). If very long descriptions become the norm, TF-IDF cosine
similarity is worth revisiting.

Salary and date are treated as CONFIRMING signals, not gating ones —
they nudge the final confidence up or down rather than being required
to match, since salary is very often missing entirely from one source
or the other, and repost dates can genuinely differ by a day or two for
what's actually the same listing.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from app.dedup.normalize import normalize_title, normalize_company, normalize_location

DESCRIPTION_COMPARE_LENGTH = 250  # characters — per the spec: first 200-300 chars

# Composite score weights. Title and description carry the most
# evidentiary weight since they're the most content-rich signals;
# location is a moderate confirming signal (same job can be posted with
# slightly different location detail); salary/date are secondary
# nudges, not primary evidence, per the "use as secondary anchors"
# requirement.
WEIGHTS = {
    "title": 0.35,
    "description": 0.35,
    "location": 0.15,
    "salary": 0.08,
    "date": 0.07,
}

# Decision thresholds on the final 0-100 composite score.
AUTO_MERGE_THRESHOLD = 85
POSSIBLE_DUPLICATE_THRESHOLD = 65

def parse_salary_range(salary_text: str) -> tuple[int | None, int | None]:
    """
    Public helper: extracts (min, max) integers from a salary string for
    storage, e.g. '£28,000 - £32,000' -> (28000, 32000), '£30,000' -> (30000, 30000).
    Returns (None, None) if nothing parseable.
    """
    nums = _parse_salary_numbers(salary_text)
    if not nums:
        return None, None
    return min(nums), max(nums)


SALARY_NUMBER_PATTERN = re.compile(r"£?\s?([\d,]+)")


@dataclass
class MatchResult:
    composite_score: float
    title_score: float
    description_score: float
    location_score: float
    salary_score: float
    date_score: float
    decision: str  # "auto_merge" | "possible_duplicate" | "distinct"


def _parse_salary_numbers(salary_text: str) -> list[int]:
    """Extracts all numeric figures from a salary string, e.g. '£28,000 - £32,000' -> [28000, 32000]."""
    if not salary_text:
        return []
    return [int(n.replace(",", "")) for n in SALARY_NUMBER_PATTERN.findall(salary_text)]


def score_title(title_a: str, title_b: str) -> float:
    norm_a, _ = normalize_title(title_a)
    norm_b, _ = normalize_title(title_b)
    if not norm_a or not norm_b:
        return 0.0
    # token_sort_ratio handles word-order differences (e.g. "Graduate
    # Software Engineer" vs "Software Engineer, Graduate") — more
    # forgiving than a raw character-by-character comparison, which is
    # what we want here since job titles get reworded a lot.
    return fuzz.token_sort_ratio(norm_a, norm_b)


def score_description(desc_a: str, desc_b: str) -> float:
    a = (desc_a or "")[:DESCRIPTION_COMPARE_LENGTH]
    b = (desc_b or "")[:DESCRIPTION_COMPARE_LENGTH]
    if not a or not b:
        return 0.0
    return fuzz.ratio(a, b)


def score_location(location_a: str, location_b: str) -> float:
    norm_a, remote_a = normalize_location(location_a)
    norm_b, remote_b = normalize_location(location_b)
    if not norm_a or not norm_b:
        return 0.0
    base_score = fuzz.token_sort_ratio(norm_a, norm_b)
    # Remote-type agreement is a strong signal beyond plain text
    # similarity — "London (Remote)" and "London (Hybrid)" have high
    # text similarity but are meaningfully different roles.
    if remote_a and remote_b and remote_a != remote_b:
        base_score *= 0.5
    return base_score


def score_salary(salary_a: str, salary_b: str) -> float:
    """
    Returns a confirming score (0-100) if salaries roughly overlap, or a
    neutral 50 if either is missing (missing salary shouldn't COUNT
    AGAINST a match — it's just not evidence either way).
    """
    nums_a = _parse_salary_numbers(salary_a)
    nums_b = _parse_salary_numbers(salary_b)
    if not nums_a or not nums_b:
        return 50.0  # neutral — no evidence either way

    # Compare the ranges' midpoints with a tolerance band, since one
    # source might list "£28k-£32k" and another just "£30k".
    mid_a = sum(nums_a) / len(nums_a)
    mid_b = sum(nums_b) / len(nums_b)
    if mid_a == 0 or mid_b == 0:
        return 50.0

    diff_ratio = abs(mid_a - mid_b) / max(mid_a, mid_b)
    if diff_ratio <= 0.05:
        return 100.0
    elif diff_ratio <= 0.15:
        return 75.0
    elif diff_ratio <= 0.30:
        return 40.0
    else:
        return 0.0  # salaries meaningfully disagree — actively suspicious


def score_date(date_a: str, date_b: str) -> float:
    """
    Returns a confirming score based on how close two posted dates are.
    Missing/unparseable dates return neutral 50, same reasoning as salary.
    """
    parsed_a = _try_parse_date(date_a)
    parsed_b = _try_parse_date(date_b)
    if not parsed_a or not parsed_b:
        return 50.0

    delta = abs((parsed_a - parsed_b).days)
    if delta <= 1:
        return 100.0
    elif delta <= 3:
        return 80.0
    elif delta <= 7:
        return 55.0
    else:
        return 20.0  # far apart dates are weak evidence against, not proof


def _try_parse_date(date_str: str):
    if not date_str:
        return None
    # Scrapers hand us dates in several formats already (ISO, RFC822,
    # DD/MM/YYYY) — try the common ones rather than assuming one.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(date_str[: len(fmt) + 5].strip(), fmt)
        except ValueError:
            continue
    return None


def compute_match(job_a: dict, job_b: dict) -> MatchResult:
    """
    Computes the full composite match score between two jobs and returns
    a decision. Each job dict is expected to have: title, company,
    location, description, salary, posted_date.
    """
    title_score = score_title(job_a["title"], job_b["title"])
    description_score = score_description(job_a.get("description", ""), job_b.get("description", ""))
    location_score = score_location(job_a.get("location", ""), job_b.get("location", ""))
    salary_score = score_salary(job_a.get("salary", ""), job_b.get("salary", ""))
    date_score = score_date(job_a.get("posted_date", ""), job_b.get("posted_date", ""))

    composite = (
        title_score * WEIGHTS["title"]
        + description_score * WEIGHTS["description"]
        + location_score * WEIGHTS["location"]
        + salary_score * WEIGHTS["salary"]
        + date_score * WEIGHTS["date"]
    )

    if composite >= AUTO_MERGE_THRESHOLD:
        decision = "auto_merge"
    elif composite >= POSSIBLE_DUPLICATE_THRESHOLD:
        decision = "possible_duplicate"
    else:
        decision = "distinct"

    return MatchResult(
        composite_score=round(composite, 1),
        title_score=round(title_score, 1),
        description_score=round(description_score, 1),
        location_score=round(location_score, 1),
        salary_score=round(salary_score, 1),
        date_score=round(date_score, 1),
        decision=decision,
    )
