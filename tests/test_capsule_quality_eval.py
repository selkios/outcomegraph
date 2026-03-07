from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import og


STALE_DOC_CASES = [
    {
        "id": "materials-lock-migration-blocker",
        "description": "Quickstart and runbooks must carry accepted truth that the old materials.lock migration blocker is stale and resolved.",
        "capsule_ids": ["quickstart", "runbooks"],
        "required_terms": ["materials.lock", "migration blocker", "stale", "resolved"],
    }
]


class _ArtifactQualityRepoTestCase(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        self.timestamp = "2026-03-07T12:00:00Z"
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "OutcomeGraph Tester"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "tester@example.com"], check=True)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def git_root_patch(self):
        return patch.object(og, "_git_root", return_value=str(self.repo))

    def _write_artifact(self, relative_path: str, payload: dict[str, object]) -> None:
        og._write_canonical_artifact(str(self.repo), relative_path, payload)

    def _capsule_payload(
        self,
        capsule_id: str,
        *,
        scope: list[str],
        decision_refs: list[str],
        invariants: list[str] | None = None,
        oracles: list[dict[str, object]] | None = None,
        behavior_claims: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": 2,
            "artifact_type": "capsule",
            "id": capsule_id,
            "goal": f"Preserve the {capsule_id} repository capability.",
            "scope": scope,
            "behavior_claims": behavior_claims or [f"{capsule_id} retains the current repository contract."],
            "constraints": [],
            "invariants": invariants or [],
            "dependencies": scope,
            "oracles": oracles or [],
            "unknowns": ["This fixture keeps the graph small and does not model the entire repository."],
            "materials_lock_ref": ".outcomegraph/materials.lock",
            "decision_refs": decision_refs,
            "lineage": {},
            "status": "success",
            "created_at": self.timestamp,
            "updated_at": self.timestamp,
        }

    def _claim_payload(
        self,
        claim_id: str,
        capsule_id: str,
        text: str,
        *,
        receipt_backed: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 2,
            "artifact_type": "claim",
            "id": claim_id,
            "capsule_id": capsule_id,
            "text": text,
            "category": "behavior",
            "created_at": self.timestamp,
            "updated_at": self.timestamp,
            "receipt_pointers": [],
        }
        if receipt_backed:
            payload["receipt_pointers"] = [
                {
                    "schema_version": 2,
                    "type": "file",
                    "target": f".outcomegraph/traces/{claim_id}.ndjson",
                    "hash": "sha256:test",
                }
            ]
        return payload

    def _decision_payload(
        self,
        decision_id: str,
        capsule_id: str,
        claim_refs: list[str],
        statement: str,
        rationale: str,
    ) -> dict[str, object]:
        return {
            "schema_version": 2,
            "artifact_type": "decision",
            "id": decision_id,
            "capsule_id": capsule_id,
            "statement": statement,
            "rationale": rationale,
            "claim_refs": claim_refs,
            "status": "accepted",
            "evidence_refs": [],
            "created_at": self.timestamp,
            "updated_at": self.timestamp,
        }

    def _seed_repo_quality_graph(
        self,
        *,
        executable_code_oracle: bool = True,
        code_invariants: bool = True,
        receipt_backed_code_claim: bool = True,
        capture_stale_doc_truth: bool = True,
    ) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()

        code_oracle = {
            "name": "og-regression-suite",
            "command": "pytest -q tests/test_og_sync_verify_replay_hooks.py",
            "reason": "The repository keeps a concrete executable regression command for the CLI contract.",
            "scope": ["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
        }
        if not executable_code_oracle:
            code_oracle = {
                "name": "og-advisory-snapshot",
                "command": None,
                "reason": "No executable oracle was retained for this capsule.",
                "scope": ["og.py"],
            }

        self._write_artifact(
            ".outcomegraph/claims/cl-og-quality.json",
            self._claim_payload(
                "cl-og-quality",
                "og",
                "og preserves the stable CLI entrypoint and runtime-version contract.",
                receipt_backed=receipt_backed_code_claim,
            ),
        )
        self._write_artifact(
            ".outcomegraph/decisions/dec-og-quality.json",
            self._decision_payload(
                "dec-og-quality",
                "og",
                [".outcomegraph/claims/cl-og-quality.json"],
                "Treat the og CLI capsule as current accepted truth for command entrypoint behavior.",
                "The repo fixture keeps the CLI shim behavior, version lookup path, and command contract aligned.",
            ),
        )
        self._write_artifact(
            ".outcomegraph/capsules/og.json",
            self._capsule_payload(
                "og",
                scope=["og", "og.py"],
                decision_refs=[".outcomegraph/decisions/dec-og-quality.json"],
                invariants=["og must remain a thin executable shim into og.main."] if code_invariants else [],
                oracles=[code_oracle],
            ),
        )

        self._write_artifact(
            ".outcomegraph/claims/cl-tests-quality.json",
            self._claim_payload(
                "cl-tests-quality",
                "tests",
                "The pytest capsule protects fixture setup and sync/verify/replay regressions.",
            ),
        )
        self._write_artifact(
            ".outcomegraph/decisions/dec-tests-quality.json",
            self._decision_payload(
                "dec-tests-quality",
                "tests",
                [".outcomegraph/claims/cl-tests-quality.json"],
                "Keep the tests capsule as accepted truth for repository regression coverage.",
                "The repo fixture exposes a concrete pytest command for the test surface.",
            ),
        )
        self._write_artifact(
            ".outcomegraph/capsules/tests.json",
            self._capsule_payload(
                "tests",
                scope=["tests/test_og_sync_verify_replay_hooks.py"],
                decision_refs=[".outcomegraph/decisions/dec-tests-quality.json"],
                invariants=["Fixture repos must remain deterministic for sync and replay contract tests."],
                oracles=[
                    {
                        "name": "tests-regression-suite",
                        "command": "pytest -q tests/test_og_sync_verify_replay_hooks.py",
                        "reason": "The repository keeps a direct pytest oracle for the tests capsule.",
                        "scope": ["tests/test_og_sync_verify_replay_hooks.py"],
                    }
                ],
            ),
        )

        quickstart_decision_refs: list[str] = []
        if capture_stale_doc_truth:
            self._write_artifact(
                ".outcomegraph/claims/cl-quickstart-stale-doc.json",
                self._claim_payload(
                    "cl-quickstart-stale-doc",
                    "quickstart",
                    "Treat the old materials.lock migration blocker note as stale because the blocker is resolved.",
                ),
            )
            self._write_artifact(
                ".outcomegraph/decisions/dec-quickstart-stale-doc.json",
                self._decision_payload(
                    "dec-quickstart-stale-doc",
                    "quickstart",
                    [".outcomegraph/claims/cl-quickstart-stale-doc.json"],
                    "The materials.lock migration blocker mentioned in quickstart/runbooks is stale and not accepted truth.",
                    "materials.lock now carries the canonical artifact_type field, so the prior migration blocker is resolved.",
                ),
            )
            quickstart_decision_refs.append(".outcomegraph/decisions/dec-quickstart-stale-doc.json")

        self._write_artifact(
            ".outcomegraph/capsules/quickstart.json",
            self._capsule_payload(
                "quickstart",
                scope=["QUICKSTART.md"],
                decision_refs=quickstart_decision_refs,
                oracles=[
                    {
                        "name": "quickstart-doc-evidence",
                        "command": None,
                        "reason": "Documentation capsules can carry advisory-only evidence.",
                        "scope": ["QUICKSTART.md"],
                    }
                ],
            ),
        )
        self._write_artifact(
            ".outcomegraph/capsules/runbooks.json",
            self._capsule_payload(
                "runbooks",
                scope=["RUNBOOKS.md"],
                decision_refs=[],
                oracles=[
                    {
                        "name": "runbooks-doc-evidence",
                        "command": None,
                        "reason": "Documentation capsules can carry advisory-only evidence.",
                        "scope": ["RUNBOOKS.md"],
                    }
                ],
            ),
        )


class TestArtifactQualityEvaluation(_ArtifactQualityRepoTestCase):
    def test_evaluate_artifact_quality_passes_repo_like_graph(self) -> None:
        self._seed_repo_quality_graph()

        evaluation = og._evaluate_artifact_quality(str(self.repo), contradiction_cases=STALE_DOC_CASES)

        self.assertEqual(evaluation["status"], "pass")
        self.assertEqual(evaluation["capsule_counts"]["by_kind"]["code"], 1)
        self.assertEqual(evaluation["capsule_counts"]["by_kind"]["test"], 1)
        self.assertEqual(evaluation["capsule_counts"]["by_kind"]["doc"], 2)
        metrics = evaluation["metrics"]
        self.assertEqual(metrics["code_test_executable_oracle_coverage"]["ratio"], 1.0)
        self.assertEqual(metrics["code_invariant_coverage"]["ratio"], 1.0)
        self.assertEqual(metrics["code_receipt_backed_behavior_claim_coverage"]["ratio"], 1.0)
        self.assertEqual(metrics["success_code_advisory_only_rate"]["ratio"], 0.0)
        self.assertEqual(metrics["stale_doc_accepted_truth_capture"]["ratio"], 1.0)
        self.assertEqual(evaluation["failures"], [])

    def test_evaluate_artifact_quality_flags_missing_code_invariants(self) -> None:
        self._seed_repo_quality_graph(code_invariants=False)

        evaluation = og._evaluate_artifact_quality(str(self.repo), contradiction_cases=STALE_DOC_CASES)

        self.assertEqual(evaluation["status"], "fail")
        metric = evaluation["metrics"]["code_invariant_coverage"]
        self.assertEqual(metric["status"], "fail")
        self.assertEqual(metric["failing_items"], ["og"])
        self.assertIn("code_invariant_coverage", evaluation["failures"])

    def test_evaluate_artifact_quality_flags_advisory_only_success_code_capsule(self) -> None:
        self._seed_repo_quality_graph(executable_code_oracle=False)

        evaluation = og._evaluate_artifact_quality(str(self.repo), contradiction_cases=STALE_DOC_CASES)

        self.assertEqual(evaluation["status"], "fail")
        self.assertEqual(
            evaluation["metrics"]["code_test_executable_oracle_coverage"]["failing_items"],
            ["og"],
        )
        advisory_metric = evaluation["metrics"]["success_code_advisory_only_rate"]
        self.assertEqual(advisory_metric["status"], "fail")
        self.assertEqual(advisory_metric["failing_items"], ["og"])

    def test_evaluate_artifact_quality_flags_missing_receipt_backed_behavior_claims(self) -> None:
        self._seed_repo_quality_graph(receipt_backed_code_claim=False)

        evaluation = og._evaluate_artifact_quality(str(self.repo), contradiction_cases=STALE_DOC_CASES)

        self.assertEqual(evaluation["status"], "fail")
        metric = evaluation["metrics"]["code_receipt_backed_behavior_claim_coverage"]
        self.assertEqual(metric["status"], "fail")
        self.assertEqual(metric["failing_items"], ["og"])

    def test_evaluate_artifact_quality_flags_missing_stale_doc_truth_capture(self) -> None:
        self._seed_repo_quality_graph(capture_stale_doc_truth=False)

        evaluation = og._evaluate_artifact_quality(str(self.repo), contradiction_cases=STALE_DOC_CASES)

        self.assertEqual(evaluation["status"], "fail")
        metric = evaluation["metrics"]["stale_doc_accepted_truth_capture"]
        self.assertEqual(metric["status"], "fail")
        self.assertEqual(metric["failing_items"], ["materials-lock-migration-blocker"])
        self.assertEqual(
            evaluation["stale_doc_contradictions"][0]["missing_terms"],
            ["materials.lock", "migration blocker", "stale", "resolved"],
        )
