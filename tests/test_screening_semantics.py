import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from kriterion import config
from kriterion import scoring as kriterion_scoring
from kriterion.config import load_profile
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
    _role_tenure_years,
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

    def test_managed_kubernetes_services_merge_into_provider_and_kubernetes(
        self,
    ) -> None:
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

        self.assertIn('class="tool-icon-light" src="tools/circleci.png"', icon_html)
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

    def test_role_tenure_does_not_use_overlap_allocation_months(self) -> None:
        army_role = Role(
            title="IT Specialist",
            start=date(2021, 12, 1),
            end=date(2022, 12, 1),
            months_added=0,
        )
        current_role = Role(
            title="DevOps Engineer",
            start=date(2023, 12, 1),
            end=date(2026, 8, 1),
            months_added=0,
        )

        self.assertEqual(_role_tenure_years(army_role), 1.0)
        self.assertEqual(_role_tenure_years(current_role), 2.67)

    def test_profile_freelance_option_defaults_true_and_requires_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile_path = Path(directory) / "profile.yaml"
            profile_path.write_text(
                "role: DevOps Engineer\n"
                "min_experience_years: 3\n"
                "must_have_in_experience: [aws]\n",
                encoding="utf-8",
            )
            self.assertTrue(load_profile(profile_path)["include_freelance_experience"])

            profile_path.write_text(
                "role: DevOps Engineer\n"
                "min_experience_years: 3\n"
                "must_have_in_experience: [aws]\n"
                "include_freelance_experience: false\n",
                encoding="utf-8",
            )
            self.assertFalse(load_profile(profile_path)["include_freelance_experience"])

            profile_path.write_text(
                "role: DevOps Engineer\n"
                "min_experience_years: 3\n"
                "must_have_in_experience: [aws]\n"
                "include_freelance_experience: 'false'\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be true or false"):
                load_profile(profile_path)

    def test_excluded_freelance_supplies_neither_years_nor_tool_evidence(self) -> None:
        salaried = self.entry(
            "DevOps Engineer | Acme | Jan 2022 - Dec 2024\nManaged Kubernetes clusters."
        )
        freelance = self.entry(
            "Freelance | Python Developer | Jan 2018 - Present\n"
            "Built AWS automation tools for clients."
        )
        pages = [salaried.text() + "\n" + freelance.text()]

        with (
            patch.object(
                kriterion_scoring,
                "extract_text_by_page",
                return_value=(pages, False),
            ),
            patch.object(
                kriterion_scoring,
                "pdf_has_multi_column_layout",
                return_value=False,
            ),
            patch.object(
                kriterion_scoring,
                "extract_experience_entries",
                return_value=[salaried, freelance],
            ),
            patch.object(config, "INCLUDE_FREELANCE_EXPERIENCE", False),
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
            patch.object(config, "MIN_DEVOPS_YEARS", 0),
            patch.object(config, "MIN_SCORE", None),
        ):
            result = screen_cv(Path("candidate.pdf"))

        self.assertIsNone(result["required_evidence"]["aws"])
        self.assertNotIn("Freelance", result["_experience_text"])
        self.assertEqual(result["experience_entries_found"], 1)
        self.assertEqual(len(result["freelance_entries_excluded"]), 1)

    def test_role_company_survives_cache_and_old_entries_remain_readable(self) -> None:
        role = Role(
            title="DevOps Engineer",
            start=date(2021, 1, 1),
            end=date(2025, 1, 1),
            months_added=48,
            company="VOIS",
        )
        restored = _deserialize_result(_serialize_result({"devops_roles": [role]}))[
            "devops_roles"
        ][0]
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

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"gitlab ci"}),
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report([result], report_path)
            report = report_path.read_text(encoding="utf-8")

        self.assertEqual(report.count('class="tool-filter-chip" data-tool="gitlab"'), 1)
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

    def test_unbulleted_wrapped_responsibilities_produce_focused_citations(
        self,
    ) -> None:
        detail = _keyword_evidence_detail(
            [
                self.entry(
                    "DevOps Engineer\n"
                    "Designed CI/CD pipelines and improved delivery quality.\n"
                    "Architected scalable AWS cloud solutions, including EC2 and S3,\n"
                    "while implementing monitoring with Prometheus.\n"
                    "Developed Python cleanup automation for Docker images."
                )
            ],
            "aws",
        )

        self.assertEqual(
            detail["citations"][0]["snippet"],
            "Architected scalable AWS cloud solutions, including EC2 and S3,\n"
            "while implementing monitoring with Prometheus.",
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

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
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

    def test_html_evidence_xray_links_citations_to_the_original_cv_page(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\n"
            "DevOps Engineer\n"
            "Managed AWS workloads in production.\n"
            "Reduced AWS infrastructure costs.",
            keyword="aws",
        )
        result["file"] = "candidate #1.pdf"

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report(
                [result],
                report_path,
                cv_folder=Path(directory) / "cvs",
            )
            report = report_path.read_text(encoding="utf-8")

        payload_text = report.split(
            '<script type="application/json" id="evidenceXrayData">', 1
        )[1].split("</script>", 1)[0]
        payload = json.loads(payload_text)

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["requirement"], "AWS")
        self.assertEqual(payload[0]["relationship"], "direct")
        self.assertEqual(payload[0]["page"], 1)
        self.assertEqual(payload[0]["matchedTerm"], "aws")
        self.assertEqual(payload[0]["sourceUrl"], "/cvs/candidate%20%231.pdf")
        self.assertEqual(payload[0]["previewUrl"], "/xray/candidate%20%231.pdf")
        self.assertTrue(payload[0]["previewAvailable"])
        self.assertIn(
            payload[0]["matchedTerm"].lower(),
            payload[0]["snippet"].lower(),
        )
        self.assertIn("DevOps Engineer", payload[0]["roleContext"])
        self.assertEqual(report.count('class="xray-open-btn"'), len(payload))
        self.assertIn('id="evidenceXray"', report)
        self.assertIn("function renderXrayExcerpt", report)

    def test_html_career_history_is_newest_first_with_upward_motion(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nManaged AWS workloads.",
            keyword="aws",
        )
        result["devops_roles"] = [
            Role(
                title="Older Platform Engineer",
                start=date(2018, 1, 1),
                end=date(2020, 1, 1),
                months_added=24,
            ),
            Role(
                title="Newest Platform Engineer",
                start=date(2023, 1, 1),
                end=date(2025, 1, 1),
                months_added=0,
            ),
        ]

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report([result], report_path)
            report = report_path.read_text(encoding="utf-8")

        self.assertLess(
            report.index("Newest Platform Engineer"),
            report.index("Older Platform Engineer"),
        )
        self.assertIn("animation:exp-flow-up 4.2s linear infinite", report)
        self.assertIn("@keyframes exp-flow-up", report)
        self.assertNotIn("exp-flow-down", report)
        self.assertIn("2023-01 — 2025-01 &middot; 2.0 yr tenure", report)
        self.assertNotIn("2023-01 — 2025-01 &middot; 0.0 yr", report)

    def test_html_ai_provider_switch_hides_credits_in_codex_mode(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nAzure services: AKS and Functions."
        )

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"kubernetes"}),
        ):
            root = Path(directory)
            codex_path = root / "codex.html"
            copilot_path = root / "copilot.html"
            write_html_report([result], codex_path, ai_provider="codex")
            write_html_report([result], copilot_path, ai_provider="copilot")
            codex_report = codex_path.read_text(encoding="utf-8")
            copilot_report = copilot_path.read_text(encoding="utf-8")

        self.assertIn('var aiProvider="codex";', codex_report)
        self.assertIn("var showAiUsage=false;", codex_report)
        self.assertIn(
            'class="section-icon section-icon-codex" aria-hidden="true">CX</div>',
            codex_report,
        )
        self.assertNotIn('id="aiUsageOverview"', codex_report)
        self.assertNotIn(
            '<img class="copilot-icon" src="GitHub-Copilot-Blink.gif"',
            codex_report,
        )

        self.assertIn('var aiProvider="copilot";', copilot_report)
        self.assertIn("var showAiUsage=true;", copilot_report)
        self.assertIn('id="aiUsageOverview"', copilot_report)
        self.assertIn(
            '<img class="copilot-icon" src="GitHub-Copilot-Blink.gif"',
            copilot_report,
        )

    def test_html_criterion_lab_embeds_safe_grounded_simulation_data(self) -> None:
        result = self.screen_single_entry(
            "Jan 2021 - Jan 2025\nDevOps Engineer\nManaged AWS workloads.",
            keyword="aws",
        )
        result["file"] = "candidate</script>.pdf"

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REQUIRED_EXPERIENCE_KEYWORDS", {"aws"}),
        ):
            report_path = Path(directory) / "screening_report.html"
            write_html_report(
                [result],
                report_path,
                profile={
                    "role": "DevOps Engineer",
                    "must_have_in_experience": ["aws"],
                    "preferred_programs": [],
                },
            )
            report = report_path.read_text(encoding="utf-8")

        payload_text = report.split(
            '<script type="application/json" id="criterionLabData">', 1
        )[1].split("</script>", 1)[0]
        payload = json.loads(payload_text)

        self.assertEqual(payload["rules"], ["aws"])
        self.assertEqual(payload["candidates"][0]["name"], "candidate</script>.pdf")
        self.assertEqual(payload["candidates"][0]["evidence"]["aws"], "found")
        self.assertNotIn("candidate</script>.pdf", payload_text)
        self.assertIn('id="criterionLab"', report)
        self.assertIn("function criterionLabClassify", report)
        self.assertIn("Report only", report)

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
