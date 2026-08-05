"""Experience extraction, entry classification, and DevOps-role computation."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from kriterion import config
from kriterion.dates import (
    DATE_RANGE_PATTERN,
    months_between,
    normalize_date_text,
    parse_date_ranges,
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


def is_date_range_line(line: str) -> bool:
    # Normalize to catch formats like "Apr, 2024 - Present" or "Mar-2024 - Present"
    return DATE_RANGE_PATTERN.search(normalize_date_text(line)) is not None


def _is_bullet_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s[0] in "•-*▪►◦·⦁‣⁃":
        return True
    if len(s) >= 2 and s[0].isdigit() and s[1] in ".):":
        return True
    return False


def build_date_based_entries_from_lines(
    lines: Sequence[Tuple[int, str]],
) -> List[Entry]:
    """
    Create entries that start at date ranges (e.g., "Feb 2024 - Present")
    and continue until the next date range or a stop heading.

    When a date-range line is found, the immediately preceding non-empty line
    is treated as the entry title (job title / company) and attached to the
    new entry rather than the previous one.

    NOTE:
    This accepts lines directly so we can restrict date-based parsing to the Experience section
    when an Experience heading is present (prevents training/education date ranges from poisoning ambiguity).
    """
    entries: List[Entry] = []
    current: List[Tuple[int, str]] = []
    capturing = False
    prev_line: Optional[Tuple[int, str]] = None

    for page_num, line in lines:
        if is_date_range_line(line):
            title_line: Optional[Tuple[int, str]] = None
            if prev_line:
                prev_text = prev_line[1].strip()
                if (
                    prev_text
                    and not is_date_range_line(prev_text)
                    and not _is_bullet_line(prev_text)
                    and normalize_heading(prev_text) not in config.STOP_HEADINGS
                ):
                    title_line = prev_line
                    if current and current[-1] == prev_line:
                        current.pop()

            if current:
                entries.append(Entry(lines=current))

            current = []
            if title_line:
                current.append(title_line)
            current.append((page_num, line))
            capturing = True
            prev_line = (page_num, line)
            continue

        if not capturing:
            if line.strip():
                prev_line = (page_num, line)
            continue

        if normalize_heading(line) in config.STOP_HEADINGS:
            if current:
                entries.append(Entry(lines=current))
            current = []
            capturing = False
            prev_line = (page_num, line)
            continue

        current.append((page_num, line))
        if line.strip():
            prev_line = (page_num, line)

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
    if not DATE_RANGE_PATTERN.search(normalize_date_text(text)):
        return False

    text_lower = text.lower()

    # Education check with context-aware patterns
    education_score = sum(1 for p in config.EDUCATION_HINTS_PATTERNS if p.search(text_lower))
    if education_score >= 2:
        return False
    if education_score == 1:
        has_job_signal = _has_job_title_signal(entry)
        has_devops_signal = is_devops_related(text)
        if not has_job_signal and not has_devops_signal:
            return False

    # Certification check -- reject entries that look like certs, not jobs
    cert_score = sum(1 for p in config.CERTIFICATION_HINTS_PATTERNS if p.search(text_lower))
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
        if not is_devops_related(e.text()):
            continue
        drs = parse_date_ranges(e.text())
        if not drs:
            ambiguity = True
            continue
        for s, en, amb in drs:
            dated.append((e, s, en, amb))

    dated.sort(key=lambda x: x[1])

    for entry, start, end, amb in dated:
        added = 0
        for month in months_between(start, end):
            if month not in total_months:
                total_months.add(month)
                added += 1
        roles.append(
            Role(
                title=entry.head(2) or "Unknown title",
                start=start,
                end=end,
                months_added=added,
            )
        )
        ambiguity = ambiguity or amb

    return roles, len(total_months), ambiguity
