"""CSV, Markdown, HTML, and Excel report generation."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from kriterion import config
from kriterion.dates import format_date, months_to_years
from kriterion.experience import Role
from kriterion.scoring import (
    build_dynamic_headers,
    build_verdict_reasons,
    excel_result_label,
    row_for_result,
)


_COPILOT_ICON_SVG = """<svg class="copilot-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M23.922 16.992c-.861 1.495-5.859 5.023-11.922 5.023-6.063 0-11.061-3.528-11.922-5.023A.641.641 0 0 1 0 16.736v-2.869c0-.075.018-.149.053-.22.372-.935 1.347-2.292 2.605-2.656.167-.429.414-1.055.644-1.517a10.195 10.195 0 0 1-.052-1.086c0-1.331.282-2.499 1.132-3.368.397-.406.89-.717 1.474-.952 1.399-1.136 3.392-2.093 6.122-2.093 2.731 0 4.767.957 6.166 2.093.584.235 1.077.546 1.474.952.85.869 1.132 2.037 1.132 3.368 0 .368-.014.733-.052 1.086.23.462.477 1.088.644 1.517 1.258.364 2.233 1.721 2.605 2.656.035.071.053.145.053.22v2.869a.641.641 0 0 1-.078.256ZM12.172 11h-.344a4.323 4.323 0 0 1-.355.508C10.703 12.455 9.555 13 7.965 13c-1.725 0-2.989-.359-3.782-1.259a2.005 2.005 0 0 1-.085-.104L4 11.741v6.585c1.435.779 4.514 2.179 8 2.179 3.486 0 6.565-1.4 8-2.179v-6.585l-.098-.104a2.005 2.005 0 0 1-.085.104c-.793.9-2.057 1.259-3.782 1.259-1.59 0-2.738-.545-3.508-1.492a4.323 4.323 0 0 1-.355-.508Zm.641-2.935c.136 1.057.403 1.913.878 2.497.442.544 1.134.938 2.344.938 1.573 0 2.292-.337 2.657-.751.384-.435.558-1.15.558-2.361 0-1.14-.243-1.847-.705-2.319-.477-.488-1.319-.862-2.824-1.025-1.487-.161-2.192.138-2.533.529-.269.307-.437.808-.438 1.578v.021c0 .265.021.562.063.893Zm-1.626 0c.042-.331.063-.628.063-.894v-.02c-.001-.77-.169-1.271-.438-1.578-.341-.391-1.046-.69-2.533-.529-1.505.163-2.347.537-2.824 1.025-.462.472-.705 1.179-.705 2.319 0 1.211.175 1.926.558 2.361.365.414 1.084.751 2.657.751 1.21 0 1.902-.394 2.344-.938.475-.584.742-1.44.878-2.497Z"/><path d="M14.5 14.25a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0v-2a1 1 0 0 1 1-1Zm-5 0a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0v-2a1 1 0 0 1 1-1Z"/></svg>"""


def write_csv(results: List[Dict[str, object]], output_path: Path) -> None:
    headers = build_dynamic_headers()
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in results:
            w.writerow(row_for_result(r, headers))


def write_report(results: List[Dict[str, object]], output_path: Path) -> None:
    total = len(results)
    passed = sum(
        1 for r in results if bool(r["passed"]) and not bool(r.get("ambiguity"))
    )
    ambiguous = sum(1 for r in results if bool(r.get("ambiguity")))
    failed = total - passed - ambiguous

    lines: List[str] = []
    lines.append("# CV Screening Report\n")
    lines.append("## Summary")
    lines.append(f"- Total CVs: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Ambiguous: {ambiguous}\n")

    lines.append("## Active Screening Criteria")
    lines.append(
        f"- Required keywords in Experience: {', '.join(sorted(config.REQUIRED_EXPERIENCE_KEYWORDS))}"
    )
    lines.append(f"- Minimum DevOps experience: {config.MIN_DEVOPS_YEARS} years\n")

    for r in results:
        lines.append(f"## {r['file']}")
        lines.append(f"- Result: {excel_result_label(r)}")
        lines.append(f"- Confidence Score: {r.get('score', 0)}/100")
        if r["used_ocr"]:
            lines.append("- Note: OCR fallback used for text extraction.")

        required_evidence: Dict[str, Optional[Tuple[int, str]]] = r["required_evidence"]  # type: ignore
        evidence_details: Dict[str, Dict[str, object]] = r.get(
            "required_evidence_details", {}
        )  # type: ignore
        lines.append("- Required keywords evidence (Experience):")
        for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS):
            ev = required_evidence.get(kw.lower())
            detail = evidence_details.get(kw.lower(), {})
            if ev:
                relationship = str(detail.get("relationship", "direct")).replace(
                    "_", " "
                )
                matched_term = str(detail.get("matched_term", kw))
                lines.append(
                    f"  - {kw}: Yes ({relationship}; matched {matched_term}; page {ev[0]})"
                )
                lines.append("    Snippet:\n\n    " + ev[1].replace("\n", "\n    "))
            elif detail.get("needs_review"):
                lines.append(
                    f"  - {kw}: Ambiguous related term "
                    f"({detail.get('matched_term')}; manual review required)"
                )
            else:
                lines.append(f"  - {kw}: No")

        lines.append(
            f"- DevOps years counted (unique, overlap-safe): {r['devops_years']}"
        )
        lines.append(
            f"- DevOps pass (>= {config.MIN_DEVOPS_YEARS} years AND no ambiguity): {'Yes' if r['devops_pass'] else 'No'}"
        )
        lines.append(f"- Date ambiguity: {'Yes' if r.get('date_ambiguity') else 'No'}")
        lines.append(
            f"- Semantic ambiguity: {'Yes' if r.get('semantic_ambiguity') else 'No'}"
        )

        roles: List[Role] = r["devops_roles"]  # type: ignore
        if roles:
            lines.append("- DevOps roles counted:")
            for role in roles:
                role_years = months_to_years(role.months_added)
                lines.append(
                    f"  - {role.title} ({format_date(role.start)} to {format_date(role.end)}): {role_years} years"
                )
        else:
            lines.append("- DevOps roles counted: None")

        excl: List[str] = r["education_program_entries"]  # type: ignore
        if excl:
            lines.append("- Education program entries (not counted as experience):")
            for e in excl:
                lines.append(f"  - {e}")
        else:
            lines.append("- Education program entries: None")

        if r.get("excluded_company"):
            lines.append(f"- EXCLUDED COMPANY: {r['excluded_company']}")
        if r.get("excluded_university"):
            lines.append(f"- EXCLUDED UNIVERSITY: {r['excluded_university']}")
        if config.PREFERRED_PROGRAM_PATTERNS:
            if r.get("preferred_program"):
                lines.append(f"- Preferred program found: {r['preferred_program']}")
            else:
                lines.append("- Preferred program found: No (REQUIRED)")

        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _highlight_term(escaped_snippet: str, matched_term: str) -> str:
    escaped_term = _html_escape(matched_term)
    pattern = re.compile(re.escape(escaped_term), re.IGNORECASE)
    return pattern.sub(
        lambda m: f'<mark class="kw-hl">{m.group(0)}</mark>',
        escaped_snippet,
    )


def write_html_report(
    results: List[Dict[str, object]],
    output_path: Path,
    cv_folder: Optional[Path] = None,
    *,
    auto_ai_review: bool = True,
    profile: Optional[Dict[str, object]] = None,
) -> None:
    total = len(results)
    passed = sum(
        1 for r in results if bool(r["passed"]) and not bool(r.get("ambiguity"))
    )
    ambiguous = sum(1 for r in results if bool(r.get("ambiguity")))
    failed = total - passed - ambiguous
    kw_coverage = {}
    for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS):
        found = sum(
            1 for r in results if r["required_evidence"].get(kw.lower()) is not None
        )
        kw_coverage[kw] = {
            "found": found,
            "missing": total - found,
            "pct": round(found / max(total, 1) * 100),
        }

    reason_counts: Dict[str, int] = {}
    for r in results:
        if r["passed"] and not r.get("ambiguity"):
            continue
        for kw, ev in r["required_evidence"].items():
            if ev is None:
                key = f"Missing: {kw}"
                reason_counts[key] = reason_counts.get(key, 0) + 1
        if r["devops_years"] < config.MIN_DEVOPS_YEARS and not r.get("ambiguity"):
            reason_counts["Insufficient experience years"] = (
                reason_counts.get("Insufficient experience years", 0) + 1
            )
        if r.get("date_ambiguity"):
            reason_counts["Date ambiguity"] = reason_counts.get("Date ambiguity", 0) + 1
        if r.get("semantic_ambiguity"):
            reason_counts["Semantic ambiguity"] = (
                reason_counts.get("Semantic ambiguity", 0) + 1
            )
        if r.get("excluded_company"):
            reason_counts["Excluded company"] = (
                reason_counts.get("Excluded company", 0) + 1
            )
        if r.get("excluded_university"):
            reason_counts["Excluded university"] = (
                reason_counts.get("Excluded university", 0) + 1
            )
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:8]
    max_reason_count = top_reasons[0][1] if top_reasons else 1

    cv_base = cv_folder.resolve() if cv_folder else None

    def _file_link(filename: str) -> str:
        escaped = _html_escape(filename)
        if cv_base:
            from urllib.parse import quote

            file_url = "/cvs/" + quote(filename, safe="")
            return f'<a href="{file_url}" target="_blank" class="file-link" title="Open CV">{escaped}</a>'
        return escaped

    kw_bars_html = ""
    for kw, data in kw_coverage.items():
        pct = data["pct"]
        color = (
            "var(--green)"
            if pct >= 70
            else "var(--amber)"
            if pct >= 40
            else "var(--red)"
        )
        kw_bars_html += f'<div class="chart-row"><span class="chart-label">{_html_escape(kw)}</span><div class="chart-bar-track"><div class="chart-bar-fill" style="width:{pct}%;background:{color}"></div></div><span class="chart-value">{pct}%</span></div>'

    reasons_bars_html = ""
    for reason, count in top_reasons:
        pct = round(count / max(max_reason_count, 1) * 100)
        reasons_bars_html += f'<div class="chart-row"><span class="chart-label">{_html_escape(reason)}</span><div class="chart-bar-track"><div class="chart-bar-fill reason-fill" style="width:{pct}%"></div></div><span class="chart-value">{count}</span></div>'

    table_rows = ""
    for idx, r in enumerate(results):
        result_label = excel_result_label(r)
        score = int(r.get("score", 0))
        status_class = result_label.lower()
        kw_found = sum(1 for v in r["required_evidence"].values() if v is not None)  # type: ignore
        kw_total = len(config.REQUIRED_EXPERIENCE_KEYWORDS)
        reasons = build_verdict_reasons(r)

        table_rows += f"""<tr class="data-row row-{status_class}" data-status="{status_class}" data-idx="{idx}" role="button" tabindex="0" aria-expanded="false" aria-label="Review candidate {_html_escape(str(r["file"]))}">
            <td class="cell-name">{_file_link(str(r["file"]))}</td>
            <td><span class="pill pill-{status_class}">{result_label}</span></td>
            <td><div class="score-bar-cell"><div class="score-bar-track"><div class="score-bar-fill score-fill-{status_class}" style="width:{score}%"></div></div><span class="score-num">{score}</span></div></td>
            <td>{math.ceil(r["devops_years"] * 2) / 2} yr</td>
            <td>{kw_found}/{kw_total}</td>
        </tr>"""

        kw_items = ""
        required_evidence: Dict[str, Optional[Tuple[int, str]]] = r["required_evidence"]  # type: ignore
        evidence_details: Dict[str, Dict[str, object]] = r.get(
            "required_evidence_details", {}
        )  # type: ignore
        for kw in sorted(config.REQUIRED_EXPERIENCE_KEYWORDS):
            ev = required_evidence.get(kw.lower())
            detail = evidence_details.get(kw.lower(), {})
            if ev:
                snippet = _html_escape(ev[1][:200])
                relationship = str(detail.get("relationship", "direct"))
                matched_term = str(detail.get("matched_term", kw))
                evidence_label = (
                    f"{relationship.replace('_', ' ')} · p.{ev[0]}"
                    if relationship != "direct"
                    else f"direct · p.{ev[0]}"
                )
                snippet_hl = _highlight_term(snippet, matched_term)
                kw_items += f"""<div class="kw-item kw-found">
                    <div class="kw-header"><span class="kw-name">{_html_escape(kw)}</span><span class="kw-badge found">{_html_escape(evidence_label)}</span></div>
                    <div class="kw-relation">Matched: {_html_escape(matched_term)}</div>
                    <pre class="kw-snippet">{snippet_hl}</pre>
                </div>"""
            elif detail.get("needs_review"):
                matched_term = _html_escape(str(detail.get("matched_term", "")))
                snippet = _html_escape(str(detail.get("snippet", ""))[:200])
                snippet_hl = _highlight_term(
                    snippet, str(detail.get("matched_term", ""))
                )
                kw_items += f"""<div class="kw-item kw-review">
                    <div class="kw-header"><span class="kw-name">{_html_escape(kw)}</span><span class="kw-badge review">review needed</span></div>
                    <div class="kw-relation">Related term: {matched_term}</div>
                    <pre class="kw-snippet">{snippet_hl}</pre>
                </div>"""
            else:
                kw_items += f"""<div class="kw-item kw-missing">
                    <div class="kw-header"><span class="kw-name">{_html_escape(kw)}</span><span class="kw-badge missing">missing</span></div>
                </div>"""

        roles: List[Role] = r["devops_roles"]  # type: ignore
        exp_items = ""
        if roles:
            for role_index, role in enumerate(roles):
                ry = months_to_years(role.months_added)
                has_next_role = role_index < len(roles) - 1
                connected_class = " exp-item-connected" if has_next_role else ""
                connector = (
                    '<div class="exp-connector" aria-hidden="true">'
                    '<span class="exp-particle"></span>'
                    '<span class="exp-particle"></span>'
                    '<span class="exp-particle"></span>'
                    "</div>"
                    if has_next_role
                    else ""
                )
                exp_items += f"""<div class="exp-item{connected_class}">
                    <div class="exp-dot"></div>
                    <div class="exp-content">
                        <div class="exp-title">{_html_escape(role.title)}</div>
                        <div class="exp-meta">{format_date(role.start)} — {format_date(role.end)} &middot; {ry} yr</div>
                    </div>
                    {connector}
                </div>"""
        else:
            exp_items = '<p class="empty-state">No DevOps roles detected</p>'

        flags_items = ""
        edu_entries: List[str] = r.get("education_program_entries", [])  # type: ignore
        if edu_entries:
            for e in edu_entries:
                flags_items += f'<div class="flag-item flag-info"><span class="flag-icon">\U0001f393</span><span>Listed as experience but classified as education: {_html_escape(e)}</span></div>'
        if r.get("excluded_company"):
            flags_items += f'<div class="flag-item flag-danger"><span class="flag-icon">\U0001f6ab</span><span>Excluded company: {_html_escape(str(r["excluded_company"]))}</span></div>'
        if r.get("excluded_university"):
            flags_items += f'<div class="flag-item flag-danger"><span class="flag-icon">\U0001f6ab</span><span>Excluded university: {_html_escape(str(r["excluded_university"]))}</span></div>'
        if config.PREFERRED_PROGRAM_PATTERNS:
            if r.get("preferred_program"):
                flags_items += f'<div class="flag-item flag-success"><span class="flag-icon">✓</span><span>Preferred program: {_html_escape(str(r["preferred_program"]))}</span></div>'
            else:
                flags_items += '<div class="flag-item flag-danger"><span class="flag-icon">✗</span><span>No preferred program found (required)</span></div>'
        if not flags_items:
            flags_items = '<p class="empty-state">No flags</p>'

        verdict_icon = (
            "✓"
            if result_label == "PASS"
            else ("⚠" if result_label == "AMBIGUOUS" else "✗")
        )
        reason_items = "".join(
            f'<li class="verdict-item">{_html_escape(reason)}</li>'
            for reason in reasons
        )

        ai_review_section = ""
        if bool(r.get("ambiguity")):
            ai_review_section = f"""<section class="review-section ai-review-section">
                <div class="review-section-head">
                    <div class="section-icon section-icon-ai">{_COPILOT_ICON_SVG}</div>
                    <div>
                        <h4>AI recommendation</h4>
                        <p>A second opinion for the unresolved evidence</p>
                    </div>
                </div>
                <div class="semantic-review-container" data-file="{_html_escape(str(r["file"]))}" data-idx="{idx}">
                    <div class="ai-scope"><span>Ambiguity only</span><span>Work experience only</span><span>Human decides</span></div>
                    <button class="semantic-review-btn" onclick="requestAmbiguityVerdict(this)">Generate recommendation</button>
                    <div class="semantic-review-output"></div>
                </div>
            </section>"""

        outcome_copy = (
            "Needs a reviewer to resolve uncertain evidence"
            if result_label == "AMBIGUOUS"
            else (
                "Meets the configured screening requirements"
                if result_label == "PASS"
                else "Does not meet one or more screening requirements"
            )
        )

        table_rows += f"""<tr class="detail-row" data-idx="{idx}" data-status="{status_class}" style="display:none">
            <td colspan="5">
                <div class="candidate-review">
                    <header class="review-hero review-hero-{status_class}">
                        <div class="review-outcome">
                            <div class="outcome-icon">{verdict_icon}</div>
                            <div>
                                <div class="review-eyebrow">Screening outcome</div>
                                <h3>{result_label}</h3>
                                <p>{outcome_copy}</p>
                            </div>
                        </div>
                        <div class="review-metrics">
                            <div class="review-metric"><strong>{score}</strong><span>Score</span></div>
                            <div class="review-metric"><strong>{math.ceil(r["devops_years"] * 2) / 2}</strong><span>Years</span></div>
                            <div class="review-metric"><strong>{kw_found}/{kw_total}</strong><span>Requirements</span></div>
                        </div>
                    </header>
                    <div class="review-body">
                        <section class="decision-rationale rationale-{status_class}">
                            <div class="rationale-heading">
                                <span>Why this decision</span>
                                <small>Deterministic screening evidence</small>
                            </div>
                            <ul>{reason_items}</ul>
                        </section>
                        <section class="review-section evidence-section">
                            <div class="review-section-head">
                                <div class="section-icon">01</div>
                                <div>
                                    <h4>Requirement evidence</h4>
                                    <p>{kw_found} of {kw_total} required technologies confirmed in work experience</p>
                                </div>
                            </div>
                            <div class="keyword-grid">{kw_items}</div>
                        </section>
                        <div class="review-split">
                            <section class="review-section">
                                <div class="review-section-head">
                                    <div class="section-icon">02</div>
                                    <div>
                                        <h4>Relevant career history</h4>
                                        <p>{len(roles)} qualifying role{"s" if len(roles) != 1 else ""} used in the calculation</p>
                                    </div>
                                </div>
                                <div class="timeline">{exp_items}</div>
                            </section>
                            <section class="review-section">
                                <div class="review-section-head">
                                    <div class="section-icon">03</div>
                                    <div>
                                        <h4>Screening notes</h4>
                                        <p>Education, exclusions, and preferred-program checks</p>
                                    </div>
                                </div>
                                <div class="screening-notes">{flags_items}</div>
                            </section>
                        </div>
                        {ai_review_section}
                    </div>
                </div>
            </td>
        </tr>"""

    pass_pct = passed / max(total, 1) * 100
    fail_pct = failed / max(total, 1) * 100
    ambiguous_pct = ambiguous / max(total, 1) * 100
    pass_rate = round(pass_pct)

    def _profile_list(key: str) -> List[str]:
        values = (profile or {}).get(key, [])
        if not isinstance(values, list):
            return []
        return [str(value) for value in values if str(value).strip()]

    def _profile_short_names(key: str) -> List[str]:
        short_names = [value for value in _profile_list(key) if len(value.split()) == 1]
        return [
            value.upper() if value.isalpha() and len(value) <= 5 else value.title()
            for value in short_names
        ]

    def _restriction_group(label: str, values: List[str], chip_class: str) -> str:
        if not values:
            return ""
        chips = "".join(
            f'<span class="chip {chip_class}">{_html_escape(value)}</span>'
            for value in values
        )
        return (
            f'<div class="criteria-section"><h4>{_html_escape(label)}</h4>'
            f'<div class="chips">{chips}</div></div>'
        )

    min_years = f"{config.MIN_DEVOPS_YEARS:g}+ years"
    restriction_groups_html = "".join(
        [
            _restriction_group(
                "Required in Experience",
                sorted(config.REQUIRED_EXPERIENCE_KEYWORDS),
                "chip-required",
            ),
            _restriction_group("Minimum Experience", [min_years], "chip-rule"),
            _restriction_group(
                "Minimum Score",
                [f"{config.MIN_SCORE}/100"] if config.MIN_SCORE is not None else [],
                "chip-rule",
            ),
            _restriction_group(
                "One Preferred Program Required",
                _profile_list("preferred_programs"),
                "chip-preferred",
            ),
            _restriction_group(
                "Excluded Companies",
                _profile_list("excluded_companies"),
                "chip-excluded",
            ),
            _restriction_group(
                "Excluded Universities",
                _profile_list("excluded_universities"),
                "chip-excluded",
            ),
            _restriction_group(
                "Not Counted as Experience",
                _profile_short_names("education_programs"),
                "chip-muted",
            ),
        ]
    )

    profile_role = _html_escape(str((profile or {}).get("role", "Target role")))
    podium_skills_html = "".join(
        f'<div class="demo-skill"><span>{_html_escape(keyword)}</span>'
        f'<b><i style="--skill:{data["pct"]}%"></i></b>'
        f'<em>{data["pct"]}%</em></div>'
        for keyword, data in list(kw_coverage.items())[:3]
    )

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kriterion — Report</title>
<link rel="icon" type="image/png" sizes="48x48" href="icon.png">
<link rel="apple-touch-icon" href="icon.png">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
--bg:#0b0e14;--bg2:#12161f;--bg3:#1a1f2e;--bg4:#222838;
--border:#2a3041;--border2:#353d52;
--text:#e2e8f4;--text2:#8892a8;--text3:#5c6680;
--accent:#7c5cfc;--accent2:#9d7dff;--accent-g:rgba(124,92,252,.12);
--green:#22c55e;--green-g:rgba(34,197,94,.1);
--red:#f43f5e;--red-g:rgba(244,63,94,.1);
--amber:#f59e0b;--amber-g:rgba(245,158,11,.1);
--radius:14px;--radius-sm:8px;
--font:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;
--mono:'JetBrains Mono','Fira Code','SF Mono',monospace;
}}
[data-theme="light"]{{
--bg:#f4f6fa;--bg2:#fff;--bg3:#fff;--bg4:#f0f2f8;
--border:#e0e4ee;--border2:#d0d5e2;
--text:#1a1f2e;--text2:#5c6680;--text3:#8892a8;
}}
body{{font-family:var(--font);font-size:16px;background:var(--bg);color:var(--text);min-height:100vh}}
a{{color:inherit}}

/* Header — 3-row structured layout */
.header{{background:var(--bg2);border-bottom:1px solid var(--border);padding:1.8rem 2.5rem 1.5rem;display:flex;flex-direction:column;gap:1.4rem}}
.header-top{{display:flex;justify-content:space-between;align-items:center}}
.header-brand{{display:flex;align-items:center;gap:1rem}}
.logo-icon{{width:76px;height:76px;border-radius:14px;overflow:hidden;animation:brand-mark-in .95s cubic-bezier(.2,.8,.2,1) both}}.logo-icon img{{width:100%;height:100%;object-fit:contain}}
.logo-text{{font-size:2rem;font-weight:760;letter-spacing:-.045em;animation:brand-name-in .85s .14s cubic-bezier(.2,.8,.2,1) both}}
.theme-btn{{background:var(--bg3);border:1px solid var(--border);border-radius:9px;padding:.55rem 1rem;cursor:pointer;font-size:.85rem;transition:all .2s;white-space:nowrap}}
.theme-btn:hover{{border-color:var(--accent)}}
@keyframes brand-mark-in{{from{{opacity:0;transform:translateY(9px) scale(.86) rotate(-3deg)}}to{{opacity:1;transform:none}}}}
@keyframes brand-name-in{{from{{opacity:0;transform:translateX(-10px);letter-spacing:.035em}}to{{opacity:1;transform:none;letter-spacing:-.045em}}}}

/* Screening summary: intake, outcomes, and pass-rate ring */
.header-middle{{position:relative;display:grid;grid-template-columns:minmax(205px,.58fr) minmax(470px,1.45fr) minmax(275px,.74fr);align-items:stretch;padding:1.45rem .2rem 1.7rem;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}}
.stat-box{{--status:var(--accent);appearance:none;background:transparent;color:inherit;font:inherit;cursor:pointer;transition:background .22s,box-shadow .22s;border:0}}
.stat-box:hover{{background:color-mix(in srgb,var(--status) 5%,transparent)}}
.stat-box:focus-visible{{outline:2px solid var(--status);outline-offset:-3px}}
.stat-box.stat-active{{background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--status) 8%,transparent));box-shadow:inset 0 -2px var(--status)}}
.screening-intake{{--status:var(--accent);display:grid;align-content:center;min-height:200px;padding:1.1rem clamp(1.2rem,2.2vw,2.4rem) 1.1rem .45rem;text-align:left;border-right:1px solid var(--border)}}
.summary-kicker{{color:var(--accent2);font-size:.7rem;font-weight:750;letter-spacing:.12em;text-transform:uppercase}}
.screening-intake .stat-val{{margin-top:.2rem;font-size:clamp(4rem,6vw,6.4rem);font-weight:780;letter-spacing:-.085em;line-height:.94}}
.screening-intake .stat-lbl{{margin-top:.6rem;color:var(--text2);font-size:.8rem}}
.outcome-grid{{display:grid;grid-template-columns:repeat(3,1fr);align-items:stretch;gap:clamp(.6rem,1.5vw,1.3rem);padding:0 clamp(1.2rem,2.6vw,2.8rem)}}
.outcome-card{{position:relative;display:grid;align-content:center;min-height:200px;padding:1.3rem .8rem 1.05rem 1.45rem;text-align:left;box-shadow:inset 0 1px var(--border),inset 0 -1px var(--border)}}
.outcome-card.stat-pass{{--status:var(--green)}}.outcome-card.stat-fail{{--status:var(--red)}}.outcome-card.stat-amb{{--status:var(--amber)}}
.outcome-bar{{position:absolute;left:0;top:14%;width:3px;height:0;border-radius:1px;background:var(--status);animation:outcome-bar-down 1.65s cubic-bezier(.2,.82,.2,1) forwards}}
.outcome-card:nth-child(2) .outcome-bar{{animation-delay:.12s}}.outcome-card:nth-child(3) .outcome-bar{{animation-delay:.24s}}
.outcome-card .stat-lbl{{color:var(--text2);font-size:.7rem;font-weight:740;letter-spacing:.11em;text-transform:uppercase}}
.outcome-card .stat-val{{margin-top:.42rem;color:var(--status);font-size:clamp(2.2rem,3.4vw,3.5rem);font-weight:750;letter-spacing:-.055em;line-height:1}}
.stat-pct{{margin-top:.55rem;color:var(--text3);font-family:var(--mono);font-size:.7rem}}
.donut-wrap{{display:flex;align-items:center;justify-content:center;gap:.9rem;padding-left:clamp(1.2rem,2.5vw,2.5rem);border-left:1px solid var(--border)}}
.donut{{width:122px;height:122px;position:relative;flex:0 0 auto}}
.donut svg{{transform:rotate(-90deg);width:100%;height:100%}}
.donut-track,.donut-segment{{fill:none;stroke-width:4.2}}.donut-track{{stroke:var(--border)}}
.donut-segment{{stroke-linecap:round;stroke-dasharray:0 100;stroke-dashoffset:var(--offset);animation:donut-draw 1.85s .5s cubic-bezier(.2,.8,.2,1) forwards}}
.donut-center{{position:absolute;inset:0;display:grid;place-content:center;text-align:center}}
.donut-center strong{{font-size:1.45rem;letter-spacing:-.04em}}.donut-center span{{margin-top:.1rem;color:var(--text3);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase}}
.donut-legend{{display:grid;gap:.55rem;min-width:112px;font-size:.78rem}}
.legend-item{{display:grid;grid-template-columns:8px 1fr auto;align-items:center;gap:.55rem;color:var(--text2)}}
.legend-item b{{color:var(--text);font-family:var(--mono);font-size:.75rem}}.legend-dot{{width:7px;height:7px;border-radius:50%;display:block;background:var(--dot)}}
.outcome-distribution{{position:absolute;right:.2rem;bottom:-1px;left:.2rem;display:flex;gap:3px;height:4px;overflow:hidden;border-radius:99px;background:var(--border)}}
.outcome-distribution i{{display:block;min-width:0;transform:scaleX(0);transform-origin:left;border-radius:inherit;animation:distribution-in 1.25s cubic-bezier(.2,.8,.2,1) forwards}}
.outcome-distribution .dist-pass{{background:var(--green)}}.outcome-distribution .dist-fail{{background:var(--red);animation-delay:.12s}}.outcome-distribution .dist-amb{{background:var(--amber);animation-delay:.24s}}
@keyframes outcome-bar-down{{to{{height:72%}}}}@keyframes distribution-in{{to{{transform:scaleX(1)}}}}@keyframes donut-draw{{to{{stroke-dasharray:var(--dash)}}}}

/* Bottom row: active profile restrictions */
.header-bottom{{display:flex;align-items:flex-start}}
.restrictions{{display:flex;align-items:flex-start;flex-wrap:wrap;gap:1rem 2rem;width:100%}}
.criteria-section{{min-width:max-content}}
.criteria-section h4{{font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:.4rem}}
.chips{{display:flex;flex-wrap:wrap;gap:.4rem}}
.chip{{padding:.3rem .7rem;border:1px solid transparent;border-radius:12px;font-size:.8rem;font-weight:600}}
.chip-required{{background:var(--accent-g);color:var(--accent2);border-color:rgba(124,92,252,.16)}}
.chip-rule{{background:var(--bg3);color:var(--text);border-color:var(--border)}}
.chip-preferred{{background:var(--green-g);color:var(--green);border-color:rgba(34,197,94,.18)}}
.chip-excluded{{background:var(--red-g);color:var(--red);border-color:rgba(244,63,94,.18)}}
.chip-muted{{background:var(--bg3);color:var(--text2);border-color:var(--border)}}

/* Scroll-driven screening insights */
.insights-stage{{--demo-enter:0;--demo-reasons:0;--demo-scan:0;--demo-coverage:0;--demo-decision:0;--demo-morph:0;--demo-pass-glow:0;--demo-fail-glow:0;--demo-amb-glow:0;--demo-flight-x:0px;--demo-flight-y:0px;--demo-tilt-y:-10deg;--demo-tilt-x:4deg;--demo-depth:70px;--demo-orb-color:var(--accent);position:relative;height:350vh;border-bottom:1px solid var(--border)}}
.insights-sticky{{position:sticky;top:0;display:grid;grid-template-columns:minmax(330px,.72fr) minmax(610px,1.28fr);gap:clamp(1.25rem,3vw,3.5rem);align-items:center;height:100vh;min-height:680px;max-width:1600px;margin:0 auto;padding:clamp(1.5rem,3vw,3rem) clamp(1.5rem,3vw,3rem);overflow:hidden}}
.charts-column{{display:grid;gap:1rem;align-content:center;position:relative;z-index:8}}
.chart-card{{--chart-stage:1;position:relative;overflow:hidden;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:1.2rem 1.5rem;opacity:calc(.08 + var(--chart-stage) * .92);transform:translateY(calc((1 - var(--chart-stage)) * 30px)) scale(calc(.975 + var(--chart-stage) * .025));filter:blur(calc((1 - var(--chart-stage)) * 5px));transition:border-color .25s,box-shadow .25s;will-change:opacity,transform,filter}}
.chart-reasons{{--chart-stage:var(--demo-reasons)}}.chart-coverage{{--chart-stage:var(--demo-coverage)}}
.chart-card::before{{content:"";position:absolute;top:-1px;right:22%;left:22%;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:var(--chart-stage);box-shadow:0 0 12px var(--accent)}}
.chart-card h3{{font-size:.88rem;font-weight:600;margin-bottom:1rem;color:var(--text)}}
.chart-row{{display:flex;align-items:center;gap:.8rem;margin-bottom:.6rem}}
.chart-label{{font-size:.82rem;min-width:120px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.chart-bar-track{{flex:1;height:10px;background:var(--bg4);border-radius:5px;overflow:hidden}}
.chart-bar-fill{{height:100%;border-radius:5px;transform:scaleX(var(--chart-stage));transform-origin:left;transition:transform .2s linear}}
.reason-fill{{background:var(--red)}}
.chart-value{{font-size:.82rem;font-weight:600;min-width:36px;text-align:right;font-family:var(--mono)}}
.podium-column{{position:relative;height:min(80vh,760px);min-height:620px;overflow:visible;perspective:1400px}}
.demo-heading{{position:absolute;z-index:20;top:.65rem;left:1.5rem;right:1.5rem;display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}}
.demo-eyebrow{{display:block;color:var(--accent2);font-size:.66rem;font-weight:760;letter-spacing:.13em;text-transform:uppercase}}
.demo-heading h2{{margin-top:.35rem;font-size:clamp(1.25rem,2vw,1.8rem);letter-spacing:-.035em}}
.demo-heading p{{margin-top:.35rem;max-width:36ch;color:var(--text2);font-size:.72rem;line-height:1.45}}
.demo-progress{{width:128px;flex:0 0 auto;padding-top:.15rem}}
.demo-progress-copy{{display:flex;justify-content:space-between;color:var(--text3);font-family:var(--mono);font-size:.6rem;text-transform:uppercase;letter-spacing:.05em}}
.demo-progress-track{{height:3px;margin-top:.5rem;overflow:hidden;border-radius:99px;background:var(--border)}}
.demo-progress-bar{{display:block;width:100%;height:100%;transform:scaleX(0);transform-origin:left;background:linear-gradient(90deg,var(--accent),#4f9cff);box-shadow:0 0 10px var(--accent)}}
.demo-scene{{position:absolute;inset:0;transform-style:preserve-3d}}
.demo-cv-float{{--enter-y:calc((1 - var(--demo-enter)) * 70px);position:absolute;z-index:14;left:42%;top:43%;width:clamp(225px,20vw,292px);opacity:var(--demo-enter);transform:translate(-50%,-50%) translate3d(var(--demo-flight-x),calc(var(--enter-y) + var(--demo-flight-y)),var(--demo-depth)) rotateY(var(--demo-tilt-y)) rotateX(var(--demo-tilt-x));will-change:transform,opacity}}
.demo-cv{{position:relative;width:100%;aspect-ratio:.74;padding:18px;border:1px solid color-mix(in srgb,var(--accent) 38%,var(--border2));border-radius:calc(18px + var(--demo-morph) * 120px);overflow:hidden;background:linear-gradient(145deg,color-mix(in srgb,var(--bg4) 88%,var(--accent) 12%),var(--bg2));box-shadow:0 28px 60px rgba(0,0,0,.42),0 0 42px rgba(124,92,252,.13);opacity:calc(1 - var(--demo-morph));transform:scale(calc(1 - var(--demo-morph) * .86));transition:border-radius .12s linear;will-change:transform,opacity,border-radius}}
.demo-cv::before{{content:"";position:absolute;inset:0;background:linear-gradient(115deg,rgba(255,255,255,.08),transparent 22%,transparent 72%,rgba(124,92,252,.07));pointer-events:none}}
.demo-verdict-orb{{position:absolute;z-index:30;top:50%;left:50%;width:24px;height:24px;border:3px solid color-mix(in srgb,var(--demo-orb-color) 42%,white);border-radius:50%;background:var(--demo-orb-color);box-shadow:0 0 8px var(--demo-orb-color),0 0 20px color-mix(in srgb,var(--demo-orb-color) 68%,transparent),0 0 38px color-mix(in srgb,var(--demo-orb-color) 30%,transparent);opacity:var(--demo-morph);transform:translate(-50%,-50%) scale(calc(.35 + var(--demo-morph) * .65));transition:background .24s,border-color .24s,box-shadow .24s;will-change:transform,opacity}}
.demo-verdict-orb::after{{content:"";position:absolute;inset:-6px;border:1px solid color-mix(in srgb,var(--demo-orb-color) 55%,transparent);border-radius:50%;opacity:calc(.25 + var(--demo-morph) * .75);animation:demo-orb-breathe 1.8s ease-in-out infinite}}
@keyframes demo-orb-breathe{{50%{{transform:scale(1.18);opacity:.25}}}}
.demo-cv-header{{position:relative;display:grid;grid-template-columns:42px 1fr;align-items:center;gap:10px;padding-bottom:11px;border-bottom:1px solid var(--border)}}
.demo-cv-mark{{width:42px;height:42px;display:grid;place-items:center;border-radius:50%;background:var(--accent-g);border:1px solid rgba(124,92,252,.34);color:var(--accent2);font-weight:800}}
.demo-cv-header strong{{display:block;font-size:.78rem}}.demo-cv-header span{{display:block;margin-top:.2rem;color:var(--text2);font-size:.55rem}}
.demo-cv-section{{position:relative;margin-top:12px}}
.demo-cv-section h4{{margin-bottom:7px;color:var(--text2);font-size:.48rem;letter-spacing:.11em;text-transform:uppercase}}
.demo-line{{height:5px;margin:5px 0;border-radius:99px;background:linear-gradient(90deg,color-mix(in srgb,var(--text2) 50%,transparent),rgba(92,102,128,.14))}}.demo-line-long{{width:100%}}.demo-line-mid{{width:76%}}.demo-line-short{{width:54%}}
.demo-role-row{{display:grid;grid-template-columns:7px 1fr;gap:8px}}.demo-role-row::before{{content:"";width:5px;height:5px;margin-top:5px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}}
.demo-skill{{display:grid;grid-template-columns:67px 1fr 27px;align-items:center;gap:6px;margin:6px 0;color:var(--text2);font-size:.5rem}}
.demo-skill b{{height:5px;overflow:hidden;border-radius:99px;background:var(--border)}}.demo-skill b i{{display:block;width:var(--skill);height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--accent),#4f9cff);transform:scaleX(var(--demo-scan));transform-origin:left}}.demo-skill em{{font-style:normal;text-align:right;color:var(--text)}}
.demo-scan-beam{{position:absolute;z-index:20;inset:0;transform:translateY(calc((var(--demo-scan) * 112%) - 7%));opacity:clamp(0,calc(var(--demo-scan) * 4),1);pointer-events:none}}
.demo-scan-line{{position:absolute;top:0;right:-14%;left:-14%;height:2px;background:#c5b6ff;box-shadow:0 0 5px #fff,0 0 18px #9b6dff,0 0 38px #6c4dff}}
.demo-scan-wash{{position:absolute;top:-34px;right:-8%;left:-8%;height:70px;background:linear-gradient(to bottom,transparent,rgba(137,94,255,.2),transparent);filter:blur(6px)}}
.demo-podium{{position:absolute;z-index:3;left:42%;bottom:5%;width:clamp(330px,36vw,500px);height:180px;transform:translateX(-50%) rotateX(61deg);transform-style:preserve-3d}}
.demo-podium::before{{content:"";position:absolute;left:50%;bottom:-24px;width:86%;height:84px;transform:translateX(-50%);border-radius:50%;background:radial-gradient(ellipse,rgba(124,92,252,.34),rgba(124,92,252,.12) 50%,transparent 73%);filter:blur(17px)}}
.demo-podium-top,.demo-podium-rim,.demo-podium-base{{position:absolute;left:50%;border-radius:50%;transform:translateX(-50%)}}
.demo-podium-top{{z-index:4;top:0;width:74%;aspect-ratio:1/.26;background:radial-gradient(ellipse at center,rgba(255,255,255,.22) 0 8%,color-mix(in srgb,var(--accent) 30%,var(--bg3)) 18%,var(--bg3) 42%,var(--bg) 100%);border:1px solid var(--border2);box-shadow:inset 0 2px 1px rgba(255,255,255,.18),inset 0 -18px 24px rgba(0,0,0,.48),0 0 40px rgba(124,92,252,.22)}}
.demo-podium-core{{position:absolute;inset:30%;border-radius:50%;background:radial-gradient(ellipse,#fff 0,var(--accent) 12%,transparent 64%);filter:blur(5px);opacity:calc(.24 + var(--demo-scan) * .5)}}
.demo-podium-rim{{z-index:3;top:23px;width:90%;aspect-ratio:1/.28;background:linear-gradient(180deg,var(--bg4),var(--bg2) 58%,var(--bg));border:1px solid var(--border2);box-shadow:0 0 0 6px var(--bg),0 0 0 7px rgba(124,92,252,.14),inset 0 8px 12px rgba(255,255,255,.05),inset 0 -14px 18px rgba(0,0,0,.55),0 20px 34px rgba(0,0,0,.35)}}
.demo-podium-base{{z-index:2;top:66px;width:98%;aspect-ratio:1/.23;background:linear-gradient(180deg,var(--bg3),var(--bg2) 42%,var(--bg));border:1px solid var(--border);box-shadow:inset 0 10px 12px rgba(255,255,255,.025),inset 0 -20px 20px rgba(0,0,0,.5),0 22px 34px rgba(0,0,0,.5)}}
.demo-podium-base::before{{content:"";position:absolute;top:44%;right:8%;left:8%;height:20%;border-radius:99px;background:linear-gradient(90deg,transparent,var(--accent),transparent);filter:blur(6px);opacity:.72}}
.demo-podium-reflection{{position:absolute;top:108px;left:50%;width:82%;height:108px;transform:translateX(-50%);background:radial-gradient(ellipse,rgba(124,92,252,.25),transparent 70%);filter:blur(22px)}}
.demo-cv-shadow{{position:absolute;left:42%;bottom:20%;width:190px;height:42px;transform:translateX(-50%) scale(calc(1 - var(--demo-morph) * .72));border-radius:50%;background:rgba(0,0,0,.62);filter:blur(15px);opacity:calc(.58 - var(--demo-morph) * .5)}}
.demo-outcomes{{position:absolute;z-index:12;top:25%;right:1.1rem;display:grid;gap:10px;width:clamp(155px,14vw,205px)}}
.demo-outcome{{--outcome-color:var(--text2);--outcome-glow:0;display:grid;grid-template-columns:38px 1fr;gap:9px;align-items:center;padding:11px;border:1px solid color-mix(in srgb,var(--outcome-color) 24%,var(--border));border-radius:14px;background:color-mix(in srgb,var(--bg2) 88%,transparent);backdrop-filter:blur(12px);opacity:calc(.14 + var(--demo-decision) * .86);transform:translateX(calc((1 - var(--demo-decision)) * 20px)) scale(calc(1 + var(--outcome-glow) * .035));filter:saturate(calc(.35 + var(--demo-decision) * .65));box-shadow:0 0 calc(var(--outcome-glow) * 44px) color-mix(in srgb,var(--outcome-color) 58%,transparent);transition:border-color .18s,background .18s,box-shadow .18s,transform .18s}}
.demo-outcome-pass{{--outcome-color:var(--green);--outcome-glow:var(--demo-pass-glow)}}
.demo-outcome-fail{{--outcome-color:var(--red);--outcome-glow:var(--demo-fail-glow)}}
.demo-outcome-amb{{--outcome-color:var(--amber);--outcome-glow:var(--demo-amb-glow)}}
.demo-outcome-icon{{width:36px;height:36px;display:grid;place-items:center;border-radius:50%;background:color-mix(in srgb,var(--outcome-color) 18%,var(--bg3));color:var(--outcome-color);font-size:1rem;font-weight:800;box-shadow:0 0 18px color-mix(in srgb,var(--outcome-color) 18%,transparent)}}
.demo-outcome span{{display:block;color:var(--text2);font-size:.53rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}.demo-outcome strong{{display:block;margin-top:.15rem;color:var(--outcome-color);font-family:var(--mono);font-size:.82rem}}
.demo-caption{{position:absolute;right:1.3rem;bottom:1.1rem;color:var(--text3);font-size:.6rem}}

/* Main area */
.main{{padding:1.5rem 2rem;max-width:1400px;margin:0 auto;width:100%}}

/* Table */
.table-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-size:.95rem}}
thead th{{text-align:left;padding:.7rem .8rem;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);border-bottom:1px solid var(--border);background:var(--bg3)}}
tbody tr.data-row{{cursor:pointer;transition:background .15s}}
tbody tr.data-row:hover{{background:var(--bg4)}}
tbody tr.data-row.selected{{background:var(--accent-g);border-left:3px solid var(--accent)}}
tbody td{{padding:.65rem .8rem;border-bottom:1px solid var(--border);vertical-align:middle}}
.cell-name{{font-weight:500;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}

/* Score bar */
.score-bar-cell{{display:flex;align-items:center;gap:.5rem}}
.score-bar-track{{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden;min-width:40px}}
.score-bar-fill{{height:100%;border-radius:2px;transition:width .6s ease}}
.score-fill-pass{{background:var(--green)}}
.score-fill-fail{{background:var(--red)}}
.score-fill-ambiguous{{background:var(--amber)}}
.score-num{{font-family:var(--mono);font-size:.85rem;font-weight:600;min-width:22px}}

/* Pills */
.pill{{display:inline-block;padding:.15rem .5rem;border-radius:10px;font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em}}
.pill-pass{{background:var(--green-g);color:var(--green)}}
.pill-fail{{background:var(--red-g);color:var(--red)}}
.pill-ambiguous{{background:var(--amber-g);color:var(--amber)}}

/* Inline candidate review */
.detail-row td{{padding:0;border-bottom:1px solid var(--border)}}
.candidate-review{{padding:1rem 1.15rem 1.35rem;background:var(--bg);animation:reviewIn .2s ease}}
@keyframes reviewIn{{from{{opacity:0;transform:translateY(-7px)}}to{{opacity:1;transform:translateY(0)}}}}

/* Candidate review workspace */
.review-hero{{display:flex;align-items:center;justify-content:space-between;gap:1.5rem;padding:1.15rem 1.25rem;background:linear-gradient(135deg,var(--bg2),var(--bg3));border:1px solid var(--border);border-top:3px solid var(--accent);border-radius:12px 12px 0 0}}
.review-hero-pass{{border-top-color:var(--green)}}.review-hero-fail{{border-top-color:var(--red)}}.review-hero-ambiguous{{border-top-color:var(--amber)}}
.review-outcome{{display:flex;align-items:center;gap:.9rem;min-width:0}}
.outcome-icon{{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;background:var(--bg4);font-size:1.25rem;font-weight:800;flex:0 0 auto}}
.review-hero-pass .outcome-icon{{background:var(--green-g);color:var(--green)}}.review-hero-fail .outcome-icon{{background:var(--red-g);color:var(--red)}}.review-hero-ambiguous .outcome-icon{{background:var(--amber-g);color:var(--amber)}}
.review-eyebrow{{font-size:.66rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--text3);margin-bottom:.2rem}}
.review-outcome h3{{font-size:1.35rem;line-height:1;font-weight:780;letter-spacing:-.02em}}
.review-hero-pass h3{{color:var(--green)}}.review-hero-fail h3{{color:var(--red)}}.review-hero-ambiguous h3{{color:var(--amber)}}
.review-outcome p{{font-size:.8rem;color:var(--text2);margin-top:.35rem}}
.review-metrics{{display:flex;align-items:stretch;border:1px solid var(--border);border-radius:10px;background:var(--bg2);overflow:hidden;flex:0 0 auto}}
.review-metric{{min-width:82px;padding:.62rem .8rem;text-align:center;border-left:1px solid var(--border)}}
.review-metric:first-child{{border-left:0}}
.review-metric strong{{display:block;font-size:1.05rem;font-family:var(--mono);line-height:1.2}}
.review-metric span{{display:block;margin-top:.2rem;font-size:.62rem;text-transform:uppercase;letter-spacing:.07em;color:var(--text3)}}
.review-body{{display:flex;flex-direction:column;gap:.85rem;padding:1rem;background:var(--bg3);border:1px solid var(--border);border-top:0;border-radius:0 0 12px 12px}}
.decision-rationale{{display:grid;grid-template-columns:minmax(180px,.32fr) 1fr;gap:1rem;align-items:start;padding:.9rem 1rem;background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:10px}}
.rationale-pass{{border-left-color:var(--green)}}.rationale-fail{{border-left-color:var(--red)}}.rationale-ambiguous{{border-left-color:var(--amber)}}
.rationale-heading span{{display:block;font-size:.86rem;font-weight:700}}
.rationale-heading small{{display:block;color:var(--text3);font-size:.68rem;margin-top:.2rem}}
.decision-rationale ul{{margin:0;padding-left:1.1rem;color:var(--text2);font-size:.78rem;line-height:1.55}}
.review-section{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:1rem}}
.review-section-head{{display:flex;align-items:center;gap:.7rem;padding-bottom:.8rem;margin-bottom:.8rem;border-bottom:1px solid var(--border)}}
.section-icon{{width:30px;height:30px;display:grid;place-items:center;border-radius:8px;background:var(--accent-g);color:var(--accent2);font-size:.65rem;font-weight:800;letter-spacing:.04em;flex:0 0 auto}}
.section-icon-ai{{background:var(--amber-g);color:var(--amber)}}
.section-icon-ai .copilot-icon{{width:17px;height:17px;fill:currentColor}}
.review-section-head h4{{font-size:.9rem;font-weight:700;line-height:1.2}}
.review-section-head p{{font-size:.7rem;color:var(--text3);margin-top:.2rem}}
.keyword-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem}}
.review-split{{display:grid;grid-template-columns:1.15fr .85fr;gap:.85rem;align-items:stretch}}

/* KW items */
.kw-item{{padding:.75rem;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg3);min-width:0}}
.kw-found{{border-top:2px solid var(--green)}}.kw-missing{{border-top:2px solid var(--red)}}.kw-review{{border-top:2px solid var(--amber)}}
.kw-header{{display:flex;justify-content:space-between;align-items:center}}
.kw-name{{font-weight:600;font-size:.88rem}}
.kw-badge{{font-size:.68rem;font-weight:600;text-transform:uppercase;padding:.1rem .4rem;border-radius:6px}}
.kw-badge.found{{background:var(--green-g);color:var(--green)}}.kw-badge.missing{{background:var(--red-g);color:var(--red)}}.kw-badge.review{{background:var(--amber-g);color:var(--amber)}}
.kw-relation{{font-size:.72rem;color:var(--text2);margin-top:.25rem}}
.kw-snippet{{font-family:var(--mono);font-size:.7rem;background:var(--bg);padding:.55rem;border-radius:6px;margin-top:.55rem;white-space:pre-wrap;word-break:break-word;max-height:96px;overflow-y:auto;line-height:1.5;color:var(--text2)}}
.kw-hl{{background:#22c55e33;color:#16a34a;font-weight:600;padding:1px 3px;border-radius:3px}}

/* Timeline */
.timeline{{--exp-axis:4px;--exp-gap:.8rem;display:flex;flex-direction:column;position:relative;margin-left:.35rem}}
.exp-item{{position:relative;padding:.25rem 0 .25rem 1rem}}
.exp-item-connected{{margin-bottom:var(--exp-gap)}}
.exp-dot{{position:absolute;z-index:2;left:var(--exp-axis);top:.48rem;width:9px;height:9px;border-radius:50%;background:var(--accent);border:2px solid var(--bg2);box-shadow:0 0 0 1px var(--accent);transform:translateX(-50%)}}
.exp-content{{position:relative;z-index:1}}
.exp-title{{font-weight:600;font-size:.9rem}}
.exp-meta{{font-size:.78rem;color:var(--text2);margin-top:.1rem}}
.exp-connector{{position:absolute;z-index:0;top:calc(.48rem + 4.5px);left:0;width:100%;height:calc(100% + var(--exp-gap));overflow:hidden;pointer-events:none}}
.exp-connector::before{{position:absolute;top:0;bottom:0;left:var(--exp-axis);width:1px;background:var(--border2);content:"";transform:translateX(-50%)}}
.exp-particle{{--exp-particle-half:2px;position:absolute;z-index:1;top:-4px;left:var(--exp-axis);width:4px;height:4px;border-radius:50%;background:var(--accent);filter:drop-shadow(0 0 4px var(--accent));opacity:0;will-change:top,opacity;animation:exp-flow-down 4.2s linear infinite}}
.exp-particle:nth-child(2){{animation-delay:-1.4s}}
.exp-particle:nth-child(3){{animation-delay:-2.8s}}
@keyframes exp-flow-down{{
    0%{{top:-4px;transform:translateX(-50%);opacity:0}}
    10%{{opacity:1}}
    96%{{opacity:1}}
    100%{{top:calc(100% + var(--exp-particle-half));transform:translateX(-50%);opacity:0}}
}}

/* Flags */
.flag-item{{display:flex;align-items:flex-start;gap:.5rem;padding:.58rem .65rem;border-radius:var(--radius-sm);margin-bottom:.4rem;font-size:.8rem;line-height:1.4}}
.flag-info{{background:var(--bg4)}}.flag-danger{{background:var(--red-g)}}.flag-success{{background:var(--green-g)}}
.flag-icon{{font-size:.9rem}}
.verdict-item{{margin-bottom:.18rem}}

.empty-state{{color:var(--text3);font-size:.8rem;font-style:italic;padding:.5rem 0}}
.file-link{{text-decoration:none;border-bottom:1px dashed var(--text3);transition:all .15s}}
.file-link:hover{{color:var(--accent);border-color:var(--accent)}}

/* Responsive */
@media(max-width:1100px){{
    .header-middle{{grid-template-columns:minmax(185px,.5fr) 1.5fr}}
    .donut-wrap{{grid-column:1/-1;min-height:150px;padding:1rem 0 0;border-top:1px solid var(--border);border-left:0}}
    .insights-sticky{{grid-template-columns:minmax(300px,.68fr) minmax(520px,1.32fr);padding-right:1.25rem;padding-left:1.25rem}}
    .demo-outcomes{{right:.65rem;width:155px}}.demo-outcome{{grid-template-columns:31px 1fr;padding:9px}}.demo-outcome-icon{{width:30px;height:30px}}
}}
@media(max-width:900px){{
    .insights-stage{{height:auto}}
    .insights-sticky{{position:relative;grid-template-columns:1fr;height:auto;min-height:0;padding:1.25rem;overflow:visible}}
    .charts-column{{order:1}}.podium-column{{order:2;height:650px;min-height:0}}
    .demo-cv-float{{left:44%;width:min(39vw,270px)}}.demo-podium,.demo-cv-shadow{{left:44%}}
}}
@media(max-width:768px){{
    .header{{padding:1rem;gap:1rem}}
    .logo-icon{{width:60px;height:60px}}.logo-text{{font-size:1.55rem}}
    .header-middle{{grid-template-columns:1fr;padding-top:.6rem}}
    .screening-intake{{min-height:145px;padding-left:.2rem;border-right:0;border-bottom:1px solid var(--border)}}
    .outcome-grid{{min-height:175px;padding:0 .2rem;gap:.25rem}}
    .outcome-card{{min-height:165px;padding-left:1rem}}
    .outcome-card .stat-lbl{{font-size:.6rem}}
    .donut-wrap{{grid-column:auto}}
    .restrictions{{gap:.8rem 1.2rem}}.criteria-section{{min-width:0}}
    .main{{padding:1rem}}
    .candidate-review{{padding:.65rem}}
    .review-hero{{align-items:flex-start;flex-direction:column}}
    .review-metrics{{width:100%}}.review-metric{{flex:1;min-width:0}}
    .decision-rationale{{grid-template-columns:1fr}}
    .keyword-grid,.review-split{{grid-template-columns:1fr}}
    .podium-column{{height:590px}}
    .demo-heading{{top:.4rem;right:1rem;left:1rem}}.demo-heading p{{display:none}}.demo-progress{{width:100px}}
    .demo-cv-float{{left:42%;top:44%;width:min(52vw,235px)}}.demo-podium,.demo-cv-shadow{{left:42%}}.demo-podium{{width:min(72vw,390px)}}
    .demo-outcomes{{top:29%;right:.45rem;width:128px;gap:7px}}.demo-outcome{{grid-template-columns:27px 1fr;gap:6px;padding:7px;border-radius:10px}}.demo-outcome-icon{{width:26px;height:26px;font-size:.75rem}}.demo-outcome strong{{font-size:.65rem}}
}}
@media(prefers-reduced-motion:reduce){{.exp-particle{{display:none}}.logo-icon,.logo-text,.outcome-bar,.donut-segment,.outcome-distribution i,.demo-cv,.demo-verdict-orb::after{{animation-duration:.001ms!important;animation-delay:0ms!important}}}}
/* Ambiguity-only AI verdict */
.semantic-review-container{{padding:0}}
.ai-scope{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.75rem}}
.ai-scope span{{padding:.25rem .55rem;border:1px solid var(--border);border-radius:999px;background:var(--bg3);color:var(--text2);font-size:.68rem;font-weight:600}}
.semantic-review-btn{{background:linear-gradient(135deg,#d97706,var(--amber));color:#111827;border:none;padding:.7rem 1.2rem;border-radius:var(--radius-sm);cursor:pointer;font-size:.88rem;font-weight:700;transition:all .2s}}
.semantic-review-btn:hover{{transform:translateY(-1px);box-shadow:0 4px 16px rgba(245,158,11,.25)}}
.semantic-review-btn:disabled{{opacity:.5;cursor:not-allowed;transform:none}}
.semantic-review-output{{margin-top:1rem;display:flex;flex-direction:column;gap:.7rem}}
.ai-verdict{{display:flex;align-items:center;gap:.55rem;padding:.8rem;border-radius:var(--radius-sm);font-weight:750;font-size:1rem}}
.ai-verdict.pass{{background:var(--green-g);color:var(--green);border-left:3px solid var(--green)}}
.ai-verdict.fail{{background:var(--red-g);color:var(--red);border-left:3px solid var(--red)}}
.semantic-summary{{padding:.7rem .8rem;background:var(--amber-g);border-left:3px solid var(--amber);border-radius:var(--radius-sm);font-size:.86rem;line-height:1.55}}
.semantic-finding{{padding:.8rem;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-sm)}}
.semantic-finding-head{{display:flex;justify-content:space-between;gap:.6rem;align-items:flex-start}}
.semantic-finding-title{{font-weight:650;font-size:.88rem}}
.semantic-classification{{font-size:.68rem;font-weight:700;padding:.15rem .45rem;border-radius:8px;background:var(--accent-g);color:var(--accent2);white-space:nowrap}}
.semantic-explanation{{font-size:.82rem;color:var(--text2);line-height:1.5;margin:.55rem 0}}
.semantic-quote{{font-family:var(--mono);font-size:.76rem;line-height:1.5;padding:.55rem;background:var(--bg);border-radius:6px;white-space:pre-wrap}}
.semantic-meta{{font-size:.7rem;color:var(--text3);margin-top:.45rem}}
.semantic-actions{{display:flex;align-items:center;gap:.45rem;margin-top:.65rem}}
.semantic-decision{{border:1px solid var(--border2);background:var(--bg4);color:var(--text);border-radius:6px;padding:.5rem .75rem;cursor:pointer;font-size:.78rem;font-weight:650}}
.semantic-decision.pass:hover{{border-color:var(--green);color:var(--green)}}.semantic-decision.fail:hover{{border-color:var(--red);color:var(--red)}}
.semantic-decision:disabled{{opacity:.5;cursor:not-allowed}}
.semantic-decision-status{{font-size:.72rem;font-weight:650;color:var(--text2)}}
.ai-loading{{display:flex;align-items:center;gap:.6rem;color:var(--text2);padding:.5rem 0}}
.ai-loading .spinner{{width:18px;height:18px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.ai-error{{display:flex;flex-direction:column;gap:.22rem;padding:.7rem .8rem;background:var(--red-g);border:1px solid rgba(244,63,94,.22);border-radius:8px}}
.ai-error-title{{color:var(--red);font-size:.8rem}}
.ai-error-detail{{color:var(--text2);font-size:.74rem;line-height:1.45}}
</style>
</head>
<body>
<header class="header">
    <div class="header-top">
        <div class="header-brand">
            <div class="logo-icon"><img src="icon.png" alt="Kriterion"></div>
            <div class="logo-text">Kriterion</div>
        </div>
        <div class="theme-btn" onclick="toggleTheme()" id="themeBtn">\U0001f319 Dark</div>
    </div>

    <div class="header-middle">
        <button type="button" class="stat-box stat-all stat-active screening-intake" data-f="all" aria-pressed="true" aria-label="Show all {total} candidates">
            <span class="summary-kicker">Screened intake</span>
            <span class="stat-val">{total}</span>
            <span class="stat-lbl">candidate CVs processed</span>
        </button>
        <div class="outcome-grid">
            <button type="button" class="stat-box stat-pass outcome-card" data-f="pass" aria-pressed="false" aria-label="Show {passed} passed candidates">
                <i class="outcome-bar" aria-hidden="true"></i><span class="stat-lbl">Passed</span><span class="stat-val">{passed}</span><span class="stat-pct">{pass_pct:.1f}%</span>
            </button>
            <button type="button" class="stat-box stat-fail outcome-card" data-f="fail" aria-pressed="false" aria-label="Show {failed} failed candidates">
                <i class="outcome-bar" aria-hidden="true"></i><span class="stat-lbl">Failed</span><span class="stat-val">{failed}</span><span class="stat-pct">{fail_pct:.1f}%</span>
            </button>
            <button type="button" class="stat-box stat-amb outcome-card" data-f="ambiguous" aria-pressed="false" aria-label="Show {ambiguous} ambiguous candidates">
                <i class="outcome-bar" aria-hidden="true"></i><span class="stat-lbl">Ambiguous</span><span class="stat-val">{ambiguous}</span><span class="stat-pct">{ambiguous_pct:.1f}%</span>
            </button>
        </div>
        <div class="donut-wrap">
            <div class="donut">
                <svg viewBox="0 0 36 36" aria-hidden="true">
                    <circle class="donut-track" cx="18" cy="18" r="14" pathLength="100"/>
                    <circle class="donut-segment" cx="18" cy="18" r="14" pathLength="100" stroke="var(--green)" style="--dash:{pass_pct:.2f} {100 - pass_pct:.2f};--offset:0"/>
                    <circle class="donut-segment" cx="18" cy="18" r="14" pathLength="100" stroke="var(--red)" style="--dash:{fail_pct:.2f} {100 - fail_pct:.2f};--offset:-{pass_pct:.2f}"/>
                    <circle class="donut-segment" cx="18" cy="18" r="14" pathLength="100" stroke="var(--amber)" style="--dash:{ambiguous_pct:.2f} {100 - ambiguous_pct:.2f};--offset:-{pass_pct + fail_pct:.2f}"/>
                </svg>
                <div class="donut-center"><strong>{pass_rate}%</strong><span>Pass rate</span></div>
            </div>
            <div class="donut-legend">
                <div class="legend-item" style="--dot:var(--green)"><span class="legend-dot"></span><span>Pass</span><b>{passed}</b></div>
                <div class="legend-item" style="--dot:var(--red)"><span class="legend-dot"></span><span>Fail</span><b>{failed}</b></div>
                <div class="legend-item" style="--dot:var(--amber)"><span class="legend-dot"></span><span>Ambiguous</span><b>{ambiguous}</b></div>
            </div>
        </div>
        <div class="outcome-distribution" aria-hidden="true"><i class="dist-pass" style="flex:{passed}"></i><i class="dist-fail" style="flex:{failed}"></i><i class="dist-amb" style="flex:{ambiguous}"></i></div>
    </div>

    <div class="header-bottom">
        <div class="restrictions">{restriction_groups_html}</div>
    </div>
</header>

<section class="insights-stage" id="screeningStage" aria-label="Screening insights and scroll demonstration">
    <div class="insights-sticky">
        <div class="charts-column">
            <div class="chart-card chart-reasons">
                <h3>Top Failure Reasons</h3>
                {reasons_bars_html}
            </div>
            <div class="chart-card chart-coverage">
                <h3>Keyword Coverage</h3>
                {kw_bars_html}
            </div>
        </div>
        <div class="podium-column" id="screenDemo">
            <div class="demo-heading">
                <div><span class="demo-eyebrow">AI-assisted review</span><h2>AI helps Kriterion resolve ambiguous evidence</h2></div>
                <div class="demo-progress" aria-label="Screening animation progress"><div class="demo-progress-copy"><span>Scan</span><span id="demoProgressPercent">0%</span></div><div class="demo-progress-track"><span class="demo-progress-bar" id="demoProgressBar"></span></div></div>
            </div>
            <div class="demo-scene">
                <div class="demo-cv-shadow"></div>
                <div class="demo-cv-float">
                    <article class="demo-cv" aria-label="Abstract candidate CV being screened">
                        <header class="demo-cv-header"><div class="demo-cv-mark">CV</div><div><strong>Candidate evidence</strong><span>{profile_role}</span></div></header>
                        <section class="demo-cv-section"><h4>Experience</h4><div class="demo-role-row"><div><div class="demo-line demo-line-long"></div><div class="demo-line demo-line-mid"></div></div></div><div class="demo-role-row"><div><div class="demo-line demo-line-mid"></div><div class="demo-line demo-line-short"></div></div></div></section>
                        <section class="demo-cv-section"><h4>Required keyword coverage</h4>{podium_skills_html}</section>
                        <section class="demo-cv-section"><h4>Career history</h4><div class="demo-line demo-line-long"></div><div class="demo-line demo-line-mid"></div><div class="demo-line demo-line-short"></div></section>
                        <div class="demo-scan-beam" aria-hidden="true"><div class="demo-scan-line"></div><div class="demo-scan-wash"></div></div>
                    </article>
                    <div class="demo-verdict-orb" aria-hidden="true"></div>
                </div>
                <div class="demo-podium" aria-hidden="true"><div class="demo-podium-top"><div class="demo-podium-core"></div></div><div class="demo-podium-rim"></div><div class="demo-podium-base"></div><div class="demo-podium-reflection"></div></div>
                <div class="demo-outcomes" aria-label="Real report outcomes">
                    <article class="demo-outcome demo-outcome-pass"><div class="demo-outcome-icon">✓</div><div><span>Passed</span><strong>{passed}</strong></div></article>
                    <article class="demo-outcome demo-outcome-fail"><div class="demo-outcome-icon">×</div><div><span>Failed</span><strong>{failed}</strong></div></article>
                    <article class="demo-outcome demo-outcome-amb"><div class="demo-outcome-icon">?</div><div><span>Ambiguous</span><strong>{ambiguous}</strong></div></article>
                </div>
            </div>
            <p class="demo-caption">Profile-driven animation · aggregate values are from this report</p>
        </div>
    </div>
</section>

<main class="main">
    <div class="table-wrap">
        <table>
            <thead><tr><th>Candidate</th><th>Result</th><th>Score</th><th>Exp</th><th>Keywords</th></tr></thead>
            <tbody id="tableBody">{table_rows}</tbody>
        </table>
    </div>
</main>

<script>
// Theme
function toggleTheme(){{
    const h=document.documentElement,t=h.dataset.theme==='dark'?'light':'dark';
    h.dataset.theme=t;localStorage.setItem('rt-theme',t);
    document.getElementById('themeBtn').textContent=t==='dark'?'\U0001f319 Dark':'☀️ Light';
}}
(()=>{{const s=localStorage.getItem('rt-theme');if(s){{document.documentElement.dataset.theme=s;document.getElementById('themeBtn').textContent=s==='dark'?'\U0001f319 Dark':'☀️ Light';}}}})();

// Native scroll-driven podium screening demonstration
const screeningStage=document.getElementById('screeningStage');
const screeningDemo=document.getElementById('screenDemo');
const demoProgressBar=document.getElementById('demoProgressBar');
const demoProgressPercent=document.getElementById('demoProgressPercent');
const demoPassTarget=screeningDemo?screeningDemo.querySelector('.demo-outcome-pass .demo-outcome-icon'):null;
const demoFailTarget=screeningDemo?screeningDemo.querySelector('.demo-outcome-fail .demo-outcome-icon'):null;
const demoAmbTarget=screeningDemo?screeningDemo.querySelector('.demo-outcome-amb .demo-outcome-icon'):null;
let screeningTicking=false;
const screeningClamp=(value,min=0,max=1)=>Math.min(max,Math.max(min,value));
const screeningRange=(value,start,end)=>screeningClamp((value-start)/(end-start));
const screeningEase=value=>value*value*(3-2*value);
const screeningMix=(from,to,amount)=>from+(to-from)*amount;
function screeningTargetOffset(target){{
    if(!target||!screeningDemo)return{{x:0,y:0}};
    const demoRect=screeningDemo.getBoundingClientRect();
    const targetRect=target.getBoundingClientRect();
    return{{
        x:targetRect.left+targetRect.width/2-(demoRect.left+screeningDemo.clientWidth*.42),
        y:targetRect.top+targetRect.height/2-(demoRect.top+screeningDemo.clientHeight*.43)
    }};
}}
function renderScreeningDemo(){{
    screeningTicking=false;
    if(!screeningStage||!screeningDemo)return;
    const compact=window.matchMedia('(max-width:900px)').matches;
    const reduced=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
    const scrollable=screeningStage.offsetHeight-window.innerHeight;
    let progress=1;
    if(!compact&&!reduced&&scrollable>0){{
        progress=screeningClamp(-screeningStage.getBoundingClientRect().top/scrollable);
    }}
    const enter=screeningEase(screeningRange(progress,.03,.19));
    const reasons=screeningEase(screeningRange(progress,.10,.30));
    const scan=screeningEase(screeningRange(progress,.22,.68));
    const coverage=screeningEase(screeningRange(progress,.36,.58));
    const morph=screeningEase(screeningRange(progress,.62,.70));
    const decision=screeningEase(screeningRange(progress,.64,.72));
    const tiltY=(-10+scan*2)*(1-morph);
    const tiltX=(4-scan*1.5)*(1-morph);
    const depth=70*(1-morph);
    const passTarget=screeningTargetOffset(demoPassTarget);
    const failTarget=screeningTargetOffset(demoFailTarget);
    const ambTarget=screeningTargetOffset(demoAmbTarget);
    let flightX=0,flightY=0,orbColor='var(--accent)';
    if(progress>=.70&&progress<.82){{
        const travel=screeningEase(screeningRange(progress,.70,.77));
        flightX=screeningMix(0,passTarget.x,travel);
        flightY=screeningMix(0,passTarget.y,travel);
        orbColor='var(--green)';
    }}else if(progress>=.82&&progress<.90){{
        const travel=screeningEase(screeningRange(progress,.82,.87));
        flightX=screeningMix(passTarget.x,failTarget.x,travel);
        flightY=screeningMix(passTarget.y,failTarget.y,travel);
        orbColor='var(--red)';
    }}else if(progress>=.90){{
        const travel=screeningEase(screeningRange(progress,.90,.95));
        flightX=screeningMix(failTarget.x,ambTarget.x,travel);
        flightY=screeningMix(failTarget.y,ambTarget.y,travel);
        orbColor='var(--amber)';
    }}
    const passGlow=screeningEase(screeningRange(progress,.755,.785))*(1-screeningEase(screeningRange(progress,.81,.835)));
    const failGlow=screeningEase(screeningRange(progress,.855,.88))*(1-screeningEase(screeningRange(progress,.89,.915)));
    const ambGlow=screeningEase(screeningRange(progress,.94,.97));
    screeningStage.style.setProperty('--demo-enter',enter.toFixed(4));
    screeningStage.style.setProperty('--demo-reasons',reasons.toFixed(4));
    screeningStage.style.setProperty('--demo-scan',scan.toFixed(4));
    screeningStage.style.setProperty('--demo-coverage',coverage.toFixed(4));
    screeningStage.style.setProperty('--demo-decision',decision.toFixed(4));
    screeningStage.style.setProperty('--demo-morph',morph.toFixed(4));
    screeningStage.style.setProperty('--demo-tilt-y',tiltY.toFixed(3)+'deg');
    screeningStage.style.setProperty('--demo-tilt-x',tiltX.toFixed(3)+'deg');
    screeningStage.style.setProperty('--demo-depth',depth.toFixed(2)+'px');
    screeningStage.style.setProperty('--demo-flight-x',flightX.toFixed(2)+'px');
    screeningStage.style.setProperty('--demo-flight-y',flightY.toFixed(2)+'px');
    screeningStage.style.setProperty('--demo-pass-glow',passGlow.toFixed(4));
    screeningStage.style.setProperty('--demo-fail-glow',failGlow.toFixed(4));
    screeningStage.style.setProperty('--demo-amb-glow',ambGlow.toFixed(4));
    screeningStage.style.setProperty('--demo-orb-color',orbColor);
    if(demoProgressBar)demoProgressBar.style.transform=`scaleX(${{progress}})`;
    if(demoProgressPercent)demoProgressPercent.textContent=`${{Math.round(progress*100)}}%`;
}}
function requestScreeningRender(){{
    if(!screeningTicking){{screeningTicking=true;requestAnimationFrame(renderScreeningDemo);}}
}}
window.addEventListener('scroll',requestScreeningRender,{{passive:true}});
window.addEventListener('resize',requestScreeningRender);
renderScreeningDemo();

// Stat box click -> filter
document.querySelectorAll('.stat-box[data-f]').forEach(box=>{{
    box.addEventListener('click',()=>{{
        const f=box.dataset.f;
        document.querySelectorAll('.stat-box[data-f]').forEach(s=>{{s.classList.remove('stat-active');s.setAttribute('aria-pressed','false');}});
        box.classList.add('stat-active');
        box.setAttribute('aria-pressed','true');
        document.querySelectorAll('#tableBody tr').forEach(r=>{{
            if(r.classList.contains('data-row')){{
                const show=(f==='all'||r.dataset.status===f);
                r.style.display=show?'':'none';
                r.classList.remove('selected');
            }}
        }});
        document.querySelectorAll('.detail-row').forEach(r=>r.style.display='none');
    }});
}});

// Row click -> inline candidate review
function toggleCandidateReview(row){{
    var detail=row.nextElementSibling;
    var wasOpen=detail.style.display==='table-row';
    document.querySelectorAll('.detail-row').forEach(item=>item.style.display='none');
    document.querySelectorAll('.data-row').forEach(item=>{{
        item.classList.remove('selected');
        item.setAttribute('aria-expanded','false');
    }});
    if(!wasOpen){{
        detail.style.display='table-row';
        row.classList.add('selected');
        row.setAttribute('aria-expanded','true');
    }}
}}

document.querySelectorAll('.data-row').forEach(row=>{{
    row.addEventListener('click',()=>{{
        toggleCandidateReview(row);
    }});
    row.addEventListener('keydown',event=>{{
        if(event.key==='Enter'||event.key===' '){{
            event.preventDefault();
            toggleCandidateReview(row);
        }}
    }});
}});
document.querySelectorAll('.data-row a').forEach(link=>{{
    link.addEventListener('click',event=>event.stopPropagation());
}});

// Ambiguity-only AI verdict
var autoAiReview={"true" if auto_ai_review else "false"};
var hashToken=(location.hash.match(/token=([^&]+)/)||[])[1]||'';
var aiToken=hashToken?decodeURIComponent(hashToken):'';
try{{
    if(hashToken){{
        sessionStorage.setItem('kriterion-token',aiToken);
        history.replaceState(null,'',location.pathname+location.search);
    }}else{{
        aiToken=sessionStorage.getItem('kriterion-token')||'';
    }}
}}catch(e){{}}
function aiHeaders(){{return{{'Content-Type':'application/json','X-Kriterion-Token':aiToken}};}}

function showAiError(node,message){{
    node.innerHTML='';
    var error=document.createElement('div');
    error.className='ai-error';
    error.appendChild(semanticElement('strong','ai-error-title','Recommendation unavailable'));
    error.appendChild(semanticElement('span','ai-error-detail',message||'Copilot could not produce a usable response.'));
    node.appendChild(error);
}}

function semanticElement(tag,className,text){{
    var node=document.createElement(tag);
    node.className=className;
    node.textContent=String(text||'');
    return node;
}}

function updateHumanDecision(container,decision){{
    var status=container.querySelector('.semantic-decision-status');
    var dataRow=document.querySelector('.data-row[data-idx="'+container.dataset.idx+'"]');
    var pill=dataRow?dataRow.querySelector('.pill'):null;
    if(!status)return;
    if(decision==='PASS'||decision==='FAIL'){{
        status.textContent='Final human decision: '+decision;
        status.style.color=decision==='PASS'?'var(--green)':'var(--red)';
        if(pill){{
            pill.textContent='FINAL '+decision;
            pill.className='pill pill-'+decision.toLowerCase();
        }}
    }}else{{
        status.textContent='Human final decision required';
        status.style.color='var(--text2)';
    }}
}}

function renderAmbiguityVerdict(container,review){{
    var output=container.querySelector('.semantic-review-output');
    output.innerHTML='';
    output.appendChild(semanticElement(
        'div',
        'ai-verdict '+String(review.ai_verdict||'').toLowerCase(),
        'AI recommendation: '+review.ai_verdict
    ));
    output.appendChild(semanticElement('div','semantic-summary',review.summary));
    (review.evidence||[]).forEach(function(finding){{
        var card=semanticElement('div','semantic-finding','');
        var head=semanticElement('div','semantic-finding-head','');
        head.appendChild(semanticElement('div','semantic-finding-title',finding.criterion));
        head.appendChild(semanticElement('span','semantic-classification',finding.stance.replaceAll('_',' ')));
        card.appendChild(head);
        card.appendChild(semanticElement('div','semantic-explanation',finding.explanation));
        card.appendChild(semanticElement('blockquote','semantic-quote',finding.source_quote));
        card.appendChild(semanticElement('div','semantic-meta','AI confidence: '+finding.confidence+'% · quotation verified against parsed work experience'));
        output.appendChild(card);
    }});
    var actions=semanticElement('div','semantic-actions','');
    var pass=semanticElement('button','semantic-decision pass','Final decision: Pass candidate');
    pass.type='button';
    pass.onclick=function(){{recordFinalDecision(pass,'PASS');}};
    var fail=semanticElement('button','semantic-decision fail','Final decision: Fail candidate');
    fail.type='button';
    fail.onclick=function(){{recordFinalDecision(fail,'FAIL');}};
    actions.appendChild(pass);
    actions.appendChild(fail);
    actions.appendChild(semanticElement('span','semantic-decision-status',''));
    output.appendChild(actions);
    updateHumanDecision(container,review.human_decision);
}}

function requestAmbiguityVerdict(btn){{
    var container=btn.closest('.semantic-review-container');
    var file=container.dataset.file;
    var output=container.querySelector('.semantic-review-output');
    if(!aiToken){{
        showAiError(output,'AI Verdict requires the locally served dashboard. Run Kriterion again to open it.');
        return Promise.resolve();
    }}
    btn.disabled=true;
    btn.textContent='Checking evidence...';
    output.innerHTML='<div class="ai-loading"><div class="spinner"></div><span>Checking the unresolved evidence...</span></div>';
    return fetch('/api/ai-verdict',{{method:'POST',headers:aiHeaders(),body:JSON.stringify({{filename:file}})}})
    .then(function(r){{return r.json().then(function(d){{if(!r.ok)throw new Error(d.error||'Failed');return d;}});}})
    .then(function(data){{
        renderAmbiguityVerdict(container,data.review);
        btn.style.display='none';
    }})
    .catch(function(e){{
        showAiError(output,e.message);
        btn.disabled=false;
        btn.textContent='Try again';
    }});
}}

function recordFinalDecision(btn,decision){{
    var container=btn.closest('.semantic-review-container');
    var file=container.dataset.file;
    var buttons=container.querySelectorAll('.semantic-decision');
    var status=container.querySelector('.semantic-decision-status');
    buttons.forEach(function(item){{item.disabled=true;}});
    status.textContent='Saving decision...';
    fetch('/api/final-decision',{{method:'POST',headers:aiHeaders(),body:JSON.stringify({{
        filename:file,decision:decision
    }})}})
    .then(function(r){{return r.json().then(function(d){{if(!r.ok)throw new Error(d.error||'Failed');return d;}});}})
    .then(function(data){{
        updateHumanDecision(container,data.human_decision);
        buttons.forEach(function(item){{item.disabled=false;}});
    }})
    .catch(function(e){{
        status.textContent=e.message;
        buttons.forEach(function(item){{item.disabled=false;}});
    }});
}}

function autoReviewAmbiguous(){{
    if(!autoAiReview||!aiToken)return;
    var buttons=Array.from(document.querySelectorAll('.semantic-review-btn'));
    var sequence=Promise.resolve();
    buttons.forEach(function(btn){{
        sequence=sequence.then(function(){{return requestAmbiguityVerdict(btn);}});
    }});
}}

function sendHeartbeat(){{
    if(aiToken)fetch('/heartbeat',{{headers:aiHeaders()}}).catch(function(){{}});
}}
sendHeartbeat();
window.setInterval(sendHeartbeat,10000);
window.setTimeout(autoReviewAmbiguous,200);
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")


def write_excel(results: List[Dict[str, object]], output_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Screening Results"

    headers = build_dynamic_headers()
    ws.append(headers)

    for r in results:
        ws.append(row_for_result(r, headers))

    header_font = Font(bold=True)
    top = Alignment(vertical="top")
    wrap_top = Alignment(wrap_text=True, vertical="top")

    ws.row_dimensions[1].height = 22
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = top

    ws.freeze_panes = "A2"

    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last_col}{ws.max_row}"

    header_to_col = {headers[i]: i + 1 for i in range(len(headers))}

    snippet_cols = [h for h in headers if h.endswith("_snippet")]
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.alignment = top
        for h in snippet_cols:
            col_idx = header_to_col[h]
            row[col_idx - 1].alignment = wrap_top

    result_col = header_to_col["result"]
    fill_pass = PatternFill(fill_type="solid", fgColor="00A000")
    fill_fail = PatternFill(fill_type="solid", fgColor="C00000")
    fill_amb = PatternFill(fill_type="solid", fgColor="F39C12")
    font_white = Font(color="FFFFFF", bold=True)

    for rr in range(2, ws.max_row + 1):
        cell = ws.cell(row=rr, column=result_col)
        val = (cell.value or "").strip().upper()
        if val == "PASS":
            cell.fill = fill_pass
            cell.font = font_white
        elif val == "FAIL":
            cell.fill = fill_fail
            cell.font = font_white
        elif val == "AMBIGUOUS":
            cell.fill = fill_amb
            cell.font = font_white
        cell.alignment = Alignment(horizontal="center", vertical="top")

    caps = {h: 45 for h in headers}
    caps["file"] = 55
    caps["result"] = 14
    caps["devops_years"] = 14
    for h in snippet_cols:
        caps[h] = 80

    for col_idx, h in enumerate(headers, start=1):
        longest = len(h)
        for rr in range(2, ws.max_row + 1):
            v = ws.cell(row=rr, column=col_idx).value
            if v is None:
                continue
            longest = max(longest, len(str(v)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(
            caps.get(h, 45), max(10, longest + 2)
        )

    snippet_col_indices = [header_to_col[h] for h in snippet_cols]
    for rr in range(2, ws.max_row + 1):
        long_snip = False
        for col in snippet_col_indices:
            val = ws.cell(row=rr, column=col).value or ""
            if len(str(val)) > 80:
                long_snip = True
                break
        ws.row_dimensions[rr].height = 70 if long_snip else 20

    wb.save(output_path)
