"""Date parsing, normalization, and range extraction for CV screening."""

from __future__ import annotations

import datetime as dt
import re
from typing import List, Optional, Set, Tuple

from kriterion import config

# ---------------------------------------------------------------------------
# Date range patterns
# ---------------------------------------------------------------------------

DATE_RANGE_PATTERN = re.compile(
    r"(?P<start>"
    r"(?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})"  # "Feb 2024", "Feb '20", "Mar. 2024"
    r"|(?:[A-Za-z]{3,9}\s+\d{4})"  # "February 2024"
    r"|(?:\d{1,2}[/.\-]\d{4})"  # "01/2020", "01.2020", "01-2020"
    r"|(?:\d{4}[/\-]\d{1,2})"  # "2020/01", "2020-01" (ISO)
    r"|(?:Q[1-4]\s+\d{4})"  # "Q1 2020"
    r"|(?:\d{4})"  # "2020" (year only)
    r")\s*"
    r"(?:-|–|—|to|until|till|~)\s*"
    r"(?P<end>"
    r"(?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})"
    r"|(?:[A-Za-z]{3,9}\s+\d{4})"
    r"|(?:\d{1,2}[/.\-]\d{4})"
    r"|(?:\d{4}[/\-]\d{1,2})"
    r"|(?:Q[1-4]\s+\d{4})"
    r"|(?:\d{4})"
    r"|(?:present|current|now|ongoing|today)"
    r")",
    re.IGNORECASE,
)

DATE_RANGE_FROM_PATTERN = re.compile(
    r"(?:from|since)\s+(?P<start>"
    r"(?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})"
    r"|(?:[A-Za-z]{3,9}\s+\d{4})"
    r"|(?:\d{1,2}[/.\-]\d{4})"
    r"|(?:\d{4}[/\-]\d{1,2})"
    r"|(?:Q[1-4]\s+\d{4})"
    r"|(?:\d{4})"
    r")\s*"
    r"(?:to|until|till|-|–|—)\s*"
    r"(?P<end>"
    r"(?:[A-Za-z]{3,9}\.?\s*'?\d{2,4})"
    r"|(?:[A-Za-z]{3,9}\s+\d{4})"
    r"|(?:\d{1,2}[/.\-]\d{4})"
    r"|(?:\d{4}[/\-]\d{1,2})"
    r"|(?:Q[1-4]\s+\d{4})"
    r"|(?:\d{4})"
    r"|(?:present|current|now|ongoing|today)"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Date normalization (edge cases)
# ---------------------------------------------------------------------------


def normalize_date_text(text: str) -> str:
    """
    Normalize common CV date formats so DATE_RANGE_PATTERN can parse them reliably.
    """
    t = text

    # Normalize unicode dashes to a plain dash
    t = t.replace("–", "-").replace("—", "-")

    # Collapse newlines between potential date components (multi-line dates)
    t = re.sub(r"(\d{4})\s*\n\s*(-|to)", r"\1 \2", t)
    t = re.sub(r"([A-Za-z]{3,9}\s+\d{4})\s*\n\s*(-|to)", r"\1 \2", t)

    # "ongoing"/"today" -> "present"
    t = re.sub(r"\bongoing\b", "present", t, flags=re.IGNORECASE)
    t = re.sub(r"\btoday\b", "present", t, flags=re.IGNORECASE)

    # Normalize "until/till now|present|current" -> "present"
    t = re.sub(r"(?i)\b(?:until|till)\s+(?:now|present|current)\b", "present", t)
    t = re.sub(r"(?i)\b-\s*(?:until|till)\s+(?:now|present|current)\b", "- present", t)

    # Normalize "since <date>" -> "<date> - present"
    t = re.sub(
        r"(?i)\bsince\s+((?:[A-Za-z]{3,9}\s*,?\s*'?\d{2,4})|(?:\d{1,2}[/.\-]\d{4})|(?:\d{4}[/\-]\d{1,2})|(?:\d{4}))\b",
        r"\1 - present",
        t,
    )

    # "Feb '20" -> "Feb 2020" (short year expansion)
    t = re.sub(r"\b([A-Za-z]{3,9})\s*'(\d{2})\b", _expand_short_year, t)

    # "Apr, 2024" -> "Apr 2024"
    t = re.sub(r"(?i)\b([A-Za-z]{3,9})\s*,\s*(\d{4})\b", r"\1 \2", t)

    # Some CVs reverse the second token: "Jun 2019 - 2021 Jun".
    # Put only recognized month names back into the conventional order.
    month_names = (
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?"
    )
    t = re.sub(
        rf"(?i)\b(\d{{4}})\s+({month_names})\b",
        r"\2 \1",
        t,
    )

    # "Mar-2024" or "Mar/2024" -> "Mar 2024" (but NOT "2020-01" which is ISO)
    t = re.sub(r"(?i)\b([A-Za-z]{3,9})\s*[-/]\s*(\d{4})\b", r"\1 \2", t)

    # "Q1 2020" -> "Jan 2020" (quarter to month)
    t = re.sub(r"\bQ([1-4])\s+(\d{4})\b", _quarter_to_month, t)

    # Collapse whitespace (including newlines) to stabilize parsing
    t = re.sub(r"\s+", " ", t).strip()

    return t


def _expand_short_year(m: re.Match) -> str:
    month = m.group(1)
    yr = int(m.group(2))
    full_year = (1900 + yr) if yr > 50 else (2000 + yr)
    return f"{month} {full_year}"


def _quarter_to_month(m: re.Match) -> str:
    q = int(m.group(1))
    year = m.group(2)
    month_map = {1: "Jan", 2: "Apr", 3: "Jul", 4: "Oct"}
    return f"{month_map[q]} {year}"


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_month_year(token: str, is_start: bool) -> Tuple[Optional[dt.date], bool]:
    token = normalize_date_text(token).strip().lower()
    today = dt.date.today()

    # Strip trailing punctuation
    token = token.strip(" .,:;()[]{}")

    if token in {"present", "current", "now", "ongoing", "today"}:
        return today, False

    # Year-only: "2020"
    if re.fullmatch(r"\d{4}", token):
        year = int(token)
        if year < 1970 or year > today.year + 1:
            return None, True
        month = 1 if is_start else 12
        return dt.date(year, month, 1), config.YEAR_ONLY_TOKENS_ARE_AMBIGUOUS

    # MM/YYYY or MM-YYYY or MM.YYYY: "01/2020", "01-2020", "01.2020"
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{4})", token)
    if m:
        month_val, year = int(m.group(1)), int(m.group(2))
        if 1 <= month_val <= 12 and 1970 <= year <= today.year + 1:
            return dt.date(year, month_val, 1), False
        return None, True

    # YYYY/MM or YYYY-MM (ISO): "2020/01", "2020-01"
    m = re.fullmatch(r"(\d{4})[/\-](\d{1,2})", token)
    if m:
        year, month_val = int(m.group(1)), int(m.group(2))
        if 1 <= month_val <= 12 and 1970 <= year <= today.year + 1:
            return dt.date(year, month_val, 1), False
        return None, True

    # "Mon YYYY" or "Month YYYY": "jan 2020", "january 2020", "mar. 2024"
    parts = token.split()
    if len(parts) == 2:
        mon_str, yr_str = parts
        mon_str = mon_str.rstrip(".")
        if mon_str in config.MONTHS and yr_str.isdigit():
            year = int(yr_str)
            if 1970 <= year <= today.year + 1:
                return dt.date(year, config.MONTHS[mon_str], 1), False
            return None, True

    return None, True


def parse_date_ranges(text: str) -> List[Tuple[dt.date, dt.date, bool]]:
    ranges: List[Tuple[dt.date, dt.date, bool]] = []
    norm = normalize_date_text(text)

    for pattern in (DATE_RANGE_PATTERN, DATE_RANGE_FROM_PATTERN):
        for m in pattern.finditer(norm):
            s_raw, e_raw = m.group("start"), m.group("end")
            s, s_amb = parse_month_year(s_raw, is_start=True)
            e, e_amb = parse_month_year(e_raw, is_start=False)
            if s and e and e >= s:
                # Sanity: reject ranges > 30 years (noise/misparse)
                if (e - s).days <= 30 * 365:
                    ranges.append((s, e, s_amb or e_amb))

    # Deduplicate
    seen: Set[Tuple[dt.date, dt.date, bool]] = set()
    deduped: List[Tuple[dt.date, dt.date, bool]] = []
    for r in ranges:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped


def months_between(start: dt.date, end: dt.date) -> List[dt.date]:
    months: List[dt.date] = []
    cur = dt.date(start.year, start.month, 1)
    last = dt.date(end.year, end.month, 1)

    while cur <= last:
        months.append(cur)
        y = cur.year + (cur.month // 12)
        m = cur.month % 12 + 1
        cur = dt.date(y, m, 1)

    return months


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------


def months_to_years(months: int) -> float:
    return round(months / 12.0, 2)


# ---------------------------------------------------------------------------
# Format helper
# ---------------------------------------------------------------------------


def format_date(d: dt.date) -> str:
    return d.strftime("%Y-%m")
