import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import serve


class CopilotInvocationTests(unittest.TestCase):
    @patch("serve.subprocess.run")
    @patch("serve.shutil.which", return_value="/usr/local/bin/copilot")
    def test_copilot_receives_explicit_safe_working_directory(
        self,
        _which: object,
        run: object,
    ) -> None:
        run.return_value.returncode = 0  # type: ignore[attr-defined]
        run.return_value.stdout = '{"status":"ok"}'  # type: ignore[attr-defined]
        run.return_value.stderr = ""  # type: ignore[attr-defined]

        self.assertEqual(serve.run_copilot("synthetic prompt"), '{"status":"ok"}')

        command = run.call_args.args[0]  # type: ignore[attr-defined]
        safe_workdir = str(Path(tempfile.gettempdir()).resolve())
        self.assertEqual(command[command.index("-C") + 1], safe_workdir)
        self.assertEqual(command[command.index("--output-format") + 1], "json")
        self.assertEqual(run.call_args.kwargs["cwd"], safe_workdir)  # type: ignore[attr-defined]

    @patch("serve.subprocess.run")
    @patch("serve.shutil.which", return_value="/usr/local/bin/copilot")
    def test_copilot_extracts_assistant_response_from_jsonl(
        self,
        _which: object,
        run: object,
    ) -> None:
        verdict = {
            "ai_verdict": "PASS",
            "summary": "Supported.",
            "evidence": [],
        }
        run.return_value.returncode = 0  # type: ignore[attr-defined]
        run.return_value.stdout = "\n".join(  # type: ignore[attr-defined]
            [
                json.dumps({"type": "session.start", "data": {"id": "1"}}),
                json.dumps(
                    {
                        "type": "assistant.message",
                        "data": {"content": json.dumps(verdict)},
                    }
                ),
                json.dumps({"type": "result", "data": {"status": "success"}}),
            ]
        )
        run.return_value.stderr = ""  # type: ignore[attr-defined]

        self.assertEqual(
            json.loads(serve.run_copilot("synthetic prompt")),
            verdict,
        )

    def test_copilot_jsonl_parser_concatenates_message_deltas(self) -> None:
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant.message_delta",
                        "data": {"deltaContent": '{"ai_verdict":"'},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant.message_delta",
                        "data": {"deltaContent": 'PASS"}'},
                    }
                ),
            ]
        )
        self.assertEqual(
            serve._extract_copilot_response(stdout),
            '{"ai_verdict":"PASS"}',
        )


class KriterionServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.outdir = Path(self.tempdir.name)
        (self.outdir / "screening_report.html").write_text(
            "<!doctype html><title>Kriterion test</title>",
            encoding="utf-8",
        )
        (self.outdir / "extracted").mkdir()
        (self.outdir / "extracted" / "candidate.pdf.txt").write_text(
            "Operated Azure Kubernetes Service clusters for production workloads.\n"
            "CERTIFICATIONS\nAWS Certified Cloud Practitioner",
            encoding="utf-8",
        )
        self.candidate = {
            "file": "candidate.pdf",
            "passed": False,
            "ambiguity": True,
            "semantic_ambiguity": True,
            "date_ambiguity": False,
            "ambiguity_reasons": [
                "Related term 'aks' may satisfy 'kubernetes', but demonstrated usage is unclear"
            ],
            "score": 79,
            "devops_years": 3.58,
            "required_evidence": {
                "aws": [1, "AWS"],
                "helm": [1, "Helm"],
                "kubernetes": None,
            },
            "required_evidence_details": {
                "kubernetes": {
                    "status": "RELATED_MENTION_NEEDS_REVIEW",
                    "relationship": "managed_service",
                    "matched_term": "aks",
                    "page": 1,
                    "snippet": "Azure Kubernetes Service",
                    "qualifies": False,
                    "needs_review": True,
                }
            },
            "_experience_text": (
                "Operated Azure Kubernetes Service clusters for production workloads."
            ),
        }
        manifest = {
            "candidate.pdf": {
                "sha256": "test",
                "result": self.candidate,
            },
            "__config__": "test",
        }
        (self.outdir / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        self.profile = {
            "role": "Senior DevOps Engineer",
            "min_experience_years": 3,
            "must_have_in_experience": ["aws", "helm", "kubernetes"],
        }
        self.token = "test-token"
        self.server = serve.KriterionServer(
            (serve.LOCAL_HOST, 0),
            serve.KriterionHandler,
        )
        self.server.outdir = self.outdir
        self.server.profile = self.profile
        self.server.token = self.token
        self.server.last_activity = 0
        self.server.last_heartbeat = 0
        self.server.heartbeat_seen = False
        self.server.sessions = {}
        self.server.session_lock = threading.Lock()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://{serve.LOCAL_HOST}:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def request(
        self,
        path: str,
        *,
        payload: Optional[dict] = None,
        token: Optional[str] = None,
    ) -> tuple[int, dict]:
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Kriterion-Token"] = token
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_health_heartbeat_and_auth(self) -> None:
        self.assertEqual(self.request("/health"), (200, {"ok": True}))
        self.assertEqual(self.request("/heartbeat")[0], 401)
        self.assertEqual(
            self.request("/heartbeat", token=self.token), (200, {"ok": True})
        )
        self.assertTrue(self.server.heartbeat_seen)
        self.assertEqual(
            self.request(
                "/api/ai-verdict",
                payload={"filename": "candidate.pdf"},
            )[0],
            401,
        )

    def test_ai_verdict_uses_nested_result_and_requires_human_final_decision(
        self,
    ) -> None:
        prompts: list[str] = []

        def fake_copilot(prompt: str, **_: object) -> str:
            prompts.append(prompt)
            return json.dumps(
                {
                    "ai_verdict": "PASS",
                    "summary": "The cited AKS operation resolves the Kubernetes ambiguity.",
                    "evidence": [
                        {
                            "criterion": "kubernetes",
                            "stance": "SUPPORTS_PASS",
                            "source_quote": (
                                "Operated Azure Kubernetes Service clusters "
                                "for production workloads."
                            ),
                            "explanation": (
                                "The candidate operated a managed Kubernetes service."
                            ),
                            "confidence": 96,
                        }
                    ],
                }
            )

        with patch("serve.run_copilot", side_effect=fake_copilot):
            status, payload = self.request(
                "/api/ai-verdict",
                payload={"filename": "candidate.pdf"},
                token=self.token,
            )
            self.assertEqual(status, 200)
            review = payload["review"]
            self.assertEqual(review["ai_verdict"], "PASS")
            self.assertEqual(review["evidence"][0]["stance"], "SUPPORTS_PASS")
            self.assertEqual(review["human_decision"], "PENDING")
            self.assertIn("Recommend PASS or FAIL", prompts[0])
            self.assertIn("Related term 'aks'", prompts[0])
            self.assertNotIn("AWS Certified Cloud Practitioner", prompts[0])

            status, decision = self.request(
                "/api/final-decision",
                payload={
                    "filename": "candidate.pdf",
                    "decision": "PASS",
                },
                token=self.token,
            )
            self.assertEqual(status, 200)
            self.assertEqual(decision["human_decision"], "PASS")
            self.assertEqual(decision["deterministic_result"], "AMBIGUOUS")
            self.assertFalse(decision["result_changed"])
            persisted = json.loads(
                (self.outdir / serve.SEMANTIC_REVIEWS_FILENAME).read_text()
            )
            self.assertEqual(persisted["candidate.pdf"]["human_decision"], "PASS")

            status, cached_payload = self.request(
                "/api/ai-verdict",
                payload={"filename": "candidate.pdf"},
                token=self.token,
            )
            self.assertEqual(status, 200)
            self.assertTrue(cached_payload["cached"])
            self.assertEqual(
                cached_payload["review"]["human_decision"],
                "PASS",
            )
            self.assertEqual(len(prompts), 1)

    def test_ai_verdict_rejects_unverifiable_ai_quote(self) -> None:
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "Review",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "Fabricated Kubernetes claim",
                        "explanation": "Unsupported",
                        "confidence": 99,
                    }
                ],
            }
        )
        with self.assertRaisesRegex(serve.KriterionError, "could not be verified"):
            serve.parse_ambiguity_verdict_response(
                raw,
                "Operated Azure Kubernetes Service clusters.",
            )

    def test_ai_verdict_anchors_typographic_variant_to_exact_cv_text(self) -> None:
        cv_text = "Technical Support Engineer                   Aug.2025 – Present"
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "The employment is current.",
                "evidence": [
                    {
                        "criterion": "employment date",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": (
                            "Technical Support Engineer Aug. 2025 - Present"
                        ),
                        "explanation": "The role started in August 2025.",
                        "confidence": 95,
                    }
                ],
            }
        )

        review = serve.parse_ambiguity_verdict_response(raw, cv_text)

        self.assertEqual(review["evidence"][0]["source_quote"], cv_text)

    def test_ai_verdict_rejects_substantively_different_date_quote(self) -> None:
        cv_text = "Technical Support Engineer Aug.2025 – Present"
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "The employment is current.",
                "evidence": [
                    {
                        "criterion": "employment date",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": (
                            "Technical Support Engineer Aug. 2024 - Present"
                        ),
                        "explanation": "The role started in August 2024.",
                        "confidence": 95,
                    }
                ],
            }
        )

        with self.assertRaisesRegex(serve.KriterionError, "Aug\\. 2024"):
            serve.parse_ambiguity_verdict_response(raw, cv_text)

    def test_ai_verdict_accepts_json_wrapped_in_copilot_commentary(self) -> None:
        raw = "\n".join(
            [
                "Here is the evidence-backed result:",
                "```json",
                json.dumps(
                    {
                        "ai_verdict": "PASS",
                        "summary": "AKS operation supports passing.",
                        "evidence": [
                            {
                                "criterion": "kubernetes",
                                "stance": "SUPPORTS_PASS",
                                "source_quote": (
                                    "Operated Azure Kubernetes Service clusters."
                                ),
                                "explanation": "This is managed Kubernetes usage.",
                                "confidence": 94,
                            }
                        ],
                    }
                ),
                "```",
                "The reviewer still makes the final decision.",
            ]
        )
        review = serve.parse_ambiguity_verdict_response(
            raw,
            "Operated Azure Kubernetes Service clusters.",
        )
        self.assertEqual(review["ai_verdict"], "PASS")
        self.assertEqual(review["evidence"][0]["confidence"], 94)

    def test_ai_verdict_automatically_retries_one_invalid_response(self) -> None:
        prompts: list[str] = []
        valid_response = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "AKS operation supports passing.",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": (
                            "Operated Azure Kubernetes Service clusters "
                            "for production workloads."
                        ),
                        "explanation": "This is managed Kubernetes usage.",
                        "confidence": 94,
                    }
                ],
            }
        )

        def fake_copilot(prompt: str, **_: object) -> str:
            prompts.append(prompt)
            return "not valid JSON" if len(prompts) == 1 else valid_response

        with patch("serve.run_copilot", side_effect=fake_copilot):
            status, payload = self.request(
                "/api/ai-verdict",
                payload={"filename": "candidate.pdf"},
                token=self.token,
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["review"]["ai_verdict"], "PASS")
        self.assertEqual(len(prompts), 2)
        self.assertIn("previous response could not be validated", prompts[1])

    def test_ai_fail_verdict_rejects_only_favorable_evidence(self) -> None:
        raw = json.dumps(
            {
                "ai_verdict": "FAIL",
                "summary": "Review",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "Operated Azure Kubernetes Service clusters.",
                        "explanation": "The quote supports passing.",
                        "confidence": 90,
                    }
                ],
            }
        )
        review = serve.parse_ambiguity_verdict_response(
            raw,
            "Operated Azure Kubernetes Service clusters.",
        )
        with self.assertRaisesRegex(serve.KriterionError, "did not cite evidence"):
            serve.KriterionHandler._validate_ambiguity_coverage(
                self.candidate,
                review,
                self.profile,
            )

    def test_ai_fail_verdict_accepts_mixed_verified_evidence(self) -> None:
        cv_text = (
            "Operated Azure Kubernetes Service clusters. "
            "No production ownership was described."
        )
        raw = json.dumps(
            {
                "ai_verdict": "FAIL",
                "summary": "AKS is relevant, but production ownership is unsupported.",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "Operated Azure Kubernetes Service clusters.",
                        "explanation": "AKS is a managed Kubernetes service.",
                        "confidence": 94,
                    },
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_FAIL",
                        "source_quote": "No production ownership was described.",
                        "explanation": "The required ownership remains unsupported.",
                        "confidence": 91,
                    },
                ],
            }
        )

        review = serve.parse_ambiguity_verdict_response(raw, cv_text)
        serve.KriterionHandler._validate_ambiguity_coverage(
            self.candidate,
            review,
            self.profile,
        )

        self.assertEqual(review["ai_verdict"], "FAIL")
        self.assertEqual(
            [item["stance"] for item in review["evidence"]],
            ["SUPPORTS_PASS", "SUPPORTS_FAIL"],
        )

    def test_ai_pass_verdict_rejects_unresolved_failing_evidence(self) -> None:
        cv_text = (
            "Operated Azure Kubernetes Service clusters. "
            "No production ownership was described."
        )
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "The candidate passes.",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "Operated Azure Kubernetes Service clusters.",
                        "explanation": "AKS is a managed Kubernetes service.",
                        "confidence": 94,
                    },
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_FAIL",
                        "source_quote": "No production ownership was described.",
                        "explanation": "The required ownership remains unsupported.",
                        "confidence": 91,
                    },
                ],
            }
        )

        review = serve.parse_ambiguity_verdict_response(raw, cv_text)
        with self.assertRaisesRegex(serve.KriterionError, "unresolved failing"):
            serve.KriterionHandler._validate_ambiguity_coverage(
                self.candidate,
                review,
                self.profile,
            )

    def test_ai_verdict_rejects_resolved_or_non_experience_criterion(self) -> None:
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "The candidate passes.",
                "evidence": [
                    {
                        "criterion": "aws",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "AWS Certified Cloud Practitioner",
                        "explanation": "The certificate shows AWS knowledge.",
                        "confidence": 90,
                    }
                ],
            }
        )
        review = serve.parse_ambiguity_verdict_response(
            raw,
            "AWS Certified Cloud Practitioner",
        )

        with self.assertRaisesRegex(serve.KriterionError, "out-of-scope"):
            serve.KriterionHandler._validate_ambiguity_coverage(
                self.candidate,
                review,
                self.profile,
            )

    def test_deterministic_missing_experience_forces_ai_fail(self) -> None:
        candidate = json.loads(json.dumps(self.candidate))
        candidate["required_evidence"]["aws"] = None
        candidate["required_evidence_details"]["aws"] = {
            "status": "NOT_FOUND",
            "needs_review": False,
        }
        raw = json.dumps(
            {
                "ai_verdict": "PASS",
                "summary": "The Kubernetes ambiguity resolves favorably.",
                "evidence": [
                    {
                        "criterion": "kubernetes",
                        "stance": "SUPPORTS_PASS",
                        "source_quote": "Operated Azure Kubernetes Service clusters.",
                        "explanation": "This demonstrates Kubernetes experience.",
                        "confidence": 92,
                    }
                ],
            }
        )
        review = serve.parse_ambiguity_verdict_response(
            raw,
            "Operated Azure Kubernetes Service clusters.",
        )

        with self.assertRaisesRegex(serve.KriterionError, "deterministic failures"):
            serve.KriterionHandler._validate_ambiguity_coverage(
                candidate,
                review,
                self.profile,
            )

    def test_unknown_candidate_and_extracted_route_are_rejected(self) -> None:
        status, _ = self.request(
            "/api/ai-verdict",
            payload={"filename": "../../profile.yaml"},
            token=self.token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.request("/extracted/candidate.pdf.txt")[0], 404)


if __name__ == "__main__":
    unittest.main()
