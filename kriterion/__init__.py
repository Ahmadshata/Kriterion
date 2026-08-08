"""Kriterion — CV screening package."""

from kriterion.config import (
    DEFAULT_PROFILE_PATH,
    EXPERIENCE_HEADINGS,
    MIN_DEVOPS_YEARS,
    MIN_SCORE,
    REQUIRED_EXPERIENCE_KEYWORDS,
    SCORE_WEIGHTS,
    SNIPPET_CONTEXT_LINES,
    STOP_HEADINGS,
    apply_cli_overrides,
    apply_profile,
    load_profile,
    PREFERRED_PROGRAM_PATTERNS,
    EXCLUDED_COMPANY_PATTERNS,
    EXCLUDED_UNIVERSITY_PATTERNS,
    EDUCATION_PROGRAM_PATTERNS,
)
from kriterion.synonyms import (
    SYNONYM_MAP,
    match_keyword_in_text,
    normalize_heading,
    rejoin_hyphenated_words,
)
from kriterion.dates import (
    format_date,
    months_between,
    months_to_years,
    normalize_date_text,
    parse_date_ranges,
    parse_month_year,
)
from kriterion.extraction import (
    extract_text_by_page,
    extract_text_from_docx,
    iter_lines_with_pages,
    pdf_has_multi_column_layout,
    try_ocr,
)
from kriterion.experience import (
    Entry,
    Role,
    capture_experience_by_heading,
    compute_devops_roles,
    extract_experience_entries,
    has_experience_layout_anomaly,
    is_devops_related,
    is_education_program,
    is_experience_entry,
    split_entries_from_lines,
)
from kriterion.scoring import (
    KeywordMatch,
    ScoringResult,
    build_dynamic_headers,
    build_verdict_reasons,
    classify_bucket,
    compute_score,
    excel_result_label,
    find_all_keyword_matches,
    find_variant_matches,
    normalize_excel_col_name,
    row_for_result,
    screen_cv,
    _keyword_evidence_detail,
)
from kriterion.output import (
    write_csv,
    write_excel,
    write_html_report,
    write_report,
)
from kriterion.cache import (
    MANIFEST_FILENAME,
    SEMANTIC_REVIEWS_FILENAME,
    _config_fingerprint,
    _deserialize_result,
    _file_hash,
    _load_manifest,
    _remove_from_buckets,
    _retain_semantic_reviews,
    _save_manifest,
    _serialize_result,
    copy_if_absent,
    distribute_pdfs,
    ensure_bucket_dirs,
)
