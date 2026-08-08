"""Scoring, evidence, screening, and output helpers."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from kriterion import config
from kriterion.dates import DATE_RANGE_PATTERN, months_to_years, normalize_date_text
from kriterion.experience import (
    Entry,
    Role,
    compute_devops_roles,
    extract_experience_entries,
    has_experience_layout_anomaly,
    is_devops_related,
    is_education_program,
)
from kriterion.extraction import (
    extract_text_by_page,
    extract_text_from_docx,
    pdf_has_multi_column_layout,
)
from kriterion.synonyms import (
    KEYWORD_INDEX,
    SEMANTIC_RELATIONSHIPS,
    SEMANTIC_RELATIONSHIPS_VERSION,
    SYNONYM_MAP,
    USAGE_ACTION_PATTERN,
    _build_keyword_pattern,
    match_keyword_in_text,
    normalize_heading,
    normalize_tool_name,
    rejoin_hyphenated_words,
)


# ---------------------
# Evidence data classes
# ---------------------


@dataclass
class KeywordMatch:
    page_num: int
    snippet: str
    matched_variant: str
    entry_index: int


_EVIDENCE_BULLET_PREFIX = re.compile(
    r"^\s*(?:[•‣◦⁃∙●○▪▫–—·►▸\-*\uf0b7]|[oO](?=\s*$))\s*"
)
_NON_FILTERABLE_TOOL_CONCEPTS = {
    "ci/cd",
    "cloud engineer",
    "devops",
    "gitops",
    "infrastructure",
    "infrastructure as code",
    "linux",
    "platform engineer",
    "sre",
}


# ---------------------
# Evidence functions
# ---------------------


def _keyword_evidence_detail(
    entries: List[Entry],
    keyword: str,
) -> Dict[str, object]:
    """Return deterministic, auditable evidence for one required concept."""
    direct_matches = find_all_keyword_matches(entries, keyword)
    if direct_matches:
        best = direct_matches[0]
        return {
            "status": "DIRECT_EXPERIENCE_MENTION",
            "relationship": "direct",
            "matched_term": best.matched_variant,
            "page": best.page_num,
            "snippet": best.snippet,
            "citations": [_citation_from_match(match) for match in direct_matches],
            "qualifies": True,
            "needs_review": False,
        }

    canonical = KEYWORD_INDEX.get(keyword.lower(), keyword.lower())
    related_groups = SEMANTIC_RELATIONSHIPS.get(canonical, {})
    for relationship, variants in related_groups.items():
        matches = find_variant_matches(entries, variants)
        if not matches:
            continue
        best = matches[0]
        demonstrated_usage = bool(USAGE_ACTION_PATTERN.search(best.snippet))
        return {
            "status": (
                "RELATED_USAGE_EVIDENCE"
                if demonstrated_usage
                else "RELATED_MENTION_NEEDS_REVIEW"
            ),
            "relationship": relationship,
            "matched_term": best.matched_variant,
            "page": best.page_num,
            "snippet": best.snippet,
            "citations": [_citation_from_match(match) for match in matches],
            "qualifies": demonstrated_usage,
            "needs_review": not demonstrated_usage,
        }

    return {
        "status": "NOT_FOUND",
        "relationship": "",
        "matched_term": "",
        "page": None,
        "snippet": "",
        "citations": [],
        "qualifies": False,
        "needs_review": False,
    }


def _citation_from_match(match: KeywordMatch) -> Dict[str, object]:
    """Return the stable, JSON-serializable shape used by report renderers."""
    return {
        "page": match.page_num,
        "snippet": match.snippet,
        "matched_term": match.matched_variant,
    }


def find_keyword_in_entries(
    entries: List[Entry], keyword: str
) -> Optional[Tuple[int, str]]:
    """
    Backward-compatible: returns (page_num, snippet) of best match, or None.
    Uses synonym-aware, boundary-respecting matching with hyphenation rejoining.
    """
    matches = find_all_keyword_matches(entries, keyword)
    if matches:
        best = matches[0]
        return best.page_num, best.snippet
    return None


def _clean_evidence_snippet(lines: List[str]) -> str:
    """Remove PDF bullet artifacts without changing the evidence wording."""
    cleaned: List[str] = []
    for line in lines:
        text = _EVIDENCE_BULLET_PREFIX.sub("", line).rstrip()
        if text.strip():
            cleaned.append(text)
    return "\n".join(cleaned).strip()


def _is_standalone_bullet(line: str) -> bool:
    match = _EVIDENCE_BULLET_PREFIX.match(line)
    return bool(match and not line[match.end() :].strip())


def _starts_with_bullet(line: str) -> bool:
    return _EVIDENCE_BULLET_PREFIX.match(line) is not None


def _is_evidence_section_heading(line: str) -> bool:
    """Recognize section headings that must never leak into evidence."""
    text = line.strip()
    if not text:
        return False
    normalized = normalize_heading(text)
    if normalized in config.EXPERIENCE_HEADINGS or normalized in config.STOP_HEADINGS:
        return True

    words = normalized.split()
    if (
        len(words) <= 6
        and "experience" in words
        and any(
            word in {"consulting", "freelance", "professional", "work"}
            for word in words
        )
    ):
        return True

    letters = [character for character in text if character.isalpha()]
    uppercase_ratio = (
        sum(character.isupper() for character in letters) / len(letters)
        if letters
        else 0.0
    )
    return len(words) <= 6 and uppercase_ratio >= 0.6


def _is_evidence_boundary(line: str) -> bool:
    return bool(
        _is_standalone_bullet(line)
        or DATE_RANGE_PATTERN.search(normalize_date_text(line))
        or _is_evidence_section_heading(line)
    )


def _evidence_paragraph(entry: Entry, match_line_index: int) -> str:
    """Return only the bullet paragraph containing a matched source line."""
    lines = [line_text for _, line_text in entry.lines]
    start = match_line_index
    if not _starts_with_bullet(lines[start]):
        while start > 0:
            previous = lines[start - 1]
            if _is_evidence_boundary(previous):
                break
            start -= 1
            if _starts_with_bullet(lines[start]):
                break

    end = match_line_index + 1
    while end < len(lines):
        following = lines[end]
        if _is_evidence_boundary(following) or _starts_with_bullet(following):
            break
        end += 1

    return _clean_evidence_snippet(lines[start:end])


def find_all_keyword_matches(entries: List[Entry], keyword: str) -> List[KeywordMatch]:
    """Find every matching evidence paragraph (including synonyms)."""
    matches: List[KeywordMatch] = []
    seen_paragraphs: Set[Tuple[int, int, str]] = set()
    canonical = keyword.lower()

    # Resolve to canonical if this is a variant
    if canonical in KEYWORD_INDEX:
        canonical = KEYWORD_INDEX[canonical].lower()

    for entry_idx, entry in enumerate(entries):
        full_text = rejoin_hyphenated_words(entry.text())

        # Check entry-level match first
        entry_matches = match_keyword_in_text(full_text, canonical)
        if not entry_matches:
            continue

        # Keep one citation for every matching source paragraph. A line may
        # contain overlapping variants (for example, "AWS" and "AWS cloud"),
        # so use the earliest, most-specific variant without duplicating it.
        found_line = False
        for line_idx, (page_num, line) in enumerate(entry.lines):
            rejoined_line = rejoin_hyphenated_words(line)
            line_matches = match_keyword_in_text(rejoined_line, canonical)
            if line_matches:
                snippet = _evidence_paragraph(entry, line_idx)
                paragraph_key = (entry_idx, page_num, snippet)
                if paragraph_key in seen_paragraphs:
                    found_line = True
                    continue
                seen_paragraphs.add(paragraph_key)
                matches.append(
                    KeywordMatch(
                        page_num=page_num,
                        snippet=snippet,
                        matched_variant=min(
                            line_matches,
                            key=lambda item: (
                                item[1].start(),
                                -(item[1].end() - item[1].start()),
                                item[0],
                            ),
                        )[0],
                        entry_index=entry_idx,
                    )
                )
                found_line = True

        if not found_line:
            # Entry-level match but no single-line match (multi-word spanning lines)
            page_num = entry.lines[0][0]
            snippet = _clean_evidence_snippet(
                [line_text for _, line_text in entry.lines[:3]]
            )
            matches.append(
                KeywordMatch(
                    page_num=page_num,
                    snippet=snippet,
                    matched_variant=entry_matches[0][0],
                    entry_index=entry_idx,
                )
            )

    return matches


def find_variant_matches(
    entries: List[Entry], variants: Set[str]
) -> List[KeywordMatch]:
    """Find literal related-concept variants without treating them as synonyms."""
    matches: List[KeywordMatch] = []
    seen_paragraphs: Set[Tuple[int, int, str]] = set()
    ordered_variants = sorted(variants, key=len, reverse=True)
    for entry_idx, entry in enumerate(entries):
        for line_idx, (page_num, line) in enumerate(entry.lines):
            rejoined_line = rejoin_hyphenated_words(line)
            matched_variant = ""
            for variant in ordered_variants:
                if _build_keyword_pattern(variant).search(rejoined_line):
                    matched_variant = variant
                    break
            if not matched_variant:
                continue
            snippet = _evidence_paragraph(entry, line_idx)
            paragraph_key = (entry_idx, page_num, snippet)
            if paragraph_key in seen_paragraphs:
                continue
            seen_paragraphs.add(paragraph_key)
            matches.append(
                KeywordMatch(
                    page_num=page_num,
                    snippet=snippet,
                    matched_variant=matched_variant,
                    entry_index=entry_idx,
                )
            )
    return matches


def detect_tools_in_entries(entries: List[Entry]) -> List[str]:
    """Return normalized technologies mentioned in professional experience."""
    experience_text = rejoin_hyphenated_words(
        "\n".join(entry.text() for entry in entries)
    )
    detected = {
        canonical
        for canonical in SYNONYM_MAP
        if canonical not in _NON_FILTERABLE_TOOL_CONCEPTS
        and match_keyword_in_text(experience_text, canonical)
    }

    # Managed Kubernetes services belong under the Kubernetes facet. Provider
    # implications keep EKS useful under AWS and AKS useful under Azure without
    # exposing duplicate service chips.
    if "eks" in detected:
        detected.add("aws")
    if "aks" in detected:
        detected.add("azure")
    kubernetes_variants = {
        variant
        for variants in SEMANTIC_RELATIONSHIPS.get("kubernetes", {}).values()
        for variant in variants
    }
    if any(
        _build_keyword_pattern(variant).search(experience_text)
        for variant in kubernetes_variants
    ):
        detected.add("kubernetes")
    detected.difference_update({"aks", "eks"})
    return sorted({normalize_tool_name(tool) for tool in detected})


# ---------------------
# Scoring
# ---------------------


@dataclass
class ScoringResult:
    total_score: int
    keyword_score: float
    experience_score: float
    recency_score: float
    depth_score: float
    clarity_score: float
    breakdown: Dict[str, object] = field(default_factory=dict)


def compute_score(
    required_evidence: Dict[str, Optional[Tuple[int, str]]],
    devops_years: float,
    roles: List[Role],
    entries: List[Entry],
    ambiguity: bool,
) -> ScoringResult:
    """Compute a 0-100 confidence score for the candidate."""
    breakdown: Dict[str, object] = {}

    # 1. Required keywords (0-30)
    total_required = len(config.REQUIRED_EXPERIENCE_KEYWORDS)
    found_required = sum(1 for ev in required_evidence.values() if ev is not None)
    keyword_score = (found_required / max(total_required, 1)) * config.SCORE_WEIGHTS[
        "keywords_found"
    ]
    breakdown["keywords_found_ratio"] = found_required / max(total_required, 1)

    # 2. DevOps years (0-30), full marks at 1.5x minimum
    year_ratio = (
        min(devops_years / (config.MIN_DEVOPS_YEARS * 1.5), 1.0)
        if config.MIN_DEVOPS_YEARS > 0
        else 1.0
    )
    experience_score = year_ratio * config.SCORE_WEIGHTS["devops_years"]
    breakdown["devops_years_ratio"] = year_ratio

    # 3. Recency (0-20)
    recency_factor = _compute_recency_factor(roles)
    recency_score = recency_factor * config.SCORE_WEIGHTS["recency"]
    breakdown["recency_factor"] = recency_factor

    # 4. Keyword depth (0-10): distinct DevOps keywords across all entries
    all_text = rejoin_hyphenated_words("\n".join(e.text() for e in entries))
    distinct_found = sum(1 for kw in SYNONYM_MAP if match_keyword_in_text(all_text, kw))
    depth_ratio = min(distinct_found / 15.0, 1.0)
    depth_score = depth_ratio * config.SCORE_WEIGHTS["keyword_depth"]
    breakdown["distinct_devops_keywords"] = distinct_found

    # 5. Clarity bonus (0-10)
    clarity_score = (
        float(config.SCORE_WEIGHTS["no_ambiguity"]) if not ambiguity else 0.0
    )
    breakdown["date_clarity"] = 1.0 if not ambiguity else 0.0

    total = int(
        round(
            keyword_score
            + experience_score
            + recency_score
            + depth_score
            + clarity_score
        )
    )
    total = max(0, min(100, total))

    return ScoringResult(
        total_score=total,
        keyword_score=keyword_score,
        experience_score=experience_score,
        recency_score=recency_score,
        depth_score=depth_score,
        clarity_score=clarity_score,
        breakdown=breakdown,
    )


def _compute_recency_factor(roles: List[Role]) -> float:
    """1.0 if most recent role ended <12mo ago, linear decay to 0 at 60mo."""
    if not roles:
        return 0.0
    today = dt.date.today()
    most_recent_end = max(r.end for r in roles)
    months_ago = (today.year - most_recent_end.year) * 12 + (
        today.month - most_recent_end.month
    )
    if months_ago <= 12:
        return 1.0
    elif months_ago >= 60:
        return 0.0
    else:
        return 1.0 - ((months_ago - 12) / 48.0)


# ---------------------
# Verdict helpers
# ---------------------


def classify_bucket(result: Dict[str, object]) -> str:
    """
    Bucket is for folder distribution (not Excel):
    - ambiguous: ambiguity == True
    - passed: passed == True and not ambiguous
    - failed: otherwise
    """
    if bool(result.get("ambiguity")):
        return "ambiguous"
    return "passed" if bool(result.get("passed")) else "failed"


def excel_result_label(result: Dict[str, object]) -> str:
    """
    Value shown in the Excel 'result' cell.
    """
    return (
        "AMBIGUOUS"
        if bool(result.get("ambiguity"))
        else ("PASS" if bool(result.get("passed")) else "FAIL")
    )


def build_verdict_reasons(result: Dict[str, object]) -> List[str]:
    reasons: List[str] = []
    if bool(result.get("ambiguity")):
        ambiguity_reasons = result.get("ambiguity_reasons", [])
        if ambiguity_reasons:
            reasons.extend(str(reason) for reason in ambiguity_reasons)
        else:
            reasons.append("Ambiguous evidence requires manual review")

    required_evidence: Dict[str, object] = result.get("required_evidence", {})  # type: ignore
    evidence_details: Dict[str, Dict[str, object]] = result.get(
        "required_evidence_details", {}
    )  # type: ignore
    missing_kw = [
        kw
        for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS)
        if required_evidence.get(kw.lower()) is None
        and not evidence_details.get(kw.lower(), {}).get("needs_review")
    ]
    if missing_kw:
        reasons.append(
            f"Missing required keywords in experience: {', '.join(missing_kw)}"
        )

    devops_years = float(result.get("devops_years", 0))
    if devops_years < config.MIN_DEVOPS_YEARS and not result.get("date_ambiguity"):
        reasons.append(
            f"Insufficient DevOps experience: {devops_years} yr (need {config.MIN_DEVOPS_YEARS})"
        )

    if result.get("excluded_company"):
        reasons.append(f"Worked at excluded company: {result['excluded_company']}")

    if result.get("excluded_university"):
        reasons.append(f"Attended excluded university: {result['excluded_university']}")

    if config.PREFERRED_PROGRAM_PATTERNS and not result.get("preferred_program"):
        reasons.append("Missing required preferred program")

    if config.MIN_SCORE is not None and int(result.get("score", 0)) < config.MIN_SCORE:
        reasons.append(
            f"Score {result.get('score')} below threshold ({config.MIN_SCORE})"
        )

    if not reasons:
        reasons.append("All criteria met")

    return reasons


def normalize_excel_col_name(keyword: str) -> str:
    s = keyword.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "keyword"


# ---------------------
# Core screening
# ---------------------


def screen_cv(cv_path: Path) -> Dict[str, object]:
    if cv_path.suffix.lower() == ".docx":
        pages, used_ocr = extract_text_from_docx(cv_path)
        multi_column_layout = False
    else:
        pages, used_ocr = extract_text_by_page(cv_path)
        multi_column_layout = pdf_has_multi_column_layout(cv_path)
    full_text = "\n".join(pages)
    exp_entries = extract_experience_entries(pages)

    # Separate education-program entries from professional experience
    education_program_entries: List[str] = []
    filtered_entries: List[Entry] = []
    for e in exp_entries:
        if is_education_program(e.head(3)):
            education_program_entries.append(e.head(3))
        else:
            filtered_entries.append(e)

    # Check excluded companies
    excluded_company_hit: Optional[str] = None
    if config.EXCLUDED_COMPANY_PATTERNS:
        for e in filtered_entries:
            for p in config.EXCLUDED_COMPANY_PATTERNS:
                m = p.search(e.text())
                if m:
                    excluded_company_hit = m.group(0)
                    break
            if excluded_company_hit:
                break

    # Check excluded universities (scan full CV text)
    excluded_university_hit: Optional[str] = None
    if config.EXCLUDED_UNIVERSITY_PATTERNS:
        for p in config.EXCLUDED_UNIVERSITY_PATTERNS:
            m = p.search(full_text)
            if m:
                excluded_university_hit = m.group(0)
                break

    # Check preferred programs (scan full CV text -- education + experience)
    preferred_program_found: Optional[str] = None
    if config.PREFERRED_PROGRAM_PATTERNS:
        for p in config.PREFERRED_PROGRAM_PATTERNS:
            m = p.search(full_text)
            if m:
                preferred_program_found = m.group(0)
                break

    required_evidence_details: Dict[str, Dict[str, object]] = {
        kw.lower(): _keyword_evidence_detail(filtered_entries, kw)
        for kw in config.REQUIRED_EXPERIENCE_KEYWORDS
    }
    required_evidence: Dict[str, Optional[Tuple[int, str]]] = {}
    for keyword, detail in required_evidence_details.items():
        if detail["qualifies"]:
            required_evidence[keyword] = (
                int(detail["page"]),
                str(detail["snippet"]),
            )
        else:
            required_evidence[keyword] = None
    all_required_found = all(ev is not None for ev in required_evidence.values())

    roles, devops_months, date_ambiguity = compute_devops_roles(filtered_entries)
    devops_years = months_to_years(devops_months)
    layout_ambiguity = bool(
        multi_column_layout
        and has_experience_layout_anomaly(filtered_entries, roles)
    )

    semantic_ambiguity = any(
        bool(detail["needs_review"]) for detail in required_evidence_details.values()
    )
    ambiguity = bool(date_ambiguity or semantic_ambiguity or layout_ambiguity)
    ambiguity_reasons: List[str] = []
    if ambiguity and date_ambiguity:
        ambiguity_reasons.append(
            "Date ambiguity detected -- experience duration requires review"
        )
    if ambiguity and semantic_ambiguity:
        for keyword, detail in required_evidence_details.items():
            if detail["needs_review"]:
                ambiguity_reasons.append(
                    f"Related term '{detail['matched_term']}' may satisfy "
                    f"'{keyword}', but demonstrated usage is unclear"
                )
    if ambiguity and layout_ambiguity:
        ambiguity_reasons.append(
            "Multi-column CV extraction produced an unreliable experience reading order"
        )

    devops_pass = (devops_years >= config.MIN_DEVOPS_YEARS) and (not ambiguity)
    passed = all_required_found and devops_pass

    # Fail if candidate worked at an excluded company
    if excluded_company_hit:
        passed = False

    # Fail if candidate attended an excluded university
    if excluded_university_hit:
        passed = False

    # Fail if preferred programs are configured but candidate has none
    if config.PREFERRED_PROGRAM_PATTERNS and not preferred_program_found:
        passed = False

    # Compute confidence score
    scoring = compute_score(
        required_evidence=required_evidence,
        devops_years=devops_years,
        roles=roles,
        entries=filtered_entries,
        ambiguity=ambiguity,
    )

    # Optional score-based pass threshold
    if config.MIN_SCORE is not None:
        passed = passed and (scoring.total_score >= config.MIN_SCORE)

    flattened: Dict[str, object] = {}
    for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS):
        col = normalize_excel_col_name(kw)
        ev = required_evidence.get(kw.lower())
        flattened[f"kw_found__{col}"] = ev is not None
        flattened[f"kw_page__{col}"] = ev[0] if ev else None
        flattened[f"kw_snippet__{col}"] = ev[1] if ev else ""

    experience_entries_found = int(len(filtered_entries))
    experience_text = "\n\n".join(entry.text() for entry in filtered_entries)
    detected_tools = detect_tools_in_entries(filtered_entries)

    return {
        "file": cv_path.name,
        "passed": passed,
        "required_evidence": required_evidence,
        "required_evidence_details": required_evidence_details,
        "devops_years": float(devops_years),
        "devops_roles": roles,
        "education_program_entries": education_program_entries,
        "excluded_company": excluded_company_hit,
        "excluded_university": excluded_university_hit,
        "preferred_program": preferred_program_found,
        "used_ocr": used_ocr,
        "ambiguity": ambiguity,
        "date_ambiguity": date_ambiguity,
        "semantic_ambiguity": semantic_ambiguity,
        "layout_ambiguity": layout_ambiguity,
        "ambiguity_reasons": ambiguity_reasons,
        "semantic_relationships_version": SEMANTIC_RELATIONSHIPS_VERSION,
        "devops_pass": devops_pass,
        "experience_entries_found": experience_entries_found,
        "detected_tools": detected_tools,
        "score": scoring.total_score,
        "score_breakdown": scoring.breakdown,
        "_full_text": full_text,
        "_experience_text": experience_text,
        **flattened,
    }


# ---------------------
# Output helpers
# ---------------------


def build_dynamic_headers() -> List[str]:
    headers: List[str] = ["file", "result", "score", "detected_tools"]
    for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS):
        base = normalize_excel_col_name(kw)
        headers.extend([f"{base}_found", f"{base}_page", f"{base}_snippet"])
    headers.extend(
        [
            "devops_years",
            "devops_pass",
            "date_ambiguity",
            "semantic_ambiguity",
            "used_ocr",
        ]
    )
    return headers


def row_for_result(r: Dict[str, object], headers: List[str]) -> List[object]:
    row: List[object] = []
    result_label = excel_result_label(r)

    for h in headers:
        if h == "file":
            row.append(r.get("file"))
        elif h == "result":
            row.append(result_label)
        elif h == "score":
            row.append(r.get("score", 0))
        elif h == "detected_tools":
            tools = r.get("detected_tools", [])
            row.append(
                "; ".join(str(tool) for tool in tools)
                if isinstance(tools, list)
                else ""
            )
        elif h.endswith("_found") and h not in {"devops_pass"}:
            key = f"kw_found__{h[:-6]}"
            row.append(bool(r.get(key, False)))
        elif h.endswith("_page"):
            key = f"kw_page__{h[:-5]}"
            row.append(r.get(key))
        elif h.endswith("_snippet"):
            key = f"kw_snippet__{h[:-8]}"
            row.append(r.get(key, ""))
        elif h == "devops_years":
            row.append(r.get("devops_years"))
        elif h == "devops_pass":
            row.append(bool(r.get("devops_pass", False)))
        elif h == "date_ambiguity":
            row.append(bool(r.get("date_ambiguity", r.get("ambiguity", False))))
        elif h == "semantic_ambiguity":
            row.append(bool(r.get("semantic_ambiguity", False)))
        elif h == "used_ocr":
            row.append(bool(r.get("used_ocr", False)))
        elif h == "experience_entries_found":
            # FIX: never write None; default to 0
            row.append(int(r.get("experience_entries_found", 0)))
        else:
            row.append(r.get(h))
    return row
