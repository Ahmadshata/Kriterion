"""Experience extraction, entry classification, and DevOps-role computation."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from kriterion import config
from kriterion.dates import (
    DATE_RANGE_PATTERN,
    months_between,
    normalize_date_text,
    parse_date_ranges,
    parse_month_year,
)
from kriterion.extraction import iter_lines_with_pages
from kriterion.synonyms import (
    SYNONYM_MAP,
    match_keyword_in_text,
    normalize_heading,
    rejoin_hyphenated_words,
)


# -----------------------------
# Data models
# -----------------------------


@dataclass
class Entry:
    lines: List[Tuple[int, str]]  # (page_number, line)

    def text(self) -> str:
        return "\n".join(line for _, line in self.lines).strip()

    def head(self, n: int = 3) -> str:
        out: List[str] = []
        for _, line in self.lines:
            s = line.strip()
            if s:
                out.append(s)
            if len(out) >= n:
                break
        return " | ".join(out)


@dataclass
class Role:
    title: str
    start: dt.date
    end: dt.date
    months_added: int
    company: str = ""


# -----------------------------
# Experience extraction
# -----------------------------


def capture_experience_by_heading(
    pages: Sequence[str], max_back_lines: int = 200
) -> List[Tuple[int, str]]:
    """
    Heading-based capture, with a backward window to handle PDFs where extracted text order is odd
    (experience content appears before the "WORK EXPERIENCE" line).
    """
    lines = list(iter_lines_with_pages(pages))
    if not lines:
        return []

    exp_idxs: List[int] = []
    for idx, (_, line) in enumerate(lines):
        if normalize_heading(line) in config.EXPERIENCE_HEADINGS:
            exp_idxs.append(idx)

    if not exp_idxs:
        return []

    captured: List[Tuple[int, int, str]] = []  # (original_idx, page_num, text)

    for h_idx in exp_idxs:
        # Backward window: only capture if no section heading exists between
        # the start of the window and the experience heading.  If another
        # section heading (stop heading) is found, anything between it and
        # the experience heading belongs to that other section.
        start_back = max(0, h_idx - max_back_lines)
        found_stop = False
        for i in range(start_back, h_idx):
            _, line_text = lines[i]
            if normalize_heading(line_text) in config.STOP_HEADINGS:
                found_stop = True
        if not found_stop:
            captured.extend(
                (i, pn, txt)
                for i, (pn, txt) in enumerate(lines[start_back:h_idx], start=start_back)
            )

        # Forward capture
        i = h_idx + 1
        while i < len(lines):
            _, line_text = lines[i]
            if normalize_heading(line_text) in config.STOP_HEADINGS:
                break
            pn, txt = lines[i]
            captured.append((i, pn, txt))
            i += 1

    # De-duplicate by position (index in original lines), preserving order
    seen_idx: Set[int] = set()
    out: List[Tuple[int, str]] = []
    for orig_idx, page_num, text in captured:
        if orig_idx not in seen_idx:
            seen_idx.add(orig_idx)
            out.append((page_num, text))
    return out


def split_entries_from_lines(experience_lines: List[Tuple[int, str]]) -> List[Entry]:
    """
    Split into entries using blank lines as separators.
    Post-process: re-split oversized entries at date-range boundaries.
    """
    entries: List[Entry] = []
    current: List[Tuple[int, str]] = []

    for page_num, line in experience_lines:
        if not line.strip():
            if current:
                entries.append(Entry(lines=current))
                current = []
            continue
        current.append((page_num, line))

    if current:
        entries.append(Entry(lines=current))

    raw = [e for e in entries if e.text()]

    # Re-split oversized entries that contain multiple date ranges
    final: List[Entry] = []
    for entry in raw:
        if len(entry.lines) > 15:
            sub_entries = _try_resplit_by_dates(entry)
            if len(sub_entries) > 1:
                final.extend(sub_entries)
                continue
        final.append(entry)

    return final


def _try_resplit_by_dates(entry: Entry) -> List[Entry]:
    """Re-split an oversized entry at lines containing date ranges."""
    split_points: List[int] = []
    for i, (_, line) in enumerate(entry.lines):
        if i > 0 and is_date_range_line(line):
            split_points.append(i)

    if not split_points:
        return [entry]

    entries: List[Entry] = []
    prev = 0
    for sp in split_points:
        chunk = entry.lines[prev:sp]
        if chunk:
            entries.append(Entry(lines=chunk))
        prev = sp
    if prev < len(entry.lines):
        entries.append(Entry(lines=entry.lines[prev:]))

    return [e for e in entries if e.text()]


_STANDALONE_MONTH_YEAR_PATTERN = re.compile(
    r"^(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+'?\d{2,4}|"
    r"(?:0?[1-9]|1[0-2])[/\-.]\d{4})$",
    re.IGNORECASE,
)


def _standalone_month_date(line: str) -> Optional[dt.date]:
    """Parse an anchored month/year used for a one-month experience entry."""
    normalized = normalize_date_text(line)
    if not _STANDALONE_MONTH_YEAR_PATTERN.fullmatch(normalized):
        return None
    parsed, _ = parse_month_year(normalized, is_start=True)
    return parsed


def is_date_range_line(line: str) -> bool:
    """Recognize both employment ranges and guarded standalone month dates."""
    normalized = normalize_date_text(line)
    if _STANDALONE_MONTH_YEAR_PATTERN.fullmatch(normalized):
        return True

    date_match = DATE_RANGE_PATTERN.search(normalized)
    if not date_match:
        return False

    stripped = line.strip()
    if stripped and stripped[0] in "•-*▪►◦·⦁‣⁃\uf0b7":
        bullet_text = normalize_date_text(stripped[1:].strip())
        return bool(DATE_RANGE_PATTERN.fullmatch(bullet_text))
    return True


def _strip_header_marker(line: str) -> str:
    """Remove a list marker when a CV formats an employer as a bullet."""
    text = line.strip()
    if text and text[0] in "•-*▪►◦·⦁‣⁃\uf0b7":
        return text[1:].strip()
    return text


def _is_bullet_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s[0] in "•-*▪►◦·⦁‣⁃\uf0b7":
        return True
    if len(s) >= 2 and s[0].isdigit() and s[1] in ".):":
        return True
    return False


def _looks_like_role_title(line: str) -> bool:
    """Return whether a line immediately beside a date looks like a role header."""
    text = line.strip()
    if (
        not text
        or is_date_range_line(text)
        or _is_bullet_line(text)
        or normalize_heading(text) in config.STOP_HEADINGS
    ):
        return False
    if "|" in text or " @ " in text or re.search(r"\s+at\s+", text, re.IGNORECASE):
        return True
    return _has_job_title_signal(Entry(lines=[(0, text)]))


def _looks_like_company_before_role(line: str) -> bool:
    """Accept a pre-title employer/location, but reject prior job prose."""
    text = _strip_header_marker(line).strip(" |,:;-–—")
    if not _looks_like_company_line(text):
        return False
    if not text or text[0].islower() or re.search(r"[.!?][\"')\]]*$", text):
        return False
    return True


def _next_line_is_role_title(lines: Sequence[Tuple[int, str]], date_index: int) -> bool:
    """Check the first non-empty line after a date without crossing a section."""
    for _, line in lines[date_index + 1 :]:
        if not line.strip():
            continue
        return _looks_like_role_title(line)
    return False


def _header_before_date(
    lines: Sequence[Tuple[int, str]], date_index: int, max_lines: int = 3
) -> List[Tuple[int, str]]:
    """Return a nearby role or education-program header before a date.

    PDF extraction frequently inserts blank lines between a title/provider and
    its date.  Ignore those blanks, but keep them in the returned slice so the
    header can still be removed cleanly from the preceding entry.
    """
    candidate_indices: List[int] = []
    candidate_index = date_index - 1
    non_empty_lines = 0
    while candidate_index >= 0 and non_empty_lines < max_lines:
        line = lines[candidate_index][1]
        if not line.strip():
            candidate_index -= 1
            continue

        header_text = _strip_header_marker(line)
        normalized = normalize_heading(header_text)
        if (
            is_date_range_line(line)
            or normalized in config.EXPERIENCE_HEADINGS
            or normalized in config.STOP_HEADINGS
        ):
            break
        if _is_bullet_line(line) and not (
            _looks_like_company_line(header_text)
            or is_education_program(header_text)
        ):
            break
        candidate_indices.append(candidate_index)
        non_empty_lines += 1
        candidate_index -= 1

    # The closest title signal is normally preceded only by the previous role's
    # prose and followed by an optional company/location line.  A configured
    # education provider is also a header even if its acronym (for example
    # ``NTI``) does not resemble a job title.
    for position, candidate_index in enumerate(candidate_indices):
        candidate = _strip_header_marker(lines[candidate_index][1])
        if _looks_like_role_title(candidate):
            header_start = candidate_index
            for preceding_index in candidate_indices[position + 1 :]:
                preceding = _strip_header_marker(lines[preceding_index][1])
                if not _looks_like_company_before_role(preceding):
                    break
                header_start = preceding_index
            return list(lines[header_start:date_index])
        if is_education_program(candidate):
            return list(lines[candidate_index:date_index])
    return []


def _entry_role_title(entry: Entry) -> str:
    """Extract a role title whether it appears before or after its date range."""
    date_index = next(
        (
            index
            for index, (_, line) in enumerate(entry.lines)
            if is_date_range_line(line)
        ),
        None,
    )
    if date_index is not None:
        date_line = normalize_date_text(entry.lines[date_index][1])
        date_match = DATE_RANGE_PATTERN.search(date_line)
        if date_match:
            inline_title = (
                date_line[: date_match.start()] + date_line[date_match.end() :]
            ).strip(" |,:;-–—")
            if _looks_like_role_title(inline_title):
                return inline_title

        for candidate_index in (date_index + 1, date_index - 1):
            if 0 <= candidate_index < len(entry.lines):
                candidate = entry.lines[candidate_index][1].strip()
                if _looks_like_role_title(candidate):
                    return candidate

    for _, line in entry.lines:
        if _looks_like_role_title(line):
            return line.strip()
    for _, line in entry.lines:
        candidate = line.strip()
        if (
            candidate
            and not is_date_range_line(candidate)
            and not _is_bullet_line(candidate)
            and normalize_heading(candidate) not in config.STOP_HEADINGS
        ):
            return candidate
    return entry.head(1) or "Unknown title"


def _looks_like_company_line(line: str) -> bool:
    """Return whether a nearby header line plausibly names an employer."""
    text = _strip_header_marker(line).strip(" |,:;-–—")
    if (
        not text
        or len(text) > 120
        or len(text.split()) > 14
        or is_date_range_line(text)
        or _is_bullet_line(text)
        or _looks_like_role_title(text)
        or normalize_heading(text) in config.EXPERIENCE_HEADINGS
        or normalize_heading(text) in config.STOP_HEADINGS
    ):
        return False
    if text.casefold() in {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "cairo",
        "egypt",
        "uae",
    }:
        return False
    return not re.match(
        r"^(?:being|build|built|engage|implement|manage|maintain|perform|provide|"
        r"managed|implemented|designed|developed|deployed|operated|"
        r"maintained|configured|automated|worked|responsible|led|provided|"
        r"supported|administered|created|monitored|migrated|collaborated|used|"
        r"wrote|writing|delivered|handled|improved|optimized|streamlined|"
        r"ensured|conducted|assisted|analyzing|building|coaching|describing|"
        r"designing|developing|executing|escalating|handling|implementing|"
        r"managing|planning|proposing|providing|sharing|supporting|working)\b",
        text,
        re.IGNORECASE,
    )


def _split_inline_role_company(role_header: str) -> Tuple[str, str]:
    """Split common single-line role/employer headers without guessing from prose."""
    text = role_header.strip()
    for separator in (r"\s+\|\s+", r"\s+@\s+", r"\s+at\s+"):
        parts = re.split(separator, text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            continue
        title, company = (part.strip(" |,:;-–—") for part in parts)
        company = re.sub(r"\s+(?:from|since)$", "", company, flags=re.IGNORECASE)
        if _looks_like_role_title(title) and _looks_like_company_line(company):
            return title, company

    # A comma also separates role and employer in some CV templates.  The
    # company classifier, rather than word count, protects titles such as
    # "Supervisor, Automation and Cloud Engineer" while allowing short brands
    # such as "Blnk" and "Konecta".
    if "," in text:
        title, company = (part.strip() for part in text.split(",", 1))
        if (
            _looks_like_role_title(title)
            and _looks_like_company_line(company)
        ):
            return title, company

    return text, ""


def _company_on_date_line(line: str) -> str:
    """Extract an employer wrapped around a date, e.g. ``Ericsson (2021-Current)``."""
    normalized = normalize_date_text(line)
    match = DATE_RANGE_PATTERN.search(normalized)
    if not match:
        return ""
    candidate = normalized[: match.start()] + normalized[match.end() :]
    candidate = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" |,:;-–—()[]{}")
    if _looks_like_company_line(candidate):
        return candidate
    return ""


def _first_adjacent_company(entry: Entry, indices: Sequence[int]) -> str:
    """Inspect one contiguous header region and stop before responsibility prose."""
    for candidate_index in indices:
        raw_candidate = entry.lines[candidate_index][1]
        candidate = _strip_header_marker(raw_candidate)
        if not candidate or is_date_range_line(candidate):
            continue
        if _looks_like_company_line(candidate):
            return candidate.strip(" |,:;-–—")
        return ""
    return ""


def _entry_role_identity(entry: Entry) -> Tuple[str, str]:
    """Extract a normalized role title and its adjacent employer, when present."""
    role_header = _entry_role_title(entry)
    title, inline_company = _split_inline_role_company(role_header)
    if inline_company:
        return title, inline_company

    date_index = next(
        (
            index
            for index, (_, line) in enumerate(entry.lines)
            if is_date_range_line(line)
        ),
        None,
    )
    title_index = next(
        (
            index
            for index, (_, line) in enumerate(entry.lines)
            if line.strip() == role_header.strip()
        ),
        None,
    )

    if date_index is not None:
        dated_company = _company_on_date_line(entry.lines[date_index][1])
        if dated_company:
            return title, dated_company

    if date_index is not None and title_index is not None:
        if title_index < date_index:
            candidate_groups = (
                range(title_index + 1, date_index),
                range(0, title_index),
                range(date_index + 1, len(entry.lines)),
            )
        else:
            candidate_groups = (
                range(0, title_index),
                range(title_index + 1, len(entry.lines)),
            )
    elif date_index is not None:
        candidate_groups = (range(date_index + 1, len(entry.lines)),)
    else:
        candidate_groups = ()

    for candidate_group in candidate_groups:
        company = _first_adjacent_company(entry, candidate_group)
        if company:
            return title, company

    return title, ""


_OCCUPATION_HEADER_PATTERN = re.compile(
    r"\b(?:administration|administrator|analyst|architect|assistant|consultant|coordinator|"
    r"designer|developer|director|engineer|intern|lead|manager|officer|"
    r"instructor|operations?|specialist|sre|student|support|teacher|teaching|"
    r"technician|trainee)\b",
    re.IGNORECASE,
)

_ADDITIONAL_JOB_TITLE_PATTERN = re.compile(
    r"\b(?:administration|assistant|instructor)\b",
    re.IGNORECASE,
)

_ACADEMIC_ROLE_PATTERN = re.compile(
    r"\b(?:instructor|lecturer|professor|teacher|teaching|tutor)\b",
    re.IGNORECASE,
)


def has_experience_layout_anomaly(entries: List[Entry], roles: List[Role]) -> bool:
    """Detect role/employer inversions that indicate unreliable reading order."""
    if entries and not roles and any(is_devops_related(entry.text()) for entry in entries):
        return True
    for entry in entries:
        date_index = next(
            (
                index
                for index, (_, line) in enumerate(entry.lines)
                if is_date_range_line(line)
            ),
            None,
        )
        if date_index is None or not 0 < date_index < len(entry.lines) - 1:
            continue
        before = entry.lines[date_index - 1][1]
        after = entry.lines[date_index + 1][1]
        if _looks_like_role_title(before) and _looks_like_role_title(after):
            return True
    for role in roles:
        if not _OCCUPATION_HEADER_PATTERN.search(role.title):
            return True
        if role.company and _OCCUPATION_HEADER_PATTERN.search(role.company):
            return True
    return False


def build_date_based_entries_from_lines(
    lines: Sequence[Tuple[int, str]],
) -> List[Entry]:
    """
    Create entries that start at date ranges (e.g., "Feb 2024 - Present")
    and continue until the next date range or a stop heading.

    Supports both common layouts: a role title immediately before its date,
    and a standalone date immediately followed by its role title. In the
    former layout the preceding title is attached to the new entry; in the
    latter the previous entry is closed without stealing its final content.

    NOTE:
    This accepts lines directly so we can restrict date-based parsing to the Experience section
    when an Experience heading is present (prevents training/education date ranges from poisoning ambiguity).
    """
    entries: List[Entry] = []
    current: List[Tuple[int, str]] = []
    capturing = False

    for line_index, (page_num, line) in enumerate(lines):
        if is_date_range_line(line):
            title_follows_date = _next_line_is_role_title(lines, line_index)
            preceding_header = _header_before_date(lines, line_index)
            header_lines = (
                []
                if title_follows_date and not preceding_header
                else preceding_header
            )
            if header_lines and current[-len(header_lines) :] == header_lines:
                header_start = len(current) - len(header_lines)
                prior_non_empty_index = next(
                    (
                        index
                        for index in range(header_start - 1, -1, -1)
                        if current[index][1].strip()
                    ),
                    None,
                )
                if (
                    prior_non_empty_index is not None
                    and is_date_range_line(current[prior_non_empty_index][1])
                ):
                    # Two role-looking lines surround the prior date. Preserve
                    # the collision so the layout-quality gate can review it.
                    header_lines = []
                else:
                    del current[-len(header_lines) :]

            if current:
                entries.append(Entry(lines=current))

            current = list(header_lines)
            current.append((page_num, line))
            capturing = True
            continue

        if not capturing:
            continue

        if normalize_heading(line) in config.STOP_HEADINGS:
            if current:
                entries.append(Entry(lines=current))
            current = []
            capturing = False
            continue

        current.append((page_num, line))

    if current:
        entries.append(Entry(lines=current))

    return [e for e in entries if e.text()]


def build_date_based_entries(pages: Sequence[str]) -> List[Entry]:
    """
    Create entries that start at date ranges (e.g., "Feb 2024 - Present")
    and continue until the next date range or a stop heading.
    """
    lines = list(iter_lines_with_pages(pages))
    return build_date_based_entries_from_lines(lines)


def is_education_program(header_text: str) -> bool:
    """Check if entry header indicates a training/education program (not professional experience)."""
    return any(p.search(header_text) for p in config.EDUCATION_PROGRAM_PATTERNS)


def is_devops_related(entry_text: str) -> bool:
    """Check if entry contains any DevOps-related keyword (synonym-aware, boundary-safe)."""
    processed = rejoin_hyphenated_words(entry_text)
    for keyword in SYNONYM_MAP:
        if match_keyword_in_text(processed, keyword):
            return True
    return False


def is_experience_entry(entry: Entry) -> bool:
    """
    Conservative filter with improved heuristics to avoid false exclusions.
    """
    text = entry.text()

    # Must have a parseable date range
    if not any(is_date_range_line(line) for _, line in entry.lines):
        return False

    text_lower = text.lower()

    # Education check with context-aware patterns
    education_score = sum(
        1 for p in config.EDUCATION_HINTS_PATTERNS if p.search(text_lower)
    )
    role_title = _entry_role_title(entry) if education_score else ""
    if education_score and _ACADEMIC_ROLE_PATTERN.search(role_title):
        return False
    if education_score >= 2:
        if not _has_job_title_signal(entry):
            return False
    if education_score == 1:
        has_job_signal = _has_job_title_signal(entry)
        has_devops_signal = is_devops_related(text)
        if not has_job_signal and not has_devops_signal:
            return False

    # Certification check -- reject entries that look like certs, not jobs
    cert_score = sum(
        1 for p in config.CERTIFICATION_HINTS_PATTERNS if p.search(text_lower)
    )
    if cert_score >= 2:
        return False
    if cert_score == 1:
        has_company_signal = bool(re.search(r",\s*[A-Z][a-z]", text))
        if not has_company_signal:
            return False

    # Positive signals
    if _has_job_title_signal(entry):
        return True
    if is_devops_related(text):
        return True

    # Fallback: entry has date range and substantial content
    non_empty = sum(1 for _, line_text in entry.lines if line_text.strip())
    if non_empty >= 4:
        return True

    return False


def _has_job_title_signal(entry: Entry) -> bool:
    """Check for job title hints across the entry (first 10 lines)."""
    for idx, (_, line) in enumerate(entry.lines):
        line_lower = line.strip().lower()
        if not line_lower:
            continue
        for hint in config.JOB_TITLE_HINTS:
            if re.search(r"\b" + re.escape(hint) + r"\b", line_lower):
                return True
        if _ADDITIONAL_JOB_TITLE_PATTERN.search(line_lower):
            return True
        if re.search(r"\b(?:senior|junior|mid|staff|principal|chief)\b", line_lower):
            return True
        if idx >= 10:
            break
    return False


def extract_experience_entries(pages: Sequence[str]) -> List[Entry]:
    """
    Primary: date-based entries (most robust)
    Fallback: heading-based capture
    """
    # Prefer Experience-heading capture if available to avoid parsing date ranges from training/education sections
    heading_lines = capture_experience_by_heading(pages)
    if heading_lines:
        date_entries = build_date_based_entries_from_lines(heading_lines)
        date_entries = [e for e in date_entries if is_experience_entry(e)]
        if date_entries:
            return date_entries

        heading_entries = split_entries_from_lines(heading_lines)
        heading_entries = [e for e in heading_entries if is_experience_entry(e)]
        return heading_entries

    # If no Experience heading exists, fall back to global date-based parsing
    date_entries = build_date_based_entries(pages)
    date_entries = [e for e in date_entries if is_experience_entry(e)]
    if date_entries:
        return date_entries

    return []


def compute_devops_roles(entries: List[Entry]) -> Tuple[List[Role], int, bool]:
    """
    Returns:
    - roles counted (with months_added after overlap removal)
    - total unique DevOps months
    - ambiguity flag (any ambiguous date parsing)
    """
    roles: List[Role] = []
    total_months: Set[dt.date] = set()
    ambiguity = False

    dated: List[Tuple[Entry, dt.date, dt.date, bool]] = []
    for e in entries:
        # Keep this defensive guard even though the screening pipeline filters
        # these entries first.  Callers of this lower-level function must not
        # accidentally count configured training programs as employment.
        if is_education_program(e.head(3)):
            continue
        title, _ = _entry_role_identity(e)
        cloud_role = bool(
            re.search(r"\bcloud\b", title, re.IGNORECASE)
            and re.search(
                r"\b(?:architect|engineer|consultant|administrator|specialist|operations?|implementation)\b",
                title,
                re.IGNORECASE,
            )
        )
        title_is_devops_related = is_devops_related(title) or cloud_role
        generic_customer_support_role = bool(
            re.search(
                r"\bcustomer\s+(?:technical\s+)?support\b",
                title,
                re.IGNORECASE,
            )
        )
        if generic_customer_support_role and not title_is_devops_related:
            continue
        if not is_devops_related(e.text()) and not title_is_devops_related:
            continue
        drs: List[Tuple[dt.date, dt.date, bool]] = []
        for _, line in e.lines:
            if is_date_range_line(line):
                drs.extend(parse_date_ranges(line))
        if not drs:
            standalone_date = next(
                (
                    parsed
                    for _, line in e.lines
                    if (parsed := _standalone_month_date(line)) is not None
                ),
                None,
            )
            if standalone_date is not None:
                drs = [(standalone_date, standalone_date, False)]
        if not drs:
            ambiguity = True
            continue
        for s, en, amb in drs:
            dated.append((e, s, en, amb))

    dated.sort(key=lambda x: x[1])

    for entry, start, end, amb in dated:
        title, company = _entry_role_identity(entry)
        added = 0
        for month in months_between(start, end):
            if month not in total_months:
                total_months.add(month)
                added += 1
        roles.append(
            Role(
                title=title,
                start=start,
                end=end,
                months_added=added,
                company=company,
            )
        )
        ambiguity = ambiguity or amb

    return roles, len(total_months), ambiguity
