from __future__ import annotations

import json
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

        self.assertEqual(payload["status"], "warn")
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
