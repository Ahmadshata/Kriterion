"""Manifest, serialization, file distribution, and incremental cache."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from kriterion import config
from kriterion.experience import Role
from kriterion.scoring import classify_bucket


MANIFEST_FILENAME = "manifest.json"
SEMANTIC_REVIEWS_FILENAME = "semantic_reviews.json"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _serialize_result(r: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for k, v in r.items():
        if k == "devops_roles":
            out[k] = [
                {
                    "title": role.title,
                    "company": role.company,
                    "start": role.start.isoformat() if role.start else None,
                    "end": role.end.isoformat() if role.end else None,
                    "months_added": role.months_added,
                }
                for role in v  # type: ignore
            ]
        elif k == "required_evidence":
            evidence: Dict[str, object] = {}
            for ek, ev in v.items():  # type: ignore
                if ev is None:
                    evidence[ek] = None
                else:
                    evidence[ek] = [ev[0], ev[1]]
            out[k] = evidence
        elif isinstance(v, dt.date):
            out[k] = v.isoformat()
        elif isinstance(v, set):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def _deserialize_result(data: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = dict(data)

    if "devops_roles" in out:
        roles = []
        for rd in out["devops_roles"]:  # type: ignore
            start = dt.date.fromisoformat(rd["start"]) if rd["start"] else None
            end = dt.date.fromisoformat(rd["end"]) if rd["end"] else None
            roles.append(
                Role(
                    title=rd["title"],
                    start=start,
                    end=end,
                    months_added=rd["months_added"],
                    company=rd.get("company", ""),
                )
            )
        out["devops_roles"] = roles

    if "required_evidence" in out:
        evidence: Dict[str, Optional[Tuple[int, str]]] = {}
        for ek, ev in out["required_evidence"].items():  # type: ignore
            if ev is None:
                evidence[ek] = None
            else:
                evidence[ek] = (ev[0], ev[1])
        out["required_evidence"] = evidence

    return out


def _config_fingerprint() -> str:
    """Hash of screening config + code — any change invalidates the cache."""
    package_dir = Path(__file__).resolve().parent
    code_hash = hashlib.sha256()
    for py_file in sorted(package_dir.glob("*.py")):
        code_hash.update(py_file.read_bytes())
    code_hex = code_hash.hexdigest()[:16]
    config_str = json.dumps(
        {
            "keywords": sorted(config.REQUIRED_EXPERIENCE_KEYWORDS),
            "min_years": config.MIN_DEVOPS_YEARS,
            "min_score": config.MIN_SCORE,
            "include_freelance_experience": config.INCLUDE_FREELANCE_EXPERIENCE,
            "code": code_hex,
        },
        sort_keys=True,
    )
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


def _load_manifest(outdir: Path) -> Dict[str, Dict[str, object]]:
    manifest_path = outdir / MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("__config__") != _config_fingerprint():
                return {}
            data.pop("__config__", None)
            return data
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_manifest(manifest: Dict[str, Dict[str, object]], outdir: Path) -> None:
    manifest_path = outdir / MANIFEST_FILENAME
    data = dict(manifest)
    data["__config__"] = _config_fingerprint()  # type: ignore
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _retain_semantic_reviews(outdir: Path, unchanged_filenames: Set[str]) -> None:
    reviews_path = outdir / SEMANTIC_REVIEWS_FILENAME
    if not reviews_path.exists():
        return
    try:
        data = json.loads(reviews_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    retained = {
        filename: review
        for filename, review in data.items()
        if filename in unchanged_filenames
    }
    reviews_path.write_text(
        json.dumps(retained, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _remove_from_buckets(filename: str, outdir: Path) -> None:
    for bucket in ("passed_cvs", "failed_cvs", "ambiguous_cvs"):
        target = outdir / bucket / filename
        if target.exists():
            target.unlink()
    extracted_text = outdir / "extracted" / f"{filename}.txt"
    if extracted_text.exists():
        extracted_text.unlink()


def ensure_bucket_dirs(output_root: Path) -> Dict[str, Path]:
    passed_dir = output_root / "passed_cvs"
    failed_dir = output_root / "failed_cvs"
    ambiguous_dir = output_root / "ambiguous_cvs"

    passed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    ambiguous_dir.mkdir(parents=True, exist_ok=True)

    return {"passed": passed_dir, "failed": failed_dir, "ambiguous": ambiguous_dir}


def copy_if_absent(src: Path, dst_dir: Path) -> None:
    dst = dst_dir / src.name
    if dst.exists():
        return
    shutil.copy2(src, dst)


def distribute_pdfs(
    results: List[Dict[str, object]], input_folder: Path, output_root: Path
) -> None:
    bucket_dirs = ensure_bucket_dirs(output_root)

    for r in results:
        filename = str(r["file"])
        pdf_path = input_folder / filename
        if not pdf_path.exists():
            continue

        bucket = classify_bucket(r)
        for other_bucket, other_dir in bucket_dirs.items():
            if other_bucket == bucket:
                continue
            stale_copy = other_dir / filename
            if stale_copy.exists():
                stale_copy.unlink()
        copy_if_absent(pdf_path, bucket_dirs[bucket])
