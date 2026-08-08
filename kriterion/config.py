import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml


# =============================================================================
# EASY CONFIG (edit these)
# =============================================================================

# Minimum DevOps experience required (years)
MIN_DEVOPS_YEARS: float = 3.0

# Required keywords that MUST appear in EXPERIENCE entries (case-insensitive)
# Example: {"Kubernetes", "AWS"} or {"Kubernetes", "AWS", "Terraform"}
REQUIRED_EXPERIENCE_KEYWORDS: Set[str] = {"Kubernetes", "AWS", "Helm"}

# How many lines around a match to include in a snippet (1 means +/-1 line)
SNIPPET_CONTEXT_LINES: int = 1

# Minimum score to pass (optional, set via --min-score CLI flag)
MIN_SCORE: Optional[int] = None

# Scoring weights (sum to 100 for a perfect candidate)
SCORE_WEIGHTS = {
    "keywords_found": 30,
    "devops_years": 30,
    "recency": 20,
    "keyword_depth": 10,
    "no_ambiguity": 10,
}


# =============================================================================
# Other config
# =============================================================================

EXPERIENCE_HEADINGS = {
    "experience",
    "experiences",
    "work experience",
    "work experiences",
    "professional experience",
    "professional experiences",
    "employment",
    "employment history",
    "career history",
    "work history",
    "positions held",
    "positions",
    "roles",
    "professional background",
    "relevant experience",
    "working experience",
    "career",
    "professional history",
    "technical experience",
    "devops experience",
    "hands-on experience",
}

STOP_HEADINGS = {
    "skills",
    "technical skills",
    "soft skills",
    "personal skills",
    "professional skills",
    "key skills",
    "core competencies",
    "education",
    "academic background",
    "academic qualifications",
    "projects",
    "project highlights",
    "project experience",
    "certificate",
    "certificates",
    "certifications",
    "certification",
    "official certificates",
    "training",
    "trainings",
    "training and courses",
    "internship",
    "internships",
    "summary",
    "professional summary",
    "profile",
    "publications",
    "courses",
    "languages",
    "language skills",
    "volunteering",
    "volunteer experience",
    "interests",
    "hobbies",
    "references",
    "awards",
    "achievements",
    "activities",
    "extracurricular activities",
    "additional activities",
    "student activities",
    "honors",
    "objective",
    "job objective",
    "career objective",
    "personal information",
    "personal details",
    "contact",
    "contact information",
    "about me",
    "about",
    "graduation project",
    "military status",
    "military service",
    "professional development",
    "affiliations",
    "memberships",
}

# Patterns for training/education programs — time in these does NOT count as
# professional experience (candidates are NOT rejected for attending them).
EDUCATION_PROGRAM_PATTERNS = [
    re.compile(r"\biti\b", re.IGNORECASE),
    re.compile(r"\bnti\b", re.IGNORECASE),
    re.compile(r"\bsprints\b", re.IGNORECASE),
    re.compile(r"\bdepi\b", re.IGNORECASE),
    re.compile(r"digital\s+egypt\s+pioneers\s+initiative", re.IGNORECASE),
    re.compile(r"information\s+technology\s+institute", re.IGNORECASE),
    re.compile(r"national\s+technology\s+institute", re.IGNORECASE),
]

# Patterns for preferred programs — candidate MUST have attended one (checked in
# both Education and Experience sections). Empty = disabled.
PREFERRED_PROGRAM_PATTERNS: List[re.Pattern] = []

# Patterns for excluded companies — reject candidate if they worked here.
EXCLUDED_COMPANY_PATTERNS: List[re.Pattern] = []

# Patterns for excluded universities — reject candidate if they attended.
EXCLUDED_UNIVERSITY_PATTERNS: List[re.Pattern] = []

EDUCATION_HINTS_PATTERNS = [
    re.compile(r"\bbachelor(?:'?s)?\s*(?:of|in|degree)?\b", re.IGNORECASE),
    re.compile(r"\bmaster(?:'?s)?\s+(?:of|in|degree)\b", re.IGNORECASE),
    re.compile(r"\b(?:ph\.?d|doctorate)\b", re.IGNORECASE),
    re.compile(r"\bdegree\s+(?:in|of|from)\b", re.IGNORECASE),
    re.compile(r"\b(?:b\.?sc|m\.?sc|b\.?eng|m\.?eng|b\.?a\b|m\.?a\b)", re.IGNORECASE),
    re.compile(r"\bfaculty\s+of\b", re.IGNORECASE),
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\bdiploma\b", re.IGNORECASE),
    re.compile(r"\bgpa\b", re.IGNORECASE),
    re.compile(r"\bcumulative\s+grade\b", re.IGNORECASE),
]

CERTIFICATION_HINTS_PATTERNS = [
    re.compile(r"\bcertified\b", re.IGNORECASE),
    re.compile(r"\bcredential\s*id\b", re.IGNORECASE),
    re.compile(r"\bcertificate\s*(?:no|number|id)\b", re.IGNORECASE),
    re.compile(r"\bcertification\b", re.IGNORECASE),
    re.compile(r"\baccreditation\b", re.IGNORECASE),
    re.compile(r"\bbadge\s*(?:id|number)\b", re.IGNORECASE),
]

JOB_TITLE_HINTS = {
    "engineer",
    "developer",
    "administrator",
    "architect",
    "consultant",
    "specialist",
    "lead",
    "manager",
    "intern",
    "head",
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# If True: year-only tokens (e.g., "2022") are marked ambiguous.
# If False: year-only ranges are treated as Jan->Dec bounds and are NOT ambiguous.
YEAR_ONLY_TOKENS_ARE_AMBIGUOUS: bool = False


# -----------------------------
# Profile loading (YAML)
# -----------------------------

DEFAULT_PROFILE_PATH = Path("profiles/profile.yaml")

_DEFAULT_SCORING_WEIGHTS = {
    "keywords_found": 30,
    "devops_years": 30,
    "recency": 20,
    "keyword_depth": 10,
    "no_ambiguity": 10,
}

_DEFAULT_EDUCATION_PROGRAMS = [
    "iti",
    "nti",
    "sprints",
    "depi",
    "information technology institute",
    "national technology institute",
    "digital egypt pioneers initiative",
]


def load_profile(path: Path) -> Dict[str, object]:
    """Load and validate a YAML job profile. Returns config dict."""
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Profile must be a YAML mapping, got {type(data).__name__}")

    # Validate required fields
    missing = []
    for field_name in ("role", "min_experience_years", "must_have_in_experience"):
        if field_name not in data or data[field_name] is None:
            missing.append(field_name)
    if missing:
        raise ValueError(f"Profile missing required fields: {', '.join(missing)}")

    if (
        not isinstance(data["must_have_in_experience"], list)
        or len(data["must_have_in_experience"]) == 0
    ):
        raise ValueError("must_have_in_experience must be a non-empty list")

    # Normalize and apply defaults for optional fields
    profile: Dict[str, object] = {
        "role": str(data["role"]),
        "min_experience_years": float(data["min_experience_years"]),
        "must_have_in_experience": [str(k) for k in data["must_have_in_experience"]],
        "min_score": data.get("min_score"),
        "education_programs": data.get(
            "education_programs", _DEFAULT_EDUCATION_PROGRAMS
        ),
        "preferred_programs": data.get("preferred_programs") or [],
        "excluded_companies": data.get("excluded_companies") or [],
        "excluded_universities": data.get("excluded_universities") or [],
        "scoring_weights": data.get("scoring_weights", _DEFAULT_SCORING_WEIGHTS),
    }

    return profile


def _compile_patterns(items: List[str]) -> List[re.Pattern]:
    """Compile a list of strings into word-boundary regex patterns."""
    return [
        re.compile(r"\b" + re.escape(str(item)) + r"\b", re.IGNORECASE)
        for item in items
    ]


def apply_profile(profile: Dict[str, object]) -> None:
    """Apply a loaded profile to the global config."""
    global MIN_DEVOPS_YEARS, REQUIRED_EXPERIENCE_KEYWORDS, MIN_SCORE, SCORE_WEIGHTS

    MIN_DEVOPS_YEARS = float(profile["min_experience_years"])  # type: ignore
    REQUIRED_EXPERIENCE_KEYWORDS = set(profile["must_have_in_experience"])  # type: ignore

    if profile.get("min_score") is not None:
        MIN_SCORE = int(profile["min_score"])  # type: ignore

    weights = profile.get("scoring_weights")
    if weights and isinstance(weights, dict):
        SCORE_WEIGHTS.update(weights)

    # Rebuild education program patterns
    programs = profile.get("education_programs", [])
    if isinstance(programs, list) and programs:
        EDUCATION_PROGRAM_PATTERNS.clear()
        EDUCATION_PROGRAM_PATTERNS.extend(_compile_patterns(programs))

    # Rebuild preferred program patterns
    preferred = profile.get("preferred_programs", [])
    if isinstance(preferred, list) and preferred:
        PREFERRED_PROGRAM_PATTERNS.clear()
        PREFERRED_PROGRAM_PATTERNS.extend(_compile_patterns(preferred))

    # Rebuild excluded company patterns
    companies = profile.get("excluded_companies", [])
    if isinstance(companies, list) and companies:
        EXCLUDED_COMPANY_PATTERNS.clear()
        EXCLUDED_COMPANY_PATTERNS.extend(_compile_patterns(companies))

    # Rebuild excluded university patterns
    universities = profile.get("excluded_universities", [])
    if isinstance(universities, list) and universities:
        EXCLUDED_UNIVERSITY_PATTERNS.clear()
        EXCLUDED_UNIVERSITY_PATTERNS.extend(_compile_patterns(universities))


def apply_cli_overrides(
    min_devops_years: Optional[float],
    required_keywords: Optional[List[str]],
    min_score: Optional[int] = None,
) -> None:
    """Apply CLI overrides on top of profile values."""
    global MIN_DEVOPS_YEARS, REQUIRED_EXPERIENCE_KEYWORDS, MIN_SCORE

    if min_devops_years is not None:
        MIN_DEVOPS_YEARS = float(min_devops_years)

    if required_keywords is not None and len(required_keywords) > 0:
        REQUIRED_EXPERIENCE_KEYWORDS = set(required_keywords)

    if min_score is not None:
        MIN_SCORE = min_score


def initialize_screening_worker(
    profile: Optional[Dict[str, object]],
    min_devops_years: float,
    required_keywords: List[str],
    min_score: Optional[int],
) -> None:
    """Apply the parent process's effective criteria inside a spawned worker."""
    if profile is not None:
        apply_profile(profile)
    apply_cli_overrides(min_devops_years, required_keywords, min_score)
