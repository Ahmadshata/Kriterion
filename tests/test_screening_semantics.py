import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from kriterion import config
from kriterion import scoring as kriterion_scoring
from kriterion.cache import (
    SEMANTIC_REVIEWS_FILENAME,
    _retain_semantic_reviews,
    distribute_pdfs,
    ensure_bucket_dirs,
)
from kriterion.experience import Entry, Role
from kriterion.scoring import (
    _keyword_evidence_detail,
    build_verdict_reasons,
    screen_cv,
)


class DeterministicSemanticEvidenceTests(unittest.TestCase):
    def entry(self, text: str) -> Entry:
        return Entry(lines=[(1, line) for line in text.splitlines()])

    def test_direct_kubernetes_experience_qualifies(self) -> None:
        detail = _keyword_evidence_detail(
            [self.entry("Built and operated Kubernetes clusters in production.")],
            "kubernetes",
        )
        self.assertEqual(detail["status"], "DIRECT_EXPERIENCE_MENTION")
        self.assertTrue(detail["qualifies"])
        self.assertFalse(detail["needs_review"])

    def test_demonstrated_aks_usage_deterministically_qualifies(self) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "Deployed production workloads to AKS and managed cluster upgrades."
                )
            ],
            "kubernetes",
        )
        self.assertEqual(detail["status"], "RELATED_USAGE_EVIDENCE")
        self.assertEqual(detail["relationship"], "managed_service")
        self.assertEqual(detail["matched_term"], "aks")
        self.assertTrue(detail["qualifies"])
        self.assertFalse(detail["needs_review"])

    def test_aks_mention_without_usage_requires_review(self) -> None:
        detail = _keyword_evidence_detail(
            [self.entry("Azure services: App Service, AKS, Functions.")],
            "kubernetes",
        )
        self.assertEqual(detail["status"], "RELATED_MENTION_NEEDS_REVIEW")
        self.assertFalse(detail["qualifies"])
        self.assertTrue(detail["needs_review"])

    def test_unrelated_action_elsewhere_does_not_prove_aks_usage(self) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "Managed Jenkins pipelines.\n"
                    "Improved build reliability.\n"
                    "Cloud platforms and services.\n"
                    "Azure services: AKS and Functions."
                )
            ],
            "kubernetes",
        )
        self.assertEqual(detail["status"], "RELATED_MENTION_NEEDS_REVIEW")
        self.assertFalse(detail["qualifies"])

    def test_absent_related_evidence_is_not_ambiguous(self) -> None:
        detail = _keyword_evidence_detail(
            [self.entry("Maintained Linux servers and Jenkins pipelines.")],
            "kubernetes",
        )
        self.assertEqual(detail["status"], "NOT_FOUND")
        self.assertFalse(detail["qualifies"])
        self.assertFalse(detail["needs_review"])

    def screen_single_entry(self, text: str, *, date_ambiguity: bool = False) -> dict:
        entry = self.entry(text)
        role = Role(
            title="DevOps Engineer",
            start=date(2021, 1, 1),
            end=date(2025, 1, 1),
            months_added=48,
        )
        with (
            patch.object(
                kriterion_scoring,
                "extract_text_by_page",
                return_value=([text], False),
            ),
            patch.object(
                kriterion_scoring,
                "extract_experience_entries",
                return_value=[entry],
            ),
            patch.object(
                kriterion_scoring,
                "compute_devops_roles",
                return_value=([role], 48, date_ambiguity),
            ),
            patch.object(
                config,
                "REQUIRED_EXPERIENCE_KEYWORDS",
                {"kubernetes"},
            ),
            patch.object(config, "MIN_DEVOPS_YEARS", 3.0),
            patch.object(config, "MIN_SCORE", None),
        ):
            return screen_cv(Path("candidate.pdf"))

    def test_weak_related_mention_makes_candidate_ambiguous(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nAzure services: AKS and Functions."
        )
        self.assertTrue(result["semantic_ambiguity"])
        self.assertTrue(result["ambiguity"])
        self.assertFalse(result["passed"])
        self.assertIn("Azure services: AKS", result["_experience_text"])

    def test_related_usage_can_pass_without_ai(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nManaged AKS clusters in production."
        )
        self.assertFalse(result["semantic_ambiguity"])
        self.assertFalse(result["ambiguity"])
        self.assertTrue(result["passed"])

    def test_absent_evidence_is_a_deterministic_failure(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nMaintained Linux servers."
        )
        self.assertFalse(result["semantic_ambiguity"])
        self.assertFalse(result["ambiguity"])
        self.assertFalse(result["passed"])

    def test_spawned_worker_receives_every_active_required_keyword(self) -> None:
        profile = {
            "min_experience_years": 3,
            "must_have_in_experience": ["aws", "helm", "kubernetes"],
            "min_score": None,
        }
        with (
            patch.object(config, "MIN_DEVOPS_YEARS", 1.0),
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
            patch.object(config, "MIN_SCORE", None),
        ):
            config.initialize_screening_worker(
                profile,
                3.0,
                ["aws", "helm", "kubernetes", "prometheus"],
                None,
            )
            self.assertEqual(config.MIN_DEVOPS_YEARS, 3.0)
            self.assertEqual(
                config.REQUIRED_EXPERIENCE_KEYWORDS,
                {"aws", "helm", "kubernetes", "prometheus"},
            )

    def test_hard_failure_does_not_hide_independent_date_ambiguity(self) -> None:
        result = self.screen_single_entry(
            "2021 - 2025\nDevOps Engineer\nMaintained Linux servers.",
            date_ambiguity=True,
        )
        self.assertTrue(result["date_ambiguity"])
        self.assertTrue(result["ambiguity"])
        self.assertFalse(result["passed"])
        with patch.object(
            config,
            "REQUIRED_EXPERIENCE_KEYWORDS",
            {"kubernetes"},
        ):
            reasons = build_verdict_reasons(result)
        self.assertTrue(any("Date ambiguity" in reason for reason in reasons))
        self.assertTrue(
            any("Missing required keywords" in reason for reason in reasons)
        )

    def test_semantic_reviews_survive_only_for_unchanged_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / SEMANTIC_REVIEWS_FILENAME
            path.write_text(
                json.dumps(
                    {
                        "unchanged.pdf": {"summary": "keep"},
                        "changed.pdf": {"summary": "discard"},
                    }
                ),
                encoding="utf-8",
            )
            _retain_semantic_reviews(
                Path(directory),
                {"unchanged.pdf"},
            )
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"unchanged.pdf": {"summary": "keep"}},
            )

    def test_bucket_copy_moves_when_candidate_becomes_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            bucket_dirs = ensure_bucket_dirs(output_dir)
            source = input_dir / "candidate.pdf"
            source.write_bytes(b"source CV")
            (bucket_dirs["failed"] / source.name).write_bytes(b"source CV")

            distribute_pdfs(
                [{"file": source.name, "ambiguity": True, "passed": False}],
                input_dir,
                output_dir,
            )

            self.assertTrue(source.exists())
            self.assertFalse((bucket_dirs["failed"] / source.name).exists())
            self.assertTrue((bucket_dirs["ambiguous"] / source.name).exists())


if __name__ == "__main__":
    unittest.main()
