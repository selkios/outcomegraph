from __future__ import annotations

import io
import json
import subprocess
import tempfile
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import og


class _RepoContractTestCase(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "OutcomeGraph Tester"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "tester@example.com"], check=True)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def repo_patches(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch.object(og, "_git_root", return_value=str(self.repo)))
        stack.enter_context(patch.object(og, "_maybe_git_root", return_value=str(self.repo)))
        return stack

    def run_main(self, args: list[str]) -> tuple[int, dict[str, object]]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = og.main(args)
        return code, json.loads(buffer.getvalue())


class TestSharedCliParserContract(TestCase):
    def test_sync_parser_rejects_changed_even_when_legacy_allow_flag_is_true(self) -> None:
        request_fields = {
            field["name"]
            for field in og._command_request_fields("sync")
            if isinstance(field, dict) and isinstance(field.get("name"), str)
        }
        self.assertNotIn("--changed", request_fields)

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as context:
                og.parse_command_flags(["--changed"], "sync", True, True, True, True)
        payload = json.loads(buffer.getvalue())

        self.assertEqual(context.exception.code, og.EXIT_USAGE)
        self.assertEqual(payload["command"], "sync")
        self.assertIn("does not accept --changed", payload["errors"][0]["message"])

    def test_status_parser_accepts_non_interactive_from_shared_contract(self) -> None:
        options, _ = og.parse_command_flags(["--non-interactive"], "status", False, False, False, False)

        self.assertTrue(options["non_interactive"])


class TestSharedCliMcpContracts(_RepoContractTestCase):
    def test_mcp_server_tools_embed_schema_signatures(self) -> None:
        with self.repo_patches():
            og._init_outcomegraph()
            schema_code, schema_payload = self.run_main(["--json", "schema"])
            mcp_code, mcp_payload = self.run_main(["--json", "mcp-server"])

        self.assertEqual(schema_code, 0)
        self.assertEqual(mcp_code, 0)
        signatures = {entry["command"]: entry for entry in schema_payload["data"]["commands"]}
        tools = {entry["name"]: entry for entry in mcp_payload["data"]["tools"]}

        self.assertEqual(
            set(tools),
            {str(entry["command"]) for entry in og._mcp_command_signatures()},
        )
        for name, tool in tools.items():
            self.assertEqual(tool["signature"], signatures[name])
        self.assertEqual(
            {entry["name"] for entry in mcp_payload["data"]["resources"]},
            set(og.MCP_CONTROL_RESOURCE_NAMES),
        )

    def test_exported_mcp_resources_follow_shared_contract_registry(self) -> None:
        with self.repo_patches():
            og._init_outcomegraph()
            og._run_export_refresh(str(self.repo))

        export_payload = json.loads((self.repo / og.EXPORT_PATHS["mcp_resources"]).read_text(encoding="utf-8"))
        signatures = {entry["command"]: entry for entry in og._schema_command_payload()["commands"]}

        self.assertEqual(
            {entry["name"] for entry in export_payload["tools"]},
            {str(entry["command"]) for entry in og._mcp_command_signatures()},
        )
        for tool in export_payload["tools"]:
            self.assertEqual(tool["signature"], signatures[tool["name"]])
        self.assertEqual(
            {entry["name"] for entry in export_payload["resources"]},
            set(og.MCP_CONTROL_RESOURCE_NAMES),
        )
        self.assertEqual(
            export_payload["artifact_counts"],
            {entry["name"]: len(entry["paths"]) for entry in export_payload["resources"]},
        )
