from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
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

    def git_root_patch(self):
        return patch.object(og, "_git_root", return_value=str(self.repo))

    def _git_completed(self, returncode: int, stdout: str = "", stderr: str = ""):
        return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


class TestHelpContracts(TestCase):
    def _run_main(self, args: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(args)
        return code, buffer.getvalue()

    def test_top_level_help_includes_global_contract(self) -> None:
        code, text = self._run_main(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Usage: og [--json] [--profile analyze|propose|apply] [--mode observe|autonomous] <command>", text)
        self.assertIn("Use: og <command> --help for command-specific contracts.", text)
        self.assertIn("Core commands:", text)

    def test_command_specific_help_contracts_are_rendered(self) -> None:
        test_cases = [
            (["init", "--help"], "Usage: og init"),
            (["sync", "--help"], "Usage: og sync"),
            (["verify", "--help"], "Usage: og verify"),
            (["replay", "--help"], "Usage: og replay"),
            (["status", "--help"], "Usage: og status"),
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
        ]

        for args, expected_usage in test_cases:
            code, text = self._run_main(args)
            self.assertEqual(code, 0, msg=f"help command failed for {args}")
            self.assertIn(expected_usage, text, msg=f"missing usage block for {args}")
            self.assertIn("Accepted options:", text, msg=f"missing options block for {args}")
            self.assertIn("Output modes:", text, msg=f"missing output modes block for {args}")
            self.assertIn("Exit codes:", text, msg=f"missing exit codes block for {args}")


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
        self.assertIn("unknown global option", payload["errors"][0])


class TestHookLifecycle(_RepoTestCase):
    def test_autopilot_init_installs_and_disables_hooks(self) -> None:
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


class TestDaemonLifecycle(_RepoTestCase):
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

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(snapshot["diff_baseline"]["resolved"], "aaaa")
        self.assertEqual(snapshot["changed_files"], ["capsules/default.yaml"])
        self.assertEqual(snapshot["changed_count"], 1)
        self.assertEqual(snapshot["has_changes"], True)

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

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git):
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

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git):
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

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git):
            snapshot = og._collect_sync_snapshot(str(self.repo), "analyze", "observe")

        self.assertEqual(snapshot["changed_count"], 0)

        with self.git_root_patch(), patch.object(og, "_run_git", side_effect=fake_run_git):
            forced_snapshot = og._collect_sync_snapshot(
                str(self.repo),
                "analyze",
                "observe",
                force_full_sync=True,
            )

        self.assertEqual(forced_snapshot["force_full_sync"], True)
        self.assertEqual(forced_snapshot["diff_baseline"]["strategy"], "head~1")
        self.assertEqual(sorted(forced_snapshot["changed_files"]), ["README.md", "capsules/default.yaml"])

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

        with self.git_root_patch(), patch.object(og, "_collect_sync_snapshot", return_value=snapshot), patch.object(
            og,
            "_compute_idempotency_key",
            return_value="stable-key",
        ), patch.object(og, "_read_work_state", return_value={"last_idempotency_key": "stable-key"}), patch.object(
            og,
            "_consume_pending",
            return_value=True,
        ), patch.object(og, "_record_sync_summary_event", return_value="events/sync-1.json"):
            payload = og._run_sync_job(str(self.repo), {"changed": False, "profile": "analyze", "mode": "observe"})

        self.assertTrue(payload["short_circuit"])
        self.assertTrue(payload["pending_consumed"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["steps"][0]["name"], "short_circuit")

    def test_run_distill_stage_marks_pending_when_worker_is_unavailable(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}

        with self.git_root_patch(), patch.object(
            og, "_collect_affected_capsules", return_value=["default"]
        ), patch.object(
            og, "_run_codex_worker", side_effect=og.WorkerAdapterError("codex executable was not found")
        ), patch.object(og, "_set_pending_state", return_value={"status": "ok"}) as set_pending:
            payload = og._run_distill_stage(str(self.repo), snapshot, "run-1", "analyze", "observe")

        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["errors"], ["codex executable was not found"])
        set_pending.assert_called_once()

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
        self.assertEqual(payload["verified_capsules"], ["default"])
        self.assertEqual(payload["changed_only"], True)


class TestReplayWorkflows(_RepoTestCase):
    def test_run_replay_stage_defaults_to_default_capsule_when_no_targets(self) -> None:
        snapshot = {"changed_files": []}
        replay_plan = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-1",
            "capsule_id": "default",
            "steps": [{"command": "echo ok"}],
            "status": "ok",
        }

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

    def test_run_replay_stage_errors_on_adapter_interface_mismatch(self) -> None:
        snapshot = {"changed_files": ["capsules/default.yaml"]}
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
        self.assertIn("schema_version must be 2", payload["errors"][0])


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

    def test_parse_worker_output_extracts_contract_from_event_stream(self) -> None:
        payload = {
            "schema_version": 2,
            "interface_version": 1,
            "run_id": "run-1",
            "capsule_updates": [
                {
                    "id": "default",
                    "status": "success",
                    "claims": [],
                    "decision_refs": [],
                    "errors": [],
                    "receipts": [],
                    "changed_files": ["capsules/default.yaml"],
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
                {
                    "id": "default",
                    "status": "success",
                    "claims": [],
                    "decision_refs": [],
                    "errors": [],
                    "receipts": [],
                    "changed_files": ["capsules/default.yaml"],
                }
            ],
        }

        def fake_subprocess_run(command, input, text, capture_output, cwd, timeout):
            self.assertTrue(text)
            self.assertTrue(capture_output)
            self.assertEqual(cwd, str(self.repo))
            self.assertTrue(timeout > 0)
            if "--output-last-message" in command:
                path = command[command.index("--output-last-message") + 1]
                Path(path).write_text(json.dumps(output_payload), encoding="utf-8")
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout='{"type":"turn.completed"}\n',
                stderr="",
            )

        with self.git_root_patch(), patch.object(og.subprocess, "run", side_effect=fake_subprocess_run):
            parsed, receipts = og._run_codex_worker("distill", input_payload, str(self.repo), "trace.json")

        self.assertEqual(parsed["run_id"], "run-2")
        self.assertEqual(parsed["capsule_updates"][0]["id"], "default")
        self.assertEqual(len(receipts), 2)
        self.assertTrue((self.repo / "trace.json").exists())

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

    def test_run_verify_stage_blocks_oracle_command_when_not_allowed(self) -> None:
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

        self.assertEqual(payload["status"], "error")
        self.assertIn("default", payload["failed_capsules"])
        checks = payload["oracle_results"].get("default", [])
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].get("code"), og.POLICY_DENIED_CODE)

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
        with self.git_root_patch():
            snapshot = {"changed_files": ["capsules/default.yaml"]}
            receipts = [
                {"schema_version": 2, "type": "file", "target": ".outcomegraph/traces/replay-run.json"},
            ]
            replay_plan = {
                "schema_version": 2,
                "interface_version": 1,
                "run_id": "run-replay-gates",
                "capsule_id": "default",
                "steps": [{"command": "echo ok"}],
                "status": "ok",
                "parity_results": {"match": True, "details": "equivalence output checksum identical"},
            }

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
        self.assertIn("equivalence", certificate_payload["replay_context"])
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

            replay_plan = {
                "schema_version": 2,
                "interface_version": 1,
                "run_id": "run-replay-gates",
                "capsule_id": "default",
                "steps": [{"command": "echo ok"}],
                "status": "ok",
            }

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
        self.assertEqual(payload["certificate_refs"], [])

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
