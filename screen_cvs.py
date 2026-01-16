import argparse
import csv
import datetime as dt
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import fitz  # PyMuPDF

# Excel formatting
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# -----------------------------
# Config
# -----------------------------

EXPERIENCE_HEADINGS = {
    "experience",
    "work experience",
    "professional experience",
    "employment history",
    "career history",
}

STOP_HEADINGS = {
    "skills",
    "technical skills",
    "education",
    "projects",
    "certifications",
    "certification",
    "training",
    "summary",
    "profile",
    "publications",
    "courses",
    "languages",
    "volunteering",
    "interests",
}

# Use regex with word boundaries to avoid false positives like "certification" containing "iti"
EXCLUDE_PATTERNS = [
    re.compile(r"\biti\b", re.IGNORECASE),
    re.compile(r"\bnti\b", re.IGNORECASE),
    re.compile(r"\bsprints\b", re.IGNORECASE),
    re.compile(r"\bdepi\b", re.IGNORECASE),
    re.compile(r"information\s+technology\s+institute", re.IGNORECASE),
    re.compile(r"national\s+technology\s+institute", re.IGNORECASE),
]

DEVOPS_KEYWORDS = {
    "devops",
    "sre",
    "site reliability",
    "platform engineer",
    "platform engineering",
    "infrastructure",
    "cloud engineer",
    "cloud engineering",
    "kubernetes",
    "terraform",
    "terragrunt",
    "ci/cd",
    "cicd",
    "jenkins",
    "github actions",
    "helm",
    "eks",
    "docker",
    "ansible",
    "prometheus",
    "grafana",
    "argo",
    "argo cd",
    "gitops",
    "linux",
    "iac",
    "infrastructure as code",
    "cloudformation",
}

EDUCATION_HINTS = {"bachelor", "master", "masters", "degree", "faculty", "university", "education"}

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

DATE_RANGE_PATTERN = re.compile(
    r"(?P<start>(?:[A-Za-z]{3,9}\s+\d{4})|(?:\d{1,2}[/-]\d{4})|(?:\d{4}))\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<end>(?:[A-Za-z]{3,9}\s+\d{4})|(?:\d{1,2}[/-]\d{4})|(?:\d{4})|"
    r"(?:present|current|now))",
    re.IGNORECASE,
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
# Text extraction
# -----------------------------

def extract_text_by_page(pdf_path: Path) -> Tuple[List[str], bool]:
    doc = fitz.open(pdf_path)
    pages = [page.get_text("text") for page in doc]
    used_ocr = False

    # Optional OCR fallback if text extraction looks empty/scanned
    text = "\n".join(pages).strip()
    if len(text) < 500:
        ocr = try_ocr(doc)
        if ocr:
            pages = ocr
            used_ocr = True

    return pages, used_ocr


def try_ocr(doc: fitz.Document) -> Optional[List[str]]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None

    ocr_pages: List[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        ocr_pages.append(pytesseract.image_to_string(img))
    return ocr_pages


def iter_lines_with_pages(pages: Sequence[str]) -> Iterable[Tuple[int, str]]:
    for i, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            yield i, line.rstrip()


def normalize_heading(line: str) -> str:
    return re.sub(r"[^a-z\s]", "", line.lower()).strip()


# -----------------------------
# Experience extraction (robust)
# -----------------------------

def capture_experience_by_heading(pages: Sequence[str], max_back_lines: int = 200) -> List[Tuple[int, str]]:
    """
    Heading-based capture, with a backward window to handle PDFs where extracted text order is odd
    (experience content appears before the "WORK EXPERIENCE" line).
    """
    lines = list(iter_lines_with_pages(pages))
    if not lines:
        return []

    exp_idxs: List[int] = []
    for idx, (_, line) in enumerate(lines):
        if normalize_heading(line) in EXPERIENCE_HEADINGS:
            exp_idxs.append(idx)

    if not exp_idxs:
        return []

    captured: List[Tuple[int, str]] = []

    for h_idx in exp_idxs:
        # Backward window
        start_back = max(0, h_idx - max_back_lines)
        for i in range(start_back, h_idx):
            _, l = lines[i]
            if normalize_heading(l) in STOP_HEADINGS:
                start_back = i + 1
        captured.extend(lines[start_back:h_idx])

        # Forward capture
        i = h_idx + 1
        while i < len(lines):
            _, l = lines[i]
            if normalize_heading(l) in STOP_HEADINGS:
                break
            captured.append(lines[i])
            i += 1

    # De-duplicate while preserving order
    seen: Set[Tuple[int, str]] = set()
    out: List[Tuple[int, str]] = []
    for item in captured:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def split_entries_from_lines(experience_lines: List[Tuple[int, str]]) -> List[Entry]:
    """
    Split into entries using blank lines as separators.
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

    return [e for e in entries if e.text()]


def is_date_range_line(line: str) -> bool:
    return DATE_RANGE_PATTERN.search(line) is not None


def build_date_based_entries(pages: Sequence[str]) -> List[Entry]:
    """
    More reliable approach: create entries that start at date ranges (e.g., "Feb 2024 - Present")
    and continue until the next date range or a hard stop heading.
    """
    lines = list(iter_lines_with_pages(pages))
    entries: List[Entry] = []
    current: List[Tuple[int, str]] = []
    capturing = False

    for page_num, line in lines:
        if is_date_range_line(line):
            if current:
                entries.append(Entry(lines=current))
            current = [(page_num, line)]
            capturing = True
            continue

        if not capturing:
            continue

        if normalize_heading(line) in STOP_HEADINGS:
            if current:
                entries.append(Entry(lines=current))
            current = []
            capturing = False
            continue

        current.append((page_num, line))

    if current:
        entries.append(Entry(lines=current))

    return [e for e in entries if e.text()]


def is_excluded(entry_text: str) -> bool:
    return any(p.search(entry_text) for p in EXCLUDE_PATTERNS)


def is_devops_related(entry_text: str) -> bool:
    lower = entry_text.lower()
    return any(k in lower for k in DEVOPS_KEYWORDS)


def is_experience_entry(entry: Entry) -> bool:
    """
    Conservative filter to avoid counting education/certificates as experience.
    """
    text = entry.text().lower()

    if not DATE_RANGE_PATTERN.search(entry.text()):
        return False

    if any(h in text for h in EDUCATION_HINTS):
        return False

    head = entry.head(4).lower()
    if any(h in head for h in JOB_TITLE_HINTS):
        return True
    if is_devops_related(text):
        return True

    return False


def extract_experience_entries(pages: Sequence[str]) -> List[Entry]:
    """
    Primary: date-based entries (most robust)
    Fallback: heading-based capture (handles some PDFs with non-standard layouts)
    """
    date_entries = build_date_based_entries(pages)
    date_entries = [e for e in date_entries if is_experience_entry(e)]
    if date_entries:
        return date_entries

    heading_lines = capture_experience_by_heading(pages)
    if not heading_lines:
        return []

    heading_entries = split_entries_from_lines(heading_lines)
    heading_entries = [e for e in heading_entries if is_experience_entry(e)]
    return heading_entries


# -----------------------------
# Evidence + date math
# -----------------------------

def find_keyword_in_entries(entries: List[Entry], keyword: str) -> Optional[Tuple[int, str]]:
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    for entry in entries:
        for idx, (page_num, line) in enumerate(entry.lines):
            if pattern.search(line):
                lines = [l for _, l in entry.lines]
                start = max(idx - 1, 0)
                end = min(idx + 2, len(lines))
                snippet = "\n".join(lines[start:end]).strip()
                return page_num, snippet
    return None


def parse_month_year(token: str, is_start: bool) -> Tuple[Optional[dt.date], bool]:
    token = token.strip().lower()
    today = dt.date.today()

    if token in {"present", "current", "now"}:
        return today, False

    # Year-only: conservative bound
    if re.fullmatch(r"\d{4}", token):
        year = int(token)
        month = 12 if is_start else 1
        return dt.date(year, month, 1), True

    if re.fullmatch(r"\d{1,2}[/-]\d{4}", token):
        month_str, year_str = re.split(r"[/-]", token)
        return dt.date(int(year_str), int(month_str), 1), False

    parts = token.split()
    if len(parts) == 2:
        m, y = parts
        if m in MONTHS and y.isdigit():
            return dt.date(int(y), MONTHS[m], 1), False

    return None, True


def parse_date_ranges(text: str) -> List[Tuple[dt.date, dt.date, bool]]:
    ranges: List[Tuple[dt.date, dt.date, bool]] = []
    for m in DATE_RANGE_PATTERN.finditer(text):
        s_raw, e_raw = m.group("start"), m.group("end")
        s, s_amb = parse_month_year(s_raw, is_start=True)
        e, e_amb = parse_month_year(e_raw, is_start=False)
        if s and e and e >= s:
            ranges.append((s, e, s_amb or e_amb))
    return ranges


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
        roles.append(Role(title=entry.head(2) or "Unknown title", start=start, end=end, months_added=added))
        ambiguity = ambiguity or amb

    return roles, len(total_months), ambiguity


def months_to_years(months: int) -> float:
    # Display years with 2 decimals (e.g., 2.08 years)
    return round(months / 12.0, 2)


# -----------------------------
# Screening + outputs
# -----------------------------

def classify_bucket(result: Dict[str, object]) -> str:
    """
    Folder classification:
    - ambiguous: ambiguity == True (regardless of pass/fail)
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
    return "AMBIGUOUS" if bool(result.get("ambiguity")) else ("PASS" if bool(result.get("passed")) else "FAIL")


def screen_pdf(pdf_path: Path) -> Dict[str, object]:
    pages, used_ocr = extract_text_by_page(pdf_path)
    exp_entries = extract_experience_entries(pages)

    excluded_entries: List[str] = []
    filtered_entries: List[Entry] = []
    for e in exp_entries:
        if is_excluded(e.text()):
            excluded_entries.append(e.head(3))
        else:
            filtered_entries.append(e)

    kube_evidence = find_keyword_in_entries(filtered_entries, "Kubernetes")
    aws_evidence = find_keyword_in_entries(filtered_entries, "AWS")

    roles, devops_months, ambiguity = compute_devops_roles(filtered_entries)
    devops_years = months_to_years(devops_months)

    # Strict interpretation:
    # - If dates are ambiguous, do NOT allow PASS (it goes to ambiguous bucket).
    devops_pass = (devops_years >= 3.0) and (not ambiguity)
    passed = (kube_evidence is not None) and (aws_evidence is not None) and devops_pass

    return {
        "file": pdf_path.name,
        "passed": passed,
        "kubernetes_found": kube_evidence is not None,
        "kubernetes_page": kube_evidence[0] if kube_evidence else None,
        "kubernetes_snippet": kube_evidence[1] if kube_evidence else "",
        "aws_found": aws_evidence is not None,
        "aws_page": aws_evidence[0] if aws_evidence else None,
        "aws_snippet": aws_evidence[1] if aws_evidence else "",
        "devops_years": devops_years,
        "devops_roles": roles,
        "excluded_entries": excluded_entries,
        "used_ocr": used_ocr,
        "ambiguity": ambiguity,
        "devops_pass": devops_pass,
        "experience_entries_found": len(filtered_entries),
    }


def write_csv(results: List[Dict[str, object]], output_path: Path) -> None:
    fields = [
        "file",
        "result",
        "kubernetes_found",
        "kubernetes_page",
        "aws_found",
        "aws_page",
        "devops_years",
        "devops_pass",
        "date_ambiguity",
        "used_ocr",
        "experience_entries_found",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(
                {
                    "file": r["file"],
                    "result": excel_result_label(r),  # PASS / FAIL / AMBIGUOUS
                    "kubernetes_found": r["kubernetes_found"],
                    "kubernetes_page": r["kubernetes_page"],
                    "aws_found": r["aws_found"],
                    "aws_page": r["aws_page"],
                    "devops_years": r["devops_years"],
                    "devops_pass": r["devops_pass"],
                    "date_ambiguity": r["ambiguity"],
                    "used_ocr": r["used_ocr"],
                    "experience_entries_found": r["experience_entries_found"],
                }
            )


def format_date(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def write_report(results: List[Dict[str, object]], output_path: Path) -> None:
    total = len(results)
    passed = sum(1 for r in results if bool(r["passed"]) and not bool(r.get("ambiguity")))
    ambiguous = sum(1 for r in results if bool(r.get("ambiguity")))
    failed = total - passed - ambiguous

    lines: List[str] = []
    lines.append("# CV Screening Report\n")
    lines.append("## Summary")
    lines.append(f"- Total CVs: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Ambiguous: {ambiguous}\n")

    for r in results:
        lines.append(f"## {r['file']}")
        lines.append(f"- Result: {excel_result_label(r)}")
        if r["used_ocr"]:
            lines.append("- Note: OCR fallback used for text extraction.")

        if r["kubernetes_found"]:
            lines.append(f"- Kubernetes in Experience: Yes (page {r['kubernetes_page']})")
            lines.append("  Snippet:\n\n  " + str(r["kubernetes_snippet"]).replace("\n", "\n  "))
        else:
            lines.append("- Kubernetes in Experience: No")

        if r["aws_found"]:
            lines.append(f"- AWS in Experience: Yes (page {r['aws_page']})")
            lines.append("  Snippet:\n\n  " + str(r["aws_snippet"]).replace("\n", "\n  "))
        else:
            lines.append("- AWS in Experience: No")

        lines.append(f"- Experience entries found (after exclusion): {r['experience_entries_found']}")
        lines.append(f"- DevOps years counted (unique, overlap-safe): {r['devops_years']}")
        lines.append(f"- DevOps pass (>= 3 years AND no ambiguity): {'Yes' if r['devops_pass'] else 'No'}")
        lines.append(f"- Date ambiguity: {'Yes' if r['ambiguity'] else 'No'}")

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

        excl: List[str] = r["excluded_entries"]  # type: ignore
        if excl:
            lines.append("- Excluded entries (ITI/NTI/Sprints/DEPI):")
            for e in excl:
                lines.append(f"  - {e}")
        else:
            lines.append("- Excluded entries (ITI/NTI/Sprints/DEPI): None")

        lines.append("")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


# -----------------------------
# Folder distribution
# -----------------------------

def safe_copy(src: Path, dst_dir: Path) -> Path:
    """Copy src into dst_dir. If filename exists, add a numeric suffix."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if not dst.exists():
        shutil.copy2(src, dst)
        return dst

    stem, suffix = src.stem, src.suffix
    for i in range(1, 10_000):
        candidate = dst_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            shutil.copy2(src, candidate)
            return candidate
    raise RuntimeError(f"Too many duplicates copying {src.name} into {dst_dir}")


def distribute_pdfs(results: List[Dict[str, object]], input_folder: Path, output_root: Path) -> None:
    passed_dir = output_root / "passed_cvs"
    failed_dir = output_root / "failed_cvs"
    ambiguous_dir = output_root / "ambiguous_cvs"

    for r in results:
        pdf_path = input_folder / str(r["file"])
        if not pdf_path.exists():
            continue

        bucket = classify_bucket(r)
        if bucket == "passed":
            safe_copy(pdf_path, passed_dir)
        elif bucket == "failed":
            safe_copy(pdf_path, failed_dir)
        else:
            safe_copy(pdf_path, ambiguous_dir)


# -----------------------------
# Excel output (formatted + colored Result)
# -----------------------------

def write_excel(results: List[Dict[str, object]], output_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Screening Results"

    headers = [
        "file",
        "result",
        "kubernetes_found",
        "kubernetes_page",
        "kubernetes_snippet",
        "aws_found",
        "aws_page",
        "aws_snippet",
        "devops_years",
        "devops_pass",
        "date_ambiguity",
        "used_ocr",
        "experience_entries_found",
    ]
    ws.append(headers)

    for r in results:
        ws.append(
            [
                r.get("file"),
                excel_result_label(r),  # PASS / FAIL / AMBIGUOUS
                r.get("kubernetes_found"),
                r.get("kubernetes_page"),
                r.get("kubernetes_snippet", ""),
                r.get("aws_found"),
                r.get("aws_page"),
                r.get("aws_snippet", ""),
                r.get("devops_years"),
                r.get("devops_pass"),
                r.get("ambiguity"),
                r.get("used_ocr"),
                r.get("experience_entries_found"),
            ]
        )

    # Formatting basics
    header_font = Font(bold=True)
    top = Alignment(vertical="top")
    wrap_top = Alignment(wrap_text=True, vertical="top")

    ws.row_dimensions[1].height = 22
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = top

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    header_to_col = {headers[i]: i + 1 for i in range(len(headers))}

    # Wrap snippets + align all cells top
    snippet_cols = {"kubernetes_snippet", "aws_snippet"}
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for c in row:
            c.alignment = top
        for name in snippet_cols:
            col_idx = header_to_col[name]
            row[col_idx - 1].alignment = wrap_top

    # Color the "result" cell:
    # - FAIL: red fill, white text
    # - PASS: green fill, white text
    # - AMBIGUOUS: orange fill, white text
    result_col = header_to_col["result"]

    fill_pass = PatternFill(fill_type="solid", fgColor="00A000")   # green
    fill_fail = PatternFill(fill_type="solid", fgColor="C00000")   # red
    fill_amb  = PatternFill(fill_type="solid", fgColor="F39C12")   # orange
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

    # Column widths (auto-ish, with caps)
    caps = {h: 45 for h in headers}
    caps["file"] = 55
    caps["result"] = 14
    caps["kubernetes_snippet"] = 80
    caps["aws_snippet"] = 80
    caps["devops_years"] = 14

    for col_idx, h in enumerate(headers, start=1):
        longest = len(h)
        for rr in range(2, ws.max_row + 1):
            v = ws.cell(row=rr, column=col_idx).value
            if v is None:
                continue
            s = str(v)
            longest = max(longest, len(s))
        width = min(caps.get(h, 45), max(10, longest + 2))
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Row heights: increase when snippets are long
    kube_col = header_to_col["kubernetes_snippet"]
    aws_col = header_to_col["aws_snippet"]
    for rr in range(2, ws.max_row + 1):
        kube_snip = ws.cell(row=rr, column=kube_col).value or ""
        aws_snip = ws.cell(row=rr, column=aws_col).value or ""
        if len(str(kube_snip)) > 80 or len(str(aws_snip)) > 80:
            ws.row_dimensions[rr].height = 70
        else:
            ws.row_dimensions[rr].height = 20

    wb.save(output_path)


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Screen CV PDFs for DevOps requirements.")
    parser.add_argument(
        "folder",
        nargs="?",
        default="./cvs",
        help="Folder containing PDF CVs (default: ./cvs)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Where to write outputs + classification folders (default: current directory)",
    )
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    outdir = Path(args.output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(folder.glob("*.pdf"))
    results: List[Dict[str, object]] = [screen_pdf(pdf) for pdf in pdfs]

    # Output files
    write_csv(results, outdir / "screening_results.csv")
    write_report(results, outdir / "screening_report.md")
    write_excel(results, outdir / "screening_results.xlsx")

    # Folder distribution
    distribute_pdfs(results, folder, outdir)


if __name__ == "__main__":
    main()
