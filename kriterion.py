"""Kriterion CV screening — thin entry point.

Entry point for ``kriterion.sh`` (``python kriterion.py``).  All logic lives
in the ``kriterion`` package.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# Re-export the full public API so that ``import kriterion`` picks up
# everything from the package.
from kriterion import *  # noqa: F401,F403

# Explicit imports for names used inside main() — avoids relying on wildcard.
from kriterion import config
from kriterion.cache import (
    SEMANTIC_REVIEWS_FILENAME,
    _deserialize_result,
    _file_hash,
    _load_manifest,
    _remove_from_buckets,
    _retain_semantic_reviews,
    _save_manifest,
    _serialize_result,
    distribute_pdfs,
)
from kriterion.config import (
    DEFAULT_PROFILE_PATH,
    apply_cli_overrides,
    apply_profile,
    load_profile,
)
from kriterion.output import write_csv, write_excel, write_html_report, write_report
from kriterion.scoring import excel_result_label, screen_cv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Screen CV PDFs for DevOps requirements."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="./cvs",
        help="Folder containing PDF CVs (default: ./cvs)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Path to YAML job profile (default: ./profiles/profile.yaml if it exists)",
    )

    parser.add_argument(
        "--min-devops-years",
        type=float,
        default=None,
        help="Override min_experience_years from profile",
    )
    parser.add_argument(
        "--required-keyword",
        action="append",
        default=None,
        help="Override must_have_in_experience (repeatable)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="Require minimum confidence score (0-100)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print per-CV scoring breakdown to stderr",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Generate the static report without starting the local AI server",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Run the foreground server without opening a browser",
    )
    parser.add_argument(
        "--no-auto-ai",
        action="store_true",
        help="Do not automatically send ambiguous CVs to Copilot when the dashboard opens",
    )

    args = parser.parse_args()

    profile_path = Path(args.profile) if args.profile else DEFAULT_PROFILE_PATH
    profile: Optional[Dict[str, object]] = None
    if profile_path.exists():
        try:
            profile = load_profile(profile_path)
            apply_profile(profile)
            print(f"  Profile: {profile['role']}", file=sys.stderr)
            print(
                f"  Min experience: {profile['min_experience_years']} years",
                file=sys.stderr,
            )
            print(
                f"  Must have in experience: {', '.join(profile['must_have_in_experience'])}",  # type: ignore
                file=sys.stderr,
            )
            print("", file=sys.stderr)
        except (ValueError, FileNotFoundError) as e:
            print(f"Error loading profile: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.profile:
        print(f"Error: profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)

    apply_cli_overrides(args.min_devops_years, args.required_keyword, args.min_score)

    role_name = profile["role"] if profile else "Screening"
    run_slug = re.sub(r"[^\w]+", "_", role_name).strip("_")
    run_date = dt.date.today().isoformat()
    run_dir_name = f"{run_slug}_{run_date}"

    folder = Path(args.folder).resolve()
    outdir = Path(args.output_dir).resolve() / run_dir_name
    outdir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".pdf", ".docx"))
    pdf_names = {p.name for p in pdfs}

    manifest = _load_manifest(outdir)

    cached_results: List[Dict[str, object]] = []
    cached_names: Set[str] = set()
    to_screen: List[Path] = []

    for pdf in pdfs:
        name = pdf.name
        file_hash = _file_hash(pdf)
        entry = manifest.get(name)
        if entry and entry.get("sha256") == file_hash:
            cached_results.append(_deserialize_result(entry["result"]))  # type: ignore
            cached_names.add(name)
        else:
            to_screen.append(pdf)

    removed_names = set(manifest.keys()) - pdf_names
    for removed in removed_names:
        _remove_from_buckets(removed, outdir)
        del manifest[removed]
    _retain_semantic_reviews(outdir, cached_names)

    fresh_results: List[Dict[str, object]] = []
    if to_screen:
        max_workers = max(1, (os.cpu_count() or 2) // 2)
        if len(to_screen) > 4 and max_workers > 1:
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=max_workers
            ) as executor:
                fresh_results = list(executor.map(screen_cv, to_screen))
        else:
            fresh_results = [screen_cv(pdf) for pdf in to_screen]

    print(
        f"  Cached: {len(cached_results)} | New/Changed: {len(fresh_results)} | Removed: {len(removed_names)}",
        file=sys.stderr,
    )

    results: List[Dict[str, object]] = cached_results + fresh_results

    for pdf, r in zip(to_screen, fresh_results):
        manifest[pdf.name] = {
            "sha256": _file_hash(pdf),
            "result": _serialize_result(r),
        }
    _save_manifest(manifest, outdir)

    results.sort(key=lambda r: int(r.get("score", 0)), reverse=True)

    if args.verbose:
        for r in results:
            label = excel_result_label(r)
            print(
                f"  {r['file']}: {label} (score: {r.get('score', 0)}/100)",
                file=sys.stderr,
            )

    icon_src = Path(__file__).parent / "assets" / "kriterion-icon.png"
    if icon_src.exists():
        shutil.copy2(icon_src, outdir / "icon.png")

    extracted_dir = outdir / "extracted"
    extracted_dir.mkdir(exist_ok=True)
    fresh_names = {str(result["file"]) for result in fresh_results}
    for r in results:
        text = r.pop("_full_text", "")
        r.pop("_experience_text", "")
        extracted_path = extracted_dir / f"{r['file']}.txt"
        if str(r["file"]) in fresh_names:
            extracted_path.write_text(text, encoding="utf-8")

    profile_data: Dict[str, object] = dict(profile or {})
    profile_data.update(
        {
            "role": role_name,
            "min_experience_years": config.MIN_DEVOPS_YEARS,
            "must_have_in_experience": sorted(config.REQUIRED_EXPERIENCE_KEYWORDS),
            "min_score": config.MIN_SCORE,
        }
    )

    write_csv(results, outdir / "screening_results.csv")
    write_report(results, outdir / "screening_report.md")
    html_path = outdir / "screening_report.html"
    write_html_report(
        results,
        html_path,
        cv_folder=folder,
        auto_ai_review=not args.no_auto_ai,
        profile=profile_data,
    )
    write_excel(results, outdir / "screening_results.xlsx")

    distribute_pdfs(results, folder, outdir)

    if args.no_serve:
        print(f"  Static dashboard: {html_path}", file=sys.stderr)
        return

    from serve import KriterionError, serve_report

    print("  Server: foreground (press Ctrl+C to stop)", file=sys.stderr)
    try:
        serve_report(
            outdir,
            profile_data,
            token=secrets.token_urlsafe(32),
            idle_timeout=0,
            heartbeat_timeout=0,
            open_browser=not args.no_open,
            cv_base=folder,
        )
    except KeyboardInterrupt:
        print("\n  Kriterion server stopped.", file=sys.stderr)
    except KriterionError as exc:
        print(f"  Warning: local AI server unavailable: {exc}", file=sys.stderr)
        print(f"  Static dashboard: {html_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
