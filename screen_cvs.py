#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import fitz  # PyMuPDF



# --- EXCLUSION: use word-boundary regex (avoid "certification" false positives) ---
EXCLUDE_PATTERNS = [
    re.compile(r"\biti\b", re.IGNORECASE),
    re.compile(r"\bnti\b", re.IGNORECASE),
    re.compile(r"\bsprints\b", re.IGNORECASE),
    re.compile(r"\bdepi\b", re.IGNORECASE),
    re.compile(r"information\s+technology\s+institute", re.IGNORECASE),
    re.compile(r"national\s+technology\s+institute", re.IGNORECASE),
]


DEVOPS_KEYWORDS = {
    "devops", "sre", "site reliability",
    "platform engineer", "platform engineering",
    "infrastructure", "cloud engineer", "cloud engineering",
    "kubernetes", "terraform", "terragrunt",
    "ci/cd", "cicd", "jenkins", "github actions",
    "helm", "eks", "docker", "ansible",
    "prometheus", "grafana", "argo", "argo cd", "gitops",
    "linux", "iac", "infrastructure as code", "cloudformation",
}

# Stop building job entries when we hit these (conservative)
ENTRY_STOP_HEADINGS = {"languages", "volunteering", "education"}

EDUCATION_HINTS = {"bachelor", "master", "masters", "degree", "faculty", "university", "education"}

JOB_TITLE_HINTS = {
    "engineer", "developer", "administrator", "architect", "consultant",
    "specialist", "lead", "manager", "intern", "head",
}

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Matches: "Feb 2024 - Present", "08/2021 - 05/2023", "2019 - 2025", etc.
DATE_RANGE_PATTERN = re.compile(
    r"(?P<start>(?:[A-Za-z]{3,9}\s+\d{4})|(?:\d{1,2}[/-]\d{4})|(?:\d{4}))\s*"
    r"(?:-|–|—|to)\s*"
    r"(?P<end>(?:[A-Za-z]{3,9}\s+\d{4})|(?:\d{1,2}[/-]\d{4})|(?:\d{4})|"
    r"(?:present|current|now))",
    re.IGNORECASE,
)


@dataclass
class Entry:
    lines: List[Tuple[int, str]]  # (page_number, line)

    def text(self) -> str:
        return "\n".join(line for _, line in self.lines).strip()

    def head(self, n: int = 3) -> str:
        out = []
        for _, line in self.lines:
            if line.strip():
                out.append(line.strip())
            if len(out) >= n:
                break
        return " | ".join(out)


@dataclass
class Role:
    title: str
    start: dt.date
    end: dt.date
    months_added: int


def extract_text_by_page(pdf_path: Path) -> Tuple[List[str], bool]:
    doc = fitz.open(pdf_path)
    pages = [page.get_text("text") for page in doc]
    used_ocr = False

    # Optional OCR fallback for scanned PDFs
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


def is_date_range_line(line: str) -> bool:
    return DATE_RANGE_PATTERN.search(line) is not None


def is_excluded(entry_text: str) -> bool:
    return any(p.search(entry_text) for p in EXCLUDE_PATTERNS)


def is_devops_related(entry_text: str) -> bool:
    lower = entry_text.lower()
    return any(k in lower for k in DEVOPS_KEYWORDS)


def is_experience_entry(entry: Entry) -> bool:
    text = entry.text().lower()

    # Filter out education-like entries
    if any(h in text for h in EDUCATION_HINTS):
        return False

    # Must contain a date range somewhere (we only build date-based entries anyway)
    if not DATE_RANGE_PATTERN.search(entry.text()):
        return False

    # Keep if it looks like a job OR clearly DevOps
    head = entry.head(4).lower()
    if any(h in head for h in JOB_TITLE_HINTS):
        return True
    if is_devops_related(text):
        return True

    return False


def build_date_based_entries(pages: Sequence[str]) -> List[Entry]:
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

        norm = normalize_heading(line)
        if norm in ENTRY_STOP_HEADINGS:
            # close current entry and stop until next date-range line
            if current:
                entries.append(Entry(lines=current))
            current = []
            capturing = False
            continue

        current.append((page_num, line))

    if current:
        entries.append(Entry(lines=current))

    # Drop empty-ish entries
    return [e for e in entries if e.text()]


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

    # Year-only: conservative lower bound
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
    ranges = []
    for m in DATE_RANGE_PATTERN.finditer(text):
        s_raw, e_raw = m.group("start"), m.group("end")
        s, s_amb = parse_month_year(s_raw, is_start=True)
        e, e_amb = parse_month_year(e_raw, is_start=False)
        if s and e and e >= s:
            ranges.append((s, e, s_amb or e_amb))
    return ranges


def months_between(start: dt.date, end: dt.date) -> List[dt.date]:
    months = []
    cur = dt.date(start.year, start.month, 1)
    last = dt.date(end.year, end.month, 1)
    while cur <= last:
        months.append(cur)
        y = cur.year + (cur.month // 12)
        m = cur.month % 12 + 1
        cur = dt.date(y, m, 1)
    return months


def compute_devops_roles(entries: List[Entry]) -> Tuple[List[Role], int, bool]:
    roles: List[Role] = []
    total_months: Set[dt.date] = set()
    ambiguity = False

    # Collect date ranges from DevOps-related entries only
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
        roles.append(Role(title=entry.head(2), start=start, end=end, months_added=added))
        ambiguity = ambiguity or amb

    return roles, len(total_months), ambiguity


def screen_pdf(pdf_path: Path) -> Dict[str, object]:
    pages, used_ocr = extract_text_by_page(pdf_path)

    # Robust experience extraction: date-range driven
    raw_entries = build_date_based_entries(pages)
    exp_entries = [e for e in raw_entries if is_experience_entry(e)]
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

    # Pass rule: >= 36 DevOps months (ambiguity is reported, not an automatic fail)
    devops_pass = devops_months >= 36
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
        "devops_months": devops_months,
        "devops_roles": roles,
        "excluded_entries": excluded_entries,
        "used_ocr": used_ocr,
        "ambiguity": ambiguity,
        "devops_pass": devops_pass,
    }
def write_csv(results: List[Dict[str, object]], output_path: Path) -> None:
    fields = [
        "file", "passed",
        "kubernetes_found", "kubernetes_page",
        "aws_found", "aws_page",
        "devops_months", "devops_pass",
        "date_ambiguity", "used_ocr",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(
                {
                    "file": r["file"],
                    "passed": r["passed"],
                    "kubernetes_found": r["kubernetes_found"],
                    "kubernetes_page": r["kubernetes_page"],
                    "aws_found": r["aws_found"],
                    "aws_page": r["aws_page"],
                    "devops_months": r["devops_months"],
                    "devops_pass": r["devops_pass"],
                    "date_ambiguity": r["ambiguity"],
                    "used_ocr": r["used_ocr"],
                }
            )


def format_date(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def write_report(results: List[Dict[str, object]], output_path: Path) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    lines: List[str] = []
    lines.append("# CV Screening Report\n")
    lines.append("## Summary")
    lines.append(f"- Total CVs: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}\n")

    for r in results:
        lines.append(f"## {r['file']}")
        lines.append(f"- Result: {'PASS' if r['passed'] else 'FAIL'}")
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

        lines.append(f"- DevOps months counted (conservative): {r['devops_months']}")
        lines.append(f"- DevOps pass (>= 36 months): {'Yes' if r['devops_pass'] else 'No'}")
        lines.append(f"- Date ambiguity: {'Yes' if r['ambiguity'] else 'No'}")

        roles: List[Role] = r["devops_roles"]  # type: ignore
        if roles:
            lines.append("- DevOps roles counted:")
            for role in roles:
                lines.append(f"  - {role.title} ({format_date(role.start)} to {format_date(role.end)}): {role.months_added} months")
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

def main() -> None:
    p = argparse.ArgumentParser(description="Screen CV PDFs for DevOps requirements.")
    p.add_argument("folder", nargs="?", default="./cvs", help="Folder containing PDF CVs (default: ./cvs)")
    args = p.parse_args()

    folder = Path(args.folder).resolve()
    pdfs = sorted(folder.glob("*.pdf"))

    results: List[Dict[str, object]] = [screen_pdf(pdf) for pdf in pdfs]
    write_csv(results, Path("screening_results.csv"))
    write_report(results, Path("screening_report.md"))


if __name__ == "__main__":
    main()
