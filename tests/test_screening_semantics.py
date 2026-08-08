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
    _deserialize_result,
    _retain_semantic_reviews,
    _serialize_result,
    distribute_pdfs,
    ensure_bucket_dirs,
)
from kriterion.experience import Entry, Role
from kriterion.output import (
    _role_label,
    _tool_icon_html,
    _tool_icon_slug,
    write_html_report,
)
from kriterion.scoring import (
    _keyword_evidence_detail,
    build_verdict_reasons,
    detect_tools_in_entries,
    screen_cv,
)
from kriterion.synonyms import normalize_tool_name


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

    def test_tool_index_normalizes_synonyms_from_experience(self) -> None:
        tools = detect_tools_in_entries(
            [
                self.entry(
                    "Managed K8s workloads on Amazon Web Services using Terraform "
                    "and Prometheus."
                )
            ]
        )

        self.assertIn("aws", tools)
        self.assertIn("kubernetes", tools)
        self.assertIn("prometheus", tools)
        self.assertIn("terraform", tools)

    def test_managed_kubernetes_services_merge_into_provider_and_kubernetes(self) -> None:
        tools = detect_tools_in_entries(
            [
                self.entry(
                    "Operated Amazon EKS, AKS, and GKE clusters across production "
                    "environments."
                )
            ]
        )

        self.assertIn("aws", tools)
        self.assertIn("azure", tools)
        self.assertIn("gcp", tools)
        self.assertIn("kubernetes", tools)
        self.assertNotIn("eks", tools)
        self.assertNotIn("aks", tools)

    def test_azure_devops_is_separate_from_azure_cloud(self) -> None:
        azure_devops_tools = detect_tools_in_entries(
            [self.entry("Implemented CI/CD using Azure DevOps Pipelines.")]
        )
        azure_cloud_tools = detect_tools_in_entries(
            [self.entry("Provisioned production resources in Microsoft Azure.")]
        )

        self.assertIn("azure devops", azure_devops_tools)
        self.assertNotIn("azure", azure_devops_tools)
        self.assertIn("azure", azure_cloud_tools)
        self.assertNotIn("azure devops", azure_cloud_tools)

    def test_azure_devops_pipeline_variants_share_one_filter(self) -> None:
        variants = (
            "Azure DevOps",
            "Azure DevOps Pipeline",
            "Azure DevOps Pipelines",
            "Azure Pipeline",
            "Azure Pipelines",
        )

        self.assertTrue(
            all(normalize_tool_name(variant) == "azure devops" for variant in variants)
        )

    def test_multiword_tool_icons_use_concatenated_asset_names(self) -> None:
        self.assertEqual(_tool_icon_slug("github actions"), "githubactions")
        self.assertEqual(_tool_icon_slug("azure devops"), "azuredevops")

    def test_white_icon_variant_is_used_only_for_dark_mode(self) -> None:
        icon_html = _tool_icon_html("circleci")

        self.assertIn(
            'class="tool-icon-light" src="tools/circleci.png"', icon_html
        )
        self.assertIn(
            'class="tool-icon-dark" src="tools/circleci-white.png"', icon_html
        )

    def test_wide_docker_and_zabbix_icons_receive_enlarged_treatment(self) -> None:
        self.assertIn(
            'class="tool-icon-enlarged tool-icon-docker"',
            _tool_icon_html("docker"),
        )
        self.assertIn(
            'class="tool-icon-enlarged tool-icon-zabbix"',
            _tool_icon_html("zabbix"),
        )
        self.assertNotIn('class="tool-icon-enlarged"', _tool_icon_html("aws"))

    def test_career_history_label_includes_company(self) -> None:
        role = Role(
            title="DevOps Engineer",
            start=date(2021, 1, 1),
            end=date(2025, 1, 1),
            months_added=48,
            company="VOIS",
        )

        self.assertEqual(_role_label(role), "DevOps Engineer @ VOIS")

    def test_role_company_survives_cache_and_old_entries_remain_readable(self) -> None:
        role = Role(
            title="DevOps Engineer",
            start=date(2021, 1, 1),
            end=date(2025, 1, 1),
            months_added=48,
            company="VOIS",
        )
        restored = _deserialize_result(
            _serialize_result({"devops_roles": [role]})
        )["devops_roles"][0]
        self.assertEqual(restored.company, "VOIS")

        legacy = _deserialize_result(
            {
                "devops_roles": [
                    {
                        "title": "DevOps Engineer",
                        "start": "2021-01-01",
                        "end": "2025-01-01",
                        "months_added": 48,
                    }
                ]
            }
        )["devops_roles"][0]
        self.assertEqual(legacy.company, "")

    def test_gitlab_and_gitlab_ci_share_one_tool_facet_and_icon(self) -> None:
        tools = detect_tools_in_entries(
            [
                self.entry(
                    "Managed GitLab repositories and built GitLab CI/CD pipelines."
                )
            ]
        )

        self.assertEqual([tool for tool in tools if "gitlab" in tool], ["gitlab"])
        self.assertEqual(_tool_icon_slug("gitlab"), "gitlab")
        self.assertEqual(_tool_icon_slug("gitlab ci"), "gitlab")

    def test_other_product_variants_share_their_canonical_tool_facet(self) -> None:
        self.assertEqual(normalize_tool_name("Docker Compose"), "docker")
        self.assertEqual(normalize_tool_name("Amazon Web Services"), "aws")
        self.assertEqual(normalize_tool_name("GitHub-Actions"), "github actions")
        self.assertEqual(normalize_tool_name("NewRelic"), "new relic")

    def test_report_deduplicates_tool_variants_per_candidate(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\n"
            "DevOps Engineer\n"
            "Managed GitLab repositories and built GitLab CI/CD pipelines.",
            keyword="gitlab ci",
        )
        # Also protects reports regenerated from older cached result shapes.
        result["detected_tools"] = ["gitlab", "gitlab ci"]

        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "REQUIRED_EXPERIENCE_KEYWORDS", {"gitlab ci"}
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report([result], report_path)
            report = report_path.read_text(encoding="utf-8")

        self.assertEqual(
            report.count('class="tool-filter-chip" data-tool="gitlab"'), 1
        )
        self.assertNotIn('data-tool="gitlab_ci"', report)
        self.assertIn('data-tools="gitlab"', report)
        self.assertIn('<img src="tools/gitlab.png" alt="">', report)

    def test_direct_evidence_keeps_every_matching_line_as_a_citation(self) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "\uf0b7\n"
                    "Managed AWS workloads in production.\n"
                    "•\n"
                    "Reduced AWS infrastructure costs.\n"
                    "- Migrated applications into Amazon Web Services.\n"
                    "\uf0b7"
                )
            ],
            "aws",
        )

        citations = detail["citations"]
        self.assertEqual(len(citations), 3)
        self.assertEqual(
            [citation["matched_term"] for citation in citations],
            ["aws", "aws", "amazon web services"],
        )
        self.assertTrue(
            all(
                "AWS" in citation["snippet"] or "Amazon" in citation["snippet"]
                for citation in citations
            )
        )
        self.assertTrue(
            all(
                "\uf0b7" not in citation["snippet"]
                and "•" not in citation["snippet"]
                and not any(
                    line.startswith("- ") for line in citation["snippet"].splitlines()
                )
                for citation in citations
            )
        )

    def test_standalone_letter_o_bullets_limit_evidence_to_matching_item(self) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "Professional Responsibilities\n"
                    "o\n"
                    "Configured Linux servers across enterprise environments.\n"
                    "o\n"
                    "Managed container orchestration with Kubernetes, deploying and scaling\n"
                    "applications, creating Helm charts, and managing services, pods, and\n"
                    "networking across multiple environments.\n"
                    "o\n"
                    "Troubleshot Kubernetes pod and networking failures."
                )
            ],
            "helm",
        )

        self.assertEqual(len(detail["citations"]), 1)
        self.assertEqual(
            detail["citations"][0]["snippet"],
            "Managed container orchestration with Kubernetes, deploying and scaling\n"
            "applications, creating Helm charts, and managing services, pods, and\n"
            "networking across multiple environments.",
        )

    def test_evidence_stops_before_the_next_experience_section(self) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "\uf0b7\n"
                    "Managed AWS infrastructure while developing Python automation scripts for\n"
                    "operational tasks\n"
                    "Freelance CONSULTING EXPERIENCE\n"
                    "Independent Cloud & DevOps Consultant | Various Clients"
                )
            ],
            "aws",
        )

        self.assertEqual(
            detail["citations"][0]["snippet"],
            "Managed AWS infrastructure while developing Python automation scripts for\n"
            "operational tasks",
        )
        self.assertNotIn("Freelance", detail["citations"][0]["snippet"])

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
                    "•\n"
                    "Managed Jenkins pipelines.\n"
                    "Improved build reliability.\n"
                    "•\n"
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

    def screen_single_entry(
        self,
        text: str,
        *,
        date_ambiguity: bool = False,
        keyword: str = "kubernetes",
        role_title: str = "DevOps Engineer",
        role_company: str = "",
    ) -> dict:
        entry = self.entry(text)
        role = Role(
            title=role_title,
            start=date(2021, 1, 1),
            end=date(2025, 1, 1),
            months_added=48,
            company=role_company,
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
                {keyword},
            ),
            patch.object(config, "MIN_DEVOPS_YEARS", 3.0),
            patch.object(config, "MIN_SCORE", None),
        ):
            return screen_cv(Path("candidate.pdf"))

    def test_scrambled_multi_column_experience_requires_ai_review(self) -> None:
        with patch.object(
            kriterion_scoring,
            "pdf_has_multi_column_layout",
            return_value=True,
        ):
            result = self.screen_single_entry(
                "Oct 2020 - Jan 2021\n"
                "Alexandria University\n"
                "Eventum Solutions\n"
                "Deployed Kubernetes workloads with Helm.",
                role_title="Alexandria University",
                role_company="Teacher Assistant",
            )

        self.assertTrue(result["layout_ambiguity"])
        self.assertTrue(result["ambiguity"])
        self.assertFalse(result["passed"])
        self.assertIn(
            "Multi-column CV extraction produced an unreliable experience reading order",
            result["ambiguity_reasons"],
        )
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.html"
            write_html_report([result], report_path)
            report = report_path.read_text(encoding="utf-8")

        self.assertIn(
            "Career history withheld because the multi-column reading order is unreliable",
            report,
        )
        self.assertIn(
            "Deterministic citations withheld because the multi-column reading order is unreliable",
            report,
        )
        self.assertNotIn("Alexandria University @ Teacher Assistant", report)

    def test_coherent_multi_column_headers_remain_deterministic(self) -> None:
        with patch.object(
            kriterion_scoring,
            "pdf_has_multi_column_layout",
            return_value=True,
        ):
            result = self.screen_single_entry(
                "Jan 2021 - Jan 2025\n"
                "DevOps Engineer\n"
                "VOIS\n"
                "Managed Kubernetes clusters in production.",
                role_company="VOIS",
            )

        self.assertFalse(result["layout_ambiguity"])
        self.assertFalse(result["ambiguity"])

    def test_html_report_renders_all_direct_evidence_citations(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\n"
            "DevOps Engineer\n"
            "\uf0b7\n"
            "Managed AWS workloads in production.\n"
            "\uf0b7\n"
            "Reduced AWS infrastructure costs.\n"
            "\uf0b7\n"
            "Migrated applications into Amazon Web Services.",
            keyword="aws",
        )

        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report([result], report_path)
            report = report_path.read_text(encoding="utf-8")
            icon_copied = (Path(directory) / "tools" / "aws.png").is_file()

        self.assertIn("direct · 3 citations", report)
        self.assertIn('<img src="tools/aws.png" alt="">', report)
        self.assertIn("Evidence 01", report)
        self.assertIn("Page 1 · Matched: aws", report)
        self.assertIn("Evidence 02", report)
        self.assertIn(
            "Page 1 · Matched: amazon web services",
            report,
        )
        self.assertTrue(icon_copied)
        self.assertIn(
            ".keyword-grid{display:flex;flex-direction:column;gap:1rem}",
            report,
        )
        self.assertIn('class="tool-filter-panel"', report)
        self.assertIn('data-tool="aws"', report)
        self.assertIn('data-tools="aws"', report)
        self.assertNotIn("max-height:96px", report)

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
