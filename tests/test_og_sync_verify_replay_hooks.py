from __future__ import annotations

import io
import json
import os
import signal
import sys
import tomllib
from contextlib import contextmanager, redirect_stdout
import subprocess
import tempfile
import warnings
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import og


class _RepoTestCase(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "OutcomeGraph Tester"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "tester@example.com"], check=True)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    @contextmanager
    def git_root_patch(self):
        with patch.object(og, "_git_root", return_value=str(self.repo)), patch.object(
            og, "_maybe_git_root", return_value=str(self.repo)
        ):
            yield

    def _git_completed(self, returncode: int, stdout: str = "", stderr: str = ""):
        return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)

    def _write_quality_pass_script(self, exit_code: int) -> Path:
        script_path = self.repo / og.AUTOPILOT_PRE_COMMIT_QUALITY_PASS
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "REPO_ROOT=\"$1\"\n"
                "mkdir -p \"$REPO_ROOT/.outcomegraph/work\"\n"
                "printf '%s\\n' \"quality-pass\" > \"$REPO_ROOT/.outcomegraph/work/quality-pass-ran\"\n"
                f"exit {exit_code}\n"
            ),
            encoding="utf-8",
        )
        script_path.chmod(0o755)
        return script_path


def _distill_update(capsule_id: str, changed_files: list[str], *, status: str = "success") -> dict[str, object]:
    scope = changed_files or [capsule_id]
    return {
        "id": capsule_id,
        "capsule_id": capsule_id,
        "status": status,
        "goal": f"Preserve and replay the {capsule_id} capability.",
        "scope": scope,
        "behavior_claims": [
            f"{capsule_id} preserves the observed behavior within the recorded capsule boundary.",
        ],
        "constraints": [],
        "invariants": [
            f"{capsule_id} must keep its current contract stable for the recorded scope.",
        ],
        "dependencies": scope,
        "oracles": [
            {
                "name": f"{capsule_id}-verify",
                "command": None,
                "reason": "This fixture does not provide an executable oracle command.",
                "scope": scope,
            }
        ],
        "claims": [
            {
                "id": None,
                "capsule_id": capsule_id,
                "category": "behavior",
                "text": f"{capsule_id} remains consistent with the observed repository state.",
                "receipt_pointers": [],
                "source_paths": scope,
            }
        ],
        "decision": {
            "statement": f"Track the current {capsule_id} behavior as a capsule.",
            "rationale": "The changed files indicate this capsule should remain part of the canonical graph.",
            "status": "accepted",
        },
        "lineage": {"parent_capsule_ids": []},
        "unknowns": [
            "Bounded fixture input may omit additional unchanged collaborators outside the recorded scope.",
        ],
        "errors": [],
        "receipts": [],
        "changed_files": changed_files,
    }


def _write_replayable_capsule_fixture(
    repo: Path,
    *,
    capsule_id: str = "default",
    source_path: str = "capsules/default.yaml",
    oracle_command: str | None = "python -c \"print('ok')\"",
    oracle_name: str | None = None,
    capsule_kind: str | None = None,
) -> dict[str, object]:
    source_file = repo / source_path
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("kind: replay-fixture\n", encoding="utf-8")
    digest = og._file_sha256(source_path, str(repo))
    if digest is None:
        raise AssertionError(f"expected digest for {source_path}")

    material_input = {
        "path": source_path,
        "digest": digest,
        "kind": "file",
        "size": source_file.stat().st_size,
    }
    resolved_oracle_name = oracle_name or f"{capsule_id}-acceptance"
    oracle_payload: dict[str, object] = {
        "name": resolved_oracle_name,
        "command": oracle_command,
        "scope": [source_path],
    }
    if oracle_command is None:
        oracle_payload["reason"] = "This fixture intentionally omits an executable replay oracle."

    capsule_payload = {
        "schema_version": 2,
        "artifact_type": "capsule",
        "id": capsule_id,
        "status": "active",
        "scope": [source_path],
        "oracles": [oracle_payload],
        "created_at": "2026-03-05T00:00:00Z",
        "updated_at": "2026-03-05T00:00:00Z",
    }
    if capsule_kind is not None:
        capsule_payload["kind"] = capsule_kind

    og_root = repo / og.OG_ROOT
    (og_root / "capsules").mkdir(parents=True, exist_ok=True)
    (og_root / "capsules" / f"{capsule_id}.json").write_text(
        json.dumps(capsule_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    og_root.mkdir(parents=True, exist_ok=True)
    (og_root / "materials.lock").write_text(
        json.dumps(
            og._build_materials_lock_payload(
                "2026-03-05T00:00:00Z",
                [material_input],
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "capsule_payload": capsule_payload,
        "scope_materials": [material_input],
        "oracles": [oracle_payload],
        "source_path": source_path,
        "digest": digest,
    }


def _build_replay_plan_fixture(
    run_id: str,
    fixture: dict[str, object],
    *,
    status: str = "ok",
    steps: list[dict[str, object]] | None = None,
    failures: list[str] | None = None,
    message: str = "",
    baseline_hash: str | None = None,
    prompt_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    scope_materials = [dict(item) for item in fixture["scope_materials"] if isinstance(item, dict)]
    oracle_payload = next(iter([item for item in fixture["oracles"] if isinstance(item, dict)]), {})
    oracle_name = str(oracle_payload.get("name") or "").strip()
    oracle_command = str(oracle_payload.get("command") or "").strip()
    material_paths = [str(item.get("path") or "") for item in scope_materials if str(item.get("path") or "")]
    acceptance_checks = []
    if oracle_name and oracle_command:
        acceptance_checks.append(
            {
                "name": oracle_name,
                "oracle_name": oracle_name,
                "command": oracle_command,
                "expected_signal": "exit_code=0",
                "reason": None,
            }
        )

    plan = {
        "schema_version": 2,
        "interface_version": 1,
        "run_id": run_id,
        "capsule_id": str(fixture["capsule_payload"].get("id") or "default"),
        "capsule_scope": list(fixture["capsule_payload"].get("scope") or []),
        "material_inputs": scope_materials,
        "steps": steps or [{"command": "echo ok", "cwd": ".", "expected_exit_code": 0, "timeout_s": None}],
        "acceptance_checks": acceptance_checks,
        "equivalence_inputs": {
            "baseline_hash": baseline_hash,
            "oracle_names": [oracle_name] if oracle_name and oracle_command else [],
            "material_paths": material_paths,
            "notes": ["Replay proof uses the recorded capsule oracle and scoped materials."],
        },
        "status": status,
        "message": message,
        "failures": failures or [],
        "parity_results": {
            "match": None,
            "details": None,
            "baseline_hash": baseline_hash,
            "observed_hash": None,
            "oracle_digest": None,
            "trace_count": None,
        },
    }
    if prompt_provenance is not None:
        plan["prompt_provenance"] = prompt_provenance
    return plan


class TestDistillSnapshotSelection(_RepoTestCase):
    def test_read_repo_file_snapshot_uses_diff_hunks_for_large_changed_python_file(self) -> None:
        file_path = self.repo / "tests" / "large_case.py"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        original_lines = [f"line_{index:04d} = '{'x' * 40}'\n" for index in range(1, 1401)]
        file_path.write_text("".join(original_lines), encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "tests/large_case.py"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        baseline = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        updated_lines = list(original_lines)
        updated_lines[1199] = "SPECIAL_LATE_TOKEN = 'diff-visible'\n"
        file_path.write_text("".join(updated_lines), encoding="utf-8")

        snapshot = og._read_repo_file_snapshot(
            str(self.repo),
            "tests/large_case.py",
            diff_baseline=baseline,
        )

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["selection"], "diff_hunks")
        self.assertTrue(snapshot["partial"])
        self.assertIn("SPECIAL_LATE_TOKEN", snapshot["content"])
        self.assertFalse(snapshot["truncated"])

    def test_build_distill_target_capsules_includes_supporting_scope_snapshots(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            runtime_payload = og._build_capsule_payload(
                "runtime",
                [".gitignore", ".outcomegraph/.gitignore"],
                [],
                None,
                og._utc_timestamp(),
                goal="Track runtime ignore rules.",
                scope=[".gitignore", ".outcomegraph/.gitignore"],
                constraints=[],
                oracles=[{"name": "runtime-verify", "command": None, "scope": [".gitignore", ".outcomegraph/.gitignore"]}],
                status="success",
            )
            (self.repo / ".outcomegraph" / "capsules" / "runtime.json").write_text(
                json.dumps(runtime_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            targets = og._build_distill_target_capsules(
                str(self.repo),
                ["runtime"],
                {"runtime": [".gitignore"]},
            )

        supporting = targets[0]["supporting_file_snapshots"]
        self.assertEqual(targets[0]["changed_files"], [".gitignore"])
        self.assertEqual(targets[0]["kind"], "runtime")
        self.assertEqual(targets[0]["existing_capsule"]["kind"], "runtime")
        self.assertTrue(any(snapshot["path"] == ".outcomegraph/.gitignore" for snapshot in supporting))

    def test_build_distill_target_capsules_exposes_changed_region_context(self) -> None:
        file_path = self.repo / "tests" / "large_case.py"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        original_lines = [f"line_{index:04d} = '{'x' * 40}'\n" for index in range(1, 1401)]
        file_path.write_text("".join(original_lines), encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "tests/large_case.py"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        baseline = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        updated_lines = list(original_lines)
        updated_lines[1199] = "SPECIAL_LATE_TOKEN = 'diff-visible'\n"
        file_path.write_text("".join(updated_lines), encoding="utf-8")

        targets = og._build_distill_target_capsules(
            str(self.repo),
            ["tests"],
            {"tests": ["tests/large_case.py"]},
            diff_baseline=baseline,
        )

        region = targets[0]["changed_region_context"][0]
        self.assertEqual(region["path"], "tests/large_case.py")
        self.assertEqual(region["selection"], "diff_hunks")
        self.assertTrue(region["partial"])
        self.assertTrue(any(item["start_line"] <= 1200 <= item["end_line"] for item in region["snippets"]))

    def test_build_distill_target_capsules_discovers_related_test_support_for_code_change(self) -> None:
        source_path = self.repo / "src" / "widget.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("def build_widget() -> str:\n    return 'ok'\n", encoding="utf-8")
        test_path = self.repo / "tests" / "test_widget.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(
            "from src.widget import build_widget\n\n\ndef test_build_widget() -> None:\n    assert build_widget() == 'ok'\n",
            encoding="utf-8",
        )

        targets = og._build_distill_target_capsules(
            str(self.repo),
            ["widget"],
            {"widget": ["src/widget.py"]},
        )

        self.assertIn("tests/test_widget.py", targets[0]["supporting_scope_paths"])
        self.assertTrue(any(snapshot["path"] == "tests/test_widget.py" for snapshot in targets[0]["supporting_file_snapshots"]))
        self.assertIn(
            {"path": "tests/test_widget.py", "reason": "discovered from changed-file feature tokens"},
            targets[0]["related_test_hints"],
        )

    def test_build_distill_target_capsules_skips_nested_test_cache_support(self) -> None:
        source_path = self.repo / "src" / "widget.py"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("def build_widget() -> str:\n    return 'ok'\n", encoding="utf-8")
        test_path = self.repo / "tests" / "test_widget.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(
            "from src.widget import build_widget\n\n\ndef test_build_widget() -> None:\n    assert build_widget() == 'ok'\n",
            encoding="utf-8",
        )
        pycache_path = self.repo / "tests" / "__pycache__" / "test_widget.cpython-314.pyc"
        pycache_path.parent.mkdir(parents=True, exist_ok=True)
        pycache_path.write_text("compiled", encoding="utf-8")

        targets = og._build_distill_target_capsules(
            str(self.repo),
            ["widget"],
            {"widget": ["src/widget.py"]},
        )

        self.assertNotIn("tests/__pycache__/test_widget.cpython-314.pyc", targets[0]["supporting_scope_paths"])
        self.assertEqual(
            targets[0]["related_test_hints"],
            [{"path": "tests/test_widget.py", "reason": "discovered from changed-file feature tokens"}],
        )

    def test_build_distill_target_capsules_adds_existing_capsule_material_and_oracle_context(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            source_path = self.repo / "src" / "feature.py"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("def feature_flag() -> str:\n    return 'enabled'\n", encoding="utf-8")
            test_path = self.repo / "tests" / "test_feature.py"
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(
                "from src.feature import feature_flag\n\n\ndef test_feature_flag() -> None:\n    assert feature_flag() == 'enabled'\n",
                encoding="utf-8",
            )

            capsule_payload = og._build_capsule_payload(
                "feature",
                ["src/feature.py"],
                [],
                None,
                og._utc_timestamp(),
                goal="Preserve the feature flag behavior.",
                scope=["src/feature.py", "tests/test_feature.py"],
                constraints=["Keep the public return value stable."],
                oracles=[
                    {
                        "name": "feature-tests",
                        "command": "pytest -q tests/test_feature.py",
                        "scope": ["src/feature.py", "tests/test_feature.py"],
                    }
                ],
                status="success",
            )
            (self.repo / ".outcomegraph" / "capsules" / "feature.json").write_text(
                json.dumps(capsule_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            claim_path = f"{og.OG_ROOT}/claims/cl-feature.json"
            claim_payload = og._build_claim_payload(
                "cl-feature",
                "feature",
                "run-1",
                "analyze",
                "observe",
                ["src/feature.py"],
                [],
                text="Feature flag remains enabled for the stable path.",
            )
            (self.repo / claim_path).write_text(json.dumps(claim_payload, indent=2, sort_keys=True), encoding="utf-8")

            decision_path = f"{og.OG_ROOT}/decisions/dec-feature.json"
            decision_payload = og._build_decision_payload(
                "dec-feature",
                "feature",
                [claim_path],
                [],
                None,
                statement="Retain the feature capsule as the replay contract.",
                rationale="The feature still uses the same source and test boundary.",
                status="accepted",
            )
            (self.repo / decision_path).write_text(json.dumps(decision_payload, indent=2, sort_keys=True), encoding="utf-8")

            certificate_path = f"{og.OG_ROOT}/certificates/cert-feature.json"
            certificate_payload = og._build_certificate_payload(
                "cert-feature",
                "feature",
                "run-1",
                [claim_path],
                "analyze",
                "observe",
                [],
                status="success",
            )
            (self.repo / certificate_path).write_text(
                json.dumps(certificate_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            materials_payload = og._build_materials_lock_payload(
                og._utc_timestamp(),
                [
                    {"path": "src/feature.py", "digest": og._file_sha256("src/feature.py", str(self.repo)), "kind": "file"},
                    {"path": "tests/test_feature.py", "digest": og._file_sha256("tests/test_feature.py", str(self.repo)), "kind": "file"},
                ],
            )
            (self.repo / og.OG_ROOT / "materials.lock").write_text(
                json.dumps(materials_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        changed_materials = [{"path": "src/feature.py", "digest": og._file_sha256("src/feature.py", str(self.repo))}]
        targets = og._build_distill_target_capsules(
            str(self.repo),
            ["feature"],
            {"feature": ["src/feature.py"]},
            changed_materials=changed_materials,
        )

        summary = targets[0]["existing_capsule_summary"]
        self.assertEqual(summary["claim_highlights"][0]["id"], "cl-feature")
        self.assertEqual(summary["decision_highlights"][0]["id"], "dec-feature")
        self.assertIn(f"{og.OG_ROOT}/certificates/cert-feature.json", summary["successful_certificate_refs"])
        self.assertTrue(any(hint["name"] == "feature-tests" for hint in targets[0]["related_oracle_hints"]))
        self.assertEqual(targets[0]["materials_context"]["changed_material_count"], 1)
        self.assertEqual(targets[0]["materials_context"]["scope_material_count"], 2)
        self.assertTrue(any(item["path"] == "tests/test_feature.py" for item in targets[0]["materials_context"]["scope_materials"]))

    def test_read_repo_file_snapshot_keeps_moderate_docs_and_lockfiles_complete(self) -> None:
        spec_path = self.repo / "SPEC-v2.md"
        lock_path = self.repo / "uv.lock"
        spec_path.write_text("spec-section\n" * 2500, encoding="utf-8")
        lock_path.write_text("package = 'demo'\n" * 2400, encoding="utf-8")

        spec_snapshot = og._read_repo_file_snapshot(str(self.repo), "SPEC-v2.md")
        lock_snapshot = og._read_repo_file_snapshot(str(self.repo), "uv.lock")

        self.assertFalse(spec_snapshot["truncated"])
        self.assertFalse(lock_snapshot["truncated"])


class TestHelpContracts(TestCase):
    def _run_main(self, args: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            try:
                code = og.main(args)
            except SystemExit as exc:
                code = int(exc.code) if isinstance(exc.code, int) else og.EXIT_RUNTIME
        return code, buffer.getvalue()

    def test_top_level_help_includes_global_contract(self) -> None:
        code, text = self._run_main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage: og [--json] [--strict] [--non-interactive] [--profile analyze|propose|apply] [--mode observe|autonomous] <command>", text)
        self.assertIn("--non-interactive", text)
        self.assertIn("Use: og <command> --help for command-specific contracts.", text)
        self.assertIn("Core commands:", text)

    def test_main_accepts_global_strict_flag(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["--strict", "--json", "schema"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "schema")
        self.assertEqual(payload["status"], "ok")

    def test_command_specific_help_contracts_are_rendered(self) -> None:
        test_cases = [
            (["init", "--help"], "Usage: og init"),
            (["sync", "--help"], "Usage: og sync"),
            (["verify", "--help"], "Usage: og verify"),
            (["replay", "--help"], "Usage: og replay"),
            (["status", "--help"], "Usage: og status"),
            (["doctor", "--help"], "Usage: og doctor"),
            (["export", "--help"], "Usage: og export"),
            (["clean", "--help"], "Usage: og clean"),
            (["explain", "--help"], "Usage: og explain"),
            (["drift", "--help"], "Usage: og drift"),
            (["mcp-server", "--help"], "Usage: og mcp-server"),
            (["optimize", "--help"], "Usage: og optimize"),
            (["optimize", "prompts", "--help"], "Usage: og optimize prompts"),
            (["autopilot", "--help"], "Usage: og autopilot"),
            (["autopilot", "init", "--help"], "Usage: og autopilot init"),
            (["autopilot", "disable", "--help"], "Usage: og autopilot disable"),
            (["daemon", "--help"], "Usage: og daemon"),
            (["daemon", "install", "--help"], "Usage: og daemon install"),
            (["daemon", "start", "--help"], "Usage: og daemon start"),
            (["daemon", "stop", "--help"], "Usage: og daemon stop"),
            (["daemon", "status", "--help"], "Usage: og daemon status"),
            (["daemon", "run", "--help"], "Usage: og daemon run"),
            (["schema", "--help"], "Usage: og schema"),
            (["describe", "--help"], "Usage: og describe"),
        ]

        for args, expected_usage in test_cases:
            code, text = self._run_main(args)
            self.assertEqual(code, 0, msg=f"help command failed for {args}")
            self.assertIn(expected_usage, text, msg=f"missing usage block for {args}")
            self.assertIn("Accepted options:", text, msg=f"missing options block for {args}")
            self.assertIn("Output modes:", text, msg=f"missing output modes block for {args}")
            self.assertIn("Exit codes:", text, msg=f"missing exit codes block for {args}")


class TestCommandIntrospectionContracts(TestCase):
    def test_schema_command_documents_cli_signatures(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["--json", "schema"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "schema")
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("subcommand", payload)
        data = payload["data"]
        self.assertEqual(data["schema_version"], og.COMMAND_INTROSPECTION_SCHEMA_VERSION)
        self.assertEqual(data["command_count"], len(data["commands"]))
        signatures = {entry["command"]: entry for entry in data["commands"]}
        for command_name in {"schema", "describe", "sync", "doctor", "daemon status", "optimize prompts", "verify", "replay", "explain", "mcp-server"}:
            self.assertIn(command_name, signatures, msg=f"missing signature for {command_name}")
            signature = signatures[command_name]
            self.assertIn("usage", signature)
            self.assertIn("request", signature)
            self.assertIn("response", signature)
            self.assertIn("known_error_codes", signature)
            self.assertIn("envelope_schema_version", signature["response"])
            request_field_names = {field["name"] for field in signature["request"]["fields"] if isinstance(field, dict)}
            if command_name == "optimize prompts":
                self.assertIn("--params", request_field_names)
                self.assertIn("--strict", request_field_names)
            if command_name == "doctor":
                response_field_names = {field["name"] for field in signature["response"]["data_fields"] if isinstance(field, dict)}
                self.assertIn("checks", response_field_names)
                self.assertIn("agent_reliability", response_field_names)
            if command_name == "status":
                response_field_names = {field["name"] for field in signature["response"]["data_fields"] if isinstance(field, dict)}
                self.assertIn("agent_reliability", response_field_names)
            if command_name in {"verify", "replay", "explain", "mcp-server"}:
                response_field_names = {field["name"] for field in signature["response"]["data_fields"] if isinstance(field, dict)}
                for flag_name in {"--output", "--fields", "--limit", "--offset"}:
                    self.assertIn(flag_name, request_field_names, msg=f"missing request field {flag_name} for {command_name}")
                self.assertIn("list_window", response_field_names, msg=f"missing list_window response field for {command_name}")
            if command_name in {"sync", "verify", "replay"}:
                for flag_name in {"--validate", "--dry-run", "--max-retries", "--timeout"}:
                    self.assertIn(flag_name, request_field_names, msg=f"missing request field {flag_name} for {command_name}")
            if command_name == "export":
                for flag_name in {"--validate", "--dry-run"}:
                    self.assertIn(flag_name, request_field_names)
            self.assertIn("--non-interactive", request_field_names)

        autopilot_init_signature = signatures["autopilot init"]
        autopilot_init_fields = {
            field["name"] for field in autopilot_init_signature["request"]["fields"] if isinstance(field, dict)
        }
        self.assertIn("--yes", autopilot_init_fields)
        autopilot_disable_signature = signatures["autopilot disable"]
        autopilot_disable_request_fields = {
            field["name"] for field in autopilot_disable_signature["request"]["fields"] if isinstance(field, dict)
        }
        self.assertIn("--session-id", autopilot_disable_request_fields)
        self.assertIn(og.SESSION_RESUME_INVALID_CODE, autopilot_disable_signature["known_error_codes"])
        daemon_status_signature = signatures["daemon status"]
        daemon_status_request_fields = {
            field["name"] for field in daemon_status_signature["request"]["fields"] if isinstance(field, dict)
        }
        daemon_status_response_fields = {
            field["name"] for field in daemon_status_signature["response"]["data_fields"] if isinstance(field, dict)
        }
        self.assertIn("--session-id", daemon_status_request_fields)
        self.assertIn("session_id", daemon_status_response_fields)
        sync_signature = signatures["sync"]
        sync_response_fields = {
            field["name"] for field in sync_signature["response"]["data_fields"] if isinstance(field, dict)
        }
        self.assertIn("session_id", sync_response_fields)
        self.assertIn(og.SESSION_CONTENDED_CODE, sync_signature["known_error_codes"])

    def test_schema_command_renders_human_summary(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["schema"])

        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("OutcomeGraph CLI schema v1", text)
        self.assertIn("Commands:", text)
        self.assertIn("og describe <command>", text)

    def test_describe_command_resolves_signature(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["--json", "describe", "daemon", "status"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "describe")
        data = payload["data"]
        self.assertEqual(data["requested_command"], "daemon status")
        signature = data["signature"]
        self.assertEqual(signature["command"], "daemon status")
        self.assertIn("response", signature)
        self.assertIn("request", signature)

    def test_describe_command_renders_human_signature(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["describe", "schema"])

        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("Command: schema", text)
        self.assertIn("Usage: og schema", text)
        self.assertIn("Response fields:", text)

    def test_describe_requires_known_command(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as context:
                og.main(["--json", "describe", "does-not-exist"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(context.exception.code, 64)
        self.assertEqual(payload["command"], "describe")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["error_code"], og.USAGE_ERROR_CODE)


class TestControlSurfaceContracts(_RepoTestCase):
    def test_mcp_tools_embed_shared_cli_signatures(self) -> None:
        schema_buffer = io.StringIO()
        mcp_buffer = io.StringIO()

        with self.git_root_patch():
            og._init_outcomegraph()
            with redirect_stdout(schema_buffer):
                schema_code = og.main(["--json", "schema"])
            with redirect_stdout(mcp_buffer):
                mcp_code = og.main(["--json", "mcp-server"])

        self.assertEqual(schema_code, 0)
        self.assertEqual(mcp_code, 0)

        schema_payload = json.loads(schema_buffer.getvalue())
        mcp_payload = json.loads(mcp_buffer.getvalue())

        expected_tools = {
            entry["command"]: entry
            for entry in schema_payload["data"]["commands"]
            if entry.get("mcp_tool") is True
        }
        observed_tools = {entry["name"]: entry for entry in mcp_payload["data"]["tools"]}

        self.assertEqual(sorted(observed_tools), sorted(expected_tools))
        for name, signature in expected_tools.items():
            tool = observed_tools[name]
            self.assertEqual(tool["description"], signature["summary"])
            self.assertEqual(tool["uri"], signature["mcp_uri"])
            self.assertEqual(tool["signature"], signature)


class TestRecoveryContracts(_RepoTestCase):
    def test_doctor_command_reports_machine_readable_checks(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", "doctor"])
        payload = json.loads(buffer.getvalue())

        self.assertIn(code, {0, 1})
        self.assertEqual(payload["command"], "doctor")
        self.assertIn(payload["status"], {"ok", "warn", "error"})
        data = payload["data"]
        self.assertIn("checks", data)
        self.assertTrue(any(check["name"] == "runtime" for check in data["checks"]))
        self.assertTrue(any(check["name"] == "agent_reliability" for check in data["checks"]))
        self.assertIn("agent_reliability", data)
        self.assertIn("agent_reliability", payload["metrics"])

    def test_sync_dry_run_reports_plan_without_writing_events(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", "sync", "--dry-run"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "sync")
        data = payload["data"]
        self.assertTrue(data["dry_run"])
        self.assertIn("plan", data)
        self.assertFalse(any((self.repo / ".outcomegraph" / "events").iterdir()))


class TestJsonEnvelopeContract(TestCase):
    def test_json_version_contract_for_command(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(["--json", "--version"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "version")
        self.assertEqual(payload["status"], "ok")
        self.assertIsInstance(payload["data"], dict)
        self.assertIn("version", payload["data"])

    def test_env_default_json_applies_to_version_output(self) -> None:
        buffer = io.StringIO()
        with patch.object(og, "_maybe_git_root", return_value=None), patch.dict(
            os.environ,
            {og.DEFAULT_OUTPUT_ENV: og.OUTPUT_MODE_JSON},
            clear=False,
        ), redirect_stdout(buffer):
            code = og.main(["--version"])
        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "version")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["version"], og.VERSION)

    def test_runtime_version_matches_project_metadata(self) -> None:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            payload = tomllib.load(handle)

        self.assertEqual(og.VERSION, payload["project"]["version"])

    def test_json_errors_are_enveloped(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as context:
                og.main(["--json", "--this-flag-does-not-exist"])
        self.assertEqual(context.exception.code, 64)
        payload = json.loads(buffer.getvalue())

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], "og")
        self.assertEqual(payload["status"], "error")
        self.assertGreater(len(payload["errors"]), 0)
        first_error = payload["errors"][0]
        self.assertEqual(first_error.get("error_code"), og.USAGE_ERROR_CODE)
        self.assertIn("unknown global option", first_error.get("message", ""))
        self.assertEqual(first_error.get("error_class"), og.ERROR_CLASS_USAGE)
        self.assertFalse(first_error.get("retryable"))

    def test_envelope_validation_falls_back_to_runtime_error_payload(self) -> None:
        envelope = og._validate_command_result_envelope(
            {
                "schema_version": "not-an-integer",
                "command": "schema",
                "status": "ok",
                "run_id": None,
                "data": {},
                "errors": [],
                "warnings": [],
                "metrics": {},
            }
        )

        self.assertEqual(envelope["schema_version"], og.COMMAND_RESULT_SCHEMA_VERSION)
        self.assertEqual(envelope["command"], "schema")
        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["errors"][0]["error_code"], og.RUNTIME_ERROR_CODE)
        data = envelope["data"]
        self.assertIsInstance(data, dict)
        self.assertIn("command envelope validation failed", str(data.get("message", "")))
        self.assertGreater(len(data.get("validation_errors", [])), 0)

    def test_envelope_validation_rejects_invalid_status_values(self) -> None:
        envelope = og._validate_command_result_envelope(
            {
                "schema_version": og.COMMAND_RESULT_SCHEMA_VERSION,
                "command": "schema",
                "status": "running",
                "run_id": None,
                "data": {},
                "errors": [],
                "warnings": [],
                "metrics": {},
            }
        )

        self.assertEqual(envelope["status"], "error")
        data = envelope["data"]
        self.assertIsInstance(data, dict)
        validation_errors = data.get("validation_errors", [])
        self.assertGreater(len(validation_errors), 0)
        self.assertIn("status must be one of", str(validation_errors[0]))

    def test_envelope_uses_session_id_from_session_payload(self) -> None:
        envelope = og._build_command_result_envelope(
            "daemon",
            {
                "status": "ok",
                "command": "daemon",
                "session": og._build_session_record(
                    og.SESSION_KIND_DAEMON,
                    og.SESSION_LIFECYCLE_RESUMABLE,
                    og.SESSION_STATE_INSTALLED,
                    session_id="daemon-20260307t000000z-abcdef1234",
                ),
            },
        )

        self.assertEqual(envelope["session_id"], "daemon-20260307t000000z-abcdef1234")


class TestAgentReliabilityMetrics(_RepoTestCase):
    def test_status_command_emits_agent_reliability_snapshot(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", "status"])

        self.assertEqual(code, og.EXIT_SUCCESS)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["command"], "status")
        snapshot = payload["metrics"]["agent_reliability"]["snapshot"]
        self.assertEqual(snapshot["totals"]["commands"], 1)
        self.assertEqual(snapshot["totals"]["schema_valid_outputs"], 1)
        self.assertEqual(snapshot["schema_valid_output_rate"]["value"], 1.0)
        self.assertEqual(payload["data"]["agent_reliability"]["totals"]["commands"], 1)

    def test_record_sync_summary_event_includes_projected_agent_reliability(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            summary_path = og._record_sync_summary_event(
                str(self.repo),
                {
                    "status": "ok",
                    "command": "sync",
                    "run_id": "sync-20260307T000000Z-metrics",
                    "session_id": "sync-20260307t000000z-metrics",
                    "session": og._build_session_record(
                        og.SESSION_KIND_SYNC,
                        og.SESSION_LIFECYCLE_EPHEMERAL,
                        og.SESSION_STATE_ACTIVE,
                        session_id="sync-20260307t000000z-metrics",
                    ),
                    "idempotency_key": "metrics-key",
                    "snapshot": {"changed_files": [], "changed_count": 0},
                    "steps": [],
                    "recovery": {},
                    "message": "sync ok",
                },
                12,
            )

        event_payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        self.assertIn("agent_reliability", event_payload)
        self.assertEqual(event_payload["agent_reliability"]["snapshot"]["totals"]["commands"], 1)
        self.assertEqual(event_payload["agent_reliability"]["snapshot"]["totals"]["successful_tasks"], 1)

    def test_agent_reliability_snapshot_tracks_retry_recovery_and_session_churn(self) -> None:
        state = og._agent_reliability_state_record("2026-03-07T00:00:00Z")
        daemon_session = og._build_session_record(
            og.SESSION_KIND_DAEMON,
            og.SESSION_LIFECYCLE_RESUMABLE,
            og.SESSION_STATE_ACTIVE,
            session_id="daemon-20260307t000000z-aaaabbbbcc",
        )
        first_daemon = og._build_command_result_envelope(
            "daemon",
            {
                "status": "ok",
                "command": "daemon",
                "subcommand": "start",
                "session": daemon_session,
                "session_id": daemon_session["session_id"],
            },
        )
        state, _ = og._apply_agent_reliability_observation(
            state,
            og._build_agent_reliability_observation(first_daemon, schema_valid_output=True),
        )
        second_daemon = og._build_command_result_envelope(
            "daemon",
            {
                "status": "ok",
                "command": "daemon",
                "subcommand": "start",
                "session": daemon_session,
                "session_id": daemon_session["session_id"],
            },
        )
        state, _ = og._apply_agent_reliability_observation(
            state,
            og._build_agent_reliability_observation(second_daemon, schema_valid_output=True),
        )
        rotated_session = og._build_session_record(
            og.SESSION_KIND_DAEMON,
            og.SESSION_LIFECYCLE_RESUMABLE,
            og.SESSION_STATE_ACTIVE,
            session_id="daemon-20260307t000100z-ddddeeeeff",
        )
        rotated_daemon = og._build_command_result_envelope(
            "daemon",
            {
                "status": "ok",
                "command": "daemon",
                "subcommand": "start",
                "session": rotated_session,
                "session_id": rotated_session["session_id"],
            },
        )
        state, _ = og._apply_agent_reliability_observation(
            state,
            og._build_agent_reliability_observation(rotated_daemon, schema_valid_output=True),
        )
        successful_sync = og._build_command_result_envelope(
            "sync",
            {
                "status": "ok",
                "command": "sync",
                "run_id": "sync-1",
                "idempotency_key": "sync-key",
                "snapshot": {"changed_files": [], "changed_count": 0},
                "steps": [],
                "recovery": {
                    "retried_operations": 1,
                    "recovered_operations": 1,
                },
            },
        )
        state, _ = og._apply_agent_reliability_observation(
            state,
            og._build_agent_reliability_observation(successful_sync, schema_valid_output=True),
        )

        snapshot = og._build_agent_reliability_snapshot(state)
        self.assertEqual(snapshot["retry_auto_recovery_rate"]["value"], 1.0)
        self.assertEqual(snapshot["session_churn"]["value"], 0.5)
        self.assertEqual(snapshot["commands_per_successful_task"]["value"], 1.0)


class TestHookLifecycle(_RepoTestCase):
    def test_autopilot_init_installs_and_disables_hooks(self) -> None:
        self._write_quality_pass_script(0)
        with self.git_root_patch():
            init = og._init_autopilot(False)
            self.assertEqual(init["status"], "ok")

            state_path = self.repo / ".outcomegraph" / "autopilot" / "state.json"
            self.assertTrue(state_path.exists())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(state["installed_hooks"]), len(og.AUTOPILOT_HOOKS))
            for raw_hook in state["installed_hooks"]:
                hook_name = raw_hook["hook"]
                hook_path = Path(raw_hook["path"])
                self.assertTrue(hook_path.exists(), msg=f"missing hook script for {hook_name}")
                hook_contents = hook_path.read_text(encoding="utf-8")
                self.assertIn("outcomegraph-autopilot-hook", hook_contents)
                if hook_name == "pre-commit":
                    self.assertIn(og.AUTOPILOT_PRE_COMMIT_QUALITY_PASS, hook_contents)

            config_value = subprocess.run(
                ["git", "-C", str(self.repo), "config", "--get", "core.hooksPath"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip()
            self.assertEqual(config_value, og.AUTOPILOT_MANAGED_HOOK_DIR)

            disable = og._disable_autopilot()
            self.assertEqual(disable["status"], "ok")
            self.assertFalse(state_path.exists())
            self.assertEqual(disable["state_present"], True)
            self.assertIsNone(disable["restored_core_hooks_path"])
            for raw_hook in state["installed_hooks"]:
                hook_path = Path(raw_hook["path"])
                self.assertFalse(hook_path.exists())

    def test_autopilot_session_id_persists_across_init_and_disable(self) -> None:
        self._write_quality_pass_script(0)
        with self.git_root_patch():
            init = og._init_autopilot(False)
            session_id = init["session_id"]
            self.assertIsInstance(session_id, str)
            disable = og._disable_autopilot(session_id)

        self.assertEqual(disable["status"], "ok")
        self.assertEqual(disable["session_id"], session_id)
        self.assertEqual(disable["session"]["state"], og.SESSION_STATE_DISABLED)

    def test_autopilot_disable_rejects_invalid_session_resume(self) -> None:
        self._write_quality_pass_script(0)
        with self.git_root_patch():
            og._init_autopilot(False)
            bad_session_id = "autopilot-20260307t000000z-deadbeef00"
            disable = og._disable_autopilot(bad_session_id)

        self.assertEqual(disable["status"], "error")
        self.assertEqual(disable["code"], og.SESSION_RESUME_INVALID_CODE)
        self.assertEqual(disable["requested_session_id"], bad_session_id)
        self.assertTrue((self.repo / ".outcomegraph" / "autopilot" / "state.json").exists())

    def test_autopilot_disable_main_returns_runtime_exit_for_invalid_session_resume(self) -> None:
        self._write_quality_pass_script(0)
        with self.git_root_patch():
            og._init_autopilot(False)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", "autopilot", "disable", "--session-id", "autopilot-20260307t000000z-deadbeef00"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, og.EXIT_RUNTIME)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["error_code"], og.SESSION_RESUME_INVALID_CODE)

    def test_autopilot_init_restores_existing_managed_hook_from_backup(self) -> None:
        hooks_dir = self.repo / og.AUTOPILOT_MANAGED_HOOK_DIR
        hooks_dir.mkdir(parents=True, exist_ok=True)
        original = hooks_dir / "pre-commit"
        original.write_text("#!/usr/bin/env bash\necho pre-commit-existing\n", encoding="utf-8")

        with self.git_root_patch():
            init = og._init_autopilot(False)
            self.assertEqual(init["status"], "ok")
            state = json.loads((self.repo / ".outcomegraph" / "autopilot" / "state.json").read_text(encoding="utf-8"))

            pre_state = next(item for item in state["installed_hooks"] if item["hook"] == "pre-commit")
            self.assertIsInstance(pre_state.get("backup"), str)
            backup_path = Path(pre_state["backup"])
            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.read_text(encoding="utf-8"), "#!/usr/bin/env bash\necho pre-commit-existing\n")

            disable = og._disable_autopilot()
            self.assertEqual(disable["status"], "ok")
            self.assertTrue((hooks_dir / "pre-commit").exists())
            self.assertEqual(
                (hooks_dir / "pre-commit").read_text(encoding="utf-8"),
                "#!/usr/bin/env bash\necho pre-commit-existing\n",
            )

    def test_autopilot_init_refreshes_existing_managed_hooks(self) -> None:
        hooks_dir = self.repo / og.AUTOPILOT_MANAGED_HOOK_DIR
        hooks_dir.mkdir(parents=True, exist_ok=True)
        legacy_hook = hooks_dir / "pre-commit"
        legacy_hook.write_text(
            "#!/usr/bin/env bash\n# outcomegraph-autopilot-hook\necho legacy-hook\n",
            encoding="utf-8",
        )

        with self.git_root_patch():
            init = og._init_autopilot(False)
            self.assertEqual(init["status"], "ok")
            state = init["state"]
            self.assertIsInstance(state, dict)
            pre_commit = next(item for item in state["installed_hooks"] if item["hook"] == "pre-commit")

        self.assertEqual(pre_commit["status"], "updated-managed")
        contents = legacy_hook.read_text(encoding="utf-8")
        self.assertIn(og.AUTOPILOT_PRE_COMMIT_QUALITY_PASS, contents)
        self.assertNotIn("legacy-hook", contents)

    def test_autopilot_pre_commit_hook_runs_quality_pass_before_marking_pending(self) -> None:
        self._write_quality_pass_script(0)
        with self.git_root_patch():
            init = og._init_autopilot(False)
            self.assertEqual(init["status"], "ok")
            state = init["state"]
            self.assertIsInstance(state, dict)
            pre_commit = next(item for item in state["installed_hooks"] if item["hook"] == "pre-commit")

        hook_path = Path(pre_commit["path"])
        result = subprocess.run([str(hook_path)], cwd=str(self.repo), text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertTrue((self.repo / ".outcomegraph" / "work" / "quality-pass-ran").exists())
        self.assertTrue((self.repo / ".outcomegraph" / "work" / "pending").exists())

    def test_autopilot_pre_commit_hook_blocks_on_quality_pass_failure(self) -> None:
        self._write_quality_pass_script(1)
        with self.git_root_patch():
            init = og._init_autopilot(False)
            self.assertEqual(init["status"], "ok")
            state = init["state"]
            self.assertIsInstance(state, dict)
            pre_commit = next(item for item in state["installed_hooks"] if item["hook"] == "pre-commit")

        hook_path = Path(pre_commit["path"])
        result = subprocess.run([str(hook_path)], cwd=str(self.repo), text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("pre-commit quality pass failed", result.stderr)
        self.assertTrue((self.repo / ".outcomegraph" / "work" / "quality-pass-ran").exists())
        self.assertFalse((self.repo / ".outcomegraph" / "work" / "pending").exists())

    def test_autopilot_init_force_path_requires_yes_for_confirmation(self) -> None:
        hooks_dir = self.repo / "existing-hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        with self.git_root_patch():
            subprocess.run(
                ["git", "-C", str(self.repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )

            for non_interactive in (False, True):
                for tty in (False, True):
                    with self.subTest(non_interactive=non_interactive, tty=tty):
                        args = ["--json", "autopilot", "init", "--force-hooks-path"]
                        if non_interactive:
                            args.insert(1, "--non-interactive")
                        buffer = io.StringIO()
                        with redirect_stdout(buffer):
                            with patch.object(og.sys.stdin, "isatty", return_value=tty):
                                with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
                                    with self.assertRaises(SystemExit) as context:
                                        og.main(args)
                        self.assertEqual(context.exception.code, og.EXIT_USAGE)
                        payload = json.loads(buffer.getvalue())
                        self.assertEqual(payload["status"], "error")
                        self.assertEqual(payload["command"], "autopilot")
                        self.assertEqual(payload["errors"][0]["error_code"], og.USAGE_ERROR_CODE)
                        self.assertIn("autopilot init requires --yes", payload["errors"][0]["message"])

    def test_autopilot_init_force_path_with_yes_is_accepted(self) -> None:
        hooks_dir = self.repo / "existing-hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        with self.git_root_patch():
            subprocess.run(
                ["git", "-C", str(self.repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(
                    [
                        "--json",
                        "--non-interactive",
                        "autopilot",
                        "init",
                        "--force-hooks-path",
                        "--yes",
                    ]
                )
            payload = json.loads(buffer.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["command"], "autopilot")
            config_value = subprocess.run(
                ["git", "-C", str(self.repo), "config", "--get", "core.hooksPath"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout.strip()
            self.assertEqual(config_value, og.AUTOPILOT_MANAGED_HOOK_DIR)

class TestDaemonLifecycle(_RepoTestCase):
    def test_daemon_build_script_uses_current_python_module(self) -> None:
        script = og._daemon_build_script(str(self.repo))

        self.assertIn("PYTHON_BIN=", script)
        self.assertIn(sys.executable, script)
        self.assertIn('exec "$PYTHON_BIN" -m og daemon run "$@"', script)
        self.assertNotIn("uvx --from", script)

    def test_daemon_run_sync_uses_current_python_module(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "og", "sync", "--json"],
            returncode=0,
            stdout=json.dumps({"status": "ok", "command": "sync"}),
            stderr="",
        )
        with patch.object(og.subprocess, "run", return_value=completed) as run:
            payload = og._daemon_run_sync(str(self.repo))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(run.call_args.args[0], [sys.executable, "-m", "og", "sync", "--json"])
        self.assertEqual(run.call_args.kwargs["env"]["OG_AUTOPILOT"], "1")

    def test_daemon_start_stop_round_trip(self) -> None:
        with self.git_root_patch(), patch.object(
            og,
            "_daemon_build_script",
            return_value="#!/usr/bin/env bash\nexec sleep 30\n",
        ):
            og._init_outcomegraph()
            install_payload = og._daemon_install()
            self.assertEqual(install_payload["status"], "ok")

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                start_payload = og._daemon_start()
            self.assertEqual(start_payload["status"], "ok")
            self.assertTrue(start_payload["runtime"]["running"])
            try:
                status_payload = og._daemon_status()
                self.assertEqual(status_payload["status"], "ok")
                self.assertTrue(status_payload["runtime"]["running"])

                stop_payload = og._daemon_stop()
                self.assertFalse(stop_payload["runtime"]["running"])
                self.assertIn(stop_payload["status"], {"ok", "error"})

                status_after_stop = og._daemon_status()
                self.assertEqual(status_after_stop["status"], "ok")
                self.assertFalse(status_after_stop["runtime"]["running"])
            finally:
                og._daemon_stop()

    def test_daemon_session_id_persists_across_install_start_status_stop(self) -> None:
        with self.git_root_patch(), patch.object(
            og,
            "_daemon_build_script",
            return_value="#!/usr/bin/env bash\nexec sleep 30\n",
        ):
            og._init_outcomegraph()
            install_payload = og._daemon_install()
            session_id = install_payload["session_id"]
            self.assertIsInstance(session_id, str)

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                start_payload = og._daemon_start(session_id)
            self.assertEqual(start_payload["session_id"], session_id)
            try:
                status_payload = og._daemon_status(session_id)
                self.assertEqual(status_payload["session_id"], session_id)
                self.assertEqual(status_payload["session"]["state"], og.SESSION_STATE_ACTIVE)

                stop_payload = og._daemon_stop(session_id)
                self.assertEqual(stop_payload["session_id"], session_id)
                self.assertEqual(stop_payload["session"]["state"], og.SESSION_STATE_STOPPED)
            finally:
                og._daemon_stop()

    def test_daemon_status_rejects_invalid_session_resume(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            og._daemon_install()
            payload = og._daemon_status("daemon-20260307t000000z-deadbeef00")

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.SESSION_RESUME_INVALID_CODE)

    def test_daemon_status_rejects_expired_session_resume(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            install_payload = og._daemon_install()
            session_id = install_payload["session_id"]
            state_path = self.repo / ".outcomegraph" / "work" / "daemon" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["session"]["expires_at"] = "2000-01-01T00:00:00Z"
            state["session"]["state"] = og.SESSION_STATE_ACTIVE
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

            payload = og._daemon_status(session_id)

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.SESSION_EXPIRED_CODE)
        self.assertEqual(payload["session"]["state"], og.SESSION_STATE_EXPIRED)

    def test_daemon_status_main_returns_runtime_exit_for_expired_session_resume(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            install_payload = og._daemon_install()
            session_id = install_payload["session_id"]
            state_path = self.repo / ".outcomegraph" / "work" / "daemon" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["session"]["expires_at"] = "2000-01-01T00:00:00Z"
            state["session"]["state"] = og.SESSION_STATE_ACTIVE
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", "daemon", "status", "--session-id", session_id])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, og.EXIT_RUNTIME)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["error_code"], og.SESSION_EXPIRED_CODE)

    def test_daemon_run_sync_rejects_invalid_status_payload(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[sys.executable, "-m", "og", "sync", "--json"],
            returncode=0,
            stdout=json.dumps({"status": "invalid-state", "command": "sync"}),
            stderr="",
        )
        with patch.object(og.subprocess, "run", return_value=completed):
            payload = og._daemon_run_sync(str(self.repo))

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["command"], "sync")
        self.assertEqual(payload["message"], "sync subprocess returned invalid status payload")
        self.assertNotIn("{\"status\"", payload["message"])
        self.assertEqual(payload["runtime"]["daemon_sync_exit_code"], 0)

    def test_sync_lock_contention_emits_session_id(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            acquired, lock_payload = og._acquire_work_lock(
                str(self.repo),
                {"pid": 12345, "host": "test-host", "command": "og sync"},
            )
            self.assertTrue(acquired)
            session_id = lock_payload["session"]["session_id"]
            try:
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = og.main(["--json", "sync"])
                payload = json.loads(buffer.getvalue())
            finally:
                og._release_work_lock(str(self.repo), {"pid": 12345, "host": "test-host", "command": "og sync"})

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(payload["session_id"], session_id)
        self.assertEqual(payload["errors"][0]["error_code"], og.SESSION_CONTENDED_CODE)
        self.assertEqual(payload["data"]["lock"]["session"]["session_id"], session_id)

    def test_refresh_work_lock_updates_timestamp_for_current_holder(self) -> None:
        holder = {"pid": 12345, "host": "test-host", "command": "og sync"}
        with self.git_root_patch():
            og._init_outcomegraph()
            acquired, _ = og._acquire_work_lock(str(self.repo), holder)
            self.assertTrue(acquired)
            try:
                with patch.object(og, "_utc_timestamp", return_value="2026-03-08T00:10:00Z"):
                    refreshed = og._refresh_work_lock(str(self.repo), holder)
                lock_payload = json.loads((self.repo / ".outcomegraph" / "work" / "lock").read_text(encoding="utf-8"))
            finally:
                og._release_work_lock(str(self.repo), holder)

        self.assertTrue(refreshed)
        self.assertEqual(lock_payload["updated_at"], "2026-03-08T00:10:00Z")
        self.assertEqual(lock_payload["session"]["updated_at"], "2026-03-08T00:10:00Z")
        self.assertEqual(lock_payload["session"]["state"], og.SESSION_STATE_ACTIVE)

    def test_refresh_work_lock_rejects_non_holder(self) -> None:
        holder = {"pid": 12345, "host": "test-host", "command": "og sync"}
        other_holder = {"pid": 99999, "host": "other-host", "command": "og sync"}
        with self.git_root_patch():
            og._init_outcomegraph()
            acquired, _ = og._acquire_work_lock(str(self.repo), holder)
            self.assertTrue(acquired)
            try:
                original_payload = json.loads((self.repo / ".outcomegraph" / "work" / "lock").read_text(encoding="utf-8"))
                with patch.object(og, "_utc_timestamp", return_value="2026-03-08T00:12:00Z"):
                    refreshed = og._refresh_work_lock(str(self.repo), other_holder)
                updated_payload = json.loads((self.repo / ".outcomegraph" / "work" / "lock").read_text(encoding="utf-8"))
            finally:
                og._release_work_lock(str(self.repo), holder)

        self.assertFalse(refreshed)
        self.assertEqual(updated_payload["updated_at"], original_payload["updated_at"])
        self.assertEqual(updated_payload["holder"]["pid"], holder["pid"])


class TestSyncWorkflows(_RepoTestCase):
    def test_sync_snapshot_falls_back_when_git_baseline_is_unavailable(self) -> None:
        with self.git_root_patch():
            with patch.object(
                og,
                "_run_git",
                side_effect=lambda _repo_root, args, check=False: self._git_completed(
                    1,
                    stdout="" if args[0] == "rev-parse" else "",
                    stderr="fatal" if args[0] == "rev-parse" else "",
                ),
            ):
                snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["repository_head"], "HEAD_NOT_AVAILABLE")
        self.assertEqual(snapshot["branch"], "detached")
        self.assertEqual(snapshot["changed_count"], 0)

    def test_collect_changed_paths_resolve_head_parent_first(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="capsules/default.yaml\n.outcomegraph/work/cache/file.txt")
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            if args == ["rev-parse", "ORIG_HEAD"]:
                return self._git_completed(1, stdout="", stderr="fatal")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(snapshot["diff_baseline"]["resolved"], "aaaa")
        self.assertEqual(snapshot["changed_files"], ["capsules/default.yaml"])
        self.assertEqual(snapshot["changed_count"], 1)
        self.assertEqual(snapshot["has_changes"], True)

    def test_collect_changed_paths_ignores_managed_generated_artifacts(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(
                    0,
                    stdout="\n".join(
                        [
                            "og.py",
                            ".outcomegraph/capsules/og.json",
                            ".outcomegraph/policy.yaml",
                            "skills/outcome-steward/SKILL.md",
                        ]
                    ),
                )
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(
                    0,
                    stdout="\n".join(
                        [
                            ".outcomegraph/materials.lock",
                            ".outcomegraph/export/README_OUTCOMES.md",
                        ]
                    ),
                )
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout=".outcomegraph/certificates/cert-og-abcdef.json")
            if args == ["rev-parse", "ORIG_HEAD"]:
                return self._git_completed(1, stdout="", stderr="fatal")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["changed_files"], [".outcomegraph/policy.yaml", "og.py"])
        self.assertEqual(snapshot["changed_count"], 2)

    def test_collect_changed_paths_prefers_orig_head_merge_base(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(1, stdout="", stderr="fatal")
            if args == ["rev-parse", "ORIG_HEAD"]:
                return self._git_completed(0, stdout="222222")
            if args == ["merge-base", "222222", "HEAD"]:
                return self._git_completed(0, stdout="333333")
            if args == ["diff", "--name-only", "333333"]:
                return self._git_completed(0, stdout="capsules/default.yaml")
            if args == ["diff", "--cached", "--name-only", "333333"]:
                return self._git_completed(0, stdout=".outcomegraph/work/tmp.outcome")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            merge_snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(merge_snapshot["diff_baseline"]["strategy"], "orig_head_merge_base")
        self.assertEqual(merge_snapshot["diff_baseline"]["resolved"], "333333")
        self.assertEqual(merge_snapshot["changed_files"], ["capsules/default.yaml"])

    def test_collect_changed_paths_falls_back_to_empty_tree(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(1, stdout="", stderr="fatal")
            if args == ["rev-parse", "ORIG_HEAD"]:
                return self._git_completed(0, stdout="222222")
            if args == ["merge-base", "222222", "HEAD"]:
                return self._git_completed(1, stdout="", stderr="fatal")
            if args == ["ls-files"]:
                return self._git_completed(
                    0,
                    stdout="capsules/default.yaml\nREADME.md\n.outcomegraph/work/runtime.json\n",
                )
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["diff_baseline"]["strategy"], "empty_tree")
        self.assertEqual(snapshot["changed_files"], ["README.md", "capsules/default.yaml"])
        self.assertEqual(snapshot["changed_count"], 2)

    def test_collect_changed_paths_forces_full_sync_when_runtime_only_changes(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout=".outcomegraph/work/cache/file.txt")
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files"]:
                return self._git_completed(0, stdout="capsules/default.yaml\nREADME.md\n.outcomegraph/work/keep.json")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["changed_count"], 0)

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            forced_snapshot = og._collect_sync_snapshot(
                str(self.repo),
                "analyze",
                "observe",
                force_full_sync=True,
            )

        self.assertEqual(forced_snapshot["force_full_sync"], True)
        self.assertEqual(forced_snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(sorted(forced_snapshot["changed_files"]), ["README.md", "capsules/default.yaml"])

    def test_collect_changed_paths_force_full_sync_collects_full_tree_even_with_diff(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="README.md")
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files"]:
                return self._git_completed(0, stdout="README.md\nog.py\n.outcomegraph/work/keep.json")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            forced_snapshot = og._collect_sync_snapshot(
                str(self.repo),
                "analyze",
                "observe",
                force_full_sync=True,
            )

        self.assertEqual(forced_snapshot["force_full_sync"], True)
        self.assertEqual(forced_snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(sorted(forced_snapshot["changed_files"]), ["README.md", "og.py"])

    def test_collect_changed_paths_force_full_sync_ignores_managed_generated_artifacts(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="README.md")
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files"]:
                return self._git_completed(
                    0,
                    stdout="\n".join(
                        [
                            "README.md",
                            ".outcomegraph/policy.yaml",
                            ".outcomegraph/constitution/default.json",
                            ".outcomegraph/capsules/og.json",
                            ".outcomegraph/export/README_OUTCOMES.md",
                            ".outcomegraph/materials.lock",
                            "skills/outcome-steward/SKILL.md",
                            ".outcomegraph/work/keep.json",
                        ]
                    ),
                )
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=False
        ):
            forced_snapshot = og._collect_sync_snapshot(
                str(self.repo),
                "analyze",
                "observe",
                force_full_sync=True,
            )

        self.assertEqual(
            sorted(forced_snapshot["changed_files"]),
            [
                ".outcomegraph/constitution/default.json",
                ".outcomegraph/policy.yaml",
                "README.md",
            ],
        )

    def test_collect_changed_paths_bootstrap_full_snapshot_when_no_capsules_exist(self) -> None:
        def fake_run_git(_repo_root: str, args: list[str], check: bool = False):
            if args == ["rev-parse", "HEAD"]:
                return self._git_completed(0, stdout="111111")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return self._git_completed(0, stdout="main")
            if args == ["rev-parse", "HEAD~1"]:
                return self._git_completed(0, stdout="aaaa")
            if args == ["diff", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="README.md")
            if args == ["diff", "--cached", "--name-only", "aaaa"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files", "--others", "--exclude-standard"]:
                return self._git_completed(0, stdout="")
            if args == ["ls-files"]:
                return self._git_completed(0, stdout="README.md\nog.py\n.outcomegraph/work/keep.json")
            return self._git_completed(1, stdout="", stderr="fatal")

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git), patch.object(
            og, "_requires_bootstrap_full_snapshot", return_value=True
        ):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(sorted(snapshot["changed_files"]), ["README.md", "og.py"])

    def test_collect_affected_capsules_groups_paths_by_scope(self) -> None:
        capsules = og._collect_affected_capsules(
            [
                "README.md",
                "og.py",
                "tests/test_og_sync_verify_replay_hooks.py",
                "skills/og-dogfood/SKILL.md",
                ".outcomegraph/materials.lock",
                ".outcomegraph/policy.yaml",
                ".outcomegraph/certificates/cert-default-abcdef1234.json",
                ".outcomegraph/claims/cl-materials-fedcba4321.json",
            ]
        )

        self.assertEqual(
            capsules,
            [
                "default",
                "materials",
                "og",
                "policy",
                "readme",
                "skill-og-dogfood",
                "tests",
            ],
        )

    def test_run_distill_stage_backfills_changed_files_per_capsule(self) -> None:
        prompt_provenance = {
            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
            "source_path": "prompts/workers/distill-v1.txt",
        }
        snapshot = {
            "changed_files": [
                "README.md",
                "og.py",
                "tests/test_og_sync_verify_replay_hooks.py",
                ".outcomegraph/materials.lock",
            ]
        }
        worker_output = {
            "schema_version": og.WORKER_SCHEMA_VERSION,
            "interface_version": og.WORKER_INTERFACE_VERSION,
            "run_id": "sync-1",
            "capsule_updates": [
                _distill_update("readme", []),
                _distill_update("og", []),
                _distill_update("tests", []),
                _distill_update("materials", []),
            ],
            "prompt_provenance": prompt_provenance,
        }

        with self.git_root_patch(), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ), patch.object(
            og,
            "_run_codex_worker",
            return_value=(worker_output, []),
        ):
            result = og._run_distill_stage(
                str(self.repo),
                snapshot,
                "sync-1",
                profile="analyze",
                mode="observe",
            )

        changed_by_capsule = {item["capsule_id"]: item["changed_files"] for item in result["generated_deltas"]}
        self.assertEqual(changed_by_capsule["readme"], ["README.md"])
        self.assertEqual(changed_by_capsule["og"], ["og.py"])
        self.assertEqual(changed_by_capsule["tests"], ["tests/test_og_sync_verify_replay_hooks.py"])
        self.assertEqual(changed_by_capsule["materials"], [".outcomegraph/materials.lock"])
        self.assertEqual(result["prompt_provenance"], prompt_provenance)
        self.assertTrue(all(item["prompt_provenance"] == prompt_provenance for item in result["generated_deltas"]))

    def test_run_distill_stage_skips_when_snapshot_has_no_changed_files(self) -> None:
        with self.git_root_patch():
            payload = og._run_distill_stage(str(self.repo), {}, "sync-1", profile="analyze", mode="observe")

        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["generated_deltas"], [])

    def test_record_sync_summary_event_collects_worker_prompt_provenance(self) -> None:
        prompt_provenance = {
            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
            "source_path": "prompts/workers/distill-v1.txt",
        }

        with self.git_root_patch():
            og._init_outcomegraph()
            event_path = og._record_sync_summary_event(
                str(self.repo),
                {
                    "run_id": "sync-1",
                    "status": "ok",
                    "session_id": "sync-20260307t000000z-abcdef1234",
                    "idempotency_key": "sync-key",
                    "snapshot": {"changed_files": ["og.py"]},
                    "steps": [
                        {
                            "name": "distill",
                            "status": "ok",
                            "prompt_provenance": prompt_provenance,
                            "generated_deltas": [
                                {
                                    "capsule_id": "og",
                                    "prompt_provenance": prompt_provenance,
                                }
                            ],
                        }
                    ],
                },
                42,
            )

        event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        self.assertEqual(event_payload["worker_prompt_provenance"], [prompt_provenance])
        self.assertEqual(event_payload["session_id"], "sync-20260307t000000z-abcdef1234")

    def test_run_distill_stage_uses_bootstrap_timeout_for_full_snapshot(self) -> None:
        snapshot = {
            "changed_files": ["README.md"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }
        worker_output = {
            "schema_version": og.WORKER_SCHEMA_VERSION,
            "interface_version": og.WORKER_INTERFACE_VERSION,
            "run_id": "sync-1",
            "capsule_updates": [
                _distill_update("readme", []),
            ],
        }

        with self.git_root_patch(), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ), patch.object(
            og,
            "_requires_bootstrap_full_snapshot",
            return_value=True,
        ), patch.object(
            og,
            "_run_codex_worker",
            return_value=(worker_output, []),
        ) as run_codex_worker:
            result = og._run_distill_stage(
                str(self.repo),
                snapshot,
                "sync-1",
                profile="analyze",
                mode="observe",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(run_codex_worker.call_args.kwargs["timeout_seconds"], og.WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS)

    def test_run_distill_stage_uses_bootstrap_timeout_for_source_heavy_snapshot(self) -> None:
        (self.repo / "og.py").write_text("print('x')\n", encoding="utf-8")
        (self.repo / "tests").mkdir(exist_ok=True)
        (self.repo / "tests" / "test_example.py").write_text("def test_example():\n    assert True\n", encoding="utf-8")
        snapshot = {
            "changed_files": ["og.py", "tests/test_example.py"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }
        worker_output = {
            "schema_version": og.WORKER_SCHEMA_VERSION,
            "interface_version": og.WORKER_INTERFACE_VERSION,
            "run_id": "sync-1",
            "capsule_updates": [
                _distill_update("og", ["og.py"]),
                _distill_update("tests", ["tests/test_example.py"]),
            ],
        }

        with self.git_root_patch(), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ), patch.object(
            og,
            "_requires_bootstrap_full_snapshot",
            return_value=False,
        ), patch.object(
            og,
            "_run_codex_worker",
            return_value=(worker_output, []),
        ) as run_codex_worker:
            result = og._run_distill_stage(
                str(self.repo),
                snapshot,
                "sync-1",
                profile="analyze",
                mode="observe",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(run_codex_worker.call_args.kwargs["timeout_seconds"], og.WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS)

    def test_run_distill_stage_batches_complex_snapshot_capsules(self) -> None:
        snapshot = {
            "changed_files": ["og.py", "tests/test_example.py"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }
        changed_by_capsule = {
            "og": ["og.py"],
            "tests": ["tests/test_example.py"],
            "readme": ["README.md"],
            "runbooks": ["RUNBOOKS.md"],
            "spec-v2": ["SPEC-v2.md"],
        }
        target_capsules = [
            {"id": capsule_id, "changed_files": changed_files}
            for capsule_id, changed_files in changed_by_capsule.items()
        ]
        worker_calls: list[tuple[list[str], int | None]] = []

        def fake_run_worker_with_retries(
            role: str,
            input_payload: dict[str, object],
            repo_root: str,
            trace_path: str,
            worker_adapter: dict[str, object],
            *,
            timeout_seconds: int,
            max_retries: int,
        ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
            self.assertEqual(role, "distill")
            worker_calls.append(
                (
                    [str(item.get("id") or "") for item in input_payload.get("target_capsules", []) if isinstance(item, dict)],
                    timeout_seconds,
                )
            )
            output_payload = {
                "schema_version": og.WORKER_SCHEMA_VERSION,
                "interface_version": og.WORKER_INTERFACE_VERSION,
                "run_id": str(input_payload["run_id"]),
                "capsule_updates": [
                    _distill_update(str(item.get("id") or "default"), list(item.get("changed_files") or []))
                    for item in input_payload.get("target_capsules", [])
                    if isinstance(item, dict)
                ],
            }
            recovery = og._build_recovery_record(
                "worker:distill",
                attempts=1,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                retryable=False,
            )
            return output_payload, [], recovery

        with self.git_root_patch(), patch.object(
            og,
            "_initialize_adapter_runtime",
            return_value=[],
        ), patch.object(
            og,
            "_collect_affected_capsules",
            return_value=list(changed_by_capsule),
        ), patch.object(
            og,
            "_collect_changed_materials",
            return_value=[],
        ), patch.object(
            og,
            "_group_changed_files_by_capsule",
            return_value=changed_by_capsule,
        ), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ), patch.object(
            og,
            "_build_distill_target_capsules",
            return_value=target_capsules,
        ), patch.object(
            og,
            "_run_worker_with_retries",
            side_effect=fake_run_worker_with_retries,
        ):
            result = og._run_distill_stage(
                str(self.repo),
                snapshot,
                "sync-1",
                profile="analyze",
                mode="observe",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(sorted(len(batch_capsules) for batch_capsules, _ in worker_calls), [2, 3])
        self.assertTrue(all(timeout == og.WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS for _, timeout in worker_calls))
        self.assertEqual(len(result["generated_deltas"]), len(changed_by_capsule))

    def test_run_distill_stage_splits_oversized_bootstrap_prompt_batches(self) -> None:
        snapshot = {
            "changed_files": ["tasks/og-dogfood-001/TASK.md", "tests/test_og_sync_verify_replay_hooks.py", "to-do.json"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }
        changed_by_capsule = {
            "tasks": ["tasks/og-dogfood-001/TASK.md"],
            "tests": ["tests/test_og_sync_verify_replay_hooks.py"],
            "to-do": ["to-do.json"],
        }
        target_capsules = [
            {"id": capsule_id, "changed_files": changed_files}
            for capsule_id, changed_files in changed_by_capsule.items()
        ]
        worker_calls: list[list[str]] = []
        prompt_lengths = {
            ("tasks", "tests"): 220,
            ("tests", "to-do"): 90,
            ("tasks", "tests", "to-do"): 280,
        }

        def fake_resolve_worker_prompt(role: str, payload: dict[str, object]) -> tuple[str, dict[str, str]]:
            self.assertEqual(role, "distill")
            capsule_ids = tuple(
                str(item.get("id") or "")
                for item in payload.get("target_capsules", [])
                if isinstance(item, dict)
            )
            prompt_chars = prompt_lengths.get(capsule_ids, 60)
            return (
                "x" * prompt_chars,
                {
                    "id": "worker-distill",
                    "version": "1.0.1",
                    "source_path": "prompts/workers/distill-v1.txt",
                },
            )

        def fake_run_worker_with_retries(
            role: str,
            input_payload: dict[str, object],
            repo_root: str,
            trace_path: str,
            worker_adapter: dict[str, object],
            *,
            timeout_seconds: int,
            max_retries: int,
        ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
            self.assertEqual(role, "distill")
            worker_calls.append(
                [str(item.get("id") or "") for item in input_payload.get("target_capsules", []) if isinstance(item, dict)]
            )
            output_payload = {
                "schema_version": og.WORKER_SCHEMA_VERSION,
                "interface_version": og.WORKER_INTERFACE_VERSION,
                "run_id": str(input_payload["run_id"]),
                "capsule_updates": [
                    _distill_update(str(item.get("id") or "default"), list(item.get("changed_files") or []))
                    for item in input_payload.get("target_capsules", [])
                    if isinstance(item, dict)
                ],
            }
            recovery = og._build_recovery_record(
                "worker:distill",
                attempts=1,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                retryable=False,
            )
            return output_payload, [], recovery

        with self.git_root_patch(), patch.object(
            og,
            "_initialize_adapter_runtime",
            return_value=[],
        ), patch.object(
            og,
            "_collect_affected_capsules",
            return_value=list(changed_by_capsule),
        ), patch.object(
            og,
            "_collect_changed_materials",
            return_value=[],
        ), patch.object(
            og,
            "_group_changed_files_by_capsule",
            return_value=changed_by_capsule,
        ), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ), patch.object(
            og,
            "_build_distill_target_capsules",
            return_value=target_capsules,
        ), patch.object(
            og,
            "_resolve_worker_prompt",
            side_effect=fake_resolve_worker_prompt,
        ), patch.object(
            og,
            "WORKER_ADAPTER_BOOTSTRAP_PROMPT_CHAR_BUDGET",
            100,
        ), patch.object(
            og,
            "_run_worker_with_retries",
            side_effect=fake_run_worker_with_retries,
        ):
            result = og._run_distill_stage(
                str(self.repo),
                snapshot,
                "sync-1",
                profile="analyze",
                mode="observe",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(worker_calls, [["tasks"], ["tests", "to-do"]])
        self.assertEqual(len(result["generated_deltas"]), len(changed_by_capsule))

    def test_select_distill_max_workers_limits_complex_snapshots_to_bootstrap_cap(self) -> None:
        snapshot = {
            "changed_files": ["og.py", "tests/test_example.py"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }

        with patch.object(og, "_requires_bootstrap_full_snapshot", return_value=False):
            max_workers = og._select_distill_max_workers(str(self.repo), snapshot, 4)

        self.assertEqual(max_workers, og.WORKER_ADAPTER_BOOTSTRAP_MAX_WORKERS)

    def test_select_distill_max_workers_keeps_parallelism_for_small_snapshots(self) -> None:
        snapshot = {
            "changed_files": ["README.md"],
            "diff_baseline": {"strategy": "head~1"},
            "force_full_sync": False,
        }

        with patch.object(og, "_requires_bootstrap_full_snapshot", return_value=False):
            max_workers = og._select_distill_max_workers(str(self.repo), snapshot, 5)

        self.assertEqual(max_workers, og.WORKER_ADAPTER_DISTILL_MAX_WORKERS)

    def test_sync_parse_accepts_force_full_sync(self) -> None:
        options, _ = og.parse_command_flags(
            ["--force-full-sync", "--profile", "apply", "--mode", "autonomous"],
            "sync",
            False,
            True,
            True,
            False,
            allow_force_full_sync=True,
        )

        self.assertTrue(options["force_full_sync"])
        self.assertEqual(options["profile"], "apply")
        self.assertEqual(options["mode"], "autonomous")

    def test_parse_command_flags_supports_command_level_strict(self) -> None:
        options, _ = og.parse_command_flags(
            ["--strict", "--profile", "analyze", "--mode", "autonomous"],
            "sync",
            False,
            True,
            True,
            False,
            default_strict=False,
            allow_force_full_sync=True,
        )
        self.assertTrue(options["strict"])
        self.assertEqual(options["profile"], "analyze")
        self.assertEqual(options["mode"], "autonomous")

    def test_parse_command_flags_strict_flag_can_be_negated_from_default(self) -> None:
        options, _ = og.parse_command_flags(
            ["--strict=false", "--profile", "analyze", "--mode", "autonomous"],
            "sync",
            False,
            True,
            True,
            False,
            default_strict=True,
            allow_force_full_sync=True,
        )
        self.assertFalse(options["strict"])

    def test_parse_command_flags_supports_output_controls(self) -> None:
        options, _ = og.parse_command_flags(
            ["--output", "jsonl", "--fields", "claims,steps", "--limit", "2", "--offset", "1"],
            "verify",
            True,
            True,
            True,
            False,
            allow_output_controls=True,
        )

        self.assertEqual(options["output_mode"], og.OUTPUT_MODE_JSONL)
        self.assertEqual(options["fields"], ["claims", "steps"])
        self.assertEqual(options["limit"], 2)
        self.assertEqual(options["offset"], 1)

    def test_parse_command_flags_rejects_invalid_output_controls(self) -> None:
        def parse_error(args: list[str], fragment: str) -> None:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og.parse_command_flags(
                        args,
                        "verify",
                        True,
                        True,
                        True,
                        True,
                        allow_output_controls=True,
                    )
            self.assertEqual(context.exception.code, og.EXIT_USAGE)
            payload = json.loads(buffer.getvalue() or "{}")
            self.assertIn(fragment, str(payload["errors"][0]["message"]))

        cases = [
            (["--output", "yaml"], "invalid --output value"),
            (["--limit", "abc"], "invalid --limit value"),
            (["--offset", "-1"], "must be zero or greater"),
            (["--limit", "0"], "must be greater than 0"),
        ]
        for args, fragment in cases:
            with self.subTest(args=args):
                parse_error(args, fragment)

    def test_parse_command_flags_apply_env_defaults_and_cli_precedence(self) -> None:
        with patch.dict(
            os.environ,
            {
                og.DEFAULT_OUTPUT_ENV: og.OUTPUT_MODE_JSON,
                og.DEFAULT_PROFILE_ENV: "propose",
                og.DEFAULT_MODE_ENV: "autonomous",
                og.CODEX_HOME_OVERRIDE_ENV: ".codex-headless",
            },
            clear=False,
        ):
            runtime_defaults = og._load_runtime_defaults(str(self.repo))
            defaulted_options, _ = og.parse_command_flags(
                [],
                "verify",
                True,
                True,
                True,
                False,
                allow_output_controls=True,
                runtime_defaults=runtime_defaults,
            )
            cli_options, _ = og.parse_command_flags(
                ["--output", "human", "--profile", "apply", "--mode", "observe"],
                "verify",
                True,
                True,
                True,
                False,
                allow_output_controls=True,
                runtime_defaults=runtime_defaults,
            )

        self.assertEqual(defaulted_options["output_mode"], og.OUTPUT_MODE_JSON)
        self.assertTrue(defaulted_options["output_json"])
        self.assertEqual(defaulted_options["profile"], "propose")
        self.assertEqual(defaulted_options["mode"], "autonomous")
        defaulted_configuration = defaulted_options["configuration"]
        self.assertEqual(defaulted_configuration["codex_home"], ".codex-headless")
        self.assertEqual(defaulted_configuration["resolved_from"]["output_mode"], f"env:{og.DEFAULT_OUTPUT_ENV}")
        self.assertEqual(defaulted_configuration["resolved_from"]["profile"], f"env:{og.DEFAULT_PROFILE_ENV}")
        self.assertEqual(defaulted_configuration["resolved_from"]["mode"], f"env:{og.DEFAULT_MODE_ENV}")
        self.assertEqual(defaulted_configuration["resolved_from"]["codex_home"], f"env:{og.CODEX_HOME_OVERRIDE_ENV}")

        self.assertEqual(cli_options["output_mode"], og.OUTPUT_MODE_HUMAN)
        self.assertFalse(cli_options["output_json"])
        self.assertEqual(cli_options["profile"], "apply")
        self.assertEqual(cli_options["mode"], "observe")
        cli_configuration = cli_options["configuration"]
        self.assertEqual(cli_configuration["resolved_from"]["output_mode"], "flag:--output")
        self.assertEqual(cli_configuration["resolved_from"]["profile"], "flag:--profile")
        self.assertEqual(cli_configuration["resolved_from"]["mode"], "flag:--mode")
        self.assertEqual(cli_configuration["resolved_from"]["codex_home"], f"env:{og.CODEX_HOME_OVERRIDE_ENV}")

    def test_parse_command_flags_use_config_defaults_and_metadata(self) -> None:
        config_dir = self.repo / ".outcomegraph"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(
            (
                "schema_version: 2\n"
                "defaults:\n"
                "  output: jsonl\n"
                "  profile: propose\n"
                "  mode: autonomous\n"
                "worker:\n"
                "  codex_home: \".codex-machine\"\n"
                "safety:\n"
                "  policy_file: \"runtime/policy-headless.yaml\"\n"
            ),
            encoding="utf-8",
        )

        runtime_defaults = og._load_runtime_defaults(str(self.repo))
        options, _ = og.parse_command_flags(
            [],
            "verify",
            True,
            True,
            True,
            False,
            allow_output_controls=True,
            runtime_defaults=runtime_defaults,
        )

        self.assertEqual(options["output_mode"], og.OUTPUT_MODE_JSONL)
        self.assertTrue(options["output_json"])
        self.assertEqual(options["profile"], "propose")
        self.assertEqual(options["mode"], "autonomous")
        configuration = options["configuration"]
        self.assertEqual(configuration["config_file"], og.DEFAULT_CONFIG_FILE)
        self.assertEqual(configuration["policy_file"], ".outcomegraph/runtime/policy-headless.yaml")
        self.assertEqual(configuration["codex_home"], ".codex-machine")
        self.assertEqual(configuration["resolved_from"]["output_mode"], f"config:{og.DEFAULT_CONFIG_FILE}")
        self.assertEqual(configuration["resolved_from"]["profile"], f"config:{og.DEFAULT_CONFIG_FILE}")
        self.assertEqual(configuration["resolved_from"]["mode"], f"config:{og.DEFAULT_CONFIG_FILE}")
        self.assertEqual(configuration["resolved_from"]["codex_home"], f"config:{og.DEFAULT_CONFIG_FILE}")

    def test_load_runtime_defaults_prefers_env_over_config_and_resolves_paths(self) -> None:
        og_root = self.repo / og.OG_ROOT
        og_root.mkdir(parents=True, exist_ok=True)
        config_path = og_root / "config.yaml"
        config_path.write_text(
            """schema_version: 2
profile: propose
mode: autonomous
output: human
safety:
  policy_file: policy-from-config.yaml
""",
            encoding="utf-8",
        )
        (og_root / "policy-from-config.yaml").write_text(
            "schema_version: 2\nmode: observe\n",
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                og.DEFAULT_OUTPUT_ENV: og.OUTPUT_MODE_JSON,
                og.DEFAULT_MODE_ENV: "observe",
                og.POLICY_FILE_ENV: "ops/policy-override.yaml",
            },
            clear=False,
        ):
            defaults = og._load_runtime_defaults(str(self.repo))

        self.assertEqual(defaults["profile"], "propose")
        self.assertEqual(defaults["mode"], "observe")
        self.assertEqual(defaults["output_mode"], og.OUTPUT_MODE_JSON)
        self.assertEqual(defaults["config_file"], f"{og.OG_ROOT}/config.yaml")
        self.assertEqual(defaults["policy_file"], "ops/policy-override.yaml")
        self.assertEqual(defaults["config_source"], "built-in")
        self.assertEqual(defaults["policy_source"], f"env:{og.POLICY_FILE_ENV}")
        self.assertEqual(defaults["resolved_from"]["profile"], f"config:{og.OG_ROOT}/config.yaml")
        self.assertEqual(defaults["resolved_from"]["mode"], f"env:{og.DEFAULT_MODE_ENV}")
        self.assertEqual(defaults["resolved_from"]["output_mode"], f"env:{og.DEFAULT_OUTPUT_ENV}")

    def test_status_uses_env_default_output_and_configuration_metadata(self) -> None:
        buffer = io.StringIO()
        with self.git_root_patch(), patch.dict(os.environ, {og.DEFAULT_OUTPUT_ENV: og.OUTPUT_MODE_JSON}, clear=False):
            with redirect_stdout(buffer):
                code = og.main(["status"])

        self.assertEqual(code, og.EXIT_SUCCESS)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["command"], "status")
        self.assertEqual(payload["status"], "warn")
        options = payload["data"]["options"]
        self.assertEqual(options["output_mode"], og.OUTPUT_MODE_JSON)
        self.assertEqual(options["configuration"]["resolved_from"]["output_mode"], f"env:{og.DEFAULT_OUTPUT_ENV}")

    def test_verify_env_defaults_match_explicit_flags_and_cli_overrides_config(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
        config_path = self.repo / og.OG_ROOT / "config.yaml"
        config_path.write_text(
            """schema_version: 2
profile: propose
mode: observe
output: human
safety:
  policy_file: policy.yaml
  max_writes_per_run: 64
""",
            encoding="utf-8",
        )

        env_buffer = io.StringIO()
        with self.git_root_patch(), patch.dict(
            os.environ,
            {
                og.DEFAULT_OUTPUT_ENV: og.OUTPUT_MODE_JSON,
                og.DEFAULT_PROFILE_ENV: "apply",
            },
            clear=False,
        ):
            with redirect_stdout(env_buffer):
                env_code = og.main(["verify", "--validate", "--mode", "autonomous"])

        explicit_buffer = io.StringIO()
        with self.git_root_patch():
            with redirect_stdout(explicit_buffer):
                explicit_code = og.main(
                    ["verify", "--validate", "--json", "--profile", "apply", "--mode", "autonomous"]
                )

        self.assertEqual(env_code, og.EXIT_SUCCESS)
        self.assertEqual(explicit_code, og.EXIT_SUCCESS)
        env_payload = json.loads(env_buffer.getvalue())
        explicit_payload = json.loads(explicit_buffer.getvalue())
        env_options = env_payload["data"]["options"]
        explicit_options = explicit_payload["data"]["options"]

        self.assertEqual(env_options["profile"], "apply")
        self.assertEqual(env_options["mode"], "autonomous")
        self.assertEqual(env_options["output_mode"], og.OUTPUT_MODE_JSON)
        self.assertEqual(env_options["profile"], explicit_options["profile"])
        self.assertEqual(env_options["mode"], explicit_options["mode"])
        self.assertEqual(env_options["output_mode"], explicit_options["output_mode"])
        self.assertEqual(env_options["configuration"]["resolved_from"]["profile"], f"env:{og.DEFAULT_PROFILE_ENV}")
        self.assertEqual(env_options["configuration"]["resolved_from"]["mode"], "flag:--mode")
        self.assertEqual(env_options["configuration"]["resolved_from"]["output_mode"], f"env:{og.DEFAULT_OUTPUT_ENV}")
        self.assertEqual(explicit_options["configuration"]["resolved_from"]["profile"], "flag:--profile")
        self.assertEqual(explicit_options["configuration"]["resolved_from"]["mode"], "flag:--mode")
        self.assertEqual(explicit_options["configuration"]["resolved_from"]["output_mode"], "flag:--json")

    def test_apply_output_controls_supports_field_filtering_and_pagination(self) -> None:
        payload = {"status": "ok", "claims": [{"id": "b"}, {"id": "a"}], "message": "full"}
        shaped = og._apply_output_controls(
            payload,
            {"fields": ["claims"], "limit": 1, "offset": 0},
            output_mode=og.OUTPUT_MODE_JSONL,
        )

        self.assertNotIn("message", shaped)
        self.assertIn("claims", shaped)
        self.assertEqual(shaped["claims"], [{"id": "a"}])
        self.assertIn("list_window", shaped)
        self.assertEqual(shaped["list_window"]["claims"]["total"], 2)
        self.assertEqual(shaped["list_window"]["claims"]["returned"], 1)

    def test_emit_command_result_jsonl_streams_lists(self) -> None:
        payload = {
            "status": "ok",
            "claims": [{"id": "b"}, {"id": "a"}],
            "message": "full",
        }
        shaped = og._apply_output_controls(
            payload,
            {"fields": ["claims"], "limit": 1, "offset": 0},
            output_mode=og.OUTPUT_MODE_JSONL,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            og.emit_command_result_jsonl(shaped, "explain")
        lines = [json.loads(line) for line in (buffer.getvalue() or "").splitlines() if line.strip()]

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["command"], "explain")
        self.assertIn("list_window", lines[0]["data"])
        self.assertIn("claims", lines[0]["data"])
        self.assertTrue(lines[0]["data"]["claims"]["_streamed"])
        self.assertEqual(lines[1], {
            "event": "item",
            "command": "explain",
            "field": "claims",
            "index": 0,
            "item": {"id": "a"},
        })

    def test_parse_command_flags_rejects_invalid_identifiers(self) -> None:
        def parse_error(args: list[str]) -> str:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og.parse_command_flags(
                        args,
                        "explain",
                        False,
                        True,
                        True,
                        True,
                        allow_capsule_filter=True,
                        allow_ref_filter=True,
                        allow_certificate_filter=True,
                    )
            self.assertEqual(context.exception.code, og.EXIT_USAGE)
            payload = json.loads(buffer.getvalue() or "{}")
            return str(payload["errors"][0]["message"])

        cases = [
            (["--capsule", "../alpha"], "unsupported characters"),
            (["--ref", "bad%2fref"], "percent-encoded input"),
            (["--certificate", "cert\x00id"], "control characters"),
        ]
        for args, expected_fragment in cases:
            with self.subTest(args=args):
                message = parse_error(args)
                self.assertIn(expected_fragment, message)

    def test_parse_optimize_prompts_flags_rejects_bad_paths(self) -> None:
        valid_candidate = "candidate.txt"
        valid_baseline = "baseline.txt"

        def parse_error(args: list[str]) -> str:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og._parse_optimize_prompts_flags(args, True)
            self.assertEqual(context.exception.code, og.EXIT_USAGE)
            payload = json.loads(buffer.getvalue() or "{}")
            return str(payload["errors"][0]["message"])

        cases = [
            (["--dataset", "../datasets/base.json", "--candidate", valid_candidate, "--baseline", valid_baseline], "contains traversal segments"),
            (["--dataset", "/tmp/base.json", "--candidate", valid_candidate, "--baseline", valid_baseline], "must be repository-relative"),
            (["--dataset", "datasets/base.json", "--candidate", "candidate%2f.txt", "--baseline", valid_baseline], "percent-encoded input"),
            (["--dataset", "datasets/base.json", "--candidate", valid_candidate, "--baseline", "base\x00.txt"], "contains control characters"),
        ]
        for args, expected_fragment in cases:
            with self.subTest(args=args):
                message = parse_error(args)
                self.assertIn(expected_fragment, message)

    def test_parse_optimize_prompts_flags_supports_json_params(self) -> None:
        payload = {
            "dataset": "datasets/base.json",
            "candidate": "candidate.txt",
            "baseline": "baseline.txt",
            "metric": "exact",
            "min_improvement": 0.12,
            "approve": True,
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        try:
            options = og._parse_optimize_prompts_flags(["--params", payload_path], True)
        finally:
            Path(payload_path).unlink()

        self.assertEqual(options["dataset"], "datasets/base.json")
        self.assertEqual(options["candidate"], "candidate.txt")
        self.assertEqual(options["baseline"], "baseline.txt")
        self.assertEqual(options["metric"], "exact")
        self.assertEqual(options["min_improvement"], 0.12)
        self.assertTrue(options["approve"])

    def test_parse_optimize_prompts_flags_supports_json_params_from_stdin(self) -> None:
        payload = {
            "dataset": "datasets/base.json",
            "candidate": "candidate.txt",
            "baseline": "baseline.txt",
            "metric": "exact",
            "min_improvement": 0.05,
            "approve": False,
        }
        with patch("sys.stdin", io.StringIO(json.dumps(payload))):
            options = og._parse_optimize_prompts_flags(["--params", "-"], True)

        self.assertEqual(options["dataset"], "datasets/base.json")
        self.assertEqual(options["candidate"], "candidate.txt")
        self.assertEqual(options["baseline"], "baseline.txt")
        self.assertEqual(options["metric"], "exact")
        self.assertEqual(options["min_improvement"], 0.05)
        self.assertFalse(options["approve"])

    def test_parse_optimize_prompts_flags_prefer_convenience_flags_over_payload(self) -> None:
        payload = {
            "dataset": "datasets/payload.json",
            "candidate": "payload-candidate.txt",
            "baseline": "payload-baseline.txt",
            "metric": "contains",
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        try:
            options = og._parse_optimize_prompts_flags(
                [
                    "--params",
                    payload_path,
                    "--dataset",
                    "datasets/cli.json",
                    "--metric",
                    "exact",
                ],
                True,
            )
        finally:
            Path(payload_path).unlink()

        self.assertEqual(options["dataset"], "datasets/cli.json")
        self.assertEqual(options["metric"], "exact")
        self.assertEqual(options["candidate"], "payload-candidate.txt")
        self.assertEqual(options["baseline"], "payload-baseline.txt")

    def test_parse_optimize_prompts_flags_strict_rejects_unknown_and_implicit_defaults(self) -> None:
        strict_unknown = {
            "dataset": "datasets/base.json",
            "candidate": "candidate.txt",
            "baseline": "baseline.txt",
            "approval": True,
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(strict_unknown, handle)
            unknown_payload_path = handle.name
        try:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og._parse_optimize_prompts_flags(["--strict", "--params", unknown_payload_path], True, default_strict=True)
            self.assertEqual(context.exception.code, 64)
            payload = json.loads(buffer.getvalue() or "{}")
            self.assertIn("unknown params fields", payload["errors"][0]["message"])
        finally:
            Path(unknown_payload_path).unlink()

        strict_min_improvement = {
            "dataset": "datasets/base.json",
            "candidate": "candidate.txt",
            "baseline": "baseline.txt",
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(strict_min_improvement, handle)
            missing_payload_path = handle.name
        try:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og._parse_optimize_prompts_flags(["--params", missing_payload_path], True, default_strict=True)
            self.assertEqual(context.exception.code, 64)
            payload = json.loads(buffer.getvalue() or "{}")
            self.assertIn("strict mode requires --metric", payload["errors"][0]["message"])
        finally:
            Path(missing_payload_path).unlink()

    def test_parse_optimize_prompts_flags_strict_rejects_payload_lossy_types(self) -> None:
        payload = {
            "dataset": "datasets/base.json",
            "candidate": "candidate.txt",
            "baseline": "baseline.txt",
            "metric": "contains",
            "min_improvement": "12.5",
            "approve": "true",
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        try:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    og._parse_optimize_prompts_flags(["--params", payload_path], True, default_strict=True)
            self.assertEqual(context.exception.code, 64)
            response = json.loads(buffer.getvalue() or "{}")
            self.assertTrue(
                any("min-improvement" in str(error["message"]) for error in response["errors"]),
            )
        finally:
            Path(payload_path).unlink()

    def test_run_sync_job_short_circuits_when_idempotent(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
        }
        session = og._build_session_record(
            og.SESSION_KIND_SYNC,
            og.SESSION_LIFECYCLE_EPHEMERAL,
            og.SESSION_STATE_ACTIVE,
            session_id="sync-20260307t000000z-shortcircuit",
            created_at="2026-03-07T00:00:00Z",
            updated_at="2026-03-07T00:00:00Z",
            ttl_seconds=og.WORK_LOCK_STALE_SECONDS,
        )

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_compute_idempotency_key",
            return_value="stable-key",
        ), patch.object(og, "_read_work_state", return_value={"last_idempotency_key": "stable-key"}), patch.object(
            og,
            "_consume_pending",
            return_value=True,
        ), patch.object(og, "_record_sync_summary_event", return_value="events/sync-1.json"):
            payload = og._run_sync_job(
                str(self.repo),
                {"changed": False, "profile": "analyze", "mode": "observe"},
                session,
            )

        self.assertTrue(payload["short_circuit"])
        self.assertTrue(payload["pending_consumed"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["steps"][0]["name"], "short_circuit")
        self.assertEqual(payload["session_id"], session["session_id"])

    def test_run_sync_job_force_full_sync_bypasses_short_circuit(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
            "diff_baseline": {"strategy": "head~1"},
        }
        distill_result = {
            "name": "distill",
            "status": "ok",
            "message": "distill ok",
            "generated_deltas": [],
            "affected_capsules": ["default"],
        }
        apply_result = {
            "name": "apply",
            "status": "ok",
            "message": "apply ok",
            "applied_changes": 0,
            "changed_capsules": ["default"],
            "claims_written": [],
            "decision_ids": [],
            "certificate_ids": [],
            "certificate_refs": [],
            "errors": [],
        }
        verify_result = {
            "name": "verify",
            "status": "ok",
            "message": "verify ok",
            "verified_capsules": ["default"],
            "failed_capsules": [],
            "errors": [],
            "oracle_results": {},
            "receipt_pointers": {},
            "certificate_refs": [],
        }
        export_result = {
            "name": "export",
            "status": "ok",
            "message": "export ok",
            "updated_exports": [],
            "unchanged_exports": [],
            "artifact_counts": {},
            "artifact_total": 0,
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_compute_idempotency_key",
            return_value="stable-key",
        ), patch.object(og, "_read_work_state", return_value={"last_idempotency_key": "stable-key"}), patch.object(
            og,
            "_consume_pending",
            return_value=False,
        ), patch.object(
            og,
            "_run_distill_stage",
            return_value=distill_result,
        ) as run_distill, patch.object(
            og,
            "_run_apply_stage",
            return_value=apply_result,
        ), patch.object(
            og,
            "_run_verify_stage",
            return_value=verify_result,
        ), patch.object(
            og,
            "_run_export_stage",
            return_value=export_result,
        ), patch.object(
            og,
            "_record_sync_summary_event",
            return_value="events/sync-2.json",
        ):
            payload = og._run_sync_job(
                str(self.repo),
                {"changed": False, "profile": "analyze", "mode": "observe", "force_full_sync": True},
            )

        self.assertFalse(payload["short_circuit"])
        self.assertEqual(payload["status"], "ok")
        run_distill.assert_called_once()

    def test_export_refresh_remains_drift_free_when_snapshot_time_changes(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            with patch.object(
                og,
                "_utc_timestamp",
                side_effect=["2026-03-05T00:00:00Z", "2026-03-05T00:01:00Z"],
            ):
                updated_exports, unchanged_exports, _snapshot = og._run_export_refresh(str(self.repo))
                drift = og._collect_export_drift_check(str(self.repo))

        self.assertTrue(bool(updated_exports))
        self.assertEqual(unchanged_exports, [])
        self.assertIsNone(drift)
        self.assertNotIn(
            "Generated at:",
            (self.repo / ".outcomegraph" / "export" / "AGENTS.md").read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "generated_at",
            (self.repo / ".outcomegraph" / "export" / "mcp-resources.json").read_text(encoding="utf-8"),
        )

    def test_run_distill_stage_marks_pending_when_worker_is_unavailable(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_run_codex_worker", side_effect=og.WorkerAdapterError("codex executable was not found")
        ), patch.object(og, "_set_pending_state", return_value={"status": "ok"}) as set_pending:
            payload = og._run_distill_stage(str(self.repo), snapshot, "run-1", "analyze", "observe")

        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["code"], og.WORKER_RUNTIME_UNAVAILABLE_CODE)
        self.assertEqual(payload["errors"][0]["error_code"], og.WORKER_RUNTIME_UNAVAILABLE_CODE)
        self.assertIn("codex executable was not found", payload["errors"][0]["message"])
        set_pending.assert_called_once()

    def test_run_distill_worker_unavailable_errors_are_retryable_in_envelope(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_run_codex_worker", side_effect=og.WorkerAdapterError("codex executable was not found")
        ), patch.object(og, "_set_pending_state", return_value={"status": "ok"}):
            payload = og._run_distill_stage(str(self.repo), snapshot, "run-1", "analyze", "observe")

        envelope = og._build_command_result_envelope("distill", payload)
        distill_error = envelope["errors"][0]
        self.assertEqual(distill_error["error_code"], og.WORKER_RUNTIME_UNAVAILABLE_CODE)
        self.assertTrue(bool(distill_error["retryable"]))

    def test_run_distill_runtime_error_is_not_retryable_in_envelope(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(og, "_run_codex_worker", side_effect=og.WorkerAdapterError("executor crashed")):
            payload = og._run_distill_stage(str(self.repo), snapshot, "run-1", "analyze", "observe")

        envelope = og._build_command_result_envelope("distill", payload)
        distill_error = envelope["errors"][0]
        self.assertEqual(distill_error["error_code"], og.RUNTIME_ERROR_CODE)
        self.assertFalse(bool(distill_error["retryable"]))

    def test_run_distill_stage_returns_runtime_error_for_unexpected_worker_exception(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}

        with self.git_root_patch(), patch.object(og, "_run_codex_worker", side_effect=RuntimeError("boom")):
            payload = og._run_distill_stage(str(self.repo), snapshot, "run-1", "analyze", "observe")

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.RUNTIME_ERROR_CODE)
        self.assertIn("distill stage failed unexpectedly: boom", payload["message"])
        self.assertEqual(payload["errors"][0]["error_code"], og.RUNTIME_ERROR_CODE)

    def test_build_envelope_normalizes_legacy_string_errors(self) -> None:
        envelope = og._build_command_result_envelope(
            "sync",
            {
                "status": "error",
                "command": "sync",
                "message": "worker crashed",
                "errors": ["worker crashed during sync"],
            },
        )

        self.assertEqual(len(envelope["errors"]), 1)
        first_error = envelope["errors"][0]
        self.assertEqual(first_error["error_code"], og.RUNTIME_ERROR_CODE)
        self.assertEqual(first_error["message"], "worker crashed during sync")
        self.assertFalse(first_error["retryable"])

    def test_run_sync_job_sets_failed_message_when_any_stage_errors(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
        }
        distill_result = {
            "name": "distill",
            "status": "error",
            "message": "distill failed",
            "affected_capsules": [],
            "generated_deltas": [],
        }
        apply_result = {"name": "apply", "status": "skipped", "message": "apply skipped"}
        verify_result = {
            "name": "verify",
            "status": "skipped",
            "message": "verify skipped",
            "verified_capsules": [],
            "failed_capsules": [],
            "errors": [],
            "oracle_results": {},
            "receipt_pointers": {},
        }
        export_result = {
            "name": "export",
            "status": "ok",
            "message": "export ok",
            "updated_exports": [],
            "unchanged_exports": [],
            "artifact_counts": {},
            "artifact_total": 0,
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_compute_idempotency_key",
            return_value="sync-key",
        ), patch.object(og, "_read_work_state", return_value={}), patch.object(
            og,
            "_consume_pending",
            return_value=False,
        ), patch.object(
            og,
            "_run_distill_stage",
            return_value=distill_result,
        ), patch.object(
            og,
            "_run_apply_stage",
            return_value=apply_result,
        ), patch.object(
            og,
            "_run_verify_stage",
            return_value=verify_result,
        ), patch.object(
            og,
            "_run_export_stage",
            return_value=export_result,
        ), patch.object(
            og,
            "_record_sync_summary_event",
            return_value="events/sync-2.json",
        ):
            payload = og._run_sync_job(str(self.repo), {"changed": False, "profile": "analyze", "mode": "observe"})

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["message"], "sync workflow failed")

    def test_run_sync_job_warn_keeps_runtime_idle(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
        }
        distill_result = {
            "name": "distill",
            "status": "ok",
            "message": "distill ok",
            "generated_deltas": [],
            "affected_capsules": ["default"],
        }
        apply_result = {"name": "apply", "status": "warn", "message": "apply warned", "warnings": ["partial evidence"]}
        verify_result = {
            "name": "verify",
            "status": "warn",
            "message": "verify warned",
            "verified_capsules": ["default"],
            "failed_capsules": [],
            "errors": [],
            "warnings": ["policy skipped one oracle"],
            "oracle_results": {},
            "receipt_pointers": {},
            "certificate_refs": [],
        }
        export_result = {
            "name": "export",
            "status": "ok",
            "message": "export ok",
            "updated_exports": [],
            "unchanged_exports": [],
            "artifact_counts": {},
            "artifact_total": 0,
        }

        with self.git_root_patch():
            og._init_outcomegraph()
            with patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
                og,
                "_compute_idempotency_key",
                return_value="sync-warn-key",
            ), patch.object(og, "_read_work_state", return_value={}), patch.object(
                og,
                "_consume_pending",
                return_value=False,
            ), patch.object(
                og,
                "_run_distill_stage",
                return_value=distill_result,
            ), patch.object(
                og,
                "_run_apply_stage",
                return_value=apply_result,
            ), patch.object(
                og,
                "_run_verify_stage",
                return_value=verify_result,
            ), patch.object(
                og,
                "_run_export_stage",
                return_value=export_result,
            ), patch.object(
                og,
                "_record_sync_summary_event",
                return_value="events/sync-warn.json",
            ):
                payload = og._run_sync_job(str(self.repo), {"changed": False, "profile": "analyze", "mode": "observe"})

            work_state = json.loads((self.repo / ".outcomegraph" / "work" / "state.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "warn")
        self.assertEqual(payload["message"], "sync workflow completed with warnings")
        self.assertEqual(work_state["status"], "idle")
        self.assertEqual(work_state["last_message"], "sync finished (warn)")

    def test_run_sync_job_apply_warn_only_keeps_overall_status_ok(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
        }
        distill_result = {
            "name": "distill",
            "status": "ok",
            "message": "distill ok",
            "generated_deltas": [],
            "affected_capsules": ["default"],
        }
        apply_result = {"name": "apply", "status": "warn", "message": "apply warned", "warnings": ["partial evidence"]}
        verify_result = {
            "name": "verify",
            "status": "ok",
            "message": "verify ok",
            "verified_capsules": ["default"],
            "failed_capsules": [],
            "errors": [],
            "warnings": [],
            "oracle_results": {},
            "receipt_pointers": {},
            "certificate_refs": [],
        }
        export_result = {
            "name": "export",
            "status": "ok",
            "message": "export ok",
            "updated_exports": [],
            "unchanged_exports": [],
            "artifact_counts": {},
            "artifact_total": 0,
        }

        with self.git_root_patch():
            og._init_outcomegraph()
            with patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
                og,
                "_compute_idempotency_key",
                return_value="sync-apply-warn-key",
            ), patch.object(og, "_read_work_state", return_value={}), patch.object(
                og,
                "_consume_pending",
                return_value=False,
            ), patch.object(
                og,
                "_run_distill_stage",
                return_value=distill_result,
            ), patch.object(
                og,
                "_run_apply_stage",
                return_value=apply_result,
            ), patch.object(
                og,
                "_run_verify_stage",
                return_value=verify_result,
            ), patch.object(
                og,
                "_run_export_stage",
                return_value=export_result,
            ), patch.object(
                og,
                "_record_sync_summary_event",
                return_value="events/sync-apply-warn.json",
            ):
                payload = og._run_sync_job(str(self.repo), {"changed": False, "profile": "analyze", "mode": "observe"})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["message"], "sync workflow completed")


class TestIntegrityValidation(_RepoTestCase):
    def _build_verified_events(self) -> None:
        og._init_outcomegraph()
        for index in range(1, 13):
            og._append_ledger_event(
                str(self.repo),
                {
                    "schema_version": 2,
                    "artifact_type": "verify",
                    "id": f"event-{index:02d}",
                    "status": "ok",
                    "created_at": f"2026-03-05T00:{index:02d}:00Z",
                },
            )

    def _build_checkpoint_at_sequence(self, sequence: int) -> None:
        target_path = self.repo / ".outcomegraph" / "events" / f"event-{sequence:02d}.json"
        payload = json.loads(target_path.read_text(encoding="utf-8"))
        og._write_integrity_checkpoint(
            str(self.repo),
            sequence,
            str(payload["id"]),
            str(payload["event_hash"]),
            str(payload["previous_event_hash"]),
        )

    def test_validate_event_chain_skips_events_covered_by_latest_checkpoint(self) -> None:
        with self.git_root_patch():
            self._build_verified_events()
            self._build_checkpoint_at_sequence(10)

            bad_payload = json.loads((self.repo / ".outcomegraph" / "events" / "event-05.json").read_text(encoding="utf-8"))
            bad_payload["event_hash"] = "sha256:invalid"
            og._write_json_file(str(self.repo / ".outcomegraph" / "events" / "event-05.json"), bad_payload)

            result = og._validate_event_chain(str(self.repo))
            newest_event = json.loads((self.repo / ".outcomegraph" / "events" / "event-12.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["event_sequence"], 12)
        self.assertEqual(result["event_hash"], str(newest_event["event_hash"]))

    def test_validate_event_chain_uses_checkpoint_previous_event_hash(self) -> None:
        with self.git_root_patch():
            self._build_verified_events()
            self._build_checkpoint_at_sequence(10)

            broken_payload = json.loads((self.repo / ".outcomegraph" / "events" / "event-11.json").read_text(encoding="utf-8"))
            broken_payload["previous_event_hash"] = "sha256:invalid-previous"
            og._write_json_file(str(self.repo / ".outcomegraph" / "events" / "event-11.json"), broken_payload)

            result = og._validate_event_chain(str(self.repo))

        self.assertEqual(result["status"], "degraded")
        self.assertIn("integrity link break at event #11", result["message"])
        self.assertEqual(result["event_count"], 10)


class TestVerifyWorkflows(_RepoTestCase):
    def test_run_verify_stage_reports_failed_oracle(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            (self.repo / ".outcomegraph" / "policy.yaml").write_text(
                """schema_version: 2\nmode: observe\nallow:\n  file_writes:\n    - \".outcomegraph/**\"\n  verify_commands:\n    - \"exit 1\"\n  sandbox_operations:\n    - read_artifacts\n""",
                encoding="utf-8",
            )
            with patch.object(
                og,
                "_load_capsule_oracles",
                return_value=[{"name": "bad-oracle", "command": "exit 1", "scope": []}],
            ):
                payload = og._run_verify_stage(
                    str(self.repo),
                    ["default"],
                    ["capsules/default.yaml"],
                    "run-verify",
                    "observe",
                )

        self.assertEqual(payload["status"], "error")
        self.assertIn("default", payload["failed_capsules"])
        self.assertEqual(payload["verified_capsules"], ["default"])

    def test_run_verify_job_executes_yaml_oracle_and_does_not_issue_success_certificate(self) -> None:
        snapshot = {
            "changed_files": ["capsules/default.yaml"],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 1,
            "has_changes": True,
            "captured_at": "2026-03-05T00:00:00Z",
        }
        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot):
            og._init_outcomegraph()
            (self.repo / ".outcomegraph" / "policy.yaml").write_text(
                (
                    "schema_version: 2\n"
                    "mode: observe\n"
                    "allow:\n"
                    "  verify_commands:\n"
                    "    - \"false\"\n"
                    "  sandbox_operations:\n"
                    "    - read_artifacts\n"
                ),
                encoding="utf-8",
            )
            (self.repo / ".outcomegraph" / "capsules" / "default.yaml").write_text(
                (
                    "schema_version: 2\n"
                    "artifact_type: capsule\n"
                    "id: default\n"
                    "oracles:\n"
                    "  - name: yaml-fail\n"
                    "    command: \"false\"\n"
                ),
                encoding="utf-8",
            )

            payload = og._run_verify_job(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["oracle_results"]["default"][0]["command"], "false")
        self.assertEqual(payload["oracle_results"]["default"][0]["status"], "fail")
        self.assertEqual(payload["certificate_refs"], [])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_verify_stage_reports_invalid_yaml_oracle_configuration(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            (self.repo / ".outcomegraph" / "capsules" / "default.yaml").write_text(
                (
                    "schema_version: 2\n"
                    "artifact_type: capsule\n"
                    "id: default\n"
                    "oracles:\n"
                    "  - name: broken\n"
                    "    command\n"
                ),
                encoding="utf-8",
            )

            payload = og._run_verify_stage(
                str(self.repo),
                ["default"],
                ["capsules/default.yaml"],
                "run-verify",
                "observe",
            )

        self.assertEqual(payload["status"], "error")
        self.assertIn("invalid oracle configuration", payload["message"])
        self.assertIn("default", payload["failed_capsules"])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_verify_stage_blocks_denied_certificate_writes_before_partial_mutation(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            (
                "schema_version: 2\n"
                "mode: observe\n"
                "allow:\n"
                "  sandbox_operations:\n"
                "    - read_artifacts\n"
                "  file_writes:\n"
                "    - \".outcomegraph/claims/**\"\n"
                "deny:\n"
                "  file_writes:\n"
                "    - \".outcomegraph/certificates/**\"\n"
            ),
            encoding="utf-8",
        )

        with self.git_root_patch():
            payload = og._run_verify_stage(
                str(self.repo),
                ["default"],
                ["capsules/default.yaml"],
                "run-verify",
                "observe",
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["category"], "file_writes")
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "claims").glob("*.json")), [])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_verify_job_with_no_changed_capsules_skips_stage(self) -> None:
        snapshot = {
            "changed_files": [],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 0,
            "has_changes": False,
            "captured_at": "2026-03-04T00:00:00Z",
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_record_verify_summary_event",
            return_value="events/verify-1.json",
        ), patch.object(
            og,
            "_list_known_capsules",
            return_value=[],
        ):
            payload = og._run_verify_job(
                str(self.repo),
                {"changed": False, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["verified_capsules"], [])
        self.assertEqual(payload["changed_only"], True)

    def test_run_verify_job_refreshes_exports_after_writing_verify_artifacts(self) -> None:
        snapshot = {
            "changed_files": ["capsules/default.yaml"],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 1,
            "has_changes": True,
            "captured_at": "2026-03-05T00:00:00Z",
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot):
            og._init_outcomegraph()
            payload = og._run_verify_job(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )
            drift = og._collect_export_drift_check(str(self.repo))

        self.assertEqual(payload["steps"][-1]["name"], "export")
        self.assertEqual(payload["steps"][-1]["status"], "ok")
        self.assertIsNone(drift)

    def test_run_verify_job_skips_export_refresh_after_verify_failure(self) -> None:
        snapshot = {
            "changed_files": ["capsules/default.yaml"],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 1,
            "has_changes": True,
            "captured_at": "2026-03-05T00:00:00Z",
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot):
            (self.repo / ".outcomegraph" / "capsules").mkdir(parents=True)
            (self.repo / ".outcomegraph" / "capsules" / "default.yaml").write_text(
                "schema_version: 2\nid: default\n",
                encoding="utf-8",
            )
            payload = og._run_verify_job(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual([step["name"] for step in payload["steps"]], ["verify"])
        self.assertFalse((self.repo / ".outcomegraph" / "export" / "AGENTS.md").exists())
        self.assertFalse((self.repo / "skills" / "outcome-steward" / "SKILL.md").exists())


class TestReplayWorkflows(_RepoTestCase):
    def test_capsule_is_advisory_for_replay_for_skill_capsules(self) -> None:
        capsule_payload = {
            "id": "skill-og-dogfood",
            "kind": "code",
            "status": "success",
            "scope": ["skills/og-dogfood/SKILL.md"],
        }

        self.assertTrue(og._capsule_is_advisory_for_replay(capsule_payload))

    def test_validate_replay_plan_contract_rejects_out_of_scope_test_step_paths(self) -> None:
        fixture = _write_replayable_capsule_fixture(
            self.repo,
            capsule_id="skill-og-dogfood",
            source_path="skills/og-dogfood/SKILL.md",
            oracle_command="uv run --with pytest --no-project pytest -q tests/test_og_sync_verify_replay_hooks.py",
            capsule_kind="code",
        )
        plan = _build_replay_plan_fixture(
            "run-1",
            fixture,
            steps=[
                {
                    "command": "uv run --with pytest --no-project pytest -q tests/test_og_sync_verify_replay_hooks.py",
                    "cwd": ".",
                    "expected_exit_code": 0,
                    "timeout_s": 900,
                }
            ],
            status="ok",
        )

        failures = og._validate_replay_plan_contract(
            "run-1",
            "skill-og-dogfood",
            plan,
            fixture["capsule_payload"],
            fixture["scope_materials"],
            fixture["oracles"],
            {},
        )

        self.assertTrue(any("outside capsule scope/material inputs" in failure for failure in failures))

    def test_validate_replay_plan_contract_backfills_missing_baseline_hash(self) -> None:
        fixture = _write_replayable_capsule_fixture(self.repo)
        plan = _build_replay_plan_fixture("run-1", fixture, baseline_hash=None)

        failures = og._validate_replay_plan_contract(
            "run-1",
            "default",
            plan,
            fixture["capsule_payload"],
            fixture["scope_materials"],
            fixture["oracles"],
            {"oracle_digest": "sha256:baseline-equivalence-hash"},
        )

        self.assertEqual(failures, [])
        self.assertEqual(
            plan["equivalence_inputs"]["baseline_hash"],
            "sha256:baseline-equivalence-hash",
        )

    def test_run_replay_step_rejects_prefix_based_cwd_escape(self) -> None:
        sandbox_root = f"{og.OG_ROOT}/work/replay/run-1/default"
        observed: dict[str, object] = {}

        def fake_subprocess_run(command, cwd, capture_output, text, timeout):
            observed["command"] = command
            observed["cwd"] = cwd
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="ok\n",
                stderr="",
            )

        step = {
            "command": "echo ok",
            "cwd": "nested/../../default-escape",
            "expected_exit_code": 0,
        }
        with patch.object(og.subprocess, "run", side_effect=fake_subprocess_run):
            payload = og._run_replay_step(
                repo_root=str(self.repo),
                sandbox_root=sandbox_root,
                run_id="run-1",
                capsule_id="default",
                step_index=0,
                step=step,
            )

        expected_cwd = str((self.repo / sandbox_root).resolve())
        self.assertEqual(observed["command"], ["echo", "ok"])
        self.assertEqual(observed["cwd"], expected_cwd)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["resolved_cwd"], ".")

    def test_run_replay_step_executes_with_bash_shell(self) -> None:
        sandbox_root = f"{og.OG_ROOT}/work/replay/run-1/default"
        observed: dict[str, object] = {}

        def fake_subprocess_run(command, cwd, capture_output, text, timeout):
            observed["command"] = command
            observed["cwd"] = cwd
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="ok\n",
                stderr="",
            )

        step = {
            "command": "set -euo pipefail\nprintf 'ok\\n'",
            "cwd": ".",
            "expected_exit_code": 0,
        }
        with patch.object(og.subprocess, "run", side_effect=fake_subprocess_run):
            payload = og._run_replay_step(
                repo_root=str(self.repo),
                sandbox_root=sandbox_root,
                run_id="run-1",
                capsule_id="default",
                step_index=0,
                step=step,
            )

        expected_cwd = str((self.repo / sandbox_root).resolve())
        self.assertEqual(observed["command"], ["bash", "-lc", "set -euo pipefail\nprintf 'ok\\n'"])
        self.assertEqual(observed["cwd"], expected_cwd)
        self.assertEqual(payload["status"], "pass")

    def test_run_replay_stage_defaults_to_default_capsule_when_no_targets(self) -> None:
        snapshot = {"changed_files": []}
        fixture = _write_replayable_capsule_fixture(self.repo)
        replay_plan = _build_replay_plan_fixture("run-1", fixture)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=[]
        ), patch.object(og, "_list_known_capsules", return_value=[]), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og, "_run_codex_worker", return_value=(replay_plan, []),
        ):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["replay_results"]), 1)
        self.assertEqual(payload["replay_results"][0]["capsule_id"], "default")
        self.assertEqual(payload["replay_results"][0]["status"], "success")
        self.assertTrue(payload["certificate_ids"][0].startswith("cert-default-"))

    def test_run_replay_job_refreshes_exports_after_writing_replay_artifacts(self) -> None:
        snapshot = {
            "changed_files": ["capsules/default.yaml"],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 1,
            "has_changes": True,
            "captured_at": "2026-03-05T00:00:00Z",
        }
        fixture = _write_replayable_capsule_fixture(self.repo)

        def build_replay_plan(role, payload, repo_root, trace_path, adapter=None, timeout_seconds=120):
            return (_build_replay_plan_fixture(str(payload["run_id"]), fixture), [])

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_run_codex_worker",
            side_effect=build_replay_plan,
        ), patch.object(
            og,
            "_collect_changed_materials",
            return_value=[],
        ):
            og._init_outcomegraph()
            payload = og._run_replay_job(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )
            drift = og._collect_export_drift_check(str(self.repo))

        self.assertEqual(payload["steps"][-1]["name"], "export")
        self.assertEqual(payload["steps"][-1]["status"], "ok")
        self.assertIsNone(drift)

    def test_run_replay_job_skips_export_refresh_after_replay_failure(self) -> None:
        snapshot = {
            "changed_files": ["capsules/default.yaml"],
            "repository_head": "abc123",
            "branch": "main",
            "changed_count": 1,
            "has_changes": True,
            "captured_at": "2026-03-05T00:00:00Z",
        }

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot):
            (self.repo / ".outcomegraph" / "capsules").mkdir(parents=True)
            (self.repo / ".outcomegraph" / "capsules" / "default.yaml").write_text(
                "schema_version: 2\nid: default\n",
                encoding="utf-8",
            )
            payload = og._run_replay_job(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual([step["name"] for step in payload["steps"]], ["replay"])
        self.assertFalse((self.repo / ".outcomegraph" / "export" / "AGENTS.md").exists())
        self.assertFalse((self.repo / "skills" / "outcome-steward" / "SKILL.md").exists())

    def test_run_replay_stage_fails_clearly_when_capsule_lacks_executable_regeneration_inputs(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
        fixture = _write_replayable_capsule_fixture(self.repo, oracle_command=None)
        replay_plan = _build_replay_plan_fixture("run-1", fixture)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og,
            "_run_codex_worker",
            return_value=(replay_plan, []),
        ):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["replay_results"][0]["status"], "failed")
        self.assertIn(
            "lacks executable acceptance oracles for regeneration proof",
            " ".join(payload["replay_results"][0]["failures"]),
        )
        self.assertEqual(payload["certificate_ids"], [])
        self.assertEqual(payload["failed_capsules"], ["default"])

    def test_run_replay_stage_skips_missing_capsule_metadata_in_observe_mode(self) -> None:
        snapshot = {"changed_files": ["src/main.py"]}
        source_file = self.repo / "src" / "main.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("print('hello')\n", encoding="utf-8")

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["src"]
        ), patch.object(
            og,
            "_run_worker_with_retries",
        ) as run_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["failed_capsules"], [])
        self.assertEqual(payload["replay_results"][0]["status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["plan_status"], "pending")
        self.assertTrue(payload["replay_results"][0]["bootstrap_missing_capsule"])
        self.assertIn("Run `og sync --json`", " ".join(payload["replay_results"][0]["failures"]))
        run_worker.assert_not_called()

    def test_run_replay_stage_fails_missing_capsule_metadata_in_enforce_mode(self) -> None:
        snapshot = {"changed_files": ["src/main.py"]}
        source_file = self.repo / "src" / "main.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("print('hello')\n", encoding="utf-8")

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["src"]
        ), patch.object(
            og,
            "_run_worker_with_retries",
        ) as run_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "enforce",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["failed_capsules"], ["src"])
        self.assertEqual(payload["replay_results"][0]["status"], "failed")
        self.assertEqual(payload["replay_results"][0]["plan_status"], "pending")
        self.assertTrue(payload["replay_results"][0]["bootstrap_missing_capsule"])
        self.assertIn("Run `og sync --json`", " ".join(payload["replay_results"][0]["failures"]))
        run_worker.assert_not_called()

    def test_run_replay_stage_skips_doc_capsule_without_executable_oracles(self) -> None:
        snapshot = {"changed_files": ["README.md"]}
        fixture = _write_replayable_capsule_fixture(
            self.repo,
            capsule_id="default",
            source_path="README.md",
            oracle_command=None,
            capsule_kind=og.CAPSULE_KIND_DOC,
        )

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og,
            "_run_codex_worker",
        ) as run_codex_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["failed_capsules"], [])
        self.assertEqual(payload["certificate_ids"], [])
        self.assertEqual(payload["replay_results"][0]["status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["plan_status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["material_inputs"], fixture["scope_materials"])
        run_codex_worker.assert_not_called()

    def test_run_replay_stage_skips_warn_code_capsule_without_executable_oracles(self) -> None:
        snapshot = {"changed_files": ["skills/example.sh"]}
        fixture = _write_replayable_capsule_fixture(
            self.repo,
            capsule_id="default",
            source_path="skills/example.sh",
            oracle_command=None,
            capsule_kind=og.CAPSULE_KIND_CODE,
        )
        capsule_path = self.repo / ".outcomegraph" / "capsules" / "default.json"
        capsule_payload = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule_payload["status"] = "warn"
        capsule_path.write_text(json.dumps(capsule_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og,
            "_run_codex_worker",
        ) as run_codex_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["failed_capsules"], [])
        self.assertEqual(payload["replay_results"][0]["status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["plan_status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["material_inputs"], fixture["scope_materials"])
        run_codex_worker.assert_not_called()

    def test_discover_replay_support_paths_includes_explicit_repo_file_references(self) -> None:
        test_path = self.repo / "tests" / "test_contract.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(
            (
                "from pathlib import Path\n\n"
                "PYPROJECT = Path(__file__).resolve().parents[1] / 'pyproject.toml'\n"
                "CONTEXT = Path(__file__).resolve().parents[1] / 'CONTEXT.md'\n"
            ),
            encoding="utf-8",
        )
        (self.repo / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
        (self.repo / "CONTEXT.md").write_text("context\n", encoding="utf-8")

        discovered = og._discover_replay_support_paths(str(self.repo), ["tests/test_contract.py"])

        self.assertEqual(discovered, ["CONTEXT.md", "pyproject.toml"])

    def test_discover_replay_support_paths_scans_late_reference_in_large_file(self) -> None:
        test_path = self.repo / "tests" / "test_contract.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        filler = "".join(f"FILLER_{index:05d} = 'xxxxxxxx'\n" for index in range(6000))
        test_path.write_text(filler + "REPO_CONTEXT = 'CONTEXT.md'\n", encoding="utf-8")
        (self.repo / "CONTEXT.md").write_text("context\n", encoding="utf-8")

        discovered = og._discover_replay_support_paths(str(self.repo), ["tests/test_contract.py"])

        self.assertEqual(discovered, ["CONTEXT.md"])

    def test_run_replay_stage_skips_warn_capsule_when_replay_plan_is_pending(self) -> None:
        snapshot = {"changed_files": ["skills/example.sh"]}
        fixture = _write_replayable_capsule_fixture(
            self.repo,
            source_path="skills/example.sh",
            capsule_kind=og.CAPSULE_KIND_CODE,
        )
        capsule_path = self.repo / ".outcomegraph" / "capsules" / "default.json"
        capsule_payload = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule_payload["status"] = "warn"
        capsule_path.write_text(json.dumps(capsule_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        replay_plan = _build_replay_plan_fixture("run-1", fixture, status="pending", message="inputs incomplete")
        replay_plan["acceptance_checks"] = []
        replay_plan["equivalence_inputs"] = {
            **dict(replay_plan["equivalence_inputs"]),
            "oracle_names": [],
        }

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og, "_run_worker_with_retries", return_value=(replay_plan, [], {})
        ) as run_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["failed_capsules"], [])
        self.assertEqual(payload["certificate_ids"], [])
        self.assertEqual(payload["replay_results"][0]["status"], "skipped")
        self.assertEqual(payload["replay_results"][0]["plan_status"], "pending")
        self.assertIn("not replay-complete", " ".join(payload["replay_results"][0]["failures"]))
        run_worker.assert_called_once()

    def test_run_replay_stage_error_message_ignores_skipped_capsules(self) -> None:
        snapshot = {"changed_files": ["README.md", "src/default.py"]}
        _write_replayable_capsule_fixture(
            self.repo,
            capsule_id="doc",
            source_path="README.md",
            oracle_command=None,
            capsule_kind=og.CAPSULE_KIND_DOC,
        )
        failing_fixture = _write_replayable_capsule_fixture(
            self.repo,
            capsule_id="default",
            source_path="src/default.py",
            oracle_command=None,
            capsule_kind=og.CAPSULE_KIND_CODE,
        )
        replay_plan = _build_replay_plan_fixture("run-1", failing_fixture)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["doc", "default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og, "_run_worker_with_retries", return_value=(replay_plan, [], {})
        ) as run_worker:
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["replay_results"][0]["status"], "skipped")
        self.assertEqual(payload["replay_results"][1]["status"], "failed")
        self.assertNotIn("Replay skipped for doc", payload["errors"][0]["message"])
        self.assertIn("lacks executable acceptance oracles", payload["errors"][0]["message"])
        run_worker.assert_called_once()

    def test_run_replay_stage_errors_on_adapter_interface_mismatch(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
        _write_replayable_capsule_fixture(self.repo)
        bad_replay_plan = {
            "schema_version": 1,
            "interface_version": 99,
            "run_id": "run-1",
            "capsule_id": "default",
            "steps": [{"command": "echo ok"}],
            "status": "ok",
        }

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_collect_changed_materials", return_value=[]
        ), patch.object(
            og,
            "_run_codex_worker",
            return_value=(bad_replay_plan, []),
        ):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["replay_results"][0]["status"], "error")
        self.assertEqual(payload["code"], og.RUNTIME_ERROR_CODE)
        self.assertIn("schema_version must be 2", payload["errors"][0]["message"])

    def test_run_replay_stage_worker_unavailable_errors_are_retryable_in_envelope(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
        _write_replayable_capsule_fixture(self.repo)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(og, "_collect_changed_materials", return_value=[]), patch.object(
            og, "_run_codex_worker", side_effect=og.WorkerAdapterError("codex executable was not found")
        ), patch.object(og, "_set_pending_state", return_value={"status": "ok"}):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        envelope = og._build_command_result_envelope("replay", payload)
        self.assertEqual(payload["code"], og.WORKER_RUNTIME_UNAVAILABLE_CODE)
        self.assertEqual(payload["replay_results"][0]["status"], "pending")
        self.assertEqual(envelope["errors"][0]["error_code"], og.WORKER_RUNTIME_UNAVAILABLE_CODE)
        self.assertTrue(bool(envelope["errors"][0]["retryable"]))

    def test_run_replay_stage_runtime_errors_are_not_retryable_in_envelope(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
        _write_replayable_capsule_fixture(self.repo)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(og, "_collect_changed_materials", return_value=[]), patch.object(
            og, "_run_codex_worker", side_effect=og.WorkerAdapterError("executor crashed")
        ):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
            )

        envelope = og._build_command_result_envelope("replay", payload)
        self.assertEqual(payload["code"], og.RUNTIME_ERROR_CODE)
        self.assertEqual(payload["replay_results"][0]["status"], "error")
        self.assertEqual(envelope["errors"][0]["error_code"], og.RUNTIME_ERROR_CODE)
        self.assertFalse(bool(envelope["errors"][0]["retryable"]))

    def test_run_replay_stage_retries_transient_worker_timeout(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
        fixture = _write_replayable_capsule_fixture(self.repo)
        replay_plan = _build_replay_plan_fixture("run-1", fixture)

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(og, "_collect_changed_materials", return_value=[]), patch.object(
            og,
            "_run_codex_worker",
            side_effect=[
                og.WorkerAdapterError("codex exec timed out after 5s (replay)"),
                (replay_plan, []),
            ],
        ):
            payload = og._run_replay_stage(
                str(self.repo),
                snapshot,
                "run-1",
                "analyze",
                "observe",
                changed_only=True,
                timeout_seconds=5,
                max_retries=1,
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["recovery"]["retried_operations"], 1)
        self.assertEqual(payload["recovery"]["recovered_operations"], 1)
        self.assertEqual(payload["recovery"]["details"][0]["timeout_seconds"], 5)


class TestVerifyRecovery(_RepoTestCase):
    def test_run_verify_stage_timeout_errors_are_retryable_in_envelope(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            policy = {
                "schema_version": 2,
                "mode": "observe",
                "allow": {
                    "file_writes": [".outcomegraph/**", "export/**", "skills/outcome-steward/**"],
                    "verify_commands": ["sleep 1"],
                    "sandbox_operations": ["read_artifacts"],
                },
                "deny": {
                    "file_writes": ["src/**"],
                    "network": [],
                    "dependencies": [],
                    "deployment": [],
                    "verify_commands": [],
                    "sandbox_operations": [],
                },
            }

            with patch.object(
                og,
                "_load_capsule_oracles",
                return_value=[{"name": "slow-oracle", "command": "sleep 1", "scope": []}],
            ), patch.object(
                og.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="sleep 1", timeout=1),
            ):
                payload = og._run_verify_stage(
                    str(self.repo),
                    ["default"],
                    ["og.py"],
                    "run-1",
                    "observe",
                    policy=policy,
                    timeout_seconds=1,
                    max_retries=1,
                )

        envelope = og._build_command_result_envelope("verify", payload)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.TIMEOUT_EXPIRED_CODE)
        self.assertTrue(bool(envelope["errors"][0]["retryable"]))
        self.assertEqual(payload["recovery"]["exhausted_operations"], 1)

    def test_exit_code_maps_error_class_semantics(self) -> None:
        self.assertEqual(
            og._command_exit_code(
                {
                    "status": "error",
                    "errors": [{"error_code": og.USAGE_ERROR_CODE, "message": "bad flags"}],
                }
            ),
            og.EXIT_USAGE,
        )
        self.assertEqual(
            og._command_exit_code(
                {
                    "status": "error",
                    "errors": [
                        {
                            "error_code": og.POLICY_CONFIG_ERROR_CODE,
                            "error_class": og.ERROR_CLASS_POLICY,
                            "message": "policy failed",
                        }
                    ],
                }
            ),
            og.EXIT_USAGE,
        )
        self.assertEqual(
            og._command_exit_code(
                {
                    "status": "error",
                    "errors": [{"error_code": og.RUNTIME_ERROR_CODE, "message": "worker crashed"}],
                }
            ),
            og.EXIT_RUNTIME,
        )


class TestAdapterCompatibilityAndPolicy(_RepoTestCase):
    def test_run_codex_worker_requires_matching_interface(self) -> None:
        with self.git_root_patch(), patch.object(
            og,
            "_build_worker_manifest",
            return_value={
                "schema_version": 2,
                "type": "worker",
                "name": "codex",
                "implementation_version": "1.0.0",
                "interface_version": 2,
                "capabilities": ["distill", "replay", "explain"],
                "entrypoint": "codex://v1",
            },
        ):
            with self.assertRaises(og.WorkerAdapterError) as context:
                og._run_codex_worker("distill", {}, str(self.repo), "trace.json")

        self.assertEqual(str(context.exception), "worker interface version mismatch")

    def test_run_codex_worker_rejects_incompatible_manifest_schema(self) -> None:
        with self.git_root_patch(), patch.object(
            og,
            "_build_worker_manifest",
            return_value={
                "schema_version": 1,
                "type": "worker",
                "name": "codex",
                "implementation_version": "1.0.0",
                "interface_version": 1,
                "capabilities": ["distill", "replay", "explain"],
                "entrypoint": "codex://v1",
            },
        ):
            with self.assertRaises(og.WorkerAdapterError) as context:
                og._run_codex_worker("distill", {"run_id": "run-1"}, str(self.repo), "trace.json")

        self.assertEqual(str(context.exception), "worker manifest schema mismatch")

    def test_policy_yaml_preserves_colon_containing_verify_commands(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            (
                "schema_version: 2\n"
                "mode: observe\n"
                "allow:\n"
                "  verify_commands:\n"
                "    - npm run lint:ci\n"
                "    - python -m pkg.module:main\n"
                "  sandbox_operations:\n"
                "    - read_artifacts\n"
            ),
            encoding="utf-8",
        )

        policy, error = og._resolve_policy_for_repo(str(self.repo))

        self.assertIsNone(error)
        self.assertIn("npm run lint:ci", policy["allow"]["verify_commands"])
        self.assertIn("python -m pkg.module:main", policy["allow"]["verify_commands"])
        self.assertIsNone(
            og._ensure_policy_action_allowed(
                policy,
                command="verify",
                category="verify_commands",
                target="npm run lint:ci",
                mode="observe",
            )
        )

    def test_parse_worker_output_extracts_contract_from_event_stream(self) -> None:
        payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-1",
            "capsule_updates": [
                {
                    "id": "default",
                    **{key: value for key, value in _distill_update("default", ["capsules/default.yaml"]).items() if key != "id"},
                }
            ],
        }
        event_lines = [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(payload)}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}),
        ]
        parsed = og._parse_worker_output("distill", "\n".join(event_lines))
        self.assertEqual(parsed["schema_version"], 2)
        self.assertEqual(parsed["run_id"], "run-1")
        self.assertEqual(parsed["capsule_updates"][0]["id"], "default")

    def test_normalize_distill_delta_accepts_capsule_id_alias(self) -> None:
        payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-1",
            "capsule_updates": [
                {
                    "capsule_id": "default",
                    **{key: value for key, value in _distill_update("default", ["capsules/default.yaml"]).items() if key != "id"},
                }
            ],
        }

        parsed = og._normalize_distill_delta(payload)
        self.assertEqual(parsed["capsule_updates"][0]["id"], "default")
        self.assertEqual(parsed["capsule_updates"][0]["behavior_claims"][0], payload["capsule_updates"][0]["behavior_claims"][0])

    def test_build_worker_prompt_distill_requests_recreation_briefs(self) -> None:
        prompt = og._build_worker_prompt(
            "distill",
            {
                "schema_version": 2,
                "interface_version": 1,
                "run_id": "run-1",
                "target_capsules": [{"id": "og", "kind": "code"}],
            },
        )

        self.assertIn("compact recreation brief", prompt)
        self.assertIn("behavior_claims", prompt)
        self.assertIn("invariants", prompt)
        self.assertIn("dependencies", prompt)
        self.assertIn("unknowns", prompt)
        self.assertIn("do not write a file-by-file summary", prompt.lower())
        self.assertIn("command=null and provide a non-empty reason", prompt)
        self.assertIn("prefer `uv run --with pytest --no-project pytest -q <path>`", prompt)
        self.assertIn("For doc, config, or runtime capsules, use status='success'", prompt)
        self.assertEqual(
            prompt,
            og._build_worker_prompt(
                "distill",
                {
                    "schema_version": 2,
                    "interface_version": 1,
                    "run_id": "run-1",
                    "target_capsules": [{"id": "og", "kind": "code"}],
                },
            ),
        )

    def test_worker_output_schemas_require_every_declared_property(self) -> None:
        def assert_required_fields(schema: object, *, path: str) -> None:
            if isinstance(schema, dict):
                schema_type = schema.get("type")
                allows_object = schema_type == "object" or (
                    isinstance(schema_type, list) and "object" in schema_type
                )
                if allows_object:
                    self.assertIs(
                        schema.get("additionalProperties"),
                        False,
                        msg=f"{path} must set additionalProperties=false for strict worker schemas",
                    )
                    if isinstance(schema.get("properties"), dict):
                        properties = schema["properties"]
                        required = schema.get("required")
                        self.assertIsInstance(required, list, msg=f"{path} missing required list")
                        self.assertEqual(
                            sorted(required),
                            sorted(properties.keys()),
                            msg=f"{path} properties must match required fields for strict worker schemas",
                        )
                for key, value in schema.items():
                    assert_required_fields(value, path=f"{path}.{key}")
                return
            if isinstance(schema, list):
                for index, value in enumerate(schema):
                    assert_required_fields(value, path=f"{path}[{index}]")

        for role in ("distill", "replay"):
            assert_required_fields(og._build_worker_output_schema(role), path=role)

    def test_build_worker_prompt_replay_mentions_regeneration_contract_fields(self) -> None:
        fixture = _write_replayable_capsule_fixture(self.repo)
        prompt = og._build_worker_prompt(
            "replay",
            og._build_replay_input(
                run_id="run-1",
                profile="analyze",
                mode="observe",
                capsule_id="default",
                changed_materials=[dict(item) for item in fixture["scope_materials"] if isinstance(item, dict)],
                capsule_payload=dict(fixture["capsule_payload"]),
                scope_materials=[dict(item) for item in fixture["scope_materials"] if isinstance(item, dict)],
                baseline_equivalence={},
            ),
        )

        self.assertIn("capsule_scope", prompt)
        self.assertIn("material_inputs", prompt)
        self.assertIn("acceptance_checks", prompt)
        self.assertIn("equivalence_inputs", prompt)
        self.assertIn("status='pending'", prompt)

    def test_build_worker_prompt_fails_fast_when_prompt_asset_is_missing(self) -> None:
        prompt_dir = self.repo / "prompts" / "workers"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        (prompt_dir / "distill-v1.txt").write_text("distill\n{{payload_json}}\n", encoding="utf-8")
        (prompt_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": og.WORKER_PROMPT_ASSET_SCHEMA_VERSION,
                    "prompts": [
                        {
                            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
                            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
                            "role": "distill",
                            "path": "distill-v1.txt",
                            "required_variables": ["payload_json"],
                        },
                        {
                            "id": og.WORKER_PROMPT_BINDINGS["replay"]["id"],
                            "version": og.WORKER_PROMPT_BINDINGS["replay"]["version"],
                            "role": "replay",
                            "path": "replay-v1.txt",
                            "required_variables": ["payload_json"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch.object(og, "WORKER_PROMPT_MANIFEST_PATH", str(prompt_dir / "manifest.json")):
            with self.assertRaises(og.WorkerAdapterError) as context:
                og._build_worker_prompt("distill", {"schema_version": 2, "interface_version": 1, "run_id": "run-1"})

        self.assertIn(
            f"worker-replay@{og.WORKER_PROMPT_BINDINGS['replay']['version']}",
            str(context.exception),
        )
        self.assertIn("is missing", str(context.exception))

    def test_build_worker_prompt_fails_fast_when_prompt_template_is_malformed(self) -> None:
        prompt_dir = self.repo / "prompts" / "workers"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        (prompt_dir / "distill-v1.txt").write_text("distill\n{{payload_json}}\n", encoding="utf-8")
        (prompt_dir / "replay-v1.txt").write_text("replay without payload placeholder\n", encoding="utf-8")
        (prompt_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": og.WORKER_PROMPT_ASSET_SCHEMA_VERSION,
                    "prompts": [
                        {
                            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
                            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
                            "role": "distill",
                            "path": "distill-v1.txt",
                            "required_variables": ["payload_json"],
                        },
                        {
                            "id": og.WORKER_PROMPT_BINDINGS["replay"]["id"],
                            "version": og.WORKER_PROMPT_BINDINGS["replay"]["version"],
                            "role": "replay",
                            "path": "replay-v1.txt",
                            "required_variables": ["payload_json"],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch.object(og, "WORKER_PROMPT_MANIFEST_PATH", str(prompt_dir / "manifest.json")):
            with self.assertRaises(og.WorkerAdapterError) as context:
                og._build_worker_prompt("distill", {"schema_version": 2, "interface_version": 1, "run_id": "run-1"})

        self.assertIn(
            f"worker-replay@{og.WORKER_PROMPT_BINDINGS['replay']['version']}",
            str(context.exception),
        )
        self.assertIn("does not reference required variables", str(context.exception))

    def test_normalize_distill_delta_requires_oracle_reason_when_command_missing(self) -> None:
        update = _distill_update("default", ["capsules/default.yaml"])
        update["oracles"] = [{"name": "default-verify", "command": None, "scope": ["capsules/default.yaml"]}]
        payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-1",
            "capsule_updates": [update],
        }

        with self.assertRaises(og.WorkerAdapterError) as context:
            og._normalize_distill_delta(payload)

        self.assertIn("reason is required when command is null", str(context.exception))

    def test_run_codex_worker_prefers_output_last_message_contract(self) -> None:
        input_payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-2",
            "adapter_profile": "analyze",
            "mode": "observe",
            "target_capsules": [{"id": "default"}],
            "changed_paths": ["capsules/default.yaml"],
            "policy_ref": ".outcomegraph/policy.yaml",
        }
        output_payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-2",
            "capsule_updates": [
                _distill_update("default", ["capsules/default.yaml"])
            ],
        }
        test_case = self

        class FakePopen:
            def __init__(self, command, *, stdin, stdout, stderr, text, cwd, env, start_new_session):
                self.command = command
                self.returncode = 0
                self._stdout = '{"type":"turn.completed"}\n'
                self._stderr = ""
                self._last_message_path = command[command.index("--output-last-message") + 1]
                self._cwd = cwd
                self._env = env
                self._text = text
                self._stdin = stdin
                self._stdout_pipe = stdout
                self._stderr_pipe = stderr
                self._start_new_session = start_new_session

            def communicate(self, input=None, timeout=None):
                test_case.assertTrue(self._text)
                test_case.assertEqual(self._stdin, subprocess.PIPE)
                test_case.assertEqual(self._stdout_pipe, subprocess.PIPE)
                test_case.assertEqual(self._stderr_pipe, subprocess.PIPE)
                test_case.assertEqual(self._cwd, str(test_case.repo))
                test_case.assertTrue(timeout > 0)
                test_case.assertIsInstance(self._env, dict)
                test_case.assertEqual(self._start_new_session, os.name != "nt")
                test_case.assertEqual(input, og._build_worker_prompt("distill", input_payload))
                Path(self._last_message_path).write_text(json.dumps(output_payload), encoding="utf-8")
                return self._stdout, self._stderr

            def kill(self):
                self.returncode = -9

        with self.git_root_patch(), patch.object(
            og.subprocess,
            "Popen",
            side_effect=lambda command, **kwargs: FakePopen(command, **kwargs),
        ):
            parsed, receipts = og._run_codex_worker("distill", input_payload, str(self.repo), "trace.json")

        expected_prompt = og._build_worker_prompt("distill", input_payload)
        expected_prompt_provenance = {
            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
            "source_path": "prompts/workers/distill-v1.txt",
        }
        self.assertEqual(parsed["run_id"], "run-2")
        self.assertEqual(parsed["capsule_updates"][0]["id"], "default")
        self.assertEqual(parsed["prompt_provenance"], expected_prompt_provenance)
        self.assertEqual(len(receipts), 6)
        self.assertTrue((self.repo / "trace.json").exists())
        trace_input = json.loads((self.repo / "trace-input.json").read_text(encoding="utf-8"))
        self.assertEqual(trace_input["configuration"]["codex_home"], None)
        self.assertEqual(trace_input["prompt"], expected_prompt)
        self.assertEqual(trace_input["prompt_provenance"], expected_prompt_provenance)
        trace_result = json.loads((self.repo / "trace-result.json").read_text(encoding="utf-8"))
        self.assertEqual(trace_result["configuration"]["codex_home"], None)
        self.assertEqual(trace_result["prompt_provenance"], expected_prompt_provenance)
        self.assertEqual(trace_result["output"]["run_id"], "run-2")

    def test_run_codex_worker_uses_configured_codex_home(self) -> None:
        input_payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-3",
            "adapter_profile": "analyze",
            "mode": "observe",
            "target_capsules": [{"id": "default"}],
            "changed_paths": ["capsules/default.yaml"],
            "policy_ref": ".outcomegraph/policy.yaml",
        }
        output_payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-3",
            "capsule_updates": [_distill_update("default", ["capsules/default.yaml"])],
        }
        (self.repo / ".outcomegraph").mkdir(parents=True, exist_ok=True)
        (self.repo / ".outcomegraph" / "config.yaml").write_text(
            (
                "schema_version: 2\n"
                "defaults:\n"
                "  output: human\n"
                "  profile: analyze\n"
                "  mode: observe\n"
                "worker:\n"
                "  codex_home: \".codex-headless\"\n"
                "safety:\n"
                "  policy_file: policy.yaml\n"
            ),
            encoding="utf-8",
        )
        test_case = self

        class FakePopen:
            def __init__(self, command, *, stdin, stdout, stderr, text, cwd, env, start_new_session):
                self.command = command
                self.returncode = 0
                self._last_message_path = command[command.index("--output-last-message") + 1]
                self._env = env
                self._cwd = cwd

            def communicate(self, input=None, timeout=None):
                test_case.assertEqual(self._cwd, str(test_case.repo))
                test_case.assertEqual(self._env["CODEX_HOME"], str(test_case.repo / ".codex-headless"))
                test_case.assertEqual(input, og._build_worker_prompt("distill", input_payload))
                Path(self._last_message_path).write_text(json.dumps(output_payload), encoding="utf-8")
                return '{"type":"turn.completed"}\n', ""

            def kill(self):
                self.returncode = -9

        with patch.object(
            og.subprocess,
            "Popen",
            side_effect=lambda command, **kwargs: FakePopen(command, **kwargs),
        ):
            parsed, _ = og._run_codex_worker("distill", input_payload, str(self.repo), "trace.json")

        self.assertEqual(parsed["run_id"], "run-3")
        trace_input = json.loads((self.repo / "trace-input.json").read_text(encoding="utf-8"))
        self.assertEqual(trace_input["configuration"]["codex_home"], ".codex-headless")
        self.assertEqual(
            trace_input["configuration"]["resolved_from"],
            f"config:{og.DEFAULT_CONFIG_FILE}",
        )
        trace_result = json.loads((self.repo / "trace-result.json").read_text(encoding="utf-8"))
        self.assertEqual(trace_result["configuration"]["codex_home"], ".codex-headless")

    def test_run_codex_worker_kills_process_group_on_timeout(self) -> None:
        input_payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-timeout",
            "adapter_profile": "analyze",
            "mode": "observe",
            "target_capsules": [{"id": "default"}],
            "changed_paths": ["capsules/default.yaml"],
            "policy_ref": ".outcomegraph/policy.yaml",
        }

        class FakePopen:
            def __init__(self, command, *, stdin, stdout, stderr, text, cwd, env, start_new_session):
                self.command = command
                self.pid = 4321
                self.returncode = None
                self.communicate_calls = 0

            def communicate(self, input=None, timeout=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    raise subprocess.TimeoutExpired(cmd=self.command, timeout=timeout)
                self.returncode = -9
                return "", ""

            def kill(self):
                self.returncode = -9

        fake_proc = FakePopen([], stdin=None, stdout=None, stderr=None, text=True, cwd="", env={}, start_new_session=True)
        with patch.object(og.subprocess, "Popen", return_value=fake_proc), patch.object(og.os, "killpg") as killpg:
            with self.assertRaises(og.WorkerAdapterError) as context:
                og._run_codex_worker("distill", input_payload, str(self.repo), "trace.json", timeout_seconds=1)

        killpg.assert_called_once_with(4321, signal.SIGKILL)
        self.assertIn("timed out after 1s", str(context.exception))

    def test_build_worker_command_variants_honors_model_override_env(self) -> None:
        with patch.dict(os.environ, {og.WORKER_MODEL_OVERRIDE_ENV: "gpt-5.4"}, clear=False):
            command = og._build_worker_command_variants("codex://v1", "schema.json", "last.json")[0]

        self.assertEqual(
            command,
            [
                "codex",
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--model",
                "gpt-5.4",
                "--output-schema",
                "schema.json",
                "--output-last-message",
                "last.json",
                "-",
            ],
        )

    def test_collect_policy_checks_flags_schema_errors(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            "schema_version: 1\nmode: unknown\n",
            encoding="utf-8",
        )

        payload = og._collect_policy_checks(str(self.repo))
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["checks"][0]["type"], "policy_schema_version")

    def test_collect_policy_checks_parses_nested_rules(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            """schema_version: 2\nallow:\n  file_writes:\n    - \".outcomegraph/**\"\ndeny:\n  file_writes:\n    - \"src/**\"\nmode: observe\n""",
            encoding="utf-8",
        )

        payload = og._collect_policy_checks(str(self.repo))
        parsed = payload["parsed"]
        self.assertEqual(payload["status"], "ok")
        self.assertIsInstance(parsed.get("allow"), dict)
        self.assertEqual(parsed.get("allow", {}).get("file_writes"), [".outcomegraph/**"])

    def test_run_apply_stage_blocks_policy_denied_writes(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            """schema_version: 2\nmode: observe\nallow:\n  file_writes:\n    - \"export/**\"\ndeny:\n  file_writes:\n    - \".outcomegraph/**\"\n""",
            encoding="utf-8",
        )

        payload = og._run_apply_stage(
            str(self.repo),
            {
                "name": "distill",
                "status": "ok",
                "generated_deltas": [],
                "affected_capsules": ["default"],
            },
            "run-1",
            "observe",
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.POLICY_DENIED_CODE)
        self.assertEqual(payload["category"], "file_writes")
        self.assertIn("forbids", str(payload["message"]).lower())

    def test_run_apply_stage_persists_pending_distill_delta_with_warning(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [
                        {
                            **_distill_update("default", ["README.md"], status="pending"),
                            "errors": ["snapshot was partial but still useful"],
                        }
                    ],
                    "affected_capsules": ["default"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "default.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["status"], "pending")
        self.assertTrue(payload["applied_capsules"])
        self.assertIn("snapshot was partial but still useful", payload["warnings"])

    def test_run_apply_stage_upgrades_existing_capsule_status(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            existing_payload = og._build_capsule_payload(
                "default",
                ["README.md"],
                [],
                None,
                og._utc_timestamp(),
                goal="Existing default capsule",
                scope=["README.md"],
                constraints=["existing constraint"],
                oracles=[{"name": "default-verify", "command": None, "scope": ["README.md"]}],
                status="warn",
            )
            (self.repo / ".outcomegraph" / "capsules" / "default.json").write_text(
                json.dumps(existing_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [
                        _distill_update("default", ["README.md"], status="success"),
                    ],
                    "affected_capsules": ["default"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "default.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(capsule_payload["kind"], "doc")
        self.assertEqual(capsule_payload["status"], "success")

    def test_run_apply_stage_does_not_infer_pytest_oracle_for_python_capsule(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [
                        _distill_update("tests", ["tests/test_example.py"], status="warn"),
                    ],
                    "affected_capsules": ["tests"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "tests.json").read_text(encoding="utf-8"))
        oracle_commands = [oracle.get("command") for oracle in capsule_payload["oracles"]]
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["kind"], "test")
        self.assertEqual(capsule_payload["status"], "warn")
        self.assertEqual(oracle_commands, [None])

    def test_run_apply_stage_does_not_mark_code_capsule_success_with_inferred_pytest_only(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [
                        _distill_update("og", ["og.py"], status="success"),
                    ],
                    "affected_capsules": ["og"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "og.json").read_text(encoding="utf-8"))
        oracle_commands = [oracle.get("command") for oracle in capsule_payload["oracles"]]
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["kind"], "code")
        self.assertEqual(capsule_payload["status"], "warn")
        self.assertEqual(oracle_commands, [None])
        self.assertTrue(any("explicit executable oracle evidence" in warning for warning in payload["warnings"]))

    def test_run_apply_stage_records_warn_certificate_for_weak_code_capsule(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [
                        _distill_update("og", ["og.py"], status="success"),
                    ],
                    "affected_capsules": ["og"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        certificate_payload = json.loads((self.repo / payload["applied_certificates"][0]).read_text(encoding="utf-8"))
        success_refs = og._collect_successful_certificate_refs_by_capsule(str(self.repo))
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(certificate_payload["status"], "warn")
        self.assertNotIn("og", success_refs)

    def test_run_apply_stage_does_not_promote_warn_python_capsule_with_executable_oracle(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("tests", ["tests/test_example.py"], status="warn")
            delta["oracles"] = [
                {
                    "name": "pytest regression suite",
                    "command": "pytest -q",
                    "scope": ["tests/test_example.py"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["tests"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "tests.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["kind"], "test")
        self.assertEqual(capsule_payload["status"], "warn")

    def test_run_apply_stage_downgrades_success_without_recreation_brief_fields(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("default", ["README.md"], status="success")
            delta["behavior_claims"] = []
            delta["dependencies"] = []
            delta["unknowns"] = []
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["default"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "default.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["status"], "warn")
        self.assertEqual(capsule_payload["behavior_claims"], [])
        self.assertTrue(any("behavior_claims" in warning for warning in payload["warnings"]))
        self.assertTrue(any("dependencies" in warning for warning in payload["warnings"]))
        self.assertTrue(any("unknowns" in warning for warning in payload["warnings"]))

    def test_run_apply_stage_preserves_evidence_gaps_over_existing_strong_capsule(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            existing_payload = og._build_capsule_payload(
                "og",
                ["og.py"],
                [],
                None,
                og._utc_timestamp(),
                goal="Provide the stable OutcomeGraph CLI and sync orchestration contract.",
                scope=["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
                kind="code",
                behavior_claims=["`og` exposes the stable CLI contract."],
                invariants=["CLI command parsing remains stable."],
                dependencies=["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
                oracles=[
                    {
                        "name": "pytest regression suite",
                        "command": "pytest -q",
                        "scope": ["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
                    }
                ],
                unknowns=["Full repo-wide sync still required for broader confidence."],
                status="success",
            )
            (self.repo / ".outcomegraph" / "capsules" / "og.json").write_text(
                json.dumps(existing_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            delta = _distill_update("og", ["og.py"], status="success")
            delta["behavior_claims"] = []
            delta["invariants"] = []
            delta["dependencies"] = []
            delta["unknowns"] = []
            delta["oracles"] = [
                {
                    "name": "og-verify",
                    "command": None,
                    "reason": "Distill did not recover an executable oracle from the bounded evidence.",
                    "scope": ["og.py"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["og"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "og.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "warn")
        self.assertEqual(capsule_payload["status"], "warn")
        self.assertEqual(capsule_payload["behavior_claims"], [])
        self.assertEqual(capsule_payload["invariants"], [])
        self.assertEqual(capsule_payload["dependencies"], [])
        self.assertEqual(capsule_payload["unknowns"], [])
        self.assertEqual(capsule_payload["oracles"][0]["command"], None)
        self.assertEqual(
            capsule_payload["oracles"][0]["reason"],
            "Distill did not recover an executable oracle from the bounded evidence.",
        )

    def test_run_apply_stage_rejects_incomplete_claims_instead_of_synthesizing_them(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("default", ["README.md"], status="success")
            delta["claims"] = [
                {
                    "id": None,
                    "capsule_id": "default",
                    "category": "",
                    "text": "",
                    "receipt_pointers": [],
                    "source_paths": ["README.md"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["default"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        self.assertEqual(payload["status"], "error")
        self.assertIn("distill claims for capsule default could not be normalized", payload["errors"])
        self.assertTrue(any("incomplete claim data" in warning for warning in payload["warnings"]))
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "claims").glob("*.json")), [])
        self.assertFalse((self.repo / ".outcomegraph" / "capsules" / "default.json").exists())

    def test_run_apply_stage_persists_recreation_brief_for_og_capsule(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("og", ["og.py"], status="success")
            delta["goal"] = "Provide the stable OutcomeGraph CLI and sync orchestration contract."
            delta["scope"] = ["og.py", "tests/test_og_sync_verify_replay_hooks.py", "README.md"]
            delta["behavior_claims"] = [
                "The `og` command keeps a stable CLI surface for sync, verify, replay, and status workflows.",
                "Structured command envelopes remain available for automation and agent callers.",
            ]
            delta["invariants"] = [
                "CLI command parsing must keep stable top-level commands and usage contracts.",
                "Sync continues to orchestrate distill, apply, verify, and export in order.",
            ]
            delta["dependencies"] = [
                "og.py",
                "tests/test_og_sync_verify_replay_hooks.py",
                "README.md",
            ]
            delta["unknowns"] = [
                "A full repo-wide sync run is still needed to confirm no hidden command-surface regressions outside the focused tests.",
            ]
            delta["oracles"] = [
                {
                    "name": "pytest regression suite",
                    "command": "pytest -q",
                    "scope": ["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
                }
            ]
            delta["claims"] = [
                {
                    "id": None,
                    "capsule_id": "og",
                    "category": "behavior",
                    "text": "`og` exposes a stable command contract with structured sync and verification workflows.",
                    "receipt_pointers": [],
                    "source_paths": ["og.py", "tests/test_og_sync_verify_replay_hooks.py"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["og"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "og.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(capsule_payload["status"], "success")
        self.assertEqual(capsule_payload["kind"], "code")
        self.assertEqual(capsule_payload["behavior_claims"], delta["behavior_claims"])
        self.assertEqual(capsule_payload["invariants"], delta["invariants"])
        self.assertEqual(capsule_payload["dependencies"], delta["dependencies"])
        self.assertEqual(capsule_payload["unknowns"], delta["unknowns"])
        self.assertEqual(capsule_payload["oracles"][0]["command"], "uv run --with pytest --no-project pytest -q")

    def test_run_apply_stage_records_prompt_provenance_in_certificate(self) -> None:
        prompt_provenance = {
            "id": og.WORKER_PROMPT_BINDINGS["distill"]["id"],
            "version": og.WORKER_PROMPT_BINDINGS["distill"]["version"],
            "source_path": "prompts/workers/distill-v1.txt",
        }

        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("default", ["README.md"], status="success")
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["default"],
                    "adapter_name": "codex",
                    "prompt_provenance": prompt_provenance,
                },
                "run-1",
                "observe",
            )

        certificate_payload = json.loads((self.repo / payload["applied_certificates"][0]).read_text(encoding="utf-8"))
        self.assertEqual(certificate_payload["prompt_provenance"], prompt_provenance)

    def test_run_apply_stage_persists_recreation_brief_for_tests_capsule(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("tests", ["tests/test_og_sync_verify_replay_hooks.py"], status="success")
            delta["goal"] = "Protect the OutcomeGraph regression contract with focused repository tests."
            delta["scope"] = ["tests/test_og_sync_verify_replay_hooks.py", "og.py"]
            delta["behavior_claims"] = [
                "The test suite exercises sync, distill, apply, verify, replay, and CLI contract regressions.",
            ]
            delta["invariants"] = [
                "Regression tests must stay deterministic and runnable from a clean temporary repository.",
            ]
            delta["dependencies"] = [
                "tests/test_og_sync_verify_replay_hooks.py",
                "og.py",
                "tests/conftest.py",
            ]
            delta["unknowns"] = [
                "Broader cross-platform behavior still depends on environments outside this focused fixture set.",
            ]
            delta["oracles"] = [
                {
                    "name": "pytest regression suite",
                    "command": "pytest -q",
                    "scope": ["tests/test_og_sync_verify_replay_hooks.py", "og.py"],
                }
            ]
            delta["claims"] = [
                {
                    "id": None,
                    "capsule_id": "tests",
                    "category": "behavior",
                    "text": "The focused regression suite validates the repository's distill/apply/verify/replay contract.",
                    "receipt_pointers": [],
                    "source_paths": ["tests/test_og_sync_verify_replay_hooks.py", "og.py"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["tests"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "tests.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(capsule_payload["status"], "success")
        self.assertEqual(capsule_payload["kind"], "test")
        self.assertEqual(capsule_payload["behavior_claims"], delta["behavior_claims"])
        self.assertEqual(capsule_payload["invariants"], delta["invariants"])
        self.assertEqual(capsule_payload["dependencies"], delta["dependencies"])
        self.assertEqual(capsule_payload["unknowns"], delta["unknowns"])
        self.assertEqual(capsule_payload["oracles"][0]["command"], "uv run --with pytest --no-project pytest -q")

    def test_run_apply_stage_keeps_uv_wrapped_pytest_oracle_in_observe_mode(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("tests", ["tests/test_og_sync_verify_replay_hooks.py"], status="success")
            delta["oracles"] = [
                {
                    "name": "sync-verify-replay-contracts",
                    "command": "uv run pytest -q tests/test_og_sync_verify_replay_hooks.py",
                    "scope": ["tests/test_og_sync_verify_replay_hooks.py", "og.py"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["tests"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "tests.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            capsule_payload["oracles"][0]["command"],
            "uv run --with pytest --no-project pytest -q tests/test_og_sync_verify_replay_hooks.py",
        )

    def test_run_apply_stage_keeps_python_unittest_oracle_in_observe_mode(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("prompts", ["prompts/workers/distill-v1.txt"], status="success")
            delta["oracles"] = [
                {
                    "name": "replay-hooks-regression",
                    "command": "python3 -m unittest -q tests.test_og_sync_verify_replay_hooks",
                    "scope": [
                        "prompts/workers/distill-v1.txt",
                        "prompts/workers/replay-v1.txt",
                        "prompts/workers/manifest.json",
                        "tests/test_og_sync_verify_replay_hooks.py",
                    ],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["prompts"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads((self.repo / ".outcomegraph" / "capsules" / "prompts.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            capsule_payload["oracles"][0]["command"],
            "python3 -m unittest -q tests.test_og_sync_verify_replay_hooks",
        )

    def test_run_apply_stage_downgrades_policy_blocked_oracle_to_advisory_only(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            delta = _distill_update("skill-og-dogfood", ["skills/og-dogfood/SKILL.md"], status="success")
            delta["oracles"] = [
                {
                    "name": "sync stage",
                    "command": "uv run og sync --json",
                    "scope": ["skills/og-dogfood/SKILL.md"],
                }
            ]
            payload = og._run_apply_stage(
                str(self.repo),
                {
                    "name": "distill",
                    "status": "ok",
                    "generated_deltas": [delta],
                    "affected_capsules": ["skill-og-dogfood"],
                    "adapter_name": "codex",
                },
                "run-1",
                "observe",
            )

        capsule_payload = json.loads(
            (self.repo / ".outcomegraph" / "capsules" / "skill-og-dogfood.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(capsule_payload["oracles"][0]["command"])
        self.assertIn("advisory only in observe mode", capsule_payload["oracles"][0]["name"])

    def test_run_verify_stage_skips_oracle_command_when_not_allowed(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            """schema_version: 2\nmode: observe\nallow:\n  verify_commands:\n    - \"echo ok\"\n  sandbox_operations:\n    - read_artifacts\ndeny:\n  verify_commands:\n    - \"go test*\"\n""",
            encoding="utf-8",
        )

        with self.git_root_patch(), patch.object(
            og,
            "_load_capsule_oracles",
            return_value=[{"name": "policy-blocked", "command": "go test ./...", "scope": []}],
        ):
            payload = og._run_verify_stage(
                str(self.repo),
                ["default"],
                ["capsules/default.yaml"],
                "run-verify",
                "observe",
            )

        self.assertEqual(payload["status"], "warn")
        self.assertEqual(payload["failed_capsules"], [])
        checks = payload["oracle_results"].get("default", [])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].get("code"), og.POLICY_DENIED_CODE)
        self.assertEqual(checks[0].get("status"), "skipped")

    def test_run_oracle_check_shortens_overlong_trace_names(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            oracle_result = og._run_oracle_check(
                str(self.repo),
                "default",
                {
                    "name": "very long oracle " + ("evidence-" * 40),
                    "command": None,
                    "scope": [],
                },
                [],
                "run-long",
                "observe",
            )

        trace_path = self.repo / oracle_result["trace"]
        self.assertEqual(oracle_result["status"], "pass")
        self.assertTrue(trace_path.exists())
        self.assertLess(len(trace_path.name), 255)

    def test_run_replay_stage_blocks_disallowed_sandbox_operation(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            """schema_version: 2\nmode: observe\nallow:\n  sandbox_operations:\n    - read_artifacts\n  file_writes:\n    - \"export/**\"\ndeny:\n  sandbox_operations:\n    - create_isolated_worktree\n""",
            encoding="utf-8",
        )

        payload = og._run_replay_stage(
            str(self.repo),
            {"changed_files": ["capsules/default.yaml"]},
            "run-replay",
            "analyze",
            "observe",
            changed_only=True,
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.POLICY_DENIED_CODE)
        self.assertEqual(payload["category"], "sandbox_operations")

    def test_run_export_stage_blocks_disallowed_writes(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            """schema_version: 2\nmode: observe\nallow:\n  file_writes:\n    - \".outcomegraph/**\"\n  sandbox_operations:\n    - read_artifacts\ndeny:\n  file_writes:\n    - \"export/**\"\n""",
            encoding="utf-8",
        )

        payload = og._run_export_stage(str(self.repo), "observe")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.POLICY_DENIED_CODE)
        self.assertEqual(payload["category"], "file_writes")


class TestSpecComplianceGates(_RepoTestCase):
    def test_validate_canonical_artifacts_enforces_schema_and_path_mapping(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            valid_snapshot = "2026-03-05T00:00:00Z"

            (base / "capsules" / "default.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "capsule",
                        "id": "default",
                        "status": "active",
                        "scope": ["**/*"],
                        "created_at": valid_snapshot,
                        "updated_at": valid_snapshot,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (base / "refs" / "main.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "ref",
                        "id": "main",
                        "capsule_id": "default",
                        "created_at": valid_snapshot,
                        "updated_at": valid_snapshot,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (base / "decisions" / "dec-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "decision",
                        "id": "dec-1",
                        "capsule_id": "default",
                        "created_at": valid_snapshot,
                        "updated_at": valid_snapshot,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (base / "claims" / "cl-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "claim",
                        "id": "cl-1",
                        "capsule_id": "default",
                        "text": "validation smoke test claim",
                        "receipt_pointers": [
                            {
                                "schema_version": 2,
                                "type": "file",
                                "target": ".outcomegraph/traces/sample.json",
                            },
                        ],
                        "created_at": valid_snapshot,
                        "origin": {"run_id": "run-1", "profile": "analyze", "mode": "observe", "changed_files": []},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (base / "certificates" / "cert-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "certificate",
                        "id": "cert-1",
                        "capsule_id": "default",
                        "run_id": "run-1",
                        "status": "success",
                        "receipt_pointers": [
                            {
                                "schema_version": 2,
                                "type": "file",
                                "target": ".outcomegraph/traces/sample.json",
                            },
                        ],
                        "claim_refs": [".outcomegraph/claims/cl-1.json"],
                        "created_at": valid_snapshot,
                        "updated_at": valid_snapshot,
                        "replay_context": {"run_id": "run-1"},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            # Canonical payloads are schema-valid and path-consistent.
            og._validate_canonical_artifact_records(str(self.repo))

            # A path/type mismatch must be rejected as a conformance failure.
            (base / "capsules" / "bad-type.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "ref",
                        "id": "bad-type",
                        "status": "active",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as context:
                og._validate_canonical_artifact_records(str(self.repo))

        self.assertIn("artifact_type 'ref' does not match expected 'capsule'", str(context.exception))

    def test_validate_canonical_artifacts_rejects_non_version_two_schema(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "refs" / "legacy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "ref",
                        "id": "legacy",
                        "capsule_id": "default",
                        "updated_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                og._validate_canonical_artifact_records(str(self.repo))

        self.assertIn("schema_version must be 2", str(context.exception))

    def test_validate_canonical_artifacts_rejects_missing_created_at_timestamp(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "refs" / "missing-created-at.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "ref",
                        "id": "missing-created-at",
                        "capsule_id": "default",
                        "updated_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                og._validate_canonical_artifact_records(str(self.repo))

        self.assertIn("missing created_at timestamp", str(context.exception))

    def test_validate_canonical_artifacts_rejects_claim_without_receipt_pointer(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "claims" / "cl-no-receipt.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "artifact_type": "claim",
                        "id": "cl-no-receipt",
                        "capsule_id": "default",
                        "category": "behavior",
                        "text": "Claim missing receipt pointers should fail canonical validation.",
                        "receipt_pointers": [],
                        "origin": {"run_id": "run-1", "profile": "analyze", "mode": "observe", "changed_files": []},
                        "created_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                og._validate_canonical_artifact_records(str(self.repo))

        self.assertIn("claim must include at least one receipt_pointer", str(context.exception))

    def test_run_apply_stage_rejects_legacy_canonical_schema_before_writes(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "refs" / "legacy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "ref",
                        "id": "legacy",
                        "capsule_id": "default",
                        "updated_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            distill_result = {
                "status": "ok",
                "profile": "analyze",
                "affected_capsules": ["default"],
                "generated_deltas": [_distill_update("default", ["og.py"])],
            }
            payload = og._run_apply_stage(
                str(self.repo),
                distill_result,
                "run-apply",
                "observe",
            )

        self.assertEqual(payload["status"], "error")
        self.assertIn("schema_version must be 2", str(payload.get("message", "")))
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "claims").glob("*.json")), [])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_verify_stage_rejects_legacy_canonical_schema_before_writes(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "refs" / "legacy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "ref",
                        "id": "legacy",
                        "capsule_id": "default",
                        "updated_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            payload = og._run_verify_stage(
                str(self.repo),
                ["default"],
                ["og.py"],
                "run-verify",
                "observe",
            )

        self.assertEqual(payload["status"], "error")
        self.assertIn("Canonical artifact validation failed", str(payload.get("message", "")))
        self.assertTrue(
            any("schema_version must be 2" in str(error) for error in payload.get("errors", [])),
        )
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "claims").glob("*.json")), [])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_replay_stage_rejects_legacy_canonical_schema_before_writes(self) -> None:
        with self.git_root_patch(), patch.object(
            og,
            "_initialize_adapter_runtime",
            return_value=[],
        ), patch.object(
            og,
            "adapter_get",
            return_value={"type": "worker", "name": "codex", "manifest": {"name": "codex"}},
        ):
            og._init_outcomegraph()
            base = self.repo / ".outcomegraph"
            (base / "refs" / "legacy.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "ref",
                        "id": "legacy",
                        "capsule_id": "default",
                        "updated_at": "2026-03-05T00:00:00Z",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            payload = og._run_replay_stage(
                str(self.repo),
                {"changed_files": ["og.py"]},
                "run-replay",
                "analyze",
                "observe",
                changed_only=True,
            )

        self.assertEqual(payload["status"], "error")
        self.assertIn("Canonical artifact validation failed", str(payload.get("message", "")))
        self.assertTrue(
            any("schema_version must be 2" in str(error) for error in payload.get("errors", [])),
        )
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "claims").glob("*.json")), [])
        self.assertEqual(sorted((self.repo / ".outcomegraph" / "certificates").glob("*.json")), [])

    def test_run_verify_stage_returns_policy_configuration_error(self) -> None:
        (self.repo / ".outcomegraph").mkdir()
        (self.repo / ".outcomegraph" / "policy.yaml").write_text(
            "schema_version: 1\nmode: observe\n",
            encoding="utf-8",
        )

        payload = og._run_verify_stage(
            str(self.repo),
            ["default"],
            ["capsules/default.yaml"],
            "run-verify",
            "observe",
        )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], og.POLICY_CONFIG_ERROR_CODE)

    def test_run_replay_stage_persists_equivalence_and_receipts(self) -> None:
        prompt_provenance = {
            "id": og.WORKER_PROMPT_BINDINGS["replay"]["id"],
            "version": og.WORKER_PROMPT_BINDINGS["replay"]["version"],
            "source_path": "prompts/workers/replay-v1.txt",
        }
        with self.git_root_patch():
            snapshot = {"changed_files": ["capsules/default.yaml"]}
            fixture = _write_replayable_capsule_fixture(self.repo)
            receipts = [
                {"schema_version": 2, "type": "file", "target": ".outcomegraph/traces/replay-run.json"},
            ]
            replay_plan = _build_replay_plan_fixture(
                "run-1",
                fixture,
                prompt_provenance=prompt_provenance,
            )
            replay_plan["parity_results"]["details"] = "equivalence output checksum identical"

            with patch.object(
                og, "_collect_affected_capsules", return_value=["default"]
            ), patch.object(
                og,
                "_collect_changed_materials",
                return_value=[],
            ), patch.object(
                og,
                "_run_codex_worker",
                return_value=(replay_plan, receipts),
            ):
                payload = og._run_replay_stage(
                    str(self.repo),
                    snapshot,
                    "run-1",
                    "analyze",
                    "observe",
                    changed_only=True,
                )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["replay_results"][0]["status"], "success")
        self.assertTrue(payload["certificate_ids"])
        self.assertEqual(len(payload["certificate_refs"]), 1)

        certificate_path = self.repo / payload["certificate_refs"][0]
        certificate_payload = json.loads(certificate_path.read_text(encoding="utf-8"))
        replay_result = payload["replay_results"][0]
        result_equivalence = replay_result.get("equivalence")
        self.assertIsInstance(result_equivalence, dict)
        self.assertEqual(replay_result["prompt_provenance"], prompt_provenance)
        self.assertEqual(payload["prompt_provenance"], prompt_provenance)
        self.assertEqual(certificate_payload["prompt_provenance"], prompt_provenance)
        self.assertIn("equivalence", certificate_payload["replay_context"])
        self.assertEqual(
            certificate_payload["replay_context"]["acceptance_checks"],
            replay_result["acceptance_checks"],
        )
        self.assertEqual(
            certificate_payload["replay_context"]["equivalence_inputs"],
            replay_result["equivalence_inputs"],
        )
        self.assertEqual(
            certificate_payload["replay_context"]["equivalence"],
            result_equivalence,
        )
        self.assertEqual(result_equivalence.get("baseline_hash"), None)
        self.assertTrue(result_equivalence.get("match"))

        claim_payload = json.loads((self.repo / certificate_payload["claim_refs"][0]).read_text(encoding="utf-8"))
        self.assertTrue(len(claim_payload["receipt_pointers"]) >= 2)
        self.assertTrue(any(item.get("target") == ".outcomegraph/traces/run-1-default-replay-step-0.json" for item in claim_payload["receipt_pointers"]))
        self.assertTrue(any(item in receipts for item in claim_payload["receipt_pointers"]))
        self.assertTrue(any(item.get("type") for item in claim_payload["receipt_pointers"]))

    def test_run_replay_stage_skips_certificate_on_equivalence_mismatch(self) -> None:
        with self.git_root_patch():
            snapshot = {"changed_files": ["capsules/default.yaml"]}
            fixture = _write_replayable_capsule_fixture(self.repo)
            baseline_claim_payload = og._build_claim_payload(
                "cl-default-replay-baseline",
                "default",
                "run-baseline",
                "replay",
                "observe",
                [],
                [],
                text="Replay baseline claim for equivalence gate test.",
            )
            og._write_canonical_artifact(
                str(self.repo),
                f"{og.OG_ROOT}/claims/cl-default-replay-baseline.json",
                baseline_claim_payload,
            )
            baseline_certificate = og._build_certificate_payload(
                "cert-default-replay-baseline",
                "default",
                "run-baseline",
                [f"{og.OG_ROOT}/claims/cl-default-replay-baseline.json"],
                "replay",
                "observe",
                [],
                status="success",
                source="replay",
            )
            baseline_certificate["replay_context"] = {
                "run_id": "run-baseline",
                "adapter_profile": "analyze",
                "source_ref": "HEAD",
                "sandbox_root": ".outcomegraph/work/replay/run-baseline/default",
                "changed_materials": [],
                "equivalence": {
                    "baseline_hash": "sha256:baseline-equivalence-hash",
                    "observed_hash": "sha256:baseline-equivalence-hash",
                    "oracle_digest": "sha256:baseline-equivalence-hash",
                    "match": True,
                },
            }
            og._write_canonical_artifact(
                str(self.repo),
                f"{og.OG_ROOT}/certificates/cert-default-replay-baseline.json",
                baseline_certificate,
            )

            replay_plan = _build_replay_plan_fixture(
                "run-mismatch",
                fixture,
                baseline_hash="sha256:baseline-equivalence-hash",
            )

            with patch.object(
                og, "_collect_affected_capsules", return_value=["default"]
            ), patch.object(
                og,
                "_collect_changed_materials",
                return_value=[],
            ), patch.object(
                og,
                "_run_codex_worker",
                return_value=(replay_plan, []),
            ):
                payload = og._run_replay_stage(
                    str(self.repo),
                    snapshot,
                    "run-mismatch",
                    "analyze",
                    "observe",
                    changed_only=True,
                )

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["replay_results"][0]["status"], "failed")
        self.assertEqual(payload["replay_results"][0]["equivalence"]["match"], False)
        self.assertEqual(
            payload["replay_results"][0]["equivalence"]["baseline_hash"],
            "sha256:baseline-equivalence-hash",
        )
        self.assertEqual(payload["certificate_ids"], [])
        self.assertEqual(payload["certificate_refs"], [".outcomegraph/certificates/cert-default-replay-baseline.json"])

    def test_build_status_payload_marks_runtime_degraded_state(self) -> None:
        with self.git_root_patch():
            og._init_outcomegraph()
            state_path = self.repo / ".outcomegraph" / "work" / "state.json"
            work_state = json.loads(state_path.read_text(encoding="utf-8"))
            work_state["status"] = "degraded"
            work_state["last_message"] = "worker runtime unavailable during conformance test"
            state_path.write_text(json.dumps(work_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            status_payload = og._build_status_payload(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(status_payload["status"], "error")
        self.assertEqual(status_payload["runtime"]["status"], "degraded")
        self.assertEqual(status_payload["runtime"]["message"], "work state is degraded")
        issue_types = {issue.get("type") for issue in status_payload.get("issues", [])}
        self.assertIn("degraded", issue_types)

    def test_build_status_payload_treats_verify_warn_as_warning(self) -> None:
        snapshot = {
            "repository_head": "abc123",
            "branch": "main",
            "changed_files": ["capsules/default.yaml"],
            "changed_count": 1,
            "has_changes": True,
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-04T00:00:00Z",
        }

        with self.git_root_patch():
            og._init_outcomegraph()
            state_path = self.repo / ".outcomegraph" / "work" / "state.json"
            work_state = json.loads(state_path.read_text(encoding="utf-8"))
            work_state["status"] = "idle"
            work_state["last_message"] = "sync finished (warn)"
            state_path.write_text(json.dumps(work_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            og._record_sync_summary_event(
                str(self.repo),
                {
                    "run_id": "sync-warn",
                    "status": "warn",
                    "idempotency_key": "sync-warn-key",
                    "snapshot": snapshot,
                    "steps": [
                        {
                            "name": "verify",
                            "status": "warn",
                            "message": "verification completed with warnings",
                            "warnings": ["policy skipped one oracle"],
                        }
                    ],
                },
                42,
            )
            status_payload = og._build_status_payload(
                str(self.repo),
                {"changed": True, "profile": "analyze", "mode": "observe"},
            )

        self.assertEqual(status_payload["status"], "warn")
        self.assertEqual(status_payload["runtime"]["status"], "idle")
        self.assertEqual(status_payload["verification"]["state"], "warn")
        issue_types = {issue.get("type") for issue in status_payload.get("issues", [])}
        self.assertIn("verify_warning", issue_types)
        self.assertNotIn("verify_error", issue_types)


class TestAgentGuidanceContract(_RepoTestCase):
    def test_init_bootstraps_context_contract_and_agents_export_projection(self) -> None:
        with self.git_root_patch():
            init_payload = og._init_outcomegraph()
            updated_exports, unchanged_exports, _snapshot = og._run_export_refresh(str(self.repo))

        self.assertIn("CONTEXT.md", init_payload["created"]["files"])
        self.assertIn(".outcomegraph/export/AGENTS.md", updated_exports)
        self.assertEqual(unchanged_exports, [])

        context_text = (self.repo / "CONTEXT.md").read_text(encoding="utf-8")
        export_text = (self.repo / ".outcomegraph" / "export" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertEqual(context_text, og._render_context_contract())
        self.assertTrue(export_text.startswith(context_text.rstrip() + "\n\n## Export snapshot\n"))
        self.assertIn("Generated from `CONTEXT.md` by OutcomeGraph export stage.", export_text)


class TestRepositoryGuidanceContract(TestCase):
    def test_repository_context_contract_matches_runtime_template(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        observed = (repo_root / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertEqual(observed, og._render_context_contract())

    def test_context_contract_mentions_required_safe_automation_patterns(self) -> None:
        text = og._render_context_contract()

        for snippet in (
            "--fields",
            "--dry-run",
            "--yes",
            "--strict",
            "--non-interactive",
            f"CLI version: {og.VERSION}",
            f"JSON envelope schema_version: {og.COMMAND_RESULT_SCHEMA_VERSION}",
        ):
            self.assertIn(snippet, text)


class TestLiveCliFlows(_RepoTestCase):
    def _run_json_command(self, args: list[str]) -> tuple[int, dict[str, object]]:
        with self.git_root_patch():
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = og.main(["--json", *args])
        return code, json.loads(buffer.getvalue())

    def test_live_cli_happy_path_sync_then_verify_then_replay(self) -> None:
        app_file = self.repo / "app.py"
        test_file = self.repo / "test_smoke.py"
        app_file.write_text("VALUE = 1\n", encoding="utf-8")
        test_file.write_text(
            (
                "import pathlib\n"
                "import unittest\n\n"
                "class SmokeTest(unittest.TestCase):\n"
                "    def test_app_file_exists(self) -> None:\n"
                "        self.assertTrue(pathlib.Path('app.py').exists())\n"
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(self.repo), "add", "app.py", "test_smoke.py"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        app_file.write_text("VALUE = 2\n", encoding="utf-8")

        with self.git_root_patch():
            og._init_outcomegraph()

        snapshot = {
            "repository_head": "HEAD",
            "branch": "main",
            "changed_files": ["app.py"],
            "changed_count": 1,
            "has_changes": True,
            "force_full_sync": False,
            "diff_baseline": {
                "strategy": "manual",
                "reference": "HEAD",
                "resolved": "HEAD",
                "details": "test fixture baseline",
            },
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-08T00:00:00Z",
        }

        def worker_side_effect(
            role: str,
            payload: dict[str, object],
            repo_root: str,
            trace_path: str,
            adapter: dict[str, object] | None,
            *,
            timeout_seconds: int,
            max_retries: int,
        ) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
            if role == "distill":
                update = _distill_update("app", ["app.py"])
                update["scope"] = ["app.py", "test_smoke.py"]
                update["dependencies"] = ["app.py", "test_smoke.py"]
                update["oracles"] = [
                    {
                        "name": "app-verify",
                        "command": "python3 -m unittest -q test_smoke",
                        "scope": ["app.py", "test_smoke.py"],
                    }
                ]
                output = {
                    "schema_version": og.WORKER_SCHEMA_VERSION,
                    "interface_version": og.WORKER_INTERFACE_VERSION,
                    "run_id": str(payload.get("run_id") or "sync-live"),
                    "capsule_updates": [update],
                }
                recovery = og._build_recovery_record(
                    "worker:distill",
                    attempts=1,
                    max_retries=max_retries,
                    timeout_seconds=timeout_seconds,
                )
                return output, [], recovery

            if role == "replay":
                scope_materials = [dict(item) for item in payload.get("scope_materials", []) if isinstance(item, dict)]
                material_paths = [str(item.get("path") or "") for item in scope_materials if str(item.get("path") or "")]
                capsule_payload = payload.get("capsule") if isinstance(payload.get("capsule"), dict) else {}
                plan = {
                    "schema_version": og.WORKER_SCHEMA_VERSION,
                    "interface_version": og.WORKER_INTERFACE_VERSION,
                    "run_id": str(payload.get("run_id") or "replay-live"),
                    "capsule_id": str(payload.get("capsule_id") or "app"),
                    "capsule_scope": [str(item) for item in capsule_payload.get("scope", []) if str(item)],
                    "material_inputs": scope_materials,
                    "steps": [
                        {
                            "command": "python3 -m unittest -q test_smoke",
                            "cwd": ".",
                            "expected_exit_code": 0,
                        }
                    ],
                    "acceptance_checks": [
                        {
                            "name": "app-verify",
                            "oracle_name": "app-verify",
                            "command": "python3 -m unittest -q test_smoke",
                            "expected_signal": "exit_code=0",
                            "reason": None,
                        }
                    ],
                    "equivalence_inputs": {
                        "baseline_hash": None,
                        "oracle_names": ["app-verify"],
                        "material_paths": material_paths,
                        "notes": ["replay proof plan generated by test fixture"],
                    },
                    "status": "ok",
                    "message": "replay plan generated",
                    "failures": [],
                    "parity_results": {
                        "match": None,
                        "details": None,
                        "baseline_hash": None,
                        "observed_hash": None,
                        "oracle_digest": None,
                        "trace_count": 0,
                    },
                }
                recovery = og._build_recovery_record(
                    "worker:replay",
                    attempts=1,
                    max_retries=max_retries,
                    timeout_seconds=timeout_seconds,
                )
                return plan, [], recovery

            raise AssertionError(f"unexpected worker role: {role}")

        with patch.object(og, "_initialize_adapter_runtime", return_value=[]), patch.object(
            og, "adapter_get", return_value={"name": "test-worker", "capabilities": ["distill", "replay"]}
        ), patch.object(og, "_run_worker_with_retries", side_effect=worker_side_effect), patch.object(
            og, "_collect_sync_snapshot", return_value=snapshot
        ):
            sync_code, sync_payload = self._run_json_command(["sync"])
            verify_code, verify_payload = self._run_json_command(["verify", "--changed"])
            replay_code, replay_payload = self._run_json_command(["replay", "--changed"])

        self.assertEqual(sync_code, 0)
        self.assertEqual(sync_payload["status"], "ok")
        self.assertEqual(sync_payload["command"], "sync")
        self.assertEqual(sync_payload["data"]["status"], "ok")

        self.assertEqual(verify_code, 0)
        self.assertEqual(verify_payload["status"], "ok")
        self.assertEqual(verify_payload["command"], "verify")
        self.assertEqual(verify_payload["data"]["status"], "ok")
        self.assertIn("app", verify_payload["data"]["verified_capsules"])

        self.assertEqual(replay_code, 0)
        self.assertEqual(replay_payload["status"], "ok")
        self.assertEqual(replay_payload["command"], "replay")
        self.assertEqual(replay_payload["data"]["status"], "ok")
        replay_results = replay_payload["data"]["replay_results"]
        self.assertTrue(replay_results)
        self.assertEqual(replay_results[0]["status"], "success")

    def test_live_cli_failure_path_replay_before_sync_metadata(self) -> None:
        source_file = self.repo / "src" / "feature.py"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("FLAG = True\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "src/feature.py"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        source_file.write_text("FLAG = False\n", encoding="utf-8")

        with self.git_root_patch():
            og._init_outcomegraph()

        snapshot = {
            "repository_head": "HEAD",
            "branch": "main",
            "changed_files": ["src/feature.py"],
            "changed_count": 1,
            "has_changes": True,
            "force_full_sync": False,
            "diff_baseline": {
                "strategy": "manual",
                "reference": "HEAD",
                "resolved": "HEAD",
                "details": "test fixture baseline",
            },
            "profile": "analyze",
            "mode": "observe",
            "captured_at": "2026-03-08T00:00:00Z",
        }

        with patch.object(og, "_initialize_adapter_runtime", return_value=[]), patch.object(
            og, "adapter_get", return_value={"name": "test-worker", "capabilities": ["replay"]}
        ), patch.object(og, "_collect_sync_snapshot", return_value=snapshot):
            replay_code, replay_payload = self._run_json_command(["replay", "--changed"])

        self.assertEqual(replay_code, 0)
        self.assertEqual(replay_payload["command"], "replay")
        self.assertEqual(replay_payload["status"], "warn")
        self.assertEqual(replay_payload["data"]["status"], "warn")
        replay_results = replay_payload["data"]["replay_results"]
        self.assertTrue(replay_results)
        self.assertEqual(replay_results[0]["status"], "skipped")
        failures = " ".join(replay_results[0].get("failures", []))
        self.assertIn("Run `og sync --json` to materialize capsule metadata before replay.", failures)
