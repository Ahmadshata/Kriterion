import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
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
        self.assertIn("--session-id", command)
        self.assertNotIn("-s", command)
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
                json.dumps(
                    {
                        "type": "assistant.usage",
                        "data": {
                            "model": "gpt-test",
                            "inputTokens": 1200,
                            "outputTokens": 86,
                            "cacheReadTokens": 400,
                            "cacheWriteTokens": 20,
                            "aiCredits": 5.3,
                            "costUsd": 0.053,
                        },
                    }
                ),
                json.dumps({"type": "result", "data": {"status": "success"}}),
            ]
        )
        run.return_value.stderr = ""  # type: ignore[attr-defined]

        response = serve.run_copilot("synthetic prompt")
        self.assertEqual(json.loads(response), verdict)
        self.assertEqual(
            response.usage,
            {
                "available": True,
                "input_tokens": 1200,
                "output_tokens": 86,
                "cache_read_tokens": 400,
                "cache_write_tokens": 20,
                "total_tokens": 1286,
                "ai_calls": 1,
                "models": ["gpt-test"],
                "ai_credits": 5.3,
                "cost_usd": 0.053,
                "credit_source": "copilot_json.aiCredits",
                "credit_exact": True,
            },
        )

    def test_copilot_usage_aggregates_multiple_ai_calls(self) -> None:
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant.usage",
                        "data": {
                            "model": "gpt-test",
                            "inputTokens": 100,
                            "outputTokens": 20,
                            "aiCredits": 1.2,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant.usage",
                        "data": {
                            "model": "gpt-test",
                            "inputTokens": 80,
                            "outputTokens": 10,
                            "cacheReadTokens": 50,
                            "aiCredits": 0.8,
                        },
                    }
                ),
            ]
        )
        usage = serve._extract_copilot_usage(stdout)
        self.assertIsNotNone(usage)
        self.assertEqual(usage["input_tokens"], 180)  # type: ignore[index]
        self.assertEqual(usage["output_tokens"], 30)  # type: ignore[index]
        self.assertEqual(usage["total_tokens"], 210)  # type: ignore[index]
        self.assertEqual(usage["ai_calls"], 2)  # type: ignore[index]
        self.assertEqual(usage["ai_credits"], 2.0)  # type: ignore[index]

    def test_exact_session_nano_ai_units_are_reported_as_credits(self) -> None:
        billing = serve._extract_copilot_session_billing(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "session.usage_checkpoint",
                            "data": {"totalNanoAiu": 4_419_270_000},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "session.shutdown",
                            "data": {
                                "totalNanoAiu": 4_419_270_000,
                                "currentModel": "claude-sonnet-4.5",
                            },
                        }
                    ),
                ]
            )
        )

        self.assertIsNotNone(billing)
        self.assertEqual(billing["ai_credits"], 4.41927)  # type: ignore[index]
        self.assertEqual(  # type: ignore[index]
            billing["credit_source"],
            "copilot_session.totalNanoAiu",
        )

    def test_combined_usage_omits_partial_credit_totals(self) -> None:
        combined = serve._combine_token_usage(
            {
                "available": True,
                "input_tokens": 100,
                "output_tokens": 10,
                "ai_calls": 1,
                "models": ["gpt-test"],
                "ai_credits": 1.2,
            },
            {
                "available": True,
                "input_tokens": 50,
                "output_tokens": 5,
                "ai_calls": 1,
                "models": ["gpt-test"],
            },
        )

        self.assertNotIn("ai_credits", combined)

    @patch("serve.subprocess.run")
    @patch("serve.shutil.which", return_value="/usr/local/bin/copilot")
    def test_copilot_reads_exact_usage_from_otel_file_exporter(
        self,
        _which: object,
        run: object,
    ) -> None:
        def fake_run(*_: object, **kwargs: object) -> object:
            child_env = kwargs["env"]
            telemetry_path = Path(  # type: ignore[index]
                child_env["COPILOT_OTEL_FILE_EXPORTER_PATH"]  # type: ignore[index]
            )
            telemetry_path.write_text(
                json.dumps(
                    {
                        "name": "invoke_agent",
                        "attributes": {
                            "gen_ai.operation.name": "invoke_agent",
                            "gen_ai.request.model": "gpt-test",
                            "gen_ai.usage.input_tokens": 2300,
                            "gen_ai.usage.output_tokens": 140,
                            "gen_ai.usage.cache_read.input_tokens": 700,
                            "gen_ai.usage.cache_creation.input_tokens": 25,
                            "github.copilot.turn_count": 2,
                            "github.copilot.aiu": 100,
                            "github.copilot.cost": 0.053,
                            "server.address": "api.githubcopilot.com",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "type": "assistant.message",
                        "data": {"content": '{"status":"ok"}'},
                    }
                ),
                stderr="",
            )

        run.side_effect = fake_run  # type: ignore[attr-defined]
        response = serve.run_copilot("synthetic prompt")

        self.assertEqual(response, '{"status":"ok"}')
        self.assertEqual(response.usage["total_tokens"], 2440)  # type: ignore[index]
        self.assertEqual(response.usage["input_tokens"], 2300)  # type: ignore[index]
        self.assertEqual(response.usage["output_tokens"], 140)  # type: ignore[index]
        self.assertEqual(response.usage["cache_read_tokens"], 700)  # type: ignore[index]
        self.assertEqual(response.usage["ai_calls"], 2)  # type: ignore[index]
        self.assertEqual(response.usage["ai_credits"], 5.3)  # type: ignore[index]
        self.assertEqual(response.usage["cost_usd"], 0.053)  # type: ignore[index]

    def test_untrusted_legacy_credit_value_is_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outdir = Path(directory)
            (outdir / serve.SEMANTIC_REVIEWS_FILENAME).write_text(
                json.dumps(
                    {
                        "candidate.pdf": {
                            "token_usage": {
                                "available": True,
                                "ai_credits": 100,
                                "cost_usd": 1,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            sessions = serve.load_semantic_review_sessions(outdir)

        usage = sessions["candidate.pdf"]["semantic_review"]["token_usage"]
        self.assertNotIn("ai_credits", usage)
        self.assertNotIn("cost_usd", usage)

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
        (self.outdir / "tools").mkdir()
        (self.outdir / "tools" / "aws.png").write_bytes(b"test-png")
        (self.outdir / "tools" / "githubactions.png").write_bytes(
            b"github-actions-png"
        )
        (self.outdir / "GitHub-Copilot-Blink.gif").write_bytes(b"test-gif")
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

    def test_tool_icons_are_served_from_the_report_assets(self) -> None:
        with urllib.request.urlopen(
            self.base_url + "/tools/aws.png", timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(response.read(), b"test-png")
        with urllib.request.urlopen(
            self.base_url + "/tools/githubactions.png", timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(response.read(), b"github-actions-png")
        self.assertEqual(self.request("/tools/not-a-png.txt")[0], 403)

    def test_copilot_gif_is_served_from_the_report_assets(self) -> None:
        with urllib.request.urlopen(
            self.base_url + "/GitHub-Copilot-Blink.gif", timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/gif")
            self.assertEqual(response.read(), b"test-gif")

    def test_ai_verdict_uses_nested_result_and_requires_human_final_decision(
        self,
    ) -> None:
        prompts: list[str] = []

        def fake_copilot(prompt: str, **_: object) -> str:
            prompts.append(prompt)
            return serve.CopilotResponse(
                json.dumps({
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
                }),
                {
                    "available": True,
                    "input_tokens": 950,
                    "output_tokens": 75,
                    "cache_read_tokens": 100,
                    "cache_write_tokens": 0,
                    "total_tokens": 1025,
                    "ai_calls": 1,
                    "models": ["gpt-test"],
                    "ai_credits": 2.6,
                    "cost_usd": 0.026,
                },
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
            self.assertEqual(review["token_usage"]["total_tokens"], 1025)
            self.assertEqual(review["token_usage"]["attempts"], 1)
            self.assertEqual(review["token_usage"]["ai_credits"], 2.6)
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
            response = "not valid JSON" if len(prompts) == 1 else valid_response
            return serve.CopilotResponse(
                response,
                {
                    "available": True,
                    "input_tokens": 100 * len(prompts),
                    "output_tokens": 10 * len(prompts),
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "total_tokens": 110 * len(prompts),
                    "ai_calls": 1,
                    "models": ["gpt-test"],
                    "ai_credits": 1.25 * len(prompts),
                    "cost_usd": 0.0125 * len(prompts),
                },
            )

        with patch("serve.run_copilot", side_effect=fake_copilot):
            status, payload = self.request(
                "/api/ai-verdict",
                payload={"filename": "candidate.pdf"},
                token=self.token,
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["review"]["ai_verdict"], "PASS")
        self.assertEqual(payload["review"]["token_usage"]["input_tokens"], 300)
        self.assertEqual(payload["review"]["token_usage"]["output_tokens"], 30)
        self.assertEqual(payload["review"]["token_usage"]["total_tokens"], 330)
        self.assertEqual(payload["review"]["token_usage"]["attempts"], 2)
        self.assertEqual(payload["review"]["token_usage"]["ai_credits"], 3.75)
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

    def test_layout_ambiguity_is_sent_to_ai_as_a_verified_target(self) -> None:
        candidate = json.loads(json.dumps(self.candidate))
        candidate["semantic_ambiguity"] = False
        candidate["layout_ambiguity"] = True
        candidate["required_evidence"]["kubernetes"] = [
            1,
            "Operated Azure Kubernetes Service clusters.",
        ]
        candidate["required_evidence_details"] = {}
        candidate["ambiguity_reasons"] = [
            "Multi-column CV extraction produced an unreliable experience reading order"
        ]
        cv_text = (
            "DevOps Engineer\nAug 2023 - Present\nTeacher Assistant\n"
            "Alexandria University\nEventum Solutions"
        )
        raw = json.dumps(
            {
                "ai_verdict": "FAIL",
                "summary": "The crossed columns prevent a reliable employment timeline.",
                "evidence": [
                    {
                        "criterion": "CV extraction layout",
                        "stance": "SUPPORTS_FAIL",
                        "source_quote": "DevOps Engineer\nAug 2023 - Present\nTeacher Assistant",
                        "explanation": "Two role titles are interleaved around one date.",
                        "confidence": 98,
                    }
                ],
            }
        )

        review = serve.parse_ambiguity_verdict_response(raw, cv_text)
        serve.KriterionHandler._validate_ambiguity_coverage(
            candidate,
            review,
            self.profile,
        )
        prompt = serve.build_ambiguity_verdict_prompt(
            candidate,
            cv_text,
            self.profile,
        )

        self.assertIn('"layout_ambiguity": true', prompt)
        self.assertIn("crossed columns", prompt)

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
