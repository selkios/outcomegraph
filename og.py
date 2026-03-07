#!/usr/bin/env python3
"""OutcomeGraph stable CLI contract scaffold."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
import importlib.metadata
import json
import fnmatch
import math
import os
import re
import shutil
import subprocess
import datetime
import sys
import socket
import hashlib
import signal
import time
import shlex
import tempfile
import string
import tomllib
from typing import Any, TypedDict, cast

import click
import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from typer.main import get_command as typer_get_command


def _load_runtime_version() -> str:
    pyproject_path = os.path.join(os.path.dirname(__file__), "pyproject.toml")
    try:
        with open(pyproject_path, "rb") as handle:
            payload = tomllib.load(handle)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        payload = None

    if isinstance(payload, dict):
        project = payload.get("project")
        version = project.get("version") if isinstance(project, dict) else None
        if isinstance(version, str):
            normalized_version = version.strip()
            if normalized_version:
                return normalized_version

    try:
        installed_version = importlib.metadata.version("outcomegraph")
    except importlib.metadata.PackageNotFoundError:
        installed_version = None
    except Exception:
        installed_version = None

    if isinstance(installed_version, str):
        normalized_version = installed_version.strip()
        if normalized_version:
            return normalized_version

    return "0.1.0"


VERSION = _load_runtime_version()
TOP_LEVEL_AGENT_GUIDANCE_PATH = "CONTEXT.md"
AGENT_GUIDANCE_CONTRACT_VERSION = 1
CANONICAL_ARTIFACT_SCHEMA_VERSION = 2

EXIT_SUCCESS = 0
EXIT_USAGE = 64
EXIT_RUNTIME = 1
USAGE_ERROR_CODE = "USAGE_ERROR"
RUNTIME_ERROR_CODE = "RUNTIME_ERROR"
SESSION_CONTENDED_CODE = "SESSION_CONTENDED"
SESSION_EXPIRED_CODE = "SESSION_EXPIRED"
SESSION_RESUME_INVALID_CODE = "SESSION_RESUME_INVALID"
WORKER_RUNTIME_UNAVAILABLE_CODE = "WORKER_RUNTIME_UNAVAILABLE"
INTEGRITY_CHECK_FAILED_CODE = "INTEGRITY_CHECK_FAILED"
ADAPTER_MANIFEST_INVALID_CODE = "ADAPTER_MANIFEST_INVALID"
ADAPTER_DUPLICATE_CODE = "ADAPTER_DUPLICATE"
ADAPTER_INTERFACE_MISMATCH_CODE = "ADAPTER_INTERFACE_MISMATCH"
TIMEOUT_EXPIRED_CODE = "TIMEOUT_EXPIRED"
RECOVERY_RETRY_EXHAUSTED_CODE = "RECOVERY_RETRY_EXHAUSTED"
POLICY_SCHEMA_VERSION = 2
POLICY_DENIED_CODE = "POLICY_DENIED"
POLICY_CONFIG_ERROR_CODE = "POLICY_CONFIG_ERROR"
AUTONOMOUS_WRITE_BLOCKED_CODE = "AUTONOMOUS_WRITE_BLOCKED"
CONTROL_SURFACE_MISMATCH_CODE = "CONTROL_SURFACE_MISMATCH"
ERROR_CLASS_USAGE = "usage"
ERROR_CLASS_SESSION = "session"
ERROR_CLASS_POLICY = "policy"
ERROR_CLASS_INTEGRITY = "integrity"
ERROR_CLASS_ADAPTER = "adapter"
ERROR_CLASS_RUNTIME = "runtime"
DEFAULT_ERROR_CLASS = ERROR_CLASS_RUNTIME
ERROR_HINT_MAX_LENGTH = 180
ERROR_HINT_DEFAULT = "Inspect command-specific errors for next-step remediation and retry decision."
IDENTIFIER_ALLOWED_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")
IDENTIFIER_MAX_LENGTH = 128
ERROR_CLASS_BY_CODE: dict[str, dict[str, object]] = {
    USAGE_ERROR_CODE: {
        "error_class": ERROR_CLASS_USAGE,
        "retryable": False,
        "hint": "Adjust command arguments/options to satisfy validation.",
    },
    SESSION_CONTENDED_CODE: {
        "error_class": ERROR_CLASS_SESSION,
        "retryable": True,
        "hint": "Wait for the active session to finish or resume the recorded session explicitly.",
    },
    SESSION_EXPIRED_CODE: {
        "error_class": ERROR_CLASS_SESSION,
        "retryable": True,
        "hint": "Start a fresh session after confirming the previous session has expired.",
    },
    SESSION_RESUME_INVALID_CODE: {
        "error_class": ERROR_CLASS_SESSION,
        "retryable": False,
        "hint": "Use the current emitted session_id when resuming a resumable command.",
    },
    POLICY_DENIED_CODE: {
        "error_class": ERROR_CLASS_POLICY,
        "retryable": False,
        "hint": "Review policy allowlist and rerun in an allowed mode with explicit policy configuration.",
    },
    POLICY_CONFIG_ERROR_CODE: {
        "error_class": ERROR_CLASS_POLICY,
        "retryable": False,
        "hint": "Repair .outcomegraph/policy.yaml and rerun the command.",
    },
    AUTONOMOUS_WRITE_BLOCKED_CODE: {
        "error_class": ERROR_CLASS_POLICY,
        "retryable": False,
        "hint": "Wait for policy/integrity remediation before attempting writes in autonomous mode.",
    },
    ADAPTER_INTERFACE_MISMATCH_CODE: {
        "error_class": ERROR_CLASS_ADAPTER,
        "retryable": False,
        "hint": "Install or update adapters to satisfy required interface versions.",
    },
    CONTROL_SURFACE_MISMATCH_CODE: {
        "error_class": ERROR_CLASS_RUNTIME,
        "retryable": False,
        "hint": "Regenerate control-surface artifacts and rerun sync.",
    },
    ADAPTER_MANIFEST_INVALID_CODE: {
        "error_class": ERROR_CLASS_ADAPTER,
        "retryable": False,
        "hint": "Validate adapter manifest syntax and manifest fields.",
    },
    ADAPTER_DUPLICATE_CODE: {
        "error_class": ERROR_CLASS_ADAPTER,
        "retryable": False,
        "hint": "Resolve duplicate adapter registrations in plugin directories.",
    },
    INTEGRITY_CHECK_FAILED_CODE: {
        "error_class": ERROR_CLASS_INTEGRITY,
        "retryable": False,
        "hint": "Repair integrity state and rerun sync.",
    },
    WORKER_RUNTIME_UNAVAILABLE_CODE: {
        "error_class": ERROR_CLASS_RUNTIME,
        "retryable": True,
        "hint": "Retry after worker runtime service becomes available.",
    },
    TIMEOUT_EXPIRED_CODE: {
        "error_class": ERROR_CLASS_RUNTIME,
        "retryable": True,
        "hint": "Increase timeout or retry after transient command delay clears.",
    },
    RECOVERY_RETRY_EXHAUSTED_CODE: {
        "error_class": ERROR_CLASS_RUNTIME,
        "retryable": True,
        "hint": "Retry with a higher retry budget only if the underlying dependency is transient.",
    },
    RUNTIME_ERROR_CODE: {
        "error_class": ERROR_CLASS_RUNTIME,
        "retryable": False,
        "hint": "Retry only after correcting the underlying runtime issue.",
    },
}
POLICY_ALLOW_CATEGORIES = {"file_writes", "verify_commands", "sandbox_operations"}
POLICY_DENY_CATEGORIES = {"file_writes", "verify_commands", "sandbox_operations", "network", "dependencies", "deployment"}

PROFILE_VALUES = {"analyze", "propose", "apply"}
MODE_VALUES = {"observe", "autonomous"}
OUTPUT_MODE_HUMAN = "human"
OUTPUT_MODE_JSON = "json"
OUTPUT_MODE_JSONL = "jsonl"
DEFAULT_PROFILE = "analyze"
DEFAULT_MODE = "observe"
DEFAULT_OUTPUT_MODE = OUTPUT_MODE_HUMAN
SESSION_LIFECYCLE_EPHEMERAL = "ephemeral"
SESSION_LIFECYCLE_RESUMABLE = "resumable"
SESSION_STATE_ACTIVE = "active"
SESSION_STATE_DISABLED = "disabled"
SESSION_STATE_EXPIRED = "expired"
SESSION_STATE_INSTALLED = "installed"
SESSION_STATE_RELEASED = "released"
SESSION_STATE_STOPPED = "stopped"
SESSION_KIND_AUTOPILOT = "autopilot"
SESSION_KIND_DAEMON = "daemon"
SESSION_KIND_SYNC = "sync"
AUTOPILOT_HOOKS = ("pre-commit", "post-commit", "post-merge", "post-checkout", "post-rewrite", "pre-push")
AUTOPILOT_STATE_FILE = ".outcomegraph/autopilot/state.json"
AUTOPILOT_MANAGED_HOOK_DIR = ".outcomegraph/hooks"
AUTOPILOT_BACKUP_DIR = ".outcomegraph/autopilot/backups"
AUTOPILOT_PRE_COMMIT_QUALITY_PASS = "skills/og-quality-pass/scripts/run_quality_pass.sh"
OG_ROOT = ".outcomegraph"
DEFAULT_CONFIG_FILE = f"{OG_ROOT}/config.yaml"
DEFAULT_POLICY_FILE = f"{OG_ROOT}/policy.yaml"
OUTCOME_GITIGNORE = f"{OG_ROOT}/.gitignore"
WORK_STATE_FILE = ".outcomegraph/work/state.json"
WORK_LOCK_FILE = ".outcomegraph/work/lock"
WORK_PENDING_FILE = ".outcomegraph/work/pending"
EVENTS_DIR = ".outcomegraph/events"
INTEGRITY_CHECKPOINT_DIR = f"{EVENTS_DIR}/checkpoints"
INTEGRITY_STATE_FILE = f"{EVENTS_DIR}/integrity_state.json"
INTEGRITY_CHECKPOINT_INTERVAL = 32
INTEGRITY_SIGNER_ENV = "OG_INTEGRITY_CHECKPOINT_SIGNER"
DEFAULT_OUTPUT_ENV = "OG_DEFAULT_OUTPUT"
DEFAULT_PROFILE_ENV = "OG_DEFAULT_PROFILE"
DEFAULT_MODE_ENV = "OG_DEFAULT_MODE"
CONFIG_FILE_ENV = "OG_CONFIG_PATH"
LEGACY_CONFIG_FILE_ENV = "OG_CONFIG_FILE"
POLICY_FILE_ENV = "OG_POLICY_PATH"
LEGACY_POLICY_FILE_ENV = "OG_POLICY_FILE"
CODEX_HOME_OVERRIDE_ENV = "OG_CODEX_HOME"
CODEX_HOME_ENV = "CODEX_HOME"
CAS_DIR = f"{OG_ROOT}/objects"
RUNTIME_IGNORE_PREFIXES = (
    ".outcomegraph/work/",
    ".outcomegraph/cache/",
    ".outcomegraph/events/",
    ".outcomegraph/objects/",
    ".outcomegraph/traces/",
)
EMPTY_TREE_OBJECT_ID = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
OG_INIT_DIRS = (
    "constitution",
    "capsules",
    "refs",
    "decisions",
    "claims",
    "certificates",
    "datasets",
    "events",
    "objects",
    "export",
    "work",
    "cache",
    "traces",
)
EXPORT_PATHS = {
    "agents": ".outcomegraph/export/AGENTS.md",
    "outcomes": ".outcomegraph/export/README_OUTCOMES.md",
    "mcp_resources": ".outcomegraph/export/mcp-resources.json",
    "skill": "skills/outcome-steward/SKILL.md",
}
CLEAN_SCOPES = {"runtime", "generated", "all"}
CLEAN_RUNTIME_TARGETS = (
    f"{OG_ROOT}/work",
    f"{OG_ROOT}/cache",
    f"{OG_ROOT}/events",
    f"{OG_ROOT}/objects",
    f"{OG_ROOT}/traces",
)
CLEAN_GENERATED_TARGETS = (
    f"{OG_ROOT}/capsules",
    f"{OG_ROOT}/refs",
    f"{OG_ROOT}/decisions",
    f"{OG_ROOT}/claims",
    f"{OG_ROOT}/certificates",
    f"{OG_ROOT}/export",
    f"{OG_ROOT}/materials.lock",
)
CLEAN_ALL_TARGETS = (
    OG_ROOT,
    "skills/outcome-steward",
    ".agents/skills/og",
    ".claude/skills/og",
)
CAPSULE_KIND_CODE = "code"
CAPSULE_KIND_TEST = "test"
CAPSULE_KIND_DOC = "doc"
CAPSULE_KIND_CONFIG = "config"
CAPSULE_KIND_RUNTIME = "runtime"
CAPSULE_KIND_VALUES = frozenset(
    {
        CAPSULE_KIND_CODE,
        CAPSULE_KIND_TEST,
        CAPSULE_KIND_DOC,
        CAPSULE_KIND_CONFIG,
        CAPSULE_KIND_RUNTIME,
    }
)
CAPSULE_KIND_DOC_EXTENSIONS = frozenset({".adoc", ".md", ".rst", ".txt"})
CAPSULE_KIND_CONFIG_EXTENSIONS = frozenset({".cfg", ".conf", ".env", ".ini", ".json", ".lock", ".toml", ".yaml", ".yml"})
CAPSULE_KIND_CODE_EXTENSIONS = frozenset(
    {
        ".bash",
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".mjs",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".ts",
        ".tsx",
        ".zsh",
    }
)
CAPSULE_KIND_TEST_PATH_PREFIXES = ("__tests__/", "test/", "tests/")
CAPSULE_KIND_DOC_PATH_PREFIXES = ("doc/", "docs/")
CAPSULE_KIND_CONFIG_PATH_PREFIXES = (".github/", ".idea/", ".vscode/")
CAPSULE_KIND_CONFIG_FILENAMES = frozenset({"dockerfile", "pyproject.toml", "to-do.json", "to-do.schema.json", "uv.lock"})
CAPSULE_KIND_CODE_FILENAMES = frozenset({"og", "ogd"})
CAPSULE_KIND_TEST_FILENAME_SUFFIXES = (
    ".spec.js",
    ".spec.py",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.py",
    ".test.ts",
    ".test.tsx",
    "_test.py",
)
ARTIFACT_QUALITY_SCHEMA_VERSION = 1
ARTIFACT_QUALITY_ACCEPTED_DECISION_STATUSES = frozenset({"accepted", "success", "updated"})
ARTIFACT_QUALITY_MIN_EXECUTABLE_ORACLE_COVERAGE = 1.0
ARTIFACT_QUALITY_MIN_CODE_INVARIANT_COVERAGE = 1.0
ARTIFACT_QUALITY_MIN_CODE_EVIDENCE_COVERAGE = 1.0
ARTIFACT_QUALITY_MAX_SUCCESS_CODE_ADVISORY_ONLY_RATE = 0.0
ARTIFACT_QUALITY_MIN_STALE_DOC_CAPTURE_RATE = 1.0
SYNC_GENERATED_IGNORE_PREFIXES = (
    f"{OG_ROOT}/capsules/",
    f"{OG_ROOT}/refs/",
    f"{OG_ROOT}/decisions/",
    f"{OG_ROOT}/claims/",
    f"{OG_ROOT}/certificates/",
    f"{OG_ROOT}/export/",
    "skills/outcome-steward/",
    ".agents/skills/og/",
    ".claude/skills/og/",
)
SYNC_GENERATED_IGNORE_PATHS = (
    f"{OG_ROOT}/materials.lock",
    OUTCOME_GITIGNORE,
)
MCP_CONTROL_TOOL_DEFS = (
    {
        "uri": "outcomegraph://tools/sync",
        "name": "sync",
        "description": "Run autonomous reconcile pipeline.",
        "category": "tool",
    },
    {
        "uri": "outcomegraph://tools/verify",
        "name": "verify",
        "description": "Run fast verification on impacted capsules.",
        "category": "tool",
    },
    {
        "uri": "outcomegraph://tools/replay",
        "name": "replay",
        "description": "Run replay checks against canonical artifacts.",
        "category": "tool",
    },
    {
        "uri": "outcomegraph://tools/explain",
        "name": "explain",
        "description": "Explain claims and provenance pointers.",
        "category": "tool",
    },
    {
        "uri": "outcomegraph://tools/status",
        "name": "status",
        "description": "Read runtime and freshness summary.",
        "category": "tool",
    },
)
MCP_CONTROL_RESOURCES = ("capsules", "refs", "constitution", "certificates")
MCP_CONTROL_PROMPTS = ("bootstrap", "replay", "repair")
MCP_CONTROL_TOOL_NAMES = tuple(item["name"] for item in MCP_CONTROL_TOOL_DEFS)
MCP_CONTROL_RESOURCE_NAMES = tuple(MCP_CONTROL_RESOURCES)
MCP_CONTROL_PROMPT_NAMES = tuple(MCP_CONTROL_PROMPTS)
CANONICAL_EXPORT_SCOPES = ("capsules", "refs", "decisions", "claims", "certificates", "datasets", "constitution")
WORK_LOCK_STALE_SECONDS = 300
OPTIMIZATION_DEFAULT_MIN_IMPROVEMENT = 0.02
OPTIMIZATION_SUPPORTED_METRICS = ("contains", "exact")
LOCK_STATUS_LOCKED = "locked"
LOCK_STATUS_UNLOCKED = "unlocked"
STATUS_SCHEMA_VERSION = 1
DRIFT_REPORT_SCHEMA_VERSION = 1
COMMAND_RESULT_SCHEMA_VERSION = 1
COMMAND_INTROSPECTION_SCHEMA_VERSION = 1
COMMAND_RESULT_ALLOWED_STATUSES = frozenset({"ok", "warn", "error"})
STATUS_SYNC_STALE_SECONDS = 3600
STATUS_VERIFY_STALE_SECONDS = 24 * 60 * 60
STATUS_CERTIFICATE_STALE_SECONDS = 24 * 60 * 60
TRACKED_EVIDENCE_TAG = "file"
UNTRACKED_EVIDENCE_TAG = "cas"
WORKER_ADAPTER_NAME = "codex"
STORE_ADAPTER_NAME = "filesystem"
ORACLE_ADAPTER_NAME = "null-impl"
SANDBOX_ADAPTER_NAME = "local-worktree"
EXPORTER_ADAPTER_NAME = "canonical"
WORKER_INTERFACE_VERSION = 1
WORKER_SCHEMA_VERSION = 2
WORKER_PROMPT_ASSET_SCHEMA_VERSION = 1
WORKER_ADAPTER_DEFAULT_TIMEOUT_SECONDS = 120
WORKER_MODEL_OVERRIDE_ENV = "OG_WORKER_MODEL"
WORKER_ADAPTER_COMPLEX_TIMEOUT_FILE_COUNT = 6
WORKER_ADAPTER_COMPLEX_TIMEOUT_BYTES = 12_000
WORKER_ADAPTER_COMPLEX_TIMEOUT_EXTENSIONS = frozenset(
    {".c", ".cc", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".jsx", ".php", ".py", ".rb", ".rs", ".sh", ".ts", ".tsx"}
)
WORKER_ADAPTER_DISTILL_BATCH_SIZE = 1
WORKER_ADAPTER_DISTILL_MAX_WORKERS = 4
WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS = 300
WORKER_PROMPT_ASSET_DIR = os.path.join(os.path.dirname(__file__), "prompts", "workers")
WORKER_PROMPT_MANIFEST_PATH = os.path.join(WORKER_PROMPT_ASSET_DIR, "manifest.json")
WORKER_PROMPT_BINDINGS: dict[str, dict[str, str]] = {
    "distill": {"id": "worker-distill", "version": "1.0.1"},
    "replay": {"id": "worker-replay", "version": "1.0.1"},
}
WORKER_PROMPT_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
TRACE_SEGMENT_MAX_LENGTH = 72
SNAPSHOT_DIFF_CONTEXT_LINES = 40
SNAPSHOT_DIFF_MAX_SNIPPETS = 8
DISTILL_SUPPORTING_SNAPSHOT_LIMIT = 6
DISTILL_RELATED_HINT_LIMIT = 4
DISTILL_EXISTING_CLAIM_LIMIT = 3
DISTILL_EXISTING_DECISION_LIMIT = 2
DISTILL_EXISTING_CERTIFICATE_LIMIT = 3
DISTILL_MATERIAL_LIMIT = 12
DISTILL_FEATURE_TOKEN_STOPWORDS = frozenset(
    {
        "app",
        "config",
        "default",
        "doc",
        "docs",
        "example",
        "file",
        "files",
        "index",
        "lib",
        "main",
        "readme",
        "spec",
        "src",
        "test",
        "tests",
    }
)
RECOVERY_MAX_RETRIES_LIMIT = 5
ORACLE_COMMAND_DEFAULT_TIMEOUT_SECONDS = 30
REPLAY_STEP_DEFAULT_TIMEOUT_SECONDS = 120
ADAPTER_SCHEMA_VERSION = 2
ADAPTER_PATH_ENV = "OG_ADAPTER_PATH"
REQUIRED_ADAPTER_TYPES = {"worker", "store"}
SUPPORTED_ADAPTER_TYPES = {"worker", "oracle", "sandbox", "store", "exporter"}
ADAPTER_REQUIRED_INTERFACE_VERSIONS: dict[str, int] = {
    "worker": 1,
    "oracle": 1,
    "sandbox": 1,
    "store": 1,
    "exporter": 1,
}
_ADAPTER_REGISTRY: dict[str, dict[str, dict[str, object]]] = {}
_ADAPTER_DEFAULTS: dict[str, str] = {}


class _AdapterBootstrapState(TypedDict):
    repo_root: str | None
    initialized: bool
    errors: list[dict[str, object]]
    warnings: list[dict[str, object]]


_ADAPTER_BOOTSTRAP_STATE: _AdapterBootstrapState = {
    "repo_root": None,
    "initialized": False,
    "errors": [],
    "warnings": [],
}
WORKER_UNAVAILABLE_ERROR = "codex executable was not found"
CANONICAL_ARTIFACT_TYPES = {
    "capsule",
    "ref",
    "decision",
    "certificate",
    "materials_lock",
    "claim",
    "prompt_pack",
    "eval_dataset",
    "optimization_eval_result",
}
CANONICAL_PATH_ARTIFACT_TYPES = {
    "capsules": "capsule",
    "refs": "ref",
    "decisions": "decision",
    "claims": "claim",
    "certificates": "certificate",
}
DAEMON_SERVICE_DIR = f"{OG_ROOT}/work/daemon"
DAEMON_SERVICE_SCRIPT = f"{DAEMON_SERVICE_DIR}/run-ogd.sh"
DAEMON_SERVICE_STATE = f"{DAEMON_SERVICE_DIR}/state.json"
DAEMON_SERVICE_LOG = f"{DAEMON_SERVICE_DIR}/daemon.log"
DAEMON_SYNC_TIMEOUT_SECONDS = 300
DAEMON_WATCH_INTERVAL_SECONDS = 2
DAEMON_SESSION_STALE_SECONDS = 15
DAEMON_WATCH_IGNORE_PREFIXES = (
    ".git/",
    ".outcomegraph/work/",
    ".outcomegraph/cache/",
    ".outcomegraph/events/",
    ".outcomegraph/objects/",
)
_DAEMON_STOP_REQUESTED = False


def _default_policy() -> dict[str, object]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "mode": "observe",
        "policy_id": "observe-default-v1",
        "allow": {
            "file_writes": [
                ".outcomegraph/**",
                "export/**",
                "skills/outcome-steward/**",
            ],
            "verify_commands": [
                "npm test --listTests",
                "npm test",
                "go test ./...",
                "pytest -q",
            ],
            "sandbox_operations": [
                "create_isolated_worktree",
                "read_repo_state",
                "read_artifacts",
            ],
        },
        "deny": {
            "file_writes": [
                "src/**",
                "lib/**",
                "app/**",
                "packages/**",
            ],
            "network": ["unrestricted"],
            "dependencies": [
                "npm install",
                "pip install",
                "cargo add",
                "go mod tidy",
            ],
            "deployment": ["push", "git commit --amend", "github pr create", "gha workflow_dispatch"],
        },
    }


def _policy_string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if value:
            values.append(value)
    return values


def _policy_merge_lists(base: list[str], incoming: list[str]) -> list[str]:
    values: list[str] = list(base)
    for item in incoming:
        if item not in values:
            values.append(item)
    return values


def _policy_pattern_matches(pattern: str, target: str) -> bool:
    if not pattern:
        return False
    return fnmatch.fnmatch(target, pattern) or target == pattern


def _build_policy_deny_payload(command: str, mode: str, category: str, target: str) -> dict[str, object]:
    normalized_mode = str(mode or "observe")
    normalized_category = category
    normalized_target = str(target or "").strip()

    if normalized_category == "verify_commands":
        message = (
            f"{normalized_mode} mode forbids oracle verification commands that are not explicitly allowlisted."
            if normalized_target
            else f"{normalized_mode} mode forbids an unconfigured oracle verification command."
        )
        remediation = [
            "Run with --mode autonomous only for this explicit action.",
            "Add the command to allowlist.verify_commands in `.outcomegraph/policy.yaml`.",
        ]
    elif normalized_category == "sandbox_operations":
        message = (
            f"{normalized_mode} mode does not allow sandbox operation '{normalized_target}'."
            if normalized_target
            else f"{normalized_mode} mode does not allow this sandbox operation."
        )
        remediation = [
            "Run with --mode autonomous only for this explicit action.",
            "Add the operation to allowlist.sandbox_operations in `.outcomegraph/policy.yaml`.",
        ]
    else:
        message = (
            f"{normalized_mode} mode forbids file writes to '{normalized_target}' without explicit allowlist."
            if normalized_target
            else f"{normalized_mode} mode forbids file writes without explicit allowlist."
        )
        remediation = [
            "Run with --mode autonomous only for this explicit action.",
            "Add the path to allowlist.file_writes in `.outcomegraph/policy.yaml`.",
        ]

    return {
        "status": "error",
        "code": POLICY_DENIED_CODE,
        "command": command,
        "mode": normalized_mode,
        "category": normalized_category,
        "target": normalized_target,
        "message": message,
        "remediation": remediation,
    }


def _enforce_policy_action(
    policy: dict[str, object],
    command: str,
    category: str,
    target: str,
    mode: str,
) -> dict[str, object] | None:
    rules = policy.get("allow") if isinstance(policy.get("allow"), dict) else {}
    deny_rules = policy.get("deny") if isinstance(policy.get("deny"), dict) else {}
    normalized_target = _normalize_repo_relative_path(str(target))
    match_targets = [normalized_target]
    og_prefix = f"{OG_ROOT}/"
    if normalized_target.startswith(og_prefix):
        trimmed = normalized_target[len(og_prefix) :]
        if trimmed:
            match_targets.append(trimmed)

    for deny in _policy_string_list(deny_rules.get(category)) if isinstance(deny_rules, dict) else []:
        if any(_policy_pattern_matches(deny, candidate) for candidate in match_targets):
            return _build_policy_deny_payload(command, mode, category, normalized_target)

    for allow in _policy_string_list(rules.get(category)) if isinstance(rules, dict) else []:
        if any(_policy_pattern_matches(allow, candidate) for candidate in match_targets):
            return None

    return _build_policy_deny_payload(command, mode, category, normalized_target)


def _evaluate_policy_writes(policy: dict[str, object], command: str, mode: str, targets: list[str]) -> dict[str, object] | None:
    for target in targets:
        denied = _enforce_policy_action(policy, command, "file_writes", target, mode)
        if denied is not None:
            return denied
    return None


class AdapterRegistryError(ValueError):
    """Raised when an adapter manifest cannot be registered."""


class AdapterInterfaceMismatchError(AdapterRegistryError):
    """Raised when manifest interface_version does not match the required version."""

    def __init__(self, payload: dict[str, object]):
        super().__init__(payload.get("message", "adapter interface mismatch"))
        self.payload = payload


def _clear_adapter_state() -> None:
    _ADAPTER_REGISTRY.clear()
    _ADAPTER_DEFAULTS.clear()
    _ADAPTER_BOOTSTRAP_STATE["errors"] = []
    _ADAPTER_BOOTSTRAP_STATE["warnings"] = []


def _set_adapter_bootstrap_result(repo_root: str, errors: list[dict[str, object]], warnings: list[dict[str, object]]) -> None:
    _ADAPTER_BOOTSTRAP_STATE["repo_root"] = repo_root
    _ADAPTER_BOOTSTRAP_STATE["initialized"] = True
    _ADAPTER_BOOTSTRAP_STATE["errors"] = errors
    _ADAPTER_BOOTSTRAP_STATE["warnings"] = warnings


def _adapter_manifest_defaults() -> dict[str, tuple[str, dict[str, object]]]:
    return {
        "worker": (WORKER_ADAPTER_NAME, _build_worker_manifest()),
        "store": (STORE_ADAPTER_NAME, _build_store_manifest()),
        "oracle": (ORACLE_ADAPTER_NAME, _build_oracle_manifest()),
        "sandbox": (SANDBOX_ADAPTER_NAME, _build_sandbox_manifest()),
        "exporter": (EXPORTER_ADAPTER_NAME, _build_exporter_manifest()),
    }


def _build_adapter_interface_payload(
    adapter_type: str,
    name: str,
    required_interface_version: int,
    detected_interface_version: object,
) -> dict[str, object]:
    detected = detected_interface_version if isinstance(detected_interface_version, int) else "unknown"
    return {
        "status": "error",
        "code": ADAPTER_INTERFACE_MISMATCH_CODE,
        "type": adapter_type,
        "name": name,
        "required_interface_version": required_interface_version,
        "detected_interface_version": detected,
        "message": (
            f"Adapter '{name}' for type '{adapter_type}' uses interface_version={detected},"
            f" expected {required_interface_version}."
        ),
        "remediation": [
            f"Install a {adapter_type} adapter with interface_version={required_interface_version}.",
            "Or upgrade steward runtime to support the detected interface_version.",
        ],
    }


def _normalize_adapter_capabilities(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("manifest.capabilities must be a string array")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        values.append(item.strip())
    return values


def _normalize_adapter_manifest(raw: object, *, source: str | None = None) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"manifest from {source} must be an object")
    manifest_type = raw.get("type")
    if manifest_type not in SUPPORTED_ADAPTER_TYPES:
        raise ValueError(
            f"manifest.type must be one of {', '.join(sorted(SUPPORTED_ADAPTER_TYPES))}: {manifest_type}"
        )
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("manifest.name must be a non-empty string")
    schema_version = raw.get("schema_version")
    if schema_version != ADAPTER_SCHEMA_VERSION:
        raise ValueError(
            f"manifest.schema_version for {manifest_type}:{name} must be {ADAPTER_SCHEMA_VERSION}, got {schema_version}"
        )
    implementation_version = raw.get("implementation_version")
    if not isinstance(implementation_version, str) or not implementation_version.strip():
        raise ValueError(f"manifest.implementation_version for {manifest_type}:{name} must be a non-empty string")
    interface_version = raw.get("interface_version")
    if not isinstance(interface_version, int):
        raise ValueError(f"manifest.interface_version for {manifest_type}:{name} must be an integer")
    required_interface_version = ADAPTER_REQUIRED_INTERFACE_VERSIONS.get(manifest_type, 1)
    if interface_version != required_interface_version:
        raise AdapterInterfaceMismatchError(
            _build_adapter_interface_payload(
                adapter_type=manifest_type,
                name=str(name),
                required_interface_version=required_interface_version,
                detected_interface_version=interface_version,
            )
        )
    entrypoint = raw.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError(f"manifest.entrypoint for {manifest_type}:{name} must be a non-empty string")
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "type": str(manifest_type),
        "name": str(name).strip(),
        "implementation_version": str(implementation_version).strip(),
        "interface_version": interface_version,
        "capabilities": _normalize_adapter_capabilities(raw.get("capabilities")),
        "entrypoint": entrypoint.strip(),
    }


def adapter_register(adapter_type: str, name: str, impl: object, manifest: object) -> None:
    normalized_type = str(adapter_type)
    normalized_name = str(name).strip()
    if not normalized_type:
        raise AdapterRegistryError("adapter type must not be empty")
    if not normalized_name:
        raise AdapterRegistryError("adapter name must not be empty")
    if normalized_type not in SUPPORTED_ADAPTER_TYPES:
        raise AdapterRegistryError(f"unsupported adapter type '{normalized_type}'")
    normalized_manifest = _normalize_adapter_manifest(manifest, source=f"{normalized_type}:{normalized_name}")
    manifest_name = normalized_manifest.get("name")
    if manifest_name != normalized_name:
        raise AdapterRegistryError(
            f"register name '{normalized_name}' does not match manifest name '{manifest_name}'"
        )
    adapters = _ADAPTER_REGISTRY.setdefault(normalized_type, {})
    if normalized_name in adapters:
        raise AdapterRegistryError(
            f"duplicate adapter registration for {normalized_type}:{normalized_name}"
        )
    adapters[normalized_name] = {"impl": impl, "manifest": normalized_manifest}


def adapter_get(adapter_type: str, name: str | None = None) -> dict[str, object]:
    normalized_type = str(adapter_type)
    if normalized_type not in SUPPORTED_ADAPTER_TYPES:
        raise AdapterRegistryError(f"unsupported adapter type '{normalized_type}'")
    adapters = _ADAPTER_REGISTRY.get(normalized_type, {})
    if not adapters:
        raise AdapterRegistryError(f"no adapters registered for type '{normalized_type}'")
    if name is None:
        default_name = _ADAPTER_DEFAULTS.get(normalized_type)
        if default_name is None:
            default_name = sorted(adapters.keys())[0]
        name = default_name
    normalized_name = str(name)
    entry = adapters.get(normalized_name)
    if entry is None:
        raise AdapterRegistryError(f"adapter '{normalized_name}' not registered for type '{normalized_type}'")
    return {"type": normalized_type, "name": normalized_name, "impl": entry["impl"], "manifest": entry["manifest"]}


def adapter_resolve(adapter_type: str, name: str | None = None) -> dict[str, object]:
    return adapter_get(adapter_type, name)


def adapter_list(adapter_type: str) -> list[dict[str, object]]:
    normalized_type = str(adapter_type)
    if normalized_type not in SUPPORTED_ADAPTER_TYPES:
        raise AdapterRegistryError(f"unsupported adapter type '{normalized_type}'")
    return [
        {
            "type": normalized_type,
            "name": name,
            "manifest": entry["manifest"],
            "impl": entry["impl"],
        }
        for name, entry in sorted(_ADAPTER_REGISTRY.get(normalized_type, {}).items())
    ]


def adapter_set_default(adapter_type: str, name: str) -> None:
    normalized_type = str(adapter_type)
    normalized_name = str(name).strip()
    if normalized_type not in SUPPORTED_ADAPTER_TYPES:
        raise AdapterRegistryError(f"unsupported adapter type '{normalized_type}'")
    if normalized_name not in _ADAPTER_REGISTRY.get(normalized_type, {}):
        raise AdapterRegistryError(f"adapter '{normalized_name}' not registered for type '{normalized_type}'")
    _ADAPTER_DEFAULTS[normalized_type] = normalized_name


def _bootstrap_default_adapters() -> None:
    for adapter_type, payload in _adapter_manifest_defaults().items():
        builtin_name, manifest = payload
        try:
            adapter_register(adapter_type, builtin_name, {"entrypoint": manifest["entrypoint"]}, manifest)
        except AdapterRegistryError:
            continue
        adapter_set_default(adapter_type, builtin_name)


def _normalize_adapter_manifest_path(raw_path: object) -> str | None:
    if not isinstance(raw_path, str):
        return None
    normalized = raw_path.strip()
    if not normalized:
        return None
    return normalized


def _normalize_adapter_search_root(raw_path: object, repo_root: str) -> str | None:
    normalized = _normalize_adapter_manifest_path(raw_path)
    if normalized is None:
        return None
    normalized = os.path.expanduser(normalized)
    if not os.path.isabs(normalized):
        normalized = os.path.normpath(os.path.join(repo_root, normalized))
    return normalized


def _collect_adapter_paths(search_root: str, adapter_type: str | None = None) -> list[str]:
    if not os.path.isdir(search_root):
        return []
    candidate_paths: list[str] = []
    if adapter_type is None:
        try:
            items = sorted(os.listdir(search_root))
        except OSError:
            return []
        candidate_paths = [
            os.path.join(search_root, filename)
            for filename in items
            if filename.endswith(".json") and os.path.isfile(os.path.join(search_root, filename))
        ]
    else:
        typed_root = os.path.join(search_root, adapter_type)
        if os.path.isdir(typed_root):
            try:
                items = sorted(os.listdir(typed_root))
            except OSError:
                items = []
            candidate_paths.extend(
                os.path.join(typed_root, filename)
                for filename in items
                if filename.endswith(".json") and os.path.isfile(os.path.join(typed_root, filename))
            )
    return candidate_paths


def _read_and_register_adapter(
    path: str,
    errors: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> None:
    payload = _read_json_file(path)
    if payload is None:
        warnings.append({
            "status": "error",
            "code": ADAPTER_MANIFEST_INVALID_CODE,
            "path": path,
            "message": f"unable to read adapter manifest: {path}",
        })
        return
    try:
        manifest = _normalize_adapter_manifest(payload, source=path)
        adapter_type = str(manifest.get("type"))
        adapter_name = str(manifest.get("name"))
    except AdapterInterfaceMismatchError as exc:
        mismatch_payload = exc.payload
        mismatch_payload["path"] = path
        if adapter_type := mismatch_payload.get("type"):
            if str(adapter_type) in REQUIRED_ADAPTER_TYPES:
                errors.append(mismatch_payload)
            else:
                warnings.append(mismatch_payload)
        else:
            warnings.append(mismatch_payload)
        return
    except ValueError as exc:
        warnings.append(
            {
                "status": "error",
                "code": ADAPTER_MANIFEST_INVALID_CODE,
                "path": path,
                "message": str(exc),
            }
        )
        return

    try:
        adapter_register(adapter_type, adapter_name, {"path": path}, manifest)
    except AdapterRegistryError:
        warnings.append(
            {
                "status": "error",
                "code": ADAPTER_DUPLICATE_CODE,
                "path": path,
                "type": adapter_type,
                "name": adapter_name,
                "message": f"duplicate adapter registration for {adapter_type}:{adapter_name} skipped",
            }
        )


def _discover_adapter_manifests(
    search_root: str, *, include_types: bool = True
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    normalized_root = os.path.normpath(search_root)
    if not os.path.isdir(normalized_root):
        return [], []
    if include_types:
        adapter_types = sorted(SUPPORTED_ADAPTER_TYPES)
    else:
        adapter_types = [None]

    seen_paths: set[str] = set()
    for adapter_type in adapter_types:
        for raw_path in _collect_adapter_paths(normalized_root, adapter_type):
            path = os.path.normpath(raw_path)
            if path in seen_paths:
                continue
            seen_paths.add(path)
            _read_and_register_adapter(path, errors, warnings)

    return errors, warnings


def _initialize_adapter_runtime(repo_root: str) -> list[dict[str, object]]:
    if _ADAPTER_BOOTSTRAP_STATE["initialized"] and _ADAPTER_BOOTSTRAP_STATE["repo_root"] == repo_root:
        if _ADAPTER_BOOTSTRAP_STATE["errors"]:
            return list(_ADAPTER_BOOTSTRAP_STATE["errors"])
        return []

    _clear_adapter_state()
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    _bootstrap_default_adapters()

    repo_adapters_root = os.path.join(repo_root, OG_ROOT, "adapters")
    for adapter_type in sorted(SUPPORTED_ADAPTER_TYPES):
        for path in _collect_adapter_paths(repo_adapters_root, adapter_type):
            _read_and_register_adapter(path, errors, warnings)

    for raw_override in os.environ.get(ADAPTER_PATH_ENV, "").split(os.pathsep):
        normalized_root = _normalize_adapter_search_root(raw_override, repo_root)
        if normalized_root is None:
            continue
        discovered_errors, discovered_warnings = _discover_adapter_manifests(normalized_root, include_types=True)
        errors.extend(discovered_errors)
        warnings.extend(discovered_warnings)

    for adapter_type in sorted(SUPPORTED_ADAPTER_TYPES):
        if adapter_type not in _ADAPTER_DEFAULTS:
            available = sorted(_ADAPTER_REGISTRY.get(adapter_type, {}).keys())
            if available:
                _ADAPTER_DEFAULTS[adapter_type] = available[0]

    for required_type in sorted(REQUIRED_ADAPTER_TYPES):
        if required_type not in _ADAPTER_DEFAULTS:
            errors.append(
                {
                    "status": "error",
                    "code": ADAPTER_INTERFACE_MISMATCH_CODE,
                    "type": required_type,
                    "name": _adapter_manifest_defaults().get(required_type, ("", {}))[0],
                    "required_interface_version": ADAPTER_REQUIRED_INTERFACE_VERSIONS[required_type],
                    "detected_interface_version": None,
                    "message": f"missing required {required_type} adapter registration",
                    "remediation": [
                        "Restore required built-in adapters or install a compatible adapter plugin.",
                        "Or update steward runtime to add support for required adapter definitions.",
                    ],
                }
            )

    # Merge errors and warnings gathered during initialization.
    _ADAPTER_BOOTSTRAP_STATE["errors"].extend(errors)
    _ADAPTER_BOOTSTRAP_STATE["warnings"].extend(warnings)
    initialized_errors = list(_ADAPTER_BOOTSTRAP_STATE["errors"])
    _set_adapter_bootstrap_result(
        repo_root,
        errors=_ADAPTER_BOOTSTRAP_STATE["errors"],
        warnings=_ADAPTER_BOOTSTRAP_STATE["warnings"],
    )
    return initialized_errors


def _build_store_manifest() -> dict[str, object]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "type": "store",
        "name": STORE_ADAPTER_NAME,
        "implementation_version": "1.0.0",
        "interface_version": ADAPTER_REQUIRED_INTERFACE_VERSIONS["store"],
        "capabilities": ["put", "get", "exists"],
        "entrypoint": "filesystem-store://v1",
    }


def _build_oracle_manifest() -> dict[str, object]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "type": "oracle",
        "name": ORACLE_ADAPTER_NAME,
        "implementation_version": "1.0.0",
        "interface_version": ADAPTER_REQUIRED_INTERFACE_VERSIONS["oracle"],
        "capabilities": ["run"],
        "entrypoint": "null-oracle://v1",
    }


def _build_sandbox_manifest() -> dict[str, object]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "type": "sandbox",
        "name": SANDBOX_ADAPTER_NAME,
        "implementation_version": "1.0.0",
        "interface_version": ADAPTER_REQUIRED_INTERFACE_VERSIONS["sandbox"],
        "capabilities": ["create", "exec", "destroy"],
        "entrypoint": "local-worktree://v1",
    }


def _build_exporter_manifest() -> dict[str, object]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "type": "exporter",
        "name": EXPORTER_ADAPTER_NAME,
        "implementation_version": "1.0.0",
        "interface_version": ADAPTER_REQUIRED_INTERFACE_VERSIONS["exporter"],
        "capabilities": ["render"],
        "entrypoint": "canonical-exporter://v1",
    }


def _build_worker_manifest() -> dict[str, object]:
    return {
        "schema_version": WORKER_SCHEMA_VERSION,
        "type": "worker",
        "name": WORKER_ADAPTER_NAME,
        "implementation_version": "1.0.0",
        "interface_version": WORKER_INTERFACE_VERSION,
        "capabilities": ["distill", "replay", "explain"],
        "entrypoint": "codex://v1",
    }


class WorkerAdapterError(ValueError):
    """Raised when a worker adapter returns malformed structured output."""


class _CommandResultErrorModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    error_class: str
    error_code: str
    message: str
    retryable: bool
    hint: str

    @field_validator("error_class", "error_code", "message", "hint")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized


class _CommandResultEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    command: str
    status: str
    run_id: str | None = None
    session_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[_CommandResultErrorModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    subcommand: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != COMMAND_RESULT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {COMMAND_RESULT_SCHEMA_VERSION}")
        return value

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("command must not be empty")
        return normalized

    @field_validator("status")
    @classmethod
    def _normalize_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("status must not be empty")
        if normalized not in COMMAND_RESULT_ALLOWED_STATUSES:
            allowed = ", ".join(sorted(COMMAND_RESULT_ALLOWED_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        return normalized

    @field_validator("run_id", "session_id", "subcommand")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty when provided")
        return normalized


class _TyperCommandContext(TypedDict):
    output_json: bool


_ACTIVE_TYPER_COMMAND_CONTEXT: ContextVar[_TyperCommandContext | None] = ContextVar(
    "_ACTIVE_TYPER_COMMAND_CONTEXT",
    default=None,
)


def _current_typer_command_context() -> _TyperCommandContext:
    context = _ACTIVE_TYPER_COMMAND_CONTEXT.get()
    if context is None:
        raise RuntimeError("typer command context is unavailable")
    return context


def emit_usage() -> str:
    return f"""Usage: og [--json] [--strict] [--non-interactive] [--profile analyze|propose|apply] [--mode observe|autonomous] <command>

Core commands:
  og init
  og sync
  og verify [--changed]
  og replay [--changed]
  og status
  og doctor
  og export
  og clean [--scope runtime|generated|all] [--dry-run] [--yes]
  og explain [--capsule <id>[,<id>...]] [--ref <id>[,<id>...]] [--certificate <id>[,<id>...]]
  og schema
  og describe <command>
  og drift
  og mcp-server
  og optimize prompts
  og autopilot init|disable
  og daemon install|start|stop|status|run

Use: og <command> --help for command-specific contracts.
Defaults: CLI flags override {DEFAULT_OUTPUT_ENV}, {DEFAULT_PROFILE_ENV}, and {DEFAULT_MODE_ENV}; env defaults override {CONFIG_FILE_ENV}; worker state can use {CODEX_HOME_OVERRIDE_ENV} or {CODEX_HOME_ENV}.
"""


def _command_contract_help() -> str:
    return """Output modes:
  default   human-readable payload/message output
  --json    machine-readable JSON payload output
  --output json|jsonl|human
            json output mode control; jsonl streams list-like payload entries as JSON lines

Default precedence:
  CLI flags  -> --json / --output / --profile / --mode
  env vars   -> OG_DEFAULT_OUTPUT / OG_DEFAULT_PROFILE / OG_DEFAULT_MODE / OG_CONFIG_PATH / OG_POLICY_PATH / OG_CODEX_HOME
  config     -> .outcomegraph/config.yaml

Exit codes:
  0        success
  1        runtime failure
  64       usage / validation failure
"""


def _command_help(usage: str, summary: str, options: list[str], examples: list[str], notes: list[str] | None = None) -> str:
    options = list(options)
    if not any(option.startswith("--strict") for option in options):
        if options == ["none"]:
            options = [*options, "--strict[=true|false]"]
        else:
            options.append("--strict[=true|false]")

    lines = [f"Usage: {usage}", "", summary, "", "Accepted options:"]
    if options:
        lines.extend(f"  {item}" for item in options)
    else:
        lines.append("  none")
    lines.extend(["", "Examples:"])
    if examples:
        lines.extend(f"  {item}" for item in examples)
    if notes:
        lines.extend(["", "Notes:"])
        lines.extend(f"  {item}" for item in notes)
    lines.append("")
    lines.append(_command_contract_help())
    return "\n".join(lines)


def _help_for_command(command: str) -> str:
    normalized = " ".join(command.split())
    if normalized == "init":
        return _command_help(
            "og init",
            "Initialize .outcomegraph state and default policy files.",
            ["--json"],
            ["og init"],
        )
    if normalized == "sync":
        return _command_help(
            "og sync [--profile analyze|propose|apply] [--mode observe|autonomous] [--force-full-sync[=true|false]] [--validate[=true|false]] [--dry-run[=true|false]] [--max-retries <n>] [--timeout <seconds>]",
            "Collect changes, distill/categorize them, apply artifacts, verify, and export outputs.",
            [
                "--json",
                "--profile analyze|propose|apply",
                "--mode observe|autonomous",
                "--force-full-sync[=true|false]",
                "--validate[=true|false]",
                "--dry-run[=true|false]",
                "--max-retries <n>",
                "--timeout <seconds>",
            ],
            [
                "og sync",
                "og sync --profile propose --mode autonomous",
                "og sync --force-full-sync=true",
                "og sync --validate --json",
                "og sync --dry-run --timeout 180 --max-retries 1",
            ],
        )
    if normalized == "verify":
        return _command_help(
            "og verify [--changed] [--profile analyze|propose|apply] [--mode observe|autonomous] [--output json|jsonl|human] [--fields <field>[,<field>...]] [--limit <n>] [--offset <n>] [--validate[=true|false]] [--dry-run[=true|false]] [--max-retries <n>] [--timeout <seconds>]",
            "Run verification for known or changed capsules and emit verification artifacts.",
            [
                "--json",
                "--output json|jsonl|human",
                "--fields <field>[,<field>...]",
                "--limit <n>",
                "--offset <n>",
                "--changed[=true|false]",
                "--profile analyze|propose|apply",
                "--mode observe|autonomous",
                "--validate[=true|false]",
                "--dry-run[=true|false]",
                "--max-retries <n>",
                "--timeout <seconds>",
            ],
            [
                "og verify",
                "og verify --changed",
                "og verify --changed=false --json",
                "og verify --validate --json",
            ],
        )
    if normalized == "replay":
        return _command_help(
            "og replay [--changed] [--profile analyze|propose|apply] [--mode observe|autonomous] [--output json|jsonl|human] [--fields <field>[,<field>...]] [--limit <n>] [--offset <n>] [--validate[=true|false]] [--dry-run[=true|false]] [--max-retries <n>] [--timeout <seconds>]",
            "Replay changed artifacts in isolated worktrees to regenerate replay receipts.",
            [
                "--json",
                "--output json|jsonl|human",
                "--fields <field>[,<field>...]",
                "--limit <n>",
                "--offset <n>",
                "--changed[=true|false]",
                "--profile analyze|propose|apply",
                "--mode observe|autonomous",
                "--validate[=true|false]",
                "--dry-run[=true|false]",
                "--max-retries <n>",
                "--timeout <seconds>",
            ],
            [
                "og replay",
                "og replay --changed",
                "og replay --json",
                "og replay --dry-run --timeout 180",
            ],
        )
    if normalized == "status":
        return _command_help(
            "og status",
            "Show freshness, lock, verification, and daemon/autopilot state.",
            ["--json"],
            ["og status", "og status --json"],
        )
    if normalized == "doctor":
        return _command_help(
            "og doctor",
            "Run machine-readable diagnostics with remediation hints for policy, integrity, exports, and runtime health.",
            ["--json"],
            ["og doctor", "og doctor --json"],
        )
    if normalized == "export":
        return _command_help(
            "og export [--validate[=true|false]] [--dry-run[=true|false]]",
            "Render configured export surfaces from canonical artifacts.",
            [
                "--json",
                "--validate[=true|false]",
                "--dry-run[=true|false]",
            ],
            ["og export", "og export --json", "og export --dry-run --json"],
        )
    if normalized == "clean":
        return _command_help(
            "og clean [--scope runtime|generated|all] [--dry-run[=true|false]] [--yes]",
            "Remove runtime and/or generated outcomegraph state.",
            [
                "--scope runtime|generated|all",
                "--dry-run[=true|false]",
                "--yes[=true|false]",
                "--json",
            ],
            [
                "og clean --scope runtime",
                "og clean --scope all --dry-run",
                "og clean --scope generated --yes",
            ],
        )
    if normalized == "explain":
        return _command_help(
            "og explain [--capsule <id>[,<id>...]] [--ref <id>[,<id>...]] [--certificate <id>[,<id>...]] [--profile analyze|propose|apply] [--mode observe|autonomous] [--output json|jsonl|human] [--fields <field>[,<field>...]] [--limit <n>] [--offset <n>]",
            "Explain artifact provenance and proof chain for selected capsules, refs, and certificates.",
            [
                "--json",
                "--output json|jsonl|human",
                "--fields <field>[,<field>...]",
                "--limit <n>",
                "--offset <n>",
                "--capsule <id>[,<id>...]",
                "--ref <id>[,<id>...]",
                "--certificate <id>[,<id>...]",
                "--profile analyze|propose|apply",
                "--mode observe|autonomous",
            ],
            [
                "og explain",
                "og explain --capsule default",
                "og explain --json --capsule default --ref ref-1",
            ],
        )
    if normalized == "drift":
        return _command_help(
            "og drift",
            "Run canonical drift checks for policy and certificate health.",
            ["--json"],
            ["og drift", "og drift --json"],
        )
    if normalized == "mcp-server":
        return _command_help(
            "og mcp-server [--output json|jsonl|human] [--fields <field>[,<field>...]] [--limit <n>] [--offset <n>]",
            "Render MCP server control surface definitions (tools/resources/prompts).",
            [
                "--json",
                "--output json|jsonl|human",
                "--fields <field>[,<field>...]",
                "--limit <n>",
                "--offset <n>",
            ],
            ["og mcp-server", "og mcp-server --json"],
        )
    if normalized == "optimize":
        return _command_help(
            "og optimize",
            "Command group for optimization workflows.",
            ["subcommand: prompts"],
            ["og optimize --help", "og optimize prompts --help"],
            ["subcommand aliases are currently not supported"],
        )
    if normalized == "optimize prompts":
        return _command_help(
            "og optimize prompts --dataset <path> --candidate <path> --baseline <path> [--metric contains|exact] [--min-improvement <float>] [--approve[=true|false]] [--params <json-file|->]",
            "Run dataset-based prompt optimization and optionally activate a candidate when it passes thresholds.",
            [
                "--dataset <path>",
                "--candidate <path>",
                "--baseline <path>",
                "--metric contains|exact",
                "--min-improvement <float>",
                "--approve[=true|false]",
                "--params <json-file|->",
                "--json",
            ],
            [
                "og optimize prompts --dataset .outcomegraph/datasets/bugfix.json --candidate next.txt --baseline base.txt",
                "og optimize prompts --dataset ds.json --candidate next.txt --baseline base.txt --approve",
                "cat payload.json | og optimize prompts --params -",
            ],
        )
    if normalized == "autopilot":
        return _command_help(
            "og autopilot",
            "Command group for hook bootstrap/teardown.",
            ["subcommand: init | disable"],
            ["og autopilot --help", "og autopilot init --help", "og autopilot disable --help"],
        )
    if normalized == "autopilot init":
        return _command_help(
            "og autopilot init [--force-hooks-path[=true|false]] [--yes]",
            "Install outcomegraph-managed git hooks for lifecycle integration.",
            [
                "--force-hooks-path[=true|false]",
                "--yes[=true|false]",
                "--json",
            ],
            ["og autopilot init", "og autopilot init --force-hooks-path --yes --json"],
        )
    if normalized == "autopilot disable":
        return _command_help(
            "og autopilot disable [--session-id <id>]",
            "Remove outcomegraph-managed hooks and restore prior hook state where available.",
            ["--session-id <id>", "--json"],
            ["og autopilot disable", "og autopilot disable --session-id autopilot-20260307t000000z-abcdef1234 --json"],
            ["`autopilot init` emits a resumable session_id that can be asserted on disable."],
        )
    if normalized == "daemon":
        return _command_help(
            "og daemon",
            "Command group for watcher lifecycle.",
            ["subcommand: install | start | stop | status | run"],
            ["og daemon --help", "og daemon status --help", "og daemon install --help", "og daemon run --help"],
        )
    if normalized == "daemon install":
        return _command_help(
            "og daemon install",
            "Install the long-running watcher wrapper under .outcomegraph/work/daemon.",
            ["--json"],
            ["og daemon install", "og daemon install --json"],
        )
    if normalized == "daemon start":
        return _command_help(
            "og daemon start [--session-id <id>]",
            "Start the managed watcher process and persist runtime status.",
            ["--session-id <id>", "--json"],
            ["og daemon start", "og daemon start --session-id daemon-20260307t000000z-abcdef1234 --json"],
            ["`daemon install` and `daemon status` emit a resumable daemon session_id."],
        )
    if normalized == "daemon stop":
        return _command_help(
            "og daemon stop [--session-id <id>]",
            "Stop the managed watcher process.",
            ["--session-id <id>", "--json"],
            ["og daemon stop", "og daemon stop --session-id daemon-20260307t000000z-abcdef1234 --json"],
        )
    if normalized == "daemon status":
        return _command_help(
            "og daemon status [--session-id <id>]",
            "Read watcher install/runtime and last-sync status.",
            ["--session-id <id>", "--json"],
            ["og daemon status", "og daemon status --session-id daemon-20260307t000000z-abcdef1234 --json"],
        )
    if normalized == "daemon run":
        return _command_help(
            "og daemon run",
            "Internal run loop entrypoint. This command is used by the installed watcher wrapper.",
            ["none"],
            ["og daemon run"],
            [
                "This command blocks while polling repository changes; no JSON payload is emitted.",
            ],
        )
    if normalized == "schema":
        return _command_help(
            "og schema",
            "Emit machine-readable command signatures and request/response schemas.",
            ["--json"],
            ["og schema", "og schema --json"],
        )
    if normalized == "describe":
        return _command_help(
            "og describe <command>",
            "Describe the request/response signature for a known CLI command.",
            ["--json"],
            ["og describe sync", "og describe daemon status"],
        )
    return emit_usage() + "\nUse --help with a recognized command for details."


def _render_command_schema_field(field: dict[str, object]) -> str:
    name = str(field.get("name") or "<unknown>")
    field_type = str(field.get("type") or "object")
    details = [field_type]
    if field.get("required") is True:
        details.append("required")
    if "default" in field:
        details.append(f"default={field['default']!r}")
    enum = field.get("enum")
    if isinstance(enum, list):
        enum_values = [str(item) for item in enum if str(item).strip()]
        if enum_values:
            details.append("enum=" + "|".join(enum_values))
    description = str(field.get("description") or "").strip()
    detail_text = ", ".join(details)
    if description:
        return f"  {name} ({detail_text}): {description}"
    return f"  {name} ({detail_text})"


def _render_command_signature(signature: dict[str, object]) -> str:
    command = str(signature.get("command") or "unknown")
    usage = str(signature.get("usage") or f"og {command}")
    summary = str(signature.get("summary") or "").strip()
    request = signature.get("request") if isinstance(signature.get("request"), dict) else {}
    response = signature.get("response") if isinstance(signature.get("response"), dict) else {}
    request_fields = request.get("fields") if isinstance(request.get("fields"), list) else []
    response_fields = response.get("data_fields") if isinstance(response.get("data_fields"), list) else []
    known_error_codes = [
        str(item)
        for item in signature.get("known_error_codes", [])
        if isinstance(item, str) and item.strip()
    ]
    examples = [
        str(item)
        for item in signature.get("examples", [])
        if isinstance(item, str) and item.strip()
    ]
    subcommands = [
        str(item)
        for item in signature.get("subcommands", [])
        if isinstance(item, str) and item.strip()
    ]
    lines = [f"Command: {command}", f"Usage: {usage}"]
    if summary:
        lines.extend(["", summary])
    lines.extend(["", "Request fields:"])
    if request_fields:
        for field in request_fields:
            if isinstance(field, dict):
                lines.append(_render_command_schema_field(cast(dict[str, object], field)))
    else:
        lines.append("  none")
    if subcommands:
        lines.extend(["", "Subcommands:"])
        lines.extend(f"  {item}" for item in subcommands)
    lines.extend(["", "Response fields:"])
    if response_fields:
        for field in response_fields:
            if isinstance(field, dict):
                lines.append(_render_command_schema_field(cast(dict[str, object], field)))
    else:
        lines.append("  none")
    if known_error_codes:
        lines.extend(["", "Known error codes:"])
        lines.extend(f"  {item}" for item in known_error_codes)
    if examples:
        lines.extend(["", "Examples:"])
        lines.extend(f"  {item}" for item in examples)
    return "\n".join(lines)


def _render_schema_overview(payload: dict[str, object]) -> str:
    schema_version = payload.get("schema_version")
    command_count = int(payload.get("command_count") or 0)
    commands = payload.get("commands") if isinstance(payload.get("commands"), list) else []
    lines = [
        f"OutcomeGraph CLI schema v{schema_version}",
        f"Envelope schema v{COMMAND_RESULT_SCHEMA_VERSION}",
        f"Commands: {command_count}",
        "",
    ]
    for entry in commands:
        if not isinstance(entry, dict):
            continue
        usage = str(entry.get("usage") or f"og {entry.get('command') or 'unknown'}")
        summary = str(entry.get("summary") or "").strip()
        lines.append(usage)
        if summary:
            lines.append(f"  {summary}")
    lines.extend(
        [
            "",
            "Use `og describe <command>` for a detailed command contract.",
            "Use `og schema --json` for machine-readable output.",
        ]
    )
    return "\n".join(lines)


def _command_schema_field(
    name: str,
    field_type: str,
    description: str,
    *,
    required: bool = False,
    default: object | None = None,
    enum: list[str] | None = None,
) -> dict[str, object]:
    field: dict[str, object] = {
        "name": name,
        "type": field_type,
        "description": description,
        "required": required,
    }
    if default is not None:
        field["default"] = default
    if enum is not None:
        field["enum"] = enum
    return field


def _command_signature_entry(
    command: str,
    usage: str,
    summary: str,
    request_fields: list[dict[str, object]],
    response_fields: list[dict[str, object]],
    known_error_codes: list[str],
    *,
    examples: list[str] | None = None,
    subcommands: list[str] | None = None,
) -> dict[str, object]:
    response_schema = {
        "envelope_schema_version": COMMAND_RESULT_SCHEMA_VERSION,
        "data_fields": response_fields,
    }
    request_fields_with_strict = list(request_fields)
    if not any(entry.get("name") == "--strict" for entry in request_fields_with_strict):
        request_fields_with_strict.append(
            _command_schema_field(
                "--strict",
                "boolean",
                "Reject unknown fields, implicit defaults, and lossy coercions in request payload mode.",
                default=False,
            )
        )
    if not any(entry.get("name") == "--non-interactive" for entry in request_fields_with_strict):
        request_fields_with_strict.append(
            _command_schema_field(
                "--non-interactive",
                "boolean",
                "Disable interactive prompting and require explicit confirmation flags.",
                default=False,
            )
        )

    required_request = [entry["name"] for entry in request_fields_with_strict if entry.get("required")]
    signature: dict[str, object] = {
        "command": command,
        "usage": usage,
        "summary": summary,
        "request": {
            "fields": request_fields_with_strict,
            "required_fields": required_request,
        },
        "response": response_schema,
        "known_error_codes": known_error_codes,
        "examples": examples or [],
    }
    if subcommands:
        signature["subcommands"] = subcommands
    return signature


def _build_cli_command_signatures() -> list[dict[str, object]]:
    command_signatures: list[dict[str, object]] = [
        _command_signature_entry(
            "init",
            "og init",
            "Initialize .outcomegraph state and default policy files.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("options", "object", "Parsed command options."),
                _command_schema_field("updated_dirs", "array", "Directories initialized for the repo."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og init", "og init --json"],
        ),
        _command_signature_entry(
            "sync",
            "og sync",
            "Collect changes, distill/categorize them, apply artifacts, verify, and export outputs.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--changed", "boolean", "Limit processing to changed scope.", default=False),
                _command_schema_field(
                    "--profile",
                    "string",
                    "Worker profile selection.",
                    enum=sorted(PROFILE_VALUES),
                ),
                _command_schema_field(
                    "--mode",
                    "string",
                    "Operational mode.",
                    enum=sorted(MODE_VALUES),
                ),
                _command_schema_field(
                    "--force-full-sync",
                    "boolean",
                    "Rebuild from all non-runtime files instead of the current git diff baseline.",
                    default=False,
                ),
                _command_schema_field("--validate", "boolean", "Run preflight validation without mutating artifacts.", default=False),
                _command_schema_field("--dry-run", "boolean", "Render a no-write execution plan for the command.", default=False),
                _command_schema_field("--max-retries", "integer", "Maximum retries for transient worker and oracle failures.", default=0),
                _command_schema_field("--timeout", "integer", "Override subprocess timeout in seconds for worker and oracle steps."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok`, `error`, or `warn`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Ephemeral sync lock session identifier."),
                _command_schema_field("session", "object", "Ephemeral sync lock session metadata."),
                _command_schema_field("options", "object", "Parsed command options."),
                _command_schema_field("steps", "array", "Pipeline stage results."),
                _command_schema_field("summary_event", "string", "Summary event path."),
                _command_schema_field("recovery", "object", "Retry/timeout recovery summary for nested operations."),
                _command_schema_field("errors", "array", "Typed error records when status is error."),
            ],
            [
                USAGE_ERROR_CODE,
                RUNTIME_ERROR_CODE,
                SESSION_CONTENDED_CODE,
                INTEGRITY_CHECK_FAILED_CODE,
                WORKER_RUNTIME_UNAVAILABLE_CODE,
                TIMEOUT_EXPIRED_CODE,
                RECOVERY_RETRY_EXHAUSTED_CODE,
            ],
            examples=["og sync", "og sync --profile propose", "og sync --force-full-sync", "og sync --validate --json"],
        ),
        _command_signature_entry(
            "verify",
            "og verify",
            "Run verification for known or changed capsules and emit verification artifacts.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field(
                    "--output",
                    "string",
                    "Output mode.",
                    enum=[OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL],
                    default=OUTPUT_MODE_JSON,
                ),
                _command_schema_field("--fields", "string", "Comma-separated top-level payload fields."),
                _command_schema_field("--limit", "integer", "Maximum list items per list-like field."),
                _command_schema_field("--offset", "integer", "0-based list offset for pagination."),
                _command_schema_field("--changed", "boolean", "Verify only changed capsules.", default=False),
                _command_schema_field("--profile", "string", "Worker profile selection.", enum=sorted(PROFILE_VALUES)),
                _command_schema_field("--mode", "string", "Operational mode.", enum=sorted(MODE_VALUES)),
                _command_schema_field("--validate", "boolean", "Run preflight validation without mutating artifacts.", default=False),
                _command_schema_field("--dry-run", "boolean", "Render a no-write execution plan for the command.", default=False),
                _command_schema_field("--max-retries", "integer", "Maximum retries for transient oracle failures.", default=0),
                _command_schema_field("--timeout", "integer", "Override oracle timeout in seconds."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("options", "object", "Parsed command options."),
                _command_schema_field("results", "array", "Verification results for each stage."),
                _command_schema_field("list_window", "object", "Pagination metadata for emitted list fields."),
                _command_schema_field("recovery", "object", "Retry/timeout recovery summary for nested operations."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE, TIMEOUT_EXPIRED_CODE, RECOVERY_RETRY_EXHAUSTED_CODE],
            examples=["og verify --changed", "og verify --json", "og verify --validate --json"],
        ),
        _command_signature_entry(
            "replay",
            "og replay",
            "Replay changed artifacts in isolated worktrees to regenerate replay receipts.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field(
                    "--output",
                    "string",
                    "Output mode.",
                    enum=[OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL],
                    default=OUTPUT_MODE_JSON,
                ),
                _command_schema_field("--fields", "string", "Comma-separated top-level payload fields."),
                _command_schema_field("--limit", "integer", "Maximum list items per list-like field."),
                _command_schema_field("--offset", "integer", "0-based list offset for pagination."),
                _command_schema_field("--changed", "boolean", "Replay only changed capsules.", default=False),
                _command_schema_field("--profile", "string", "Worker profile selection.", enum=sorted(PROFILE_VALUES)),
                _command_schema_field("--mode", "string", "Operational mode.", enum=sorted(MODE_VALUES)),
                _command_schema_field("--validate", "boolean", "Run preflight validation without mutating artifacts.", default=False),
                _command_schema_field("--dry-run", "boolean", "Render a no-write execution plan for the command.", default=False),
                _command_schema_field("--max-retries", "integer", "Maximum retries for transient worker, replay-step, and oracle failures.", default=0),
                _command_schema_field("--timeout", "integer", "Override worker, replay-step, and oracle timeouts in seconds."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("options", "object", "Parsed command options."),
                _command_schema_field("replay_plans", "array", "Replay plan artifacts produced."),
                _command_schema_field("replay_results", "array", "Replay execution results."),
                _command_schema_field("certificate_ids", "array", "Replay certificates issued."),
                _command_schema_field("list_window", "object", "Pagination metadata for emitted list fields."),
                _command_schema_field("recovery", "object", "Retry/timeout recovery summary for nested operations."),
            ],
            [
                USAGE_ERROR_CODE,
                RUNTIME_ERROR_CODE,
                WORKER_RUNTIME_UNAVAILABLE_CODE,
                TIMEOUT_EXPIRED_CODE,
                RECOVERY_RETRY_EXHAUSTED_CODE,
            ],
            examples=["og replay --changed", "og replay --json", "og replay --dry-run --json"],
        ),
        _command_signature_entry(
            "status",
            "og status",
            "Show freshness, lock, verification, and daemon/autopilot state.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok`, `warn`, or `error`)."),
                _command_schema_field("schema_version", "integer", "Status schema version."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og status", "og status --json"],
        ),
        _command_signature_entry(
            "doctor",
            "og doctor",
            "Run machine-readable diagnostics with remediation hints for runtime recovery.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok`, `warn`, or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("checks", "array", "Structured diagnostic checks with remediation."),
                _command_schema_field("remediation", "array", "Deduplicated remediation hints."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE, INTEGRITY_CHECK_FAILED_CODE],
            examples=["og doctor", "og doctor --json"],
        ),
        _command_signature_entry(
            "export",
            "og export",
            "Render configured export surfaces from canonical artifacts.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--validate", "boolean", "Run preflight validation without mutating artifacts.", default=False),
                _command_schema_field("--dry-run", "boolean", "Render a no-write execution plan for the command.", default=False),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("updated_exports", "array", "Exports updated by the command."),
                _command_schema_field("planned_exports", "array", "Exports that would be updated by a dry-run."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og export", "og export --json", "og export --dry-run --json"],
        ),
        _command_signature_entry(
            "clean",
            "og clean",
            "Remove runtime and/or generated outcomegraph state.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--scope", "string", "Target cleanup scope (`runtime`, `generated`, `all`).", enum=sorted(CLEAN_SCOPES)),
                _command_schema_field("--dry-run", "boolean", "Calculate cleanup plan without deleting.", default=False),
                _command_schema_field("--yes", "boolean", "Confirm destructive cleanup.", default=False),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("options", "object", "Parsed command options."),
                _command_schema_field("removed_paths", "array", "Paths removed by clean job."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og clean --scope runtime", "og clean --scope all --dry-run --json"],
        ),
        _command_signature_entry(
            "explain",
            "og explain",
            "Explain artifact provenance and proof chain for selected capsules, refs, and certificates.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field(
                    "--output",
                    "string",
                    "Output mode.",
                    enum=[OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL],
                    default=OUTPUT_MODE_JSON,
                ),
                _command_schema_field("--fields", "string", "Comma-separated top-level payload fields."),
                _command_schema_field("--limit", "integer", "Maximum list items per list-like field."),
                _command_schema_field("--offset", "integer", "0-based list offset for pagination."),
                _command_schema_field("--capsule", "array", "One or more capsule IDs to filter by."),
                _command_schema_field("--ref", "array", "One or more ref IDs to filter by."),
                _command_schema_field("--certificate", "array", "One or more certificate IDs to filter by."),
                _command_schema_field("--profile", "string", "Worker profile selection.", enum=sorted(PROFILE_VALUES)),
                _command_schema_field("--mode", "string", "Operational mode.", enum=sorted(MODE_VALUES)),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("claims", "array", "Explained claim artifacts."),
                _command_schema_field("certificates", "array", "Explained certificate artifacts."),
                _command_schema_field("decisions", "array", "Decision artifacts for the explain run."),
                _command_schema_field("list_window", "object", "Pagination metadata for emitted list fields."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og explain --capsule default", "og explain --json --certificate cert-1"],
        ),
        _command_signature_entry(
            "drift",
            "og drift",
            "Run canonical drift checks for policy and certificate health.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok`, `warn`, or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("drift_state", "string", "Drift state summary."),
                _command_schema_field("checks", "array", "Executed drift check results."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE, INTEGRITY_CHECK_FAILED_CODE],
            examples=["og drift", "og drift --json"],
        ),
        _command_signature_entry(
            "mcp-server",
            "og mcp-server",
            "Render MCP server control surface definitions (tools/resources/prompts).",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field(
                    "--output",
                    "string",
                    "Output mode.",
                    enum=[OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL],
                    default=OUTPUT_MODE_JSON,
                ),
                _command_schema_field("--fields", "string", "Comma-separated top-level payload fields."),
                _command_schema_field("--limit", "integer", "Maximum list items per list-like field."),
                _command_schema_field("--offset", "integer", "0-based list offset for pagination."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("tools", "array", "Discovered MCP tools."),
                _command_schema_field("resources", "array", "Discovered MCP resources."),
                _command_schema_field("list_window", "object", "Pagination metadata for emitted list fields."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE, CONTROL_SURFACE_MISMATCH_CODE],
            examples=["og mcp-server", "og mcp-server --json"],
        ),
        _command_signature_entry(
            "optimize",
            "og optimize",
            "Command group for optimization workflows.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            subcommands=["prompts"],
            examples=["og optimize", "og optimize --help"],
        ),
        _command_signature_entry(
            "optimize prompts",
            "og optimize prompts",
            "Run dataset-based prompt optimization and optionally activate a candidate when it passes thresholds.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field(
                    "--params",
                    "string",
                    "Path to JSON payload file, or - for stdin payload stream.",
                ),
                _command_schema_field("--dataset", "string", "Path to eval_dataset artifact.", required=True),
                _command_schema_field("--candidate", "string", "Path to candidate prompt artifact text.", required=True),
                _command_schema_field("--baseline", "string", "Path to baseline prompt artifact text.", required=True),
                _command_schema_field(
                    "--metric",
                    "string",
                    "Metric for prompt comparison.",
                    enum=["contains", "exact"],
                ),
                _command_schema_field("--min-improvement", "number", "Minimum improvement required before promotion."),
                _command_schema_field("--approve", "boolean", "Persist qualifying prompt pack as active.", default=False),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("evaluation", "object", "Evaluation summary for optimization run."),
                _command_schema_field("result_path", "string", "Path to generated prompt-pack artifact."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og optimize prompts --dataset ds.json --candidate next.txt --baseline base.txt"],
        ),
        _command_signature_entry(
            "autopilot",
            "og autopilot",
            "Command group for hook bootstrap/teardown.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            subcommands=["init", "disable"],
            examples=["og autopilot --help", "og autopilot init --json"],
        ),
        _command_signature_entry(
            "autopilot init",
            "og autopilot init",
            "Install outcomegraph-managed git hooks for lifecycle integration.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--force-hooks-path", "boolean", "Allow hook path override when hooks are already configured."),
                _command_schema_field("--yes", "boolean", "Confirm privileged hook-path changes."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable autopilot session identifier."),
                _command_schema_field("session", "object", "Current autopilot session metadata."),
                _command_schema_field("installed_hooks", "array", "Hooks managed during install."),
            ],
            [USAGE_ERROR_CODE, POLICY_DENIED_CODE, RUNTIME_ERROR_CODE],
            examples=["og autopilot init", "og autopilot init --force-hooks-path --yes --json"],
        ),
        _command_signature_entry(
            "autopilot disable",
            "og autopilot disable [--session-id <id>]",
            "Remove outcomegraph-managed hooks and restore prior hook state.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--session-id", "string", "Assert the autopilot session being disabled."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable autopilot session identifier."),
                _command_schema_field("session", "object", "Disabled autopilot session metadata."),
                _command_schema_field("state_present", "boolean", "Whether disable state was found."),
            ],
            [USAGE_ERROR_CODE, POLICY_DENIED_CODE, SESSION_EXPIRED_CODE, SESSION_RESUME_INVALID_CODE, RUNTIME_ERROR_CODE],
            examples=["og autopilot disable", "og autopilot disable --session-id autopilot-20260307t000000z-abcdef1234 --json"],
        ),
        _command_signature_entry(
            "daemon",
            "og daemon",
            "Command group for watcher lifecycle.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            subcommands=["install", "start", "stop", "status", "run"],
            examples=["og daemon --help", "og daemon status --json"],
        ),
        _command_signature_entry(
            "daemon install",
            "og daemon install",
            "Install the long-running watcher process.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable daemon session identifier."),
                _command_schema_field("session", "object", "Current daemon session metadata."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og daemon install", "og daemon install --json"],
        ),
        _command_signature_entry(
            "daemon start",
            "og daemon start [--session-id <id>]",
            "Start the managed watcher process and persist runtime status.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--session-id", "string", "Resume the known daemon session instead of creating a new one."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable daemon session identifier."),
                _command_schema_field("session", "object", "Current daemon session metadata."),
                _command_schema_field("runtime", "object", "Current runtime lifecycle state."),
            ],
            [USAGE_ERROR_CODE, SESSION_EXPIRED_CODE, SESSION_RESUME_INVALID_CODE, RUNTIME_ERROR_CODE],
            examples=["og daemon start", "og daemon start --session-id daemon-20260307t000000z-abcdef1234 --json"],
        ),
        _command_signature_entry(
            "daemon stop",
            "og daemon stop [--session-id <id>]",
            "Stop the managed watcher process.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--session-id", "string", "Resume the known daemon session before stopping it."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable daemon session identifier."),
                _command_schema_field("session", "object", "Stopped daemon session metadata."),
                _command_schema_field("runtime", "object", "Current runtime lifecycle state."),
            ],
            [USAGE_ERROR_CODE, SESSION_EXPIRED_CODE, SESSION_RESUME_INVALID_CODE, RUNTIME_ERROR_CODE],
            examples=["og daemon stop", "og daemon stop --session-id daemon-20260307t000000z-abcdef1234 --json"],
        ),
        _command_signature_entry(
            "daemon status",
            "og daemon status [--session-id <id>]",
            "Read watcher install/runtime and last-sync status.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("--session-id", "string", "Resume the known daemon session for explicit lifecycle checks."),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("session_id", "string", "Resumable daemon session identifier."),
                _command_schema_field("session", "object", "Current daemon session metadata."),
                _command_schema_field("runtime", "object", "Current runtime lifecycle state."),
                _command_schema_field("install", "object", "Installation details for daemon wrapper."),
            ],
            [USAGE_ERROR_CODE, SESSION_EXPIRED_CODE, SESSION_RESUME_INVALID_CODE, RUNTIME_ERROR_CODE],
            examples=["og daemon status", "og daemon status --session-id daemon-20260307t000000z-abcdef1234 --json"],
        ),
        _command_signature_entry(
            "daemon run",
            "og daemon run",
            "Internal run loop entrypoint for watcher wrappers.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("message", "string", "Human-facing lifecycle output."),
            ],
            [USAGE_ERROR_CODE, SESSION_CONTENDED_CODE, RUNTIME_ERROR_CODE],
            examples=["og daemon run"],
        ),
        _command_signature_entry(
            "schema",
            "og schema",
            "Emit machine-readable CLI command signatures and request/response schema.",
            [_command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False)],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("schema_version", "integer", "Schema payload schema version."),
                _command_schema_field("commands", "array", "All known command signatures."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og schema", "og schema --json"],
        ),
        _command_signature_entry(
            "describe",
            "og describe <command>",
            "Describe the request/response signature for a known CLI command.",
            [
                _command_schema_field("--json", "boolean", "Emit machine-readable JSON output.", default=False),
                _command_schema_field("command", "string", "Target command name or nested command path (e.g. `daemon status`).", required=True),
            ],
            [
                _command_schema_field("status", "string", "Command status (`ok` or `error`)."),
                _command_schema_field("command", "string", "Command identifier for envelope payload."),
                _command_schema_field("schema_version", "integer", "Schema payload schema version."),
                _command_schema_field("requested_command", "string", "Requested command string."),
                _command_schema_field("signature", "object", "Resolved command signature."),
            ],
            [USAGE_ERROR_CODE, RUNTIME_ERROR_CODE],
            examples=["og describe sync", "og describe daemon status"],
        ),
    ]
    return command_signatures


_CLI_COMMAND_SIGNATURES = _build_cli_command_signatures()
_CLI_COMMAND_SIGNATURE_BY_NAME = {entry["command"]: entry for entry in _CLI_COMMAND_SIGNATURES}


def _normalize_command_signature_target(raw_target: str) -> str:
    return " ".join(raw_target.split())



def _build_recovery_record(
    operation: str,
    *,
    attempts: int,
    max_retries: int,
    timeout_seconds: int | None,
    recovered: bool = False,
    exhausted: bool = False,
    retryable: bool = False,
    retryable_failures: list[dict[str, object]] | None = None,
    error_code: str | None = None,
    message: str | None = None,
) -> dict[str, object]:
    retries_used = max(attempts - 1, 0)
    payload: dict[str, object] = {
        "operation": operation,
        "attempts": attempts,
        "max_retries": max_retries,
        "retries_used": retries_used,
        "recovered": recovered,
        "exhausted": exhausted,
        "retryable": retryable,
        "timed_out": any(bool(item.get("timed_out")) for item in retryable_failures or []),
    }
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    if retryable_failures:
        payload["retryable_failures"] = retryable_failures
    if error_code:
        payload["error_code"] = error_code
    if message:
        payload["message"] = message
    return payload


def _summarize_recovery_records(records: list[dict[str, object]]) -> dict[str, object]:
    relevant = [record for record in records if isinstance(record, dict)]
    if not relevant:
        return {
            "operations": 0,
            "retried_operations": 0,
            "recovered_operations": 0,
            "exhausted_operations": 0,
            "timeout_operations": 0,
            "total_retries_used": 0,
        }

    return {
        "operations": len(relevant),
        "retried_operations": sum(1 for record in relevant if int(record.get("retries_used") or 0) > 0),
        "recovered_operations": sum(1 for record in relevant if bool(record.get("recovered"))),
        "exhausted_operations": sum(1 for record in relevant if bool(record.get("exhausted"))),
        "timeout_operations": sum(1 for record in relevant if bool(record.get("timed_out"))),
        "total_retries_used": sum(int(record.get("retries_used") or 0) for record in relevant),
        "details": relevant,
    }


def _recovery_error_code_for_message(message: str) -> str:
    lowered = str(message or "").lower()
    if "timed out" in lowered:
        return TIMEOUT_EXPIRED_CODE
    if _is_worker_unavailable_error(message):
        return WORKER_RUNTIME_UNAVAILABLE_CODE
    return RUNTIME_ERROR_CODE


def _run_worker_with_retries(
    role: str,
    payload: dict[str, object],
    repo_root: str,
    trace_path: str,
    adapter: dict[str, object] | None,
    *,
    timeout_seconds: int,
    max_retries: int,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    attempts = 0
    retryable_failures: list[dict[str, object]] = []
    while True:
        attempts += 1
        try:
            output, receipts = _run_codex_worker(
                role,
                payload,
                repo_root,
                trace_path,
                adapter=adapter,
                timeout_seconds=timeout_seconds,
            )
        except WorkerAdapterError as exc:
            error_message = str(exc)
            retryable = _is_worker_unavailable_error(error_message)
            error_code = _recovery_error_code_for_message(error_message)
            if retryable and attempts <= max_retries:
                retryable_failures.append(
                    {
                        "attempt": attempts,
                        "error_code": error_code,
                        "message": error_message,
                        "timed_out": error_code == TIMEOUT_EXPIRED_CODE,
                    }
                )
                continue
            recovery = _build_recovery_record(
                f"worker:{role}",
                attempts=attempts,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                recovered=False,
                exhausted=retryable and attempts > 1,
                retryable=retryable,
                retryable_failures=retryable_failures,
                error_code=RECOVERY_RETRY_EXHAUSTED_CODE if retryable_failures else error_code,
                message=error_message,
            )
            setattr(exc, "recovery", recovery)
            raise

        recovery = _build_recovery_record(
            f"worker:{role}",
            attempts=attempts,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            recovered=bool(retryable_failures),
            exhausted=False,
            retryable=False,
            retryable_failures=retryable_failures,
        )
        return output, receipts, recovery


def _preflight_status_for_checks(checks: list[dict[str, object]]) -> str:
    status = "ok"
    for check in checks:
        check_status = str(check.get("status") or "ok").lower()
        if check_status in {"error", "degraded"}:
            return "error"
        if check_status in {"warn", "stale", "unknown"}:
            status = "warn"
    return status


def _preflight_messages_for_checks(checks: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str]]:
    errors: list[dict[str, object]] = []
    warnings: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "ok").lower()
        message = str(check.get("message") or "").strip()
        if status in {"error", "degraded"}:
            errors.append(
                _normalize_error_record(
                    {
                        "error_code": check.get("error_code") or check.get("code") or RUNTIME_ERROR_CODE,
                        "message": message or "preflight validation failed",
                        "hint": check.get("hint"),
                    }
                )
            )
        elif status in {"warn", "stale", "unknown"} and message:
            warnings.append(message)
    return errors, warnings


def _ensure_text_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    output: list[str] = []
    for item in raw:
        if isinstance(item, str):
            output.append(item)
        elif isinstance(item, (int, float, bool)):
            output.append(str(item))
        else:
            output.append(str(item))
    return output


def _bounded_hint(text: object) -> str:
    hint = str(text or ERROR_HINT_DEFAULT)
    if len(hint) > ERROR_HINT_MAX_LENGTH:
        hint = f"{hint[:ERROR_HINT_MAX_LENGTH - 3]}..."
    return hint


def _error_class_for_code(code: str) -> str:
    mapping = ERROR_CLASS_BY_CODE.get(code)
    if isinstance(mapping, dict):
        return str(mapping.get("error_class") or DEFAULT_ERROR_CLASS)
    return DEFAULT_ERROR_CLASS


def _error_retryable_for_code(code: str, fallback_retryable: object | None = None) -> bool:
    if isinstance(fallback_retryable, bool):
        return fallback_retryable
    mapping = ERROR_CLASS_BY_CODE.get(code)
    if isinstance(mapping, dict) and isinstance(mapping.get("retryable"), bool):
        return bool(mapping.get("retryable"))
    return False


def _error_hint_for_code(code: str, fallback_hint: object | None = None) -> str:
    mapping = ERROR_CLASS_BY_CODE.get(code)
    if isinstance(fallback_hint, str) and fallback_hint.strip():
        return _bounded_hint(fallback_hint)
    if isinstance(mapping, dict):
        return _bounded_hint(mapping.get("hint"))
    return ERROR_HINT_DEFAULT


def _normalize_error_code(raw: object | None, default_code: str | None = None) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if default_code:
        return default_code
    return RUNTIME_ERROR_CODE


def _normalize_error_record(
    raw: object,
    fallback_code: str | None = None,
    fallback_message: str | None = None,
) -> dict[str, object]:
    if isinstance(raw, dict):
        code = _normalize_error_code(raw.get("error_code") or raw.get("code"), fallback_code)
        message = str(raw.get("message") or raw.get("detail") or raw.get("text") or fallback_message or "").strip()
        if not message:
            message = "operation failed"
        error_payload: dict[str, object] = {
            "error_class": _error_class_for_code(code),
            "error_code": code,
            "message": message,
            "retryable": _error_retryable_for_code(code, raw.get("retryable")),
            "hint": _error_hint_for_code(code, raw.get("hint")),
        }
        for key in ["command", "subcommand", "category", "target", "mode", "type", "name", "path", "remediation"]:
            if key in raw:
                error_payload[key] = raw[key]
        return error_payload

    message = str(raw).strip() if raw is not None else str(fallback_message or "").strip()
    if not message:
        message = str(fallback_message or "").strip() or "operation failed"
    code = _normalize_error_code(None, fallback_code or RUNTIME_ERROR_CODE)
    return {
        "error_class": _error_class_for_code(code),
        "error_code": code,
        "message": message,
        "retryable": _error_retryable_for_code(code),
        "hint": _error_hint_for_code(code),
    }


def _normalize_error_list(
    raw: object,
    fallback_code: str | None = None,
    fallback_message: str | None = None,
) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        if raw is None:
            return []
        return [_normalize_error_record(raw, fallback_code=fallback_code, fallback_message=fallback_message)]

    output: list[dict[str, object]] = []
    for item in raw:
        output.append(_normalize_error_record(item, fallback_code=fallback_code, fallback_message=fallback_message))
    return output


def _normalize_errors_recursive(
    raw: object,
    fallback_code: str | None = None,
    fallback_message: str | None = None,
) -> object:
    if isinstance(raw, dict):
        status = str(raw.get("status") or "").lower()
        normalized: dict[str, object] = {}
        message_hint = str(raw.get("message") or fallback_message or "")
        code_hint = _normalize_error_code(raw.get("error_code") or raw.get("code"), fallback_code)
        for key, value in raw.items():
            if key == "errors":
                normalized[key] = _normalize_error_list(
                    value,
                    fallback_code=code_hint,
                    fallback_message=message_hint,
                )
            elif key == "warnings":
                normalized[key] = _ensure_text_list(value)
            elif isinstance(value, (dict, list)):
                normalized[key] = _normalize_errors_recursive(
                    value,
                    fallback_code=code_hint,
                    fallback_message=message_hint,
                )
            else:
                normalized[key] = value
        if status == "error" and not normalized.get("errors"):
            normalized["errors"] = [
                _normalize_error_record(
                    None,
                    fallback_code=code_hint,
                    fallback_message=message_hint,
                )
            ]
        return normalized
    if isinstance(raw, list):
        return [_normalize_errors_recursive(item, fallback_code=fallback_code, fallback_message=fallback_message) for item in raw]
    return raw


def _build_command_result_envelope(
    command: str,
    payload: dict[str, object] | None,
) -> dict[str, object]:
    if payload is None or not isinstance(payload, dict):
        payload = {}
    payload = _normalize_errors_recursive(payload)
    command_id = str(payload.get("command") or command).strip()
    if not command_id:
        command_id = "og"

    raw_status = str(payload.get("status") or "ok").lower()
    status = raw_status if raw_status in COMMAND_RESULT_ALLOWED_STATUSES else "error"
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        run_id = None
    session = _session_from_payload(payload.get("session"))
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = None
    if session_id is None and isinstance(session, dict):
        raw_session_id = session.get("session_id")
        if isinstance(raw_session_id, str) and raw_session_id.strip():
            session_id = raw_session_id

    errors = payload.get("errors")
    status_message = str(payload.get("message") or "")
    fallback_code = str(payload.get("error_code") or payload.get("code") or RUNTIME_ERROR_CODE)
    if isinstance(errors, list):
        errors = _normalize_error_list(
            errors,
            fallback_code=fallback_code,
            fallback_message=status_message,
        )
    else:
        errors = [] if status != "error" else [
            _normalize_error_record(
                None,
                fallback_code=fallback_code,
                fallback_message=status_message,
            )
        ]
    if status == "error" and not errors:
        errors = [
            _normalize_error_record(
                None,
                fallback_code=fallback_code,
                fallback_message=status_message,
            )
        ]

    warnings = _ensure_text_list(payload.get("warnings"))

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}

    envelope: dict[str, object] = {
        "schema_version": COMMAND_RESULT_SCHEMA_VERSION,
        "command": command_id,
        "status": status,
        "run_id": run_id,
        "session_id": session_id,
        "data": payload,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics,
    }
    subcommand = payload.get("subcommand")
    if isinstance(subcommand, str):
        envelope["subcommand"] = subcommand
    return _validate_command_result_envelope(envelope)


def _validate_command_result_envelope(envelope: dict[str, object]) -> dict[str, object]:
    try:
        validated = _CommandResultEnvelopeModel.model_validate(envelope)
    except ValidationError as exc:
        command_id = str(envelope.get("command") or "og").strip() or "og"
        message = "command envelope validation failed"
        fallback = _CommandResultEnvelopeModel(
            schema_version=COMMAND_RESULT_SCHEMA_VERSION,
            command=command_id,
            status="error",
            run_id=None,
            data={
                "status": "error",
                "command": command_id,
                "message": message,
                "validation_errors": exc.errors(include_url=False),
            },
            errors=[
                _CommandResultErrorModel(
                    error_class=_error_class_for_code(RUNTIME_ERROR_CODE),
                    error_code=RUNTIME_ERROR_CODE,
                    message=message,
                    retryable=_error_retryable_for_code(RUNTIME_ERROR_CODE),
                    hint=_error_hint_for_code(RUNTIME_ERROR_CODE),
                )
            ],
            warnings=[],
            metrics={},
        )
        fallback_payload = cast(dict[str, object], fallback.model_dump(mode="python"))
        if "subcommand" not in envelope and fallback_payload.get("subcommand") is None:
            fallback_payload.pop("subcommand", None)
        return fallback_payload
    validated_payload = cast(dict[str, object], validated.model_dump(mode="python"))
    if "subcommand" not in envelope and validated_payload.get("subcommand") is None:
        validated_payload.pop("subcommand", None)
    return validated_payload


def _error_code_for_exit_code(exit_code: int) -> str:
    if exit_code == EXIT_USAGE:
        return USAGE_ERROR_CODE
    if exit_code == EXIT_SUCCESS:
        return ""
    return RUNTIME_ERROR_CODE


def emit_error(
    message: str,
    command: str | None,
    code: int,
    output_json: bool = False,
    *,
    error_code: str | None = None,
) -> None:
    payload_error_code = error_code or _error_code_for_exit_code(code)
    if output_json:
        emit_command_result(
            {
                "status": "error",
                "code": payload_error_code,
                "error_code": payload_error_code,
                "command": command,
                "message": message,
                "errors": [
                    {
                        "error_code": payload_error_code,
                        "message": message,
                    }
                ],
            },
            True,
            command or "og",
        )
    else:
        print(f"og: {message}", file=sys.stderr)
    sys.exit(code)


def emit_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def emit_jsonl_line(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def emit_command_result_jsonl(payload: dict, command: str | None) -> None:
    payload = _build_command_result_envelope(command or "og", payload)
    list_fields = {
        str(key): value
        for key, value in payload.get("data", {}).items()
        if isinstance(value, list)
    }
    if not list_fields:
        emit_jsonl_line(payload)
        return

    list_window = payload.get("data", {}).get("list_window")
    if not isinstance(list_window, dict):
        list_window = {}

    stream_payload = dict(payload.get("data", {}))
    stream_list_window: dict[str, dict[str, object]] = {}
    for name in sorted(list_fields):
        window = list_window.get(name)
        items = list_fields[name]
        metadata = {
            "total": len(items),
            "offset": int(window.get("offset", 0)),
            "returned": len(items),
        }
        if isinstance(window, dict) and "limit" in window:
            metadata["limit"] = window["limit"]
        if isinstance(window, dict):
            for key in ("total", "offset", "returned", "limit"):
                if key in window:
                    metadata[key] = window[key]
        stream_payload[name] = {"_streamed": True, "metadata": metadata}
        stream_list_window[name] = metadata
    if stream_list_window:
        stream_payload["list_window"] = stream_list_window
    payload["data"] = stream_payload
    emit_jsonl_line(payload)

    for list_name in sorted(list_fields):
        items = list_fields[list_name]
        window = stream_list_window.get(list_name)
        if not isinstance(window, dict):
            window = {}
        base_offset = int(window.get("offset", 0))
        for index, item in enumerate(items):
            emit_jsonl_line(
                {
                    "event": "item",
                    "command": command or "og",
                    "field": list_name,
                    "index": base_offset + index,
                    "item": item,
                }
            )


def emit_command_result(payload: dict, output_json: bool, command: str | None = None) -> None:
    if output_json:
        emit_json(_build_command_result_envelope(command or "og", payload))
        return
    message = payload.get("message")
    if isinstance(message, str):
        print(message)


def parse_bool_option(raw: str) -> bool:
    value = raw.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value '{raw}'")


def parse_int_option(raw: str, field: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{field} must be zero or greater")
    return value


def _parse_csv_fields(raw: str, field: str) -> list[str]:
    fields = [item.strip() for item in raw.split(",")]
    if not fields or not any(field_name for field_name in fields):
        raise ValueError(f"{field} must contain at least one non-empty field name")
    normalized: list[str] = []
    for item in fields:
        if not item:
            continue
        if item not in normalized:
            normalized.append(item)
    if not normalized:
        raise ValueError(f"{field} must contain at least one non-empty field name")
    return normalized


def _stable_list_sort(values: list[object]) -> list[object]:
    try:
        return sorted(values, key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=True))
    except TypeError:
        return sorted(values, key=lambda value: json.dumps(value, default=str, sort_keys=True, ensure_ascii=True))


def _normalize_pagination(payload: dict[str, object], options: dict[str, object], *, force_sort: bool) -> dict[str, object]:
    fields = options.get("fields")
    limit = options.get("limit")
    offset = options.get("offset")
    limit_value = limit if isinstance(limit, int) else None
    offset_value = int(offset) if isinstance(offset, int) else 0
    if not isinstance(fields, list):
        fields = None
    else:
        fields = [item for item in fields if isinstance(item, str)]
    if fields is not None:
        field_keys = fields
    else:
        field_keys = [key for key in payload.keys()]

    output_payload: dict[str, object] = {}
    window_payload: dict[str, object] = {}
    if not payload:
        return {}

    for key in field_keys:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            normalized = list(value)
            if force_sort:
                normalized = _stable_list_sort(normalized)
            total_count = len(normalized)
            start = max(0, offset_value)
            if limit_value is None:
                end = total_count
            else:
                end = start + limit_value
            windowed = normalized[start:end]
            output_payload[key] = windowed
            if limit_value is not None or offset_value > 0:
                window_payload[key] = {
                    "total": total_count,
                    "offset": start,
                    "limit": limit_value,
                    "returned": len(windowed),
                }
        else:
            output_payload[key] = value

    if window_payload:
        output_payload["list_window"] = window_payload

    return output_payload


def _apply_output_controls(payload: dict[str, object], options: dict[str, object], *, output_mode: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        return payload
    if output_mode != OUTPUT_MODE_JSONL and output_mode != OUTPUT_MODE_JSON:
        return payload

    limit = options.get("limit")
    offset = options.get("offset")
    limit_value = limit if isinstance(limit, int) else None
    offset_value = offset if isinstance(offset, int) else 0
    return _normalize_pagination(
        payload,
        options,
        force_sort=bool(limit_value is not None or offset_value > 0 or output_mode == OUTPUT_MODE_JSONL),
    )


def parse_float_option(raw: str, field: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a number") from exc
    if math.isinf(value) or math.isnan(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _build_run_id(prefix: str, run_suffix: str | None = None) -> str:
    suffix = run_suffix or _short_hash(f"{prefix}:{_utc_timestamp()}", 10)
    return f"{prefix}-{_utc_timestamp().replace(':', '').replace('-', '')}-{suffix}"


def _string_list(raw: object, field: str, *, required: bool = False) -> list[str]:
    if raw is None:
        if required:
            raise WorkerAdapterError(f"{field} must be present and be a list")
        return []
    if not isinstance(raw, list):
        raise WorkerAdapterError(f"{field} must be a list")
    values: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    if required and not values:
        raise WorkerAdapterError(f"{field} must contain at least one item")
    return values


def _required_str(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise WorkerAdapterError(f"{field} must be a non-empty string")
    return raw.strip()


def _optional_int(raw: object, field: str, default: int | None = None) -> int | None:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise WorkerAdapterError(f"{field} must be an integer")
    return raw


def _run_git(repo_root: str, args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", repo_root, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _git_root() -> str:
    result = _run_git(".", ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        emit_error("not inside a git repository", None, EXIT_RUNTIME, False)
    return result.stdout.strip()


def _maybe_git_root() -> str | None:
    result = _run_git(".", ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _metadata_path(base_dir: str, absolute_path: str) -> str:
    normalized_base = os.path.abspath(base_dir)
    normalized_path = os.path.abspath(absolute_path)
    try:
        relative = os.path.relpath(normalized_path, normalized_base)
    except ValueError:
        return normalized_path.replace("\\", "/")
    if relative == ".":
        return "."
    if relative.startswith(".."):
        return normalized_path.replace("\\", "/")
    return relative.replace("\\", "/")


def _resolve_path_reference(base_dir: str, raw_value: str, *, field_name: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise ValueError(f"{field_name} cannot be empty")
    if os.path.isabs(value):
        return os.path.abspath(value)
    return os.path.abspath(os.path.join(base_dir, value))


def _utc_timestamp() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_timestamp(raw: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _session_expiry_timestamp(started_at: str, ttl_seconds: int | None) -> str | None:
    if ttl_seconds is None:
        return None
    started = _parse_utc_timestamp(started_at)
    if started is None:
        return None
    expires = started + datetime.timedelta(seconds=ttl_seconds)
    return expires.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_session_id(kind: str, *parts: object) -> str:
    created_at = _utc_timestamp().replace(":", "").replace("-", "").lower()
    seed = "|".join([str(kind), created_at, *(str(part) for part in parts if part is not None)])
    return f"{kind}-{created_at}-{_short_hash(seed, 10)}"


def _build_session_record(
    kind: str,
    lifecycle: str,
    state: str,
    *,
    session_id: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    ttl_seconds: int | None = None,
    resume_command: str | None = None,
) -> dict[str, object]:
    created = created_at or _utc_timestamp()
    updated = updated_at or created
    payload: dict[str, object] = {
        "session_id": session_id or _build_session_id(kind, state, created),
        "kind": kind,
        "lifecycle": lifecycle,
        "state": state,
        "resume_supported": lifecycle == SESSION_LIFECYCLE_RESUMABLE,
        "created_at": created,
        "updated_at": updated,
        "expires_at": _session_expiry_timestamp(updated, ttl_seconds),
    }
    if resume_command:
        payload["resume_command"] = resume_command
    return payload


def _session_from_payload(raw: object, *, now: datetime.datetime | None = None) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    session_id = str(raw.get("session_id") or "").strip()
    if not session_id:
        return None
    session: dict[str, object] = {
        "session_id": session_id,
        "kind": str(raw.get("kind") or "").strip() or "runtime",
        "lifecycle": str(raw.get("lifecycle") or SESSION_LIFECYCLE_EPHEMERAL).strip() or SESSION_LIFECYCLE_EPHEMERAL,
        "state": str(raw.get("state") or SESSION_STATE_ACTIVE).strip() or SESSION_STATE_ACTIVE,
        "resume_supported": bool(raw.get("resume_supported"))
        or str(raw.get("lifecycle") or SESSION_LIFECYCLE_EPHEMERAL).strip() == SESSION_LIFECYCLE_RESUMABLE,
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "expires_at": raw.get("expires_at"),
    }
    resume_command = raw.get("resume_command")
    if isinstance(resume_command, str) and resume_command.strip():
        session["resume_command"] = resume_command.strip()
    if _session_is_expired(session, now=now):
        session["state"] = SESSION_STATE_EXPIRED
    return session


def _session_is_expired(session: object, *, now: datetime.datetime | None = None) -> bool:
    if not isinstance(session, dict):
        return False
    expires_at = session.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at.strip():
        return False
    parsed = _parse_utc_timestamp(expires_at)
    if parsed is None:
        return False
    reference = now or datetime.datetime.now(tz=datetime.timezone.utc)
    return parsed <= reference


def _set_session_state(
    session: dict[str, object] | None,
    state: str,
    *,
    updated_at: str | None = None,
    ttl_seconds: int | None = None,
    refresh_expiry: bool = False,
) -> dict[str, object] | None:
    if not isinstance(session, dict):
        return None
    next_session = dict(session)
    next_session["state"] = state
    next_session["updated_at"] = updated_at or _utc_timestamp()
    if refresh_expiry:
        next_session["expires_at"] = _session_expiry_timestamp(str(next_session["updated_at"]), ttl_seconds)
    return next_session


def _normalize_session_id(value: object, field: str = "session_id") -> str:
    return _normalize_agent_identifier(str(value or ""), field)


def _build_session_error(
    code: str,
    message: str,
    *,
    command: str,
    session: dict[str, object] | None = None,
    requested_session_id: str | None = None,
    actual_session_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "error",
        "code": code,
        "command": command,
        "message": message,
    }
    if isinstance(session, dict):
        payload["session"] = session
        session_id = session.get("session_id")
        if isinstance(session_id, str) and session_id.strip():
            payload["session_id"] = session_id
    if requested_session_id:
        payload["requested_session_id"] = requested_session_id
    if actual_session_id:
        payload["actual_session_id"] = actual_session_id
    return payload


def _validate_resumed_session(
    command: str,
    requested_session_id: str | None,
    session: dict[str, object] | None,
) -> dict[str, object] | None:
    if not requested_session_id:
        return None
    if not isinstance(session, dict):
        return _build_session_error(
            SESSION_RESUME_INVALID_CODE,
            f"{command} cannot resume session '{requested_session_id}'; no resumable session is recorded.",
            command=command,
            requested_session_id=requested_session_id,
        )
    actual_session_id = str(session.get("session_id") or "").strip()
    if actual_session_id != requested_session_id:
        return _build_session_error(
            SESSION_RESUME_INVALID_CODE,
            f"{command} cannot resume session '{requested_session_id}'; active session is '{actual_session_id or 'none'}'.",
            command=command,
            session=session,
            requested_session_id=requested_session_id,
            actual_session_id=actual_session_id or None,
        )
    if _session_is_expired(session):
        return _build_session_error(
            SESSION_EXPIRED_CODE,
            f"{command} session '{requested_session_id}' expired at {session.get('expires_at')}.",
            command=command,
            session=_set_session_state(session, SESSION_STATE_EXPIRED) or session,
            requested_session_id=requested_session_id,
            actual_session_id=requested_session_id,
        )
    return None


def _humanize_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"{seconds}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{'' if remainder == 0 else f' {remainder}s'}"
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{'' if remainder == 0 else f' {remainder}m'}"
    days, remainder = divmod(hours, 24)
    return f"{days}d{'' if remainder == 0 else f' {remainder}h'}"


def _iso_from_dt(value: datetime.datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")

def _read_json_file(path: str) -> dict[str, object] | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return cast(dict[str, object], data) if isinstance(data, dict) else None


class _YamlToken(TypedDict):
    content: str
    indent: int
    line: int


def _yaml_scalar(raw_value: str) -> str:
    value = raw_value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _yaml_tokens(raw: str) -> list[_YamlToken]:
    tokens: list[_YamlToken] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        tokens.append(
            {
                "content": line.strip(),
                "indent": len(line) - len(line.lstrip(" ")),
                "line": line_number,
            }
        )
    return tokens


def _yaml_mapping_separator_index(content: str) -> int | None:
    for index, char in enumerate(content):
        if char != ":":
            continue
        next_char = content[index + 1 : index + 2]
        if next_char and not next_char.isspace():
            continue
        if content[:index].strip():
            return index
    return None


def _yaml_key_value(content: str, line_number: int) -> tuple[str, str]:
    separator_index = _yaml_mapping_separator_index(content)
    if separator_index is None:
        raise ValueError(f"invalid YAML mapping entry on line {line_number}: {content!r}")
    key = content[:separator_index].strip()
    value = content[separator_index + 1 :].strip()
    if not key:
        raise ValueError(f"invalid YAML key on line {line_number}")
    return key, value


def _parse_yaml_tokens(tokens: list[_YamlToken], index: int, indent: int) -> tuple[object, int]:
    if index >= len(tokens):
        return {}, index

    if tokens[index]["content"].startswith("-"):
        items: list[object] = []
        while index < len(tokens):
            token = tokens[index]
            if token["indent"] != indent or not token["content"].startswith("-"):
                break

            remainder = token["content"][1:].strip()
            index += 1
            if not remainder:
                if index < len(tokens) and tokens[index]["indent"] > indent:
                    child, index = _parse_yaml_tokens(tokens, index, tokens[index]["indent"])
                    items.append(child)
                else:
                    items.append("")
                continue

            if remainder.startswith('"') or remainder.startswith("'"):
                items.append(_yaml_scalar(remainder))
                continue

            if _yaml_mapping_separator_index(remainder) is None:
                items.append(_yaml_scalar(remainder))
                continue

            key, value = _yaml_key_value(remainder, token["line"])
            item: dict[str, object] = {}
            if value:
                item[key] = _yaml_scalar(value)
            elif index < len(tokens) and tokens[index]["indent"] > indent:
                child, index = _parse_yaml_tokens(tokens, index, tokens[index]["indent"])
                item[key] = child
            else:
                item[key] = []

            if index < len(tokens) and tokens[index]["indent"] > indent:
                child, index = _parse_yaml_tokens(tokens, index, tokens[index]["indent"])
                if not isinstance(child, dict):
                    raise ValueError(
                        f"invalid YAML list item continuation on line {token['line']}: expected mapping fields"
                    )
                item.update(child)

            items.append(item)

        return items, index

    result: dict[str, object] = {}
    while index < len(tokens):
        token = tokens[index]
        if token["indent"] != indent:
            break
        if token["content"].startswith("-"):
            raise ValueError(f"unexpected YAML list item on line {token['line']}")

        key, value = _yaml_key_value(token["content"], token["line"])
        index += 1
        if value:
            result[key] = _yaml_scalar(value)
            continue

        if index < len(tokens) and tokens[index]["indent"] > indent:
            child, index = _parse_yaml_tokens(tokens, index, tokens[index]["indent"])
            result[key] = child
        else:
            result[key] = []

    return result, index


def _read_json_payload_source(path: str, *, command: str, output_json: bool) -> dict[str, object] | None:
    text = ""
    try:
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
    except OSError as exc:
        if path == "-":
            emit_error(f"failed reading params from stdin: {exc}", command, EXIT_USAGE, output_json)
        emit_error(f"failed reading params file '{path}': {exc}", command, EXIT_USAGE, output_json)
        return None

    if not text.strip():
        emit_error("params payload is empty", command, EXIT_USAGE, output_json)
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        emit_error(f"params payload is not valid JSON: {exc}", command, EXIT_USAGE, output_json)
        return None

    if not isinstance(payload, dict):
        emit_error("params payload must be a JSON object", command, EXIT_USAGE, output_json)
        return None
    return cast(dict[str, object], payload)


def _read_file_updated_at(repo_root: str, relative_path: str) -> datetime.datetime | None:
    full_path = os.path.join(repo_root, relative_path)
    updated_at_raw = None
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.lstrip().startswith("-"):
                    continue
                value = _extract_artifact_field(raw_line, "updated_at")
                if value:
                    updated_at_raw = value
                    break
    except OSError:
        return None
    if updated_at_raw:
        parsed = _parse_utc_timestamp(updated_at_raw)
        if parsed is not None:
            return parsed
    try:
        mtime = os.path.getmtime(full_path)
    except OSError:
        return None
    return datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)


def _read_work_pending_file(repo_root: str) -> tuple[bool, str | None]:
    payload = _read_json_file(os.path.join(repo_root, WORK_PENDING_FILE))
    if not isinstance(payload, dict):
        return False, None
    hook = payload.get("hook")
    if isinstance(hook, str) and hook:
        return True, hook
    return True, None


def _read_lock_status(repo_root: str, now: datetime.datetime) -> dict[str, object]:
    path = os.path.join(repo_root, WORK_LOCK_FILE)
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return {
            "status": LOCK_STATUS_UNLOCKED,
            "holder": None,
            "session": None,
            "is_stale": False,
            "age_seconds": None,
            "created_at": None,
            "updated_at": None,
        }

    raw_status = payload.get("status")
    status = raw_status if raw_status in {LOCK_STATUS_LOCKED, LOCK_STATUS_UNLOCKED} else LOCK_STATUS_UNLOCKED
    is_stale = _is_lock_stale(payload, now) if status == LOCK_STATUS_LOCKED else False
    if is_stale and status == LOCK_STATUS_LOCKED:
        status = "stale"

    updated_at_raw = payload.get("updated_at")
    updated_at = _parse_utc_timestamp(updated_at_raw) if isinstance(updated_at_raw, str) else None
    created_at_raw = payload.get("created_at")
    created_at = _parse_utc_timestamp(created_at_raw) if isinstance(created_at_raw, str) else None
    age_seconds = int((now - updated_at).total_seconds()) if updated_at else None

    return {
        "status": status,
        "holder": payload.get("holder") if isinstance(payload.get("holder"), dict) else None,
        "session": _session_from_payload(payload.get("session"), now=now),
        "is_stale": is_stale,
        "age_seconds": age_seconds,
        "created_at": _iso_from_dt(created_at),
        "updated_at": _iso_from_dt(updated_at),
    }


def _read_latest_event_record(
    repo_root: str, command: str
) -> tuple[dict | None, datetime.datetime | None, str | None]:
    events_path = os.path.join(repo_root, EVENTS_DIR)
    if not os.path.isdir(events_path):
        return None, None, None

    latest_event: dict | None = None
    latest_timestamp: datetime.datetime | None = None
    latest_path: str | None = None
    for filename in sorted(os.listdir(events_path)):
        if not filename.endswith(".json"):
            continue
        payload = _read_json_file(os.path.join(events_path, filename))
        if not isinstance(payload, dict):
            continue
        if payload.get("command") != command:
            continue
        raw_timestamp = payload.get("created_at")
        created_at = _parse_utc_timestamp(raw_timestamp) if isinstance(raw_timestamp, str) else None
        if created_at is None:
            try:
                created_at = datetime.datetime.fromtimestamp(
                    os.path.getmtime(os.path.join(events_path, filename)),
                    tz=datetime.timezone.utc,
                )
            except OSError:
                created_at = None
        if created_at is None:
            continue
        if latest_timestamp is None or created_at > latest_timestamp:
            latest_timestamp = created_at
            latest_event = payload
            latest_path = os.path.join(events_path, filename)

    return latest_event, latest_timestamp, latest_path


def _read_latest_sync_event(repo_root: str) -> tuple[dict | None, datetime.datetime | None]:
    latest_event, latest_timestamp, _ = _read_latest_event_record(repo_root, "sync")
    return latest_event, latest_timestamp


def _read_latest_replay_event(repo_root: str) -> tuple[dict | None, datetime.datetime | None]:
    latest_event, latest_timestamp, _ = _read_latest_event_record(repo_root, "replay")
    return latest_event, latest_timestamp


def _read_latest_drift_event(repo_root: str) -> tuple[dict | None, datetime.datetime | None, str | None]:
    return _read_latest_event_record(repo_root, "drift")


def _collect_certificate_freshness(repo_root: str, now: datetime.datetime) -> dict[str, object]:
    cert_root = os.path.join(repo_root, OG_ROOT, "certificates")
    if not os.path.isdir(cert_root):
        return {
            "state": "unknown",
            "count": 0,
            "age_seconds": None,
            "age_human": _humanize_duration(None),
            "newest": None,
            "oldest": None,
            "message": "no certificates directory exists",
            "paths": [],
            "stale_threshold_seconds": STATUS_CERTIFICATE_STALE_SECONDS,
        }

    certificate_records: list[dict[str, object]] = []
    for dirpath, _, filenames in os.walk(cert_root):
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            if not filename.endswith((".yaml", ".yml", ".json")):
                continue
            relative_path = os.path.relpath(os.path.join(dirpath, filename), repo_root).replace("\\", "/")
            updated_at = _read_file_updated_at(repo_root, relative_path)
            age = int((now - updated_at).total_seconds()) if updated_at else None
            certificate_records.append(
                {
                    "path": relative_path,
                    "updated_at": _iso_from_dt(updated_at),
                    "updated_at_dt": updated_at,
                    "age_seconds": age,
                }
            )

    if not certificate_records:
        return {
            "state": "unknown",
            "count": 0,
            "age_seconds": None,
            "age_human": _humanize_duration(None),
            "newest": None,
            "oldest": None,
            "message": "certificate scope is empty",
            "paths": [],
            "stale_threshold_seconds": STATUS_CERTIFICATE_STALE_SECONDS,
        }

    newest = max(
        (record for record in certificate_records if isinstance(record["updated_at_dt"], datetime.datetime)),
        key=lambda item: item["updated_at_dt"],
        default=None,
    )
    oldest = min(
        (record for record in certificate_records if isinstance(record["updated_at_dt"], datetime.datetime)),
        key=lambda item: item["updated_at_dt"],
        default=None,
    )
    stale_age = newest["age_seconds"] if isinstance(newest, dict) else None
    if stale_age is None:
        state = "unknown"
        message = "could not parse certificate freshness timestamps"
    elif stale_age > STATUS_CERTIFICATE_STALE_SECONDS:
        state = "stale"
        message = "certificate freshness exceeds threshold"
    else:
        state = "fresh"
        message = "certificates are within freshness window"

    return {
        "state": state,
        "count": len(certificate_records),
        "age_seconds": stale_age,
        "age_human": _humanize_duration(stale_age),
        "newest": newest["path"] if isinstance(newest, dict) else None,
        "oldest": oldest["path"] if isinstance(oldest, dict) else None,
        "message": message,
        "paths": [record["path"] for record in sorted(certificate_records, key=lambda item: item["path"])],
        "recent_paths": [
            record["path"]
            for record in certificate_records
            if isinstance(record["age_seconds"], int) and record["age_seconds"] <= 60
        ],
        "stale_threshold_seconds": STATUS_CERTIFICATE_STALE_SECONDS,
    }


def _collect_verification_state(
    repo_root: str,
    sync_event: dict | None,
    now: datetime.datetime,
) -> dict[str, object]:
    replay_event, _ = _read_latest_replay_event(repo_root)

    def _verification_from_event(event: dict[str, object], step_name: str) -> dict[str, object]:
        created_at_raw = event.get("created_at")
        created_at = _parse_utc_timestamp(created_at_raw) if isinstance(created_at_raw, str) else None
        age = int((now - created_at).total_seconds()) if created_at else None
        steps = event.get("steps") if isinstance(event.get("steps"), list) else []
        matching_step = None
        for raw_step in steps:
            if not isinstance(raw_step, dict):
                continue
            if raw_step.get("name") == step_name:
                matching_step = raw_step
                break

        status = matching_step.get("status") if isinstance(matching_step, dict) else event.get("status")
        status_text = status if isinstance(status, str) else "unknown"
        status_lower = status_text.lower()

        if status_lower in {"error", "failed", "fail"}:
            state = "degraded"
            if step_name == "replay":
                message = "replay failures detected in last replay event"
            else:
                message = "verification failures detected in last sync"
        elif status_lower == "warn":
            state = "warn"
            if step_name == "replay":
                message = "replay completed with warnings"
            else:
                message = "verification completed with warnings"
        elif status_lower == "ok":
            state = "fresh" if (age is None or age <= STATUS_VERIFY_STALE_SECONDS) else "stale"
            message = "verification recently completed"
            if state == "stale":
                message = "verification is older than freshness threshold"
        elif status_lower == "skipped":
            state = "unknown"
            message = "verification was not required for last sync event"
        else:
            state = "unknown"
            if matching_step is None:
                message = f"no {step_name} step found in latest {event.get('command')} event"
            else:
                message = f"{step_name} result could not be interpreted"

        return {
            "state": state,
            "status": status_text,
            "run_id": event.get("run_id") if isinstance(event.get("run_id"), str) else None,
            "age_seconds": age,
            "age_human": _humanize_duration(age),
            "message": message,
            "last_verified_at": created_at_raw if isinstance(created_at_raw, str) else None,
            "sync_status": event.get("status", "unknown"),
            "steps": steps,
            "threshold_seconds": STATUS_VERIFY_STALE_SECONDS,
            "event_created_at": created_at_raw if isinstance(created_at_raw, str) else None,
            "command": event.get("command"),
        }

    candidates: list[tuple[datetime.datetime | None, dict[str, object]]] = []
    if isinstance(sync_event, dict):
        candidates.append(
            (
                _parse_utc_timestamp(sync_event.get("created_at"))
                if isinstance(sync_event.get("created_at"), str)
                else None,
                _verification_from_event(sync_event, "verify"),
            )
        )
    if isinstance(replay_event, dict):
        candidates.append(
            (
                _parse_utc_timestamp(replay_event.get("created_at"))
                if isinstance(replay_event.get("created_at"), str)
                else None,
                _verification_from_event(replay_event, "replay"),
            )
        )

    if not candidates:
        return {
            "state": "unknown",
            "status": "unknown",
            "run_id": None,
            "age_seconds": None,
            "age_human": _humanize_duration(None),
            "message": "no sync or replay summary available",
            "steps": [],
            "threshold_seconds": STATUS_VERIFY_STALE_SECONDS,
        }

    def _candidate_key(item: tuple[datetime.datetime | None, dict[str, object]]) -> datetime.datetime:
        return item[0] if item[0] is not None else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

    return max(candidates, key=_candidate_key)[1]


def _collect_sync_freshness(sync_event: dict | None, now: datetime.datetime) -> dict[str, object]:
    if sync_event is None:
        return {
            "state": "unknown",
            "status": "unknown",
            "run_id": None,
            "age_seconds": None,
            "age_human": _humanize_duration(None),
            "message": "no sync summary available",
            "threshold_seconds": STATUS_SYNC_STALE_SECONDS,
        }

    run_id = sync_event.get("run_id")
    created_at_raw = sync_event.get("created_at")
    created_at = _parse_utc_timestamp(created_at_raw) if isinstance(created_at_raw, str) else None
    age = int((now - created_at).total_seconds()) if created_at else None
    sync_status = sync_event.get("status", "unknown")
    if sync_status == "error":
        state = "degraded"
        message = "latest sync ended with errors"
    elif age is not None and age > STATUS_SYNC_STALE_SECONDS:
        state = "stale"
        message = "latest sync is older than freshness threshold"
    else:
        state = "fresh"
        message = "latest sync is recent"

    return {
        "state": state,
        "status": sync_status if isinstance(sync_status, str) else "unknown",
        "run_id": run_id if isinstance(run_id, str) else None,
        "age_seconds": age,
        "age_human": _humanize_duration(age),
        "message": message,
        "last_sync_at": created_at_raw if isinstance(created_at_raw, str) else None,
        "threshold_seconds": STATUS_SYNC_STALE_SECONDS,
    }


def _parse_yaml_style_fields(raw: str) -> dict[str, object]:
    tokens = _yaml_tokens(raw)
    if not tokens:
        return {}
    parsed, next_index = _parse_yaml_tokens(tokens, 0, tokens[0]["indent"])
    if next_index != len(tokens):
        raise ValueError(f"unexpected YAML content on line {tokens[next_index]['line']}")
    if not isinstance(parsed, dict):
        raise ValueError("top-level YAML payload must be a mapping")
    return cast(dict[str, object], parsed)


def _read_yaml_file(path: str) -> dict[str, object]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise exc
    except OSError as exc:
        raise ValueError(f"cannot read YAML file: {exc}") from exc

    parsed = _parse_yaml_style_fields(raw)
    if not isinstance(parsed, dict):
        raise ValueError("top-level YAML payload must be a mapping")
    return parsed


def _read_structured_mapping_file(path: str) -> dict[str, object]:
    extension = os.path.splitext(path)[1].lower()
    if extension == ".json":
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON content: {exc}") from exc
        except OSError as exc:
            raise ValueError(f"cannot read JSON file: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON payload must be an object")
        return cast(dict[str, object], payload)
    if extension in {".yaml", ".yml"}:
        return _read_yaml_file(path)
    raise ValueError(f"unsupported structured file type: {extension}")


def _env_override(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        raw_value = os.environ.get(name, "").strip()
        if raw_value:
            return raw_value, name
    return None, None


def _load_runtime_defaults(repo_root: str | None) -> dict[str, object]:
    base_dir = os.path.abspath(repo_root or os.getcwd())
    config_path = os.path.abspath(os.path.join(base_dir, DEFAULT_CONFIG_FILE))
    config_display = DEFAULT_CONFIG_FILE
    config_source = "built-in"
    config_explicit = False

    defaults: dict[str, object] = {
        "profile": DEFAULT_PROFILE,
        "mode": DEFAULT_MODE,
        "output_mode": DEFAULT_OUTPUT_MODE,
        "config_file": config_display,
        "config_source": config_source,
        "config_file_path": config_path,
        "config_explicit": config_explicit,
        "policy_file": DEFAULT_POLICY_FILE,
        "policy_source": "built-in",
        "policy_file_path": os.path.abspath(os.path.join(base_dir, DEFAULT_POLICY_FILE)),
        "policy_explicit": False,
        "codex_home": None,
        "codex_home_path": None,
        "codex_home_explicit": False,
        "resolved_from": {
            "profile": "built-in",
            "mode": "built-in",
            "output_mode": "built-in",
            "codex_home": "unset",
        },
    }

    raw_config_override, config_env_name = _env_override(CONFIG_FILE_ENV, LEGACY_CONFIG_FILE_ENV)
    if raw_config_override and config_env_name:
        config_path = _resolve_path_reference(base_dir, raw_config_override, field_name=config_env_name)
        config_display = _metadata_path(base_dir, config_path)
        config_source = f"env:{config_env_name}"
        config_explicit = True
        defaults["config_file"] = config_display
        defaults["config_source"] = config_source
        defaults["config_file_path"] = config_path
        defaults["config_explicit"] = True

    raw_output_override = os.environ.get(DEFAULT_OUTPUT_ENV, "").strip()
    if raw_output_override:
        output_mode = raw_output_override.lower()
        if output_mode not in {OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL}:
            raise ValueError(
                f"{DEFAULT_OUTPUT_ENV} must be one of: {OUTPUT_MODE_HUMAN}, {OUTPUT_MODE_JSON}, {OUTPUT_MODE_JSONL}"
            )
        defaults["output_mode"] = output_mode
        cast(dict[str, str], defaults["resolved_from"])["output_mode"] = f"env:{DEFAULT_OUTPUT_ENV}"

    raw_profile_override = os.environ.get(DEFAULT_PROFILE_ENV, "").strip()
    if raw_profile_override:
        profile = raw_profile_override.lower()
        if profile not in PROFILE_VALUES:
            raise ValueError(f"{DEFAULT_PROFILE_ENV} must be one of: {', '.join(sorted(PROFILE_VALUES))}")
        defaults["profile"] = profile
        cast(dict[str, str], defaults["resolved_from"])["profile"] = f"env:{DEFAULT_PROFILE_ENV}"

    raw_mode_override = os.environ.get(DEFAULT_MODE_ENV, "").strip()
    if raw_mode_override:
        mode = raw_mode_override.lower()
        if mode not in MODE_VALUES:
            raise ValueError(f"{DEFAULT_MODE_ENV} must be one of: {', '.join(sorted(MODE_VALUES))}")
        defaults["mode"] = mode
        cast(dict[str, str], defaults["resolved_from"])["mode"] = f"env:{DEFAULT_MODE_ENV}"

    raw_policy_override, policy_env_name = _env_override(POLICY_FILE_ENV, LEGACY_POLICY_FILE_ENV)
    if raw_policy_override and policy_env_name:
        policy_path = _resolve_path_reference(base_dir, raw_policy_override, field_name=policy_env_name)
        defaults["policy_file_path"] = policy_path
        defaults["policy_file"] = _metadata_path(base_dir, policy_path)
        defaults["policy_source"] = f"env:{policy_env_name}"
        defaults["policy_explicit"] = True

    raw_codex_home_override, codex_home_env_name = _env_override(CODEX_HOME_OVERRIDE_ENV, CODEX_HOME_ENV)
    if raw_codex_home_override and codex_home_env_name:
        codex_home_path = _resolve_path_reference(base_dir, raw_codex_home_override, field_name=codex_home_env_name)
        defaults["codex_home"] = _metadata_path(base_dir, codex_home_path)
        defaults["codex_home_path"] = codex_home_path
        defaults["codex_home_explicit"] = True
        cast(dict[str, str], defaults["resolved_from"])["codex_home"] = f"env:{codex_home_env_name}"

    config_exists = os.path.exists(config_path)
    if config_explicit and not config_exists:
        raise ValueError(f"{config_env_name or CONFIG_FILE_ENV} points to missing file '{config_display}'")

    if not config_exists:
        return defaults

    try:
        parsed = _read_structured_mapping_file(config_path)
    except FileNotFoundError:
        raise ValueError(f"{config_env_name or CONFIG_FILE_ENV} points to missing file '{config_display}'") from None
    except ValueError as exc:
        raise ValueError(f"invalid config file '{config_display}': {exc}") from exc

    schema_version_raw = parsed.get("schema_version")
    if schema_version_raw is None:
        raise ValueError(f"config file '{config_display}' is missing schema_version")
    try:
        schema_version = int(str(schema_version_raw))
    except ValueError as exc:
        raise ValueError(f"config file '{config_display}' has a non-integer schema_version") from exc
    if schema_version != 2:
        raise ValueError(f"config file '{config_display}' uses unsupported schema_version {schema_version}")

    config_defaults = parsed.get("defaults")
    if config_defaults is not None and not isinstance(config_defaults, dict):
        raise ValueError(f"config file '{config_display}' field `defaults` must be an object")
    if not isinstance(config_defaults, dict):
        config_defaults = {}

    if cast(dict[str, str], defaults["resolved_from"]).get("output_mode") == "built-in":
        raw_output = config_defaults.get("output")
        if raw_output is None:
            raw_output = config_defaults.get("output_mode")
        if raw_output is None:
            raw_output = parsed.get("output")
        if raw_output is not None:
            if not isinstance(raw_output, str):
                raise ValueError(f"config file '{config_display}' field `defaults.output` must be a string")
            output_mode = raw_output.strip().lower()
            if output_mode not in {OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL}:
                raise ValueError(
                    f"config file '{config_display}' field `defaults.output` must be one of: "
                    f"{OUTPUT_MODE_HUMAN}, {OUTPUT_MODE_JSON}, {OUTPUT_MODE_JSONL}"
                )
            defaults["output_mode"] = output_mode
            cast(dict[str, str], defaults["resolved_from"])["output_mode"] = f"config:{config_display}"

    if cast(dict[str, str], defaults["resolved_from"]).get("profile") == "built-in":
        raw_profile = config_defaults.get("profile")
        if raw_profile is None:
            raw_profile = parsed.get("profile")
        if raw_profile is not None:
            if not isinstance(raw_profile, str):
                raise ValueError(f"config file '{config_display}' field `defaults.profile` must be a string")
            profile = raw_profile.strip().lower()
            if profile not in PROFILE_VALUES:
                raise ValueError(
                    f"config file '{config_display}' field `defaults.profile` must be one of: {', '.join(sorted(PROFILE_VALUES))}"
                )
            defaults["profile"] = profile
            cast(dict[str, str], defaults["resolved_from"])["profile"] = f"config:{config_display}"

    if cast(dict[str, str], defaults["resolved_from"]).get("mode") == "built-in":
        raw_mode = config_defaults.get("mode")
        if raw_mode is None:
            raw_mode = parsed.get("mode")
        if raw_mode is not None:
            if not isinstance(raw_mode, str):
                raise ValueError(f"config file '{config_display}' field `defaults.mode` must be a string")
            mode = raw_mode.strip().lower()
            if mode not in MODE_VALUES:
                raise ValueError(
                    f"config file '{config_display}' field `defaults.mode` must be one of: {', '.join(sorted(MODE_VALUES))}"
                )
            defaults["mode"] = mode
            cast(dict[str, str], defaults["resolved_from"])["mode"] = f"config:{config_display}"

    safety = parsed.get("safety")
    if safety is not None and not isinstance(safety, dict):
        raise ValueError(f"config file '{config_display}' field `safety` must be an object")

    if not defaults.get("policy_explicit") and isinstance(safety, dict) and "policy_file" in safety:
        raw_policy = safety.get("policy_file")
        if not isinstance(raw_policy, str):
            raise ValueError(f"config file '{config_display}' field `safety.policy_file` must be a string")
        policy_path = _resolve_path_reference(
            os.path.dirname(config_path),
            raw_policy,
            field_name="safety.policy_file",
        )
        defaults["policy_file_path"] = policy_path
        defaults["policy_file"] = _metadata_path(base_dir, policy_path)
        defaults["policy_source"] = f"config:{config_display}"
        defaults["policy_explicit"] = True

    worker = parsed.get("worker")
    if worker is not None and not isinstance(worker, dict):
        raise ValueError(f"config file '{config_display}' field `worker` must be an object")
    if not defaults.get("codex_home_explicit") and isinstance(worker, dict) and "codex_home" in worker:
        raw_codex_home = worker.get("codex_home")
        if not isinstance(raw_codex_home, str):
            raise ValueError(f"config file '{config_display}' field `worker.codex_home` must be a string")
        codex_home_value = raw_codex_home.strip()
        if codex_home_value:
            codex_home_path = _resolve_path_reference(base_dir, codex_home_value, field_name="worker.codex_home")
            defaults["codex_home"] = _metadata_path(base_dir, codex_home_path)
            defaults["codex_home_path"] = codex_home_path
            cast(dict[str, str], defaults["resolved_from"])["codex_home"] = f"config:{config_display}"

    return defaults


def _apply_output_json_override(runtime_defaults: dict[str, object], output_json_override: bool | None) -> dict[str, object]:
    resolved = dict(runtime_defaults)
    resolved_sources = dict(cast(dict[str, str], runtime_defaults.get("resolved_from") or {}))
    resolved["resolved_from"] = resolved_sources
    if output_json_override is None:
        return resolved
    resolved["output_mode"] = OUTPUT_MODE_JSON if output_json_override else OUTPUT_MODE_HUMAN
    resolved_sources["output_mode"] = "flag:--json" if output_json_override else "flag:--json=false"
    return resolved


def _command_write_targets(command: str, *, include_exports: bool = False) -> list[str]:
    normalized = str(command).strip()
    targets: list[str] = []
    if normalized in {"verify", "replay"}:
        targets.extend(
            [
                f"{OG_ROOT}/traces/**",
                f"{OG_ROOT}/objects/**",
                f"{OG_ROOT}/claims/**",
                f"{OG_ROOT}/certificates/**",
                f"{OG_ROOT}/events/**",
                f"{INTEGRITY_CHECKPOINT_DIR}/**",
                INTEGRITY_STATE_FILE,
            ]
        )
    if include_exports:
        targets.extend(sorted(EXPORT_PATHS.values()))
    return targets


def _event_write_targets(event_id: str) -> list[str]:
    return [
        f"{EVENTS_DIR}/{event_id}.json",
        f"{EVENTS_DIR}/**",
        f"{INTEGRITY_CHECKPOINT_DIR}/**",
        INTEGRITY_STATE_FILE,
    ]


def _recorded_export_step(payload: dict[str, object]) -> dict[str, object] | None:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return None
    for raw_step in steps:
        if isinstance(raw_step, dict) and str(raw_step.get("name") or "") == "export":
            return cast(dict[str, object], raw_step)
    return None


def _append_export_refresh_step(
    payload: dict[str, object],
    repo_root: str,
    mode: str,
    policy: dict[str, object],
) -> dict[str, object]:
    export_step = _run_export_stage(repo_root, mode=mode, policy=policy)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        steps = []
        payload["steps"] = steps
    steps.append(export_step)

    if str(export_step.get("status") or "error").lower() != "ok":
        payload["status"] = "error"
        payload["message"] = str(export_step.get("message") or payload.get("message") or "export refresh failed")
        existing_errors = payload.get("errors")
        if not isinstance(existing_errors, list):
            existing_errors = []
            payload["errors"] = existing_errors
        export_errors = export_step.get("errors")
        if isinstance(export_errors, list) and export_errors:
            existing_errors.extend(export_errors)
        else:
            existing_errors.append(str(export_step.get("message") or "export refresh failed"))
    return export_step


def _collect_policy_checks(repo_root: str) -> dict[str, object]:
    try:
        runtime_defaults = _load_runtime_defaults(repo_root)
    except ValueError as exc:
        return {
            "path": DEFAULT_POLICY_FILE,
            "present": False,
            "status": "error",
            "message": f"cannot resolve policy file: {exc}",
            "checks": [
                {
                    "type": "policy_config",
                    "status": "error",
                    "message": f"cannot resolve policy file: {exc}",
                    "remediation": [
                        "Repair runtime defaults in environment variables or config files before rerunning the command."
                    ],
                }
            ],
            "policy": _default_policy(),
            "status_counts": {"error": 1, "warn": 0},
            "parsed": {},
        }

    policy_path = str(runtime_defaults.get("policy_file_path") or os.path.join(repo_root, DEFAULT_POLICY_FILE))
    policy_display = str(runtime_defaults.get("policy_file") or DEFAULT_POLICY_FILE)
    policy_explicit = bool(runtime_defaults.get("policy_explicit"))
    payload: dict[str, object] = {
        "path": policy_display,
        "present": False,
        "status": "ok",
        "message": "policy file is not explicit; built-in defaults apply",
        "checks": [],
        "policy": _default_policy(),
        "status_counts": {"error": 0, "warn": 0},
        "parsed": {},
    }
    if not os.path.exists(policy_path):
        if policy_explicit:
            payload["status"] = "error"
            payload["message"] = f"configured policy file is missing: {policy_display}"
            payload["checks"] = [
                {
                    "type": "policy_file_read",
                    "status": "error",
                    "message": payload["message"],
                    "remediation": [f"Create or repoint the configured policy file at '{policy_display}'."],
                }
            ]
            payload["status_counts"] = {"error": 1, "warn": 0}
        return payload

    try:
        parsed = _read_structured_mapping_file(policy_path)
    except FileNotFoundError:
        payload["present"] = True
        payload["status"] = "error"
        payload["message"] = f"configured policy file is missing: {policy_display}"
        payload["checks"] = [
            {
                "type": "policy_file_read",
                "status": "error",
                "message": payload["message"],
                "remediation": [f"Create or repoint the configured policy file at '{policy_display}'."],
            }
        ]
        payload["status_counts"] = {"error": 1, "warn": 0}
        return payload
    except ValueError as exc:
        payload["present"] = True
        payload["status"] = "error"
        payload["message"] = f"cannot parse policy file: {exc}"
        payload["checks"] = [
            {
                "type": "policy_parse",
                "status": "error",
                "message": payload["message"],
                "remediation": [f"Repair structured syntax in '{policy_display}' and rerun the command."],
            }
        ]
        payload["parsed"] = {}
        payload["status_counts"] = {"error": 1, "warn": 0}
        return payload
    payload["present"] = True
    payload["parsed"] = parsed

    policy: dict[str, object] = _default_policy()
    checks: list[dict[str, object]] = []
    errors = 0
    warnings = 0

    schema_version_raw = parsed.get("schema_version")
    if schema_version_raw is None:
        errors += 1
        checks.append(
            {
                "type": "policy_schema_version",
                "status": "error",
                "message": "missing `schema_version` in policy file",
                "remediation": [f"Add `schema_version: 2` to '{policy_display}'."],
            }
        )
    else:
        try:
            schema_version = int(str(schema_version_raw))
        except ValueError:
            errors += 1
            checks.append(
                {
                    "type": "policy_schema_version",
                    "status": "error",
                    "message": "policy schema_version is not an integer",
                    "remediation": [f"Add `schema_version: 2` to '{policy_display}'."],
                }
            )
        else:
            if schema_version != 2:
                errors += 1
                checks.append(
                    {
                        "type": "policy_schema_version",
                        "status": "error",
                        "message": f"policy schema_version {schema_version} is incompatible",
                        "remediation": ["Set policy `schema_version: 2` for compatibility."],
                    }
                )

    mode = str(parsed.get("mode") or policy.get("mode") or "observe")
    if mode and mode not in MODE_VALUES:
        warnings += 1
        checks.append(
            {
                "type": "policy_mode",
                "status": "warn",
                "message": f"policy mode '{mode}' is unsupported",
                "remediation": ["Use `observe` or `autonomous` for `mode` in policy file."],
            }
        )
        mode = "observe"
    policy["mode"] = mode

    allow_raw = parsed.get("allow")
    deny_raw = parsed.get("deny")
    if allow_raw is not None and not isinstance(allow_raw, dict):
        errors += 1
        checks.append(
            {
                "type": "policy_allow",
                "status": "error",
                "message": "policy field `allow` must be an object",
                "remediation": [f"Use YAML/JSON object syntax for `allow` in '{policy_display}'."],
            }
        )

    if deny_raw is not None and not isinstance(deny_raw, dict):
        errors += 1
        checks.append(
            {
                "type": "policy_deny",
                "status": "error",
                "message": "policy field `deny` must be an object",
                "remediation": [f"Use YAML/JSON object syntax for `deny` in '{policy_display}'."],
            }
        )

    allow = allow_raw if isinstance(allow_raw, dict) else {}
    deny = deny_raw if isinstance(deny_raw, dict) else {}
    if errors == 0:
        allow_rules = policy.setdefault("allow", {})
        deny_rules = policy.setdefault("deny", {})
        if isinstance(allow_rules, dict):
            for category in POLICY_ALLOW_CATEGORIES:
                if category in allow:
                    allow_rules[category] = _policy_merge_lists(
                        _policy_string_list(allow_rules.get(category)),
                        _policy_string_list(allow.get(category)),
                    )
        if isinstance(deny_rules, dict):
            for category in POLICY_DENY_CATEGORIES:
                if category in deny:
                    deny_rules[category] = _policy_merge_lists(
                        _policy_string_list(deny_rules.get(category)),
                        _policy_string_list(deny.get(category)),
                    )
        policy["mode"] = mode

    payload["policy"] = policy
    if errors:
        payload["status"] = "error"
        payload["message"] = "policy checks failed"
    elif warnings:
        payload["status"] = "warn"
        payload["message"] = "policy file has warnings"
    else:
        payload["message"] = "policy file validated"

    payload["checks"] = checks
    payload["status_counts"] = {"error": errors, "warn": warnings}
    return payload


def _resolve_policy_for_repo(
    repo_root: str,
    policy_payload: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    if isinstance(policy_payload, dict) and "status" not in policy_payload and "policy" not in policy_payload:
        allow = policy_payload.get("allow")
        deny = policy_payload.get("deny")
        if isinstance(allow, dict) and isinstance(deny, dict):
            return policy_payload, None
    payload = policy_payload or _collect_policy_checks(repo_root)
    status = str(payload.get("status") or "error").lower() if isinstance(payload, dict) else "error"
    if status == "error":
        return _default_policy(), {
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "command": "policy",
            "message": "policy configuration is invalid",
            "policy": payload,
        }

    policy = payload.get("policy")
    if isinstance(policy, dict):
        return cast(dict[str, object], policy), None
    return _default_policy(), None


def _build_autonomous_write_block_payload(
    repo_root: str,
    mode: str,
    *,
    name: str,
    command: str,
) -> dict[str, object] | None:
    if str(mode or "").lower() != "autonomous":
        return None

    policy_checks = _collect_policy_checks(repo_root)
    policy_status = str(policy_checks.get("status") or "error").lower()
    integrity = _collect_integrity_state(repo_root)
    integrity_state = str(integrity.get("state") or "").lower()

    if policy_status == "ok" and integrity_state == "ok":
        return None

    reasons: list[str] = []
    remediation: list[str] = []
    if policy_status != "ok":
        reasons.append(f"policy state is {policy_status}")
        for raw_check in policy_checks.get("checks", []):
            if not isinstance(raw_check, dict):
                continue
            for item in raw_check.get("remediation", []):
                if isinstance(item, str):
                    remediation.append(item)
    if integrity_state != "ok":
        reasons.append("integrity ledger is degraded")
        remediation.append("Repair integrity index before running autonomous writes.")
    message = f"Autonomous writes blocked because {' and '.join(reasons)}."

    return {
        "name": name,
        "status": "error",
        "code": AUTONOMOUS_WRITE_BLOCKED_CODE,
        "command": command,
        "mode": mode,
        "message": message,
        "errors": [message],
        "remediation": sorted(set(remediation)),
        "policy": policy_checks,
        "integrity": integrity,
    }


def _ensure_policy_action_allowed(
    action_policy: dict[str, object],
    command: str,
    category: str,
    target: str,
    mode: str,
) -> dict[str, object] | None:
    return _enforce_policy_action(action_policy, command, category, target, mode)


def _collect_drift_state(repo_root: str, now: datetime.datetime, include_ledger: bool = True) -> dict[str, object]:
    certificates = _collect_certificate_freshness(repo_root, now)
    policy = _collect_policy_checks(repo_root)
    integrity = _collect_integrity_state(repo_root)
    checks: list[dict[str, object]] = []
    remediation: list[str] = []

    if str(integrity.get("state") or "ok") != "ok":
        integrity_check = {
            "type": "integrity_ledger",
            "status": "error",
            "message": str(integrity.get("message") or "integrity ledger is degraded"),
            "remediation": [
                "Repair integrity index before running further writes and sync verification.",
            ],
            "details": {
                "state": integrity.get("state"),
                "status": integrity.get("status"),
                "event_count": integrity.get("event_count"),
            },
        }
        checks.append(integrity_check)
        remediation.extend(integrity_check["remediation"])

    if certificates["state"] in {"unknown", "stale"}:
        check_status = "error" if certificates["state"] == "unknown" else "warn"
        certificate_check = {
            "type": "stale_certificates",
            "status": check_status,
            "message": certificates["message"],
            "remediation": [
                "Run `og sync` to regenerate current certificates.",
                "Check `.outcomegraph/events` for prior sync summary failures.",
            ],
            "details": {
                "state": certificates["state"],
                "count": certificates.get("count", 0),
                "age_seconds": certificates.get("age_seconds"),
            },
        }
        checks.append(certificate_check)
        remediation.extend(certificate_check["remediation"])

    for raw_check in policy.get("checks", []):
        if not isinstance(raw_check, dict):
            continue
        checks.append(
            {
                "type": str(raw_check.get("type") or "policy"),
                "status": str(raw_check.get("status") or "warn"),
                "message": str(raw_check.get("message") or "policy check requires attention"),
                "remediation": raw_check.get("remediation", []),
                "details": {"type": str(raw_check.get("type") or "")},
            }
        )
        for item in raw_check.get("remediation", []):
            if isinstance(item, str):
                remediation.append(item)

    export_surface = _collect_export_drift_check(repo_root)
    if export_surface is not None:
        checks.append(export_surface)
        for item in export_surface.get("remediation", []):
            if isinstance(item, str):
                remediation.append(item)

    if not checks:
        checks.append(
            {
                "type": "policy_certificates",
                "status": "ok",
                "message": "drift checks for policy and certificates passed",
            }
        )

    drift_state = "ok"
    for check in checks:
        check_status = str(check.get("status") or "ok")
        if check_status == "error":
            drift_state = "error"
            break
        if check_status == "warn":
            drift_state = "warn"

    latest_event: dict | None = None
    latest_event_path: str | None = None
    if include_ledger:
        latest_event, _, latest_event_path = _read_latest_drift_event(repo_root)

    return {
        "status_schema_version": DRIFT_REPORT_SCHEMA_VERSION,
        "state": drift_state,
        "status": "ok" if drift_state == "ok" else drift_state,
        "checks": checks,
        "remediation": sorted(set(remediation)),
        "certificates": certificates,
        "policy": policy,
        "latest_event": (
            {
                "run_id": latest_event.get("run_id") if isinstance(latest_event, dict) else None,
                "status": latest_event.get("status") if isinstance(latest_event, dict) else None,
                "created_at": latest_event.get("created_at") if isinstance(latest_event, dict) else None,
                "path": latest_event_path,
            }
            if latest_event
            else None
        ),
    }


def _collect_export_drift_check(repo_root: str) -> dict[str, object] | None:
    try:
        snapshot = _canonical_export_snapshot(repo_root)
    except Exception as exc:
        return {
            "type": "export_control_surface",
            "status": "error",
            "message": f"Unable to compute canonical export snapshot: {exc}",
            "remediation": [
                "Run `og sync` to rebuild canonical snapshots and repair schema violations.",
            ],
            "details": {"phase": "snapshot"},
        }

    outputs = _build_export_outputs(snapshot)
    mismatches: list[dict[str, object]] = []

    for relative_path, content in outputs.items():
        full_path = os.path.join(repo_root, relative_path)
        generated_hash = _content_sha256(content.encode("utf-8"))
        if not os.path.exists(full_path):
            mismatches.append({"path": relative_path, "type": "missing", "generated_hash": generated_hash})
            continue
        observed_hash = _read_file_content_hash(repo_root, relative_path)
        if generated_hash != observed_hash:
            mismatches.append(
                {"path": relative_path, "type": "hash_mismatch", "generated_hash": generated_hash, "observed_hash": observed_hash}
            )

    try:
        payload = _build_mcp_server_payload(snapshot, {})
        mcp_surface_issues = _validate_mcp_control_surface_payload(payload)
        for item in mcp_surface_issues:
            mismatches.append({"type": "control_surface", "message": item})
    except Exception as exc:
        mismatches.append({"type": "control_surface", "message": f"Unable to validate control surface payload: {exc}"})

    if not mismatches:
        return None

    return {
        "type": "export_control_surface",
        "status": "warn",
        "message": "Exported control surfaces are out of sync with canonical artifacts.",
        "remediation": [
            "Run `og export` to regenerate AGENTS/skill/MCP control-surface outputs from canonical artifacts.",
            "Re-run `og sync` after fixing canonical artifact path/type or payload errors.",
        ],
        "details": {
            "total_artifacts": snapshot.get("counts", {}).get("total", 0),
            "issues": mismatches,
        },
    }


def _build_status_payload(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    state = _read_work_state(repo_root)
    lock = _read_lock_status(repo_root, now)
    pending_file_present, pending_file_source = _read_work_pending_file(repo_root)
    sync_event, _ = _read_latest_sync_event(repo_root)
    sync = _collect_sync_freshness(sync_event, now)
    verification = _collect_verification_state(repo_root, sync_event, now)
    certificates = _collect_certificate_freshness(repo_root, now)
    drift = _collect_drift_state(repo_root, now)
    integrity = _collect_integrity_state(repo_root)

    has_pending = bool(state.get("pending", False)) or pending_file_present
    runtime_message = "runtime is idle"
    if lock["status"] == "stale":
        runtime_message = "active work lock is stale"
    elif lock["status"] == "locked":
        runtime_message = "sync is currently running"
    elif has_pending or state.get("status") == "pending":
        runtime_message = "pending work is queued"
    elif state.get("status") == "degraded":
        runtime_message = "work state is degraded"
    elif integrity.get("state") == "degraded":
        runtime_message = "integrity ledger is degraded"

    overall_status = "ok"
    if (
        sync["state"] == "degraded"
        or verification["state"] == "degraded"
        or state.get("status") == "degraded"
        or integrity.get("state") == "degraded"
        or state.get("status") == "error"
    ):
        overall_status = "error"
    elif (
        sync["state"] in {"stale", "unknown"}
        or verification["state"] == "warn"
        or verification["state"] in {"stale", "unknown"}
        or certificates["state"] in {"stale", "unknown"}
        or drift["state"] in {"warn", "error"}
        or has_pending
        or lock["status"] == "stale"
    ):
        overall_status = "warn"

    issues = []
    if has_pending:
        source = state.get("pending_source") or pending_file_source or "work queue"
        issues.append({"type": "pending", "message": f"pending work recorded from {source}"})
    if state.get("status") == "degraded":
        issues.append({"type": "degraded", "message": "runtime state flagged as degraded"})
    if sync["state"] == "stale":
        issues.append({"type": "stale_sync", "message": sync["message"]})
    if sync["state"] == "degraded":
        issues.append({"type": "sync_error", "message": sync["message"]})
    if verification["state"] == "degraded":
        issues.append({"type": "verify_error", "message": verification["message"]})
    elif verification["state"] == "warn":
        issues.append({"type": "verify_warning", "message": verification["message"]})
    elif verification["state"] == "stale":
        issues.append({"type": "stale_verification", "message": verification["message"]})
    elif verification["state"] == "unknown":
        issues.append({"type": "unknown_verification", "message": verification["message"]})
    if certificates["state"] == "stale":
        issues.append({"type": "stale_certificates", "message": certificates["message"]})
    elif certificates["state"] == "unknown":
        issues.append({"type": "unknown_certificates", "message": certificates["message"]})
    if drift["state"] == "error":
        issues.append({"type": "drift_error", "message": "policy/certificate drift checks failed"})
    elif drift["state"] == "warn":
        issues.append({"type": "drift_warning", "message": "policy/certificate drift checks suggest remediation"})
    if integrity.get("state") == "degraded":
        issues.append({"type": "integrity", "message": str(integrity.get("message") or "integrity ledger is degraded")})

    if not issues and overall_status == "ok":
        issues = []

    holder = lock.get("holder")
    lock_holder = None
    if isinstance(holder, dict):
        lock_holder = {
            "pid": holder.get("pid"),
            "host": holder.get("host"),
            "command": holder.get("command"),
        }
    lock_session = _session_from_payload(lock.get("session"), now=now)

    payload: dict[str, object] = {
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "status": overall_status,
        "command": "status",
        "options": dict(options),
        "generated_at": _utc_timestamp(),
        "message": "status dashboard computed",
        "issues": issues,
        "freshness": {
            "sync": sync,
            "certificates": certificates,
            "message": f"sync={sync['state']}, certificates={certificates['state']}",
        },
        "drift": drift,
        "integrity": integrity,
        "verification": verification,
        "remediation": drift.get("remediation", []),
        "runtime": {
            "status": state.get("status"),
            "pending": has_pending,
            "pending_source": state.get("pending_source"),
            "pending_file": {
                "present": pending_file_present,
                "source": pending_file_source,
            },
            "last_message": state.get("last_message"),
            "lock": {
                "status": lock["status"],
                "age_human": _humanize_duration(lock["age_seconds"]),
                "holder": lock_holder,
                "session": lock_session,
            },
            "message": runtime_message,
        },
    }
    if overall_status == "warn":
        payload["message"] = "status dashboard indicates warnings"
    if overall_status == "error":
        payload["message"] = "status dashboard indicates degraded sync/verification state"
    return payload


def _sync_write_targets(*, include_exports: bool = False) -> list[str]:
    targets = [
        f"{OG_ROOT}/traces/**",
        f"{OG_ROOT}/objects/**",
        f"{OG_ROOT}/capsules/**",
        f"{OG_ROOT}/refs/**",
        f"{OG_ROOT}/decisions/**",
        f"{OG_ROOT}/claims/**",
        f"{OG_ROOT}/certificates/**",
        f"{OG_ROOT}/materials.lock",
        f"{OG_ROOT}/events/**",
        f"{INTEGRITY_CHECKPOINT_DIR}/**",
        INTEGRITY_STATE_FILE,
    ]
    if include_exports:
        targets.extend(sorted(EXPORT_PATHS.values()))
    return targets


def _make_preflight_check(
    name: str,
    status: str,
    message: str,
    *,
    error_code: str | None = None,
    remediation: list[str] | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "status": status,
        "message": message,
    }
    if error_code:
        payload["error_code"] = error_code
    if remediation:
        payload["remediation"] = remediation
    if details:
        payload["details"] = details
    return payload


def _build_preflight_payload(
    command: str,
    options: dict[str, object],
    checks: list[dict[str, object]],
    *,
    message: str,
    run_id: str | None = None,
    plan: dict[str, object] | None = None,
    write_targets: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    status = _preflight_status_for_checks(checks)
    errors, warnings = _preflight_messages_for_checks(checks)
    payload: dict[str, object] = {
        "status": status,
        "command": command,
        "options": options,
        "validate": bool(options.get("validate")),
        "dry_run": bool(options.get("dry_run")),
        "checks": checks,
        "message": message,
        "errors": errors,
        "warnings": warnings,
    }
    if run_id:
        payload["run_id"] = run_id
    if plan is not None:
        payload["plan"] = plan
    if write_targets is not None:
        payload["write_targets"] = sorted(set(write_targets))
    if extra:
        payload.update(extra)
    return payload


def _run_export_preflight(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    planned_exports: list[str] = []
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        checks.append(
            _make_preflight_check(
                "policy",
                "error",
                str(policy_error.get("message") or "policy configuration is invalid"),
                error_code=POLICY_CONFIG_ERROR_CODE,
            )
        )
    else:
        write_check = _evaluate_policy_writes(policy_payload, "export", "observe", list(EXPORT_PATHS.values()))
        if write_check is None:
            checks.append(_make_preflight_check("policy", "ok", "export write targets are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "policy",
                    "error",
                    str(write_check.get("message") or "policy denied export writes"),
                    error_code=str(write_check.get("error_code") or write_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(write_check.get("remediation")),
                )
            )

    drift = _collect_export_drift_check(repo_root)
    if drift is None:
        checks.append(_make_preflight_check("exports", "ok", "export surfaces are already in sync"))
    else:
        issues = drift.get("details", {}).get("issues", []) if isinstance(drift.get("details"), dict) else []
        planned_exports = sorted(
            {
                str(item.get("path"))
                for item in issues
                if isinstance(item, dict) and isinstance(item.get("path"), str) and item.get("path")
            }
        )
        checks.append(
            _make_preflight_check(
                "exports",
                "warn" if planned_exports else str(drift.get("status") or "warn"),
                str(drift.get("message") or "export surfaces need regeneration"),
                remediation=_safe_string_list(drift.get("remediation")),
                details={"planned_exports": planned_exports},
            )
        )

    plan = {"planned_exports": planned_exports} if bool(options.get("dry_run")) else None
    return _build_preflight_payload(
        "export",
        options,
        checks,
        message="export dry-run completed." if bool(options.get("dry_run")) else "export validation completed.",
        plan=plan,
        write_targets=list(EXPORT_PATHS.values()),
        extra={"planned_exports": planned_exports},
    )


def _run_verify_preflight(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    changed_only = bool(options.get("changed"))
    timeout_override = options.get("timeout")
    max_retries = int(options.get("max_retries") or 0)
    snapshot = _collect_sync_snapshot(repo_root, profile, mode)
    changed_files = [str(item) for item in snapshot.get("changed_files", [])] if isinstance(snapshot.get("changed_files"), list) else []
    changed_capsules = _collect_affected_capsules(changed_files) if changed_only else _list_known_capsules(repo_root)
    if not changed_capsules and not changed_only:
        changed_only = True
        changed_capsules = ["default"]
    run_id = _build_run_id("verify", _short_hash(f"{profile}:{mode}:{'changed' if changed_only else 'all'}", 10))

    checks: list[dict[str, object]] = []
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        checks.append(
            _make_preflight_check(
                "policy",
                "error",
                str(policy_error.get("message") or "policy configuration is invalid"),
                error_code=POLICY_CONFIG_ERROR_CODE,
            )
        )
    else:
        autonomous_block = _build_autonomous_write_block_payload(repo_root, mode, name="verify", command="verify")
        if autonomous_block is not None:
            checks.append(
                _make_preflight_check(
                    "autonomous_writes",
                    "error",
                    str(autonomous_block.get("message") or "autonomous writes are blocked"),
                    error_code=AUTONOMOUS_WRITE_BLOCKED_CODE,
                    remediation=_safe_string_list(autonomous_block.get("remediation")),
                )
            )
        sandbox_check = _ensure_policy_action_allowed(
            policy_payload,
            command="verify",
            category="sandbox_operations",
            target="read_artifacts",
            mode=mode,
        )
        if sandbox_check is None:
            checks.append(_make_preflight_check("sandbox", "ok", "verify sandbox reads are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "sandbox",
                    "error",
                    str(sandbox_check.get("message") or "policy denied sandbox reads"),
                    error_code=str(sandbox_check.get("error_code") or sandbox_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(sandbox_check.get("remediation")),
                )
            )
        write_targets = _command_write_targets("verify", include_exports=True)
        write_check = _evaluate_policy_writes(policy_payload, "verify", mode, write_targets)
        if write_check is None:
            checks.append(_make_preflight_check("writes", "ok", "verify write targets are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "writes",
                    "error",
                    str(write_check.get("message") or "policy denied verify writes"),
                    error_code=str(write_check.get("error_code") or write_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(write_check.get("remediation")),
                )
            )
    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        checks.append(_make_preflight_check("canonical", "error", f"Canonical artifact validation failed: {exc}"))
    else:
        checks.append(_make_preflight_check("canonical", "ok", "canonical artifacts validate before verify"))

    planned_oracles: dict[str, list[str]] = {}
    if bool(options.get("dry_run")):
        for capsule in changed_capsules:
            capsule_oracles = _load_capsule_oracles(repo_root, capsule)
            impacted_oracles = [
                oracle
                for oracle in capsule_oracles
                if isinstance(oracle, dict) and _oracle_scopes_match(oracle, changed_files)
            ]
            if not impacted_oracles:
                impacted_oracles = capsule_oracles[:1]
            planned_oracles[capsule] = [str(oracle.get("name") or "unknown-oracle") for oracle in impacted_oracles]

    return _build_preflight_payload(
        "verify",
        options,
        checks,
        message="verify dry-run completed." if bool(options.get("dry_run")) else "verify validation completed.",
        run_id=run_id,
        plan=(
            {
                "changed_only": changed_only,
                "changed_files": changed_files if changed_only else [],
                "planned_capsules": changed_capsules,
                "planned_oracles": planned_oracles,
                "max_retries": max_retries,
                "timeout_seconds": timeout_override,
            }
            if bool(options.get("dry_run"))
            else None
        ),
        write_targets=_command_write_targets("verify", include_exports=True),
        extra={
            "changed_only": changed_only,
            "changed_files": changed_files if changed_only else [],
            "planned_capsules": changed_capsules,
            "planned_oracles": planned_oracles,
        },
    )


def _run_replay_preflight(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    changed_only = bool(options.get("changed"))
    timeout_override = options.get("timeout")
    max_retries = int(options.get("max_retries") or 0)
    snapshot = _collect_sync_snapshot(repo_root, profile, mode)
    run_id = _build_run_id("replay", _short_hash(f"{profile}:{mode}:{snapshot.get('changed_count', 0)}", 8))
    changed_files = [str(item) for item in snapshot.get("changed_files", [])] if isinstance(snapshot.get("changed_files"), list) else []
    targets = _collect_affected_capsules(changed_files) if changed_only else _list_known_capsules(repo_root)
    if not targets:
        targets = ["default"]

    checks: list[dict[str, object]] = []
    adapter_errors = _initialize_adapter_runtime(repo_root)
    if adapter_errors:
        first_error = adapter_errors[0]
        checks.append(
            _make_preflight_check(
                "adapter",
                "error",
                str(first_error.get("message") or "adapter initialization failed"),
                error_code=str(first_error.get("code") or ADAPTER_INTERFACE_MISMATCH_CODE),
                remediation=_safe_string_list(first_error.get("remediation")),
            )
        )
    else:
        checks.append(_make_preflight_check("adapter", "ok", "worker adapter initialized for replay"))

    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        checks.append(
            _make_preflight_check(
                "policy",
                "error",
                str(policy_error.get("message") or "policy configuration is invalid"),
                error_code=POLICY_CONFIG_ERROR_CODE,
            )
        )
    else:
        autonomous_block = _build_autonomous_write_block_payload(repo_root, mode, name="replay", command="replay")
        if autonomous_block is not None:
            checks.append(
                _make_preflight_check(
                    "autonomous_writes",
                    "error",
                    str(autonomous_block.get("message") or "autonomous writes are blocked"),
                    error_code=AUTONOMOUS_WRITE_BLOCKED_CODE,
                    remediation=_safe_string_list(autonomous_block.get("remediation")),
                )
            )
        sandbox_check = _ensure_policy_action_allowed(
            policy_payload,
            command="replay",
            category="sandbox_operations",
            target="create_isolated_worktree",
            mode=mode,
        )
        if sandbox_check is None:
            sandbox_check = _ensure_policy_action_allowed(
                policy_payload,
                command="replay",
                category="sandbox_operations",
                target="read_artifacts",
                mode=mode,
            )
        if sandbox_check is None:
            checks.append(_make_preflight_check("sandbox", "ok", "replay sandbox operations are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "sandbox",
                    "error",
                    str(sandbox_check.get("message") or "policy denied sandbox operations"),
                    error_code=str(sandbox_check.get("error_code") or sandbox_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(sandbox_check.get("remediation")),
                )
            )
        write_targets = _command_write_targets("replay", include_exports=True)
        write_check = _evaluate_policy_writes(policy_payload, "replay", mode, write_targets)
        if write_check is None:
            checks.append(_make_preflight_check("writes", "ok", "replay write targets are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "writes",
                    "error",
                    str(write_check.get("message") or "policy denied replay writes"),
                    error_code=str(write_check.get("error_code") or write_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(write_check.get("remediation")),
                )
            )
    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        checks.append(_make_preflight_check("canonical", "error", f"Canonical artifact validation failed: {exc}"))
    else:
        checks.append(_make_preflight_check("canonical", "ok", "canonical artifacts validate before replay"))

    return _build_preflight_payload(
        "replay",
        options,
        checks,
        message="replay dry-run completed." if bool(options.get("dry_run")) else "replay validation completed.",
        run_id=run_id,
        plan=(
            {
                "planned_capsules": targets,
                "changed_files": changed_files if changed_only else [],
                "max_retries": max_retries,
                "timeout_seconds": timeout_override,
            }
            if bool(options.get("dry_run"))
            else None
        ),
        write_targets=_command_write_targets("replay", include_exports=True),
        extra={"planned_capsules": targets},
    )


def _run_sync_preflight(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    force_full_sync = bool(options.get("force_full_sync", False))
    timeout_override = options.get("timeout")
    max_retries = int(options.get("max_retries") or 0)
    snapshot = _collect_sync_snapshot(repo_root, profile, mode, force_full_sync=force_full_sync)
    idempotency_key = _compute_idempotency_key(snapshot, profile, mode)
    run_id = f"sync-{_utc_timestamp().replace(':', '').replace('-', '')}-{idempotency_key[:10]}"
    changed_files = [str(item) for item in snapshot.get("changed_files", [])] if isinstance(snapshot.get("changed_files"), list) else []
    changed_capsules = _collect_affected_capsules(changed_files)
    checks: list[dict[str, object]] = []

    integrity = _validate_event_chain(repo_root)
    if str(integrity.get("status") or "ok") != "ok":
        checks.append(
            _make_preflight_check(
                "integrity",
                "error",
                str(integrity.get("message") or "integrity ledger is degraded"),
                error_code=INTEGRITY_CHECK_FAILED_CODE,
                remediation=["Repair integrity index before running sync."],
            )
        )
    else:
        checks.append(_make_preflight_check("integrity", "ok", "integrity ledger validates before sync"))

    lock_state = _read_lock_status(repo_root, datetime.datetime.now(tz=datetime.timezone.utc))
    lock_status = str(lock_state.get("status") or "free")
    if lock_status == "locked":
        checks.append(_make_preflight_check("lock", "warn", "sync lock is currently held; sync would queue pending work"))
    elif lock_status == "stale":
        checks.append(_make_preflight_check("lock", "warn", "sync lock appears stale and may require operator review"))
    else:
        checks.append(_make_preflight_check("lock", "ok", "sync lock is free"))

    adapter_errors = _initialize_adapter_runtime(repo_root)
    if adapter_errors:
        first_error = adapter_errors[0]
        checks.append(
            _make_preflight_check(
                "adapter",
                "error",
                str(first_error.get("message") or "adapter initialization failed"),
                error_code=str(first_error.get("code") or ADAPTER_INTERFACE_MISMATCH_CODE),
                remediation=_safe_string_list(first_error.get("remediation")),
            )
        )
    else:
        checks.append(_make_preflight_check("adapter", "ok", "worker adapter initialized for sync"))

    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        checks.append(
            _make_preflight_check(
                "policy",
                "error",
                str(policy_error.get("message") or "policy configuration is invalid"),
                error_code=POLICY_CONFIG_ERROR_CODE,
            )
        )
    else:
        write_check = _evaluate_policy_writes(policy_payload, "sync", mode, _sync_write_targets(include_exports=True))
        if write_check is None:
            checks.append(_make_preflight_check("writes", "ok", "sync write targets are allowed by policy"))
        else:
            checks.append(
                _make_preflight_check(
                    "writes",
                    "error",
                    str(write_check.get("message") or "policy denied sync writes"),
                    error_code=str(write_check.get("error_code") or write_check.get("code") or POLICY_DENIED_CODE),
                    remediation=_safe_string_list(write_check.get("remediation")),
                )
            )
    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        checks.append(_make_preflight_check("canonical", "error", f"Canonical artifact validation failed: {exc}"))
    else:
        checks.append(_make_preflight_check("canonical", "ok", "canonical artifacts validate before sync"))

    current_state = _read_work_state(repo_root)
    short_circuit = not force_full_sync and current_state.get("last_idempotency_key") == idempotency_key
    if short_circuit:
        checks.append(_make_preflight_check("idempotency", "warn", "sync would short-circuit because the idempotency key is unchanged"))
    else:
        checks.append(_make_preflight_check("idempotency", "ok", "sync would execute a full reconciliation pass"))

    planned_steps = ["distill", "apply", "verify", "export"]
    if short_circuit:
        planned_steps = ["short_circuit"]

    return _build_preflight_payload(
        "sync",
        options,
        checks,
        message="sync dry-run completed." if bool(options.get("dry_run")) else "sync validation completed.",
        run_id=run_id,
        plan=(
            {
                "changed_files": changed_files,
                "affected_capsules": changed_capsules,
                "planned_steps": planned_steps,
                "idempotency_key": idempotency_key,
                "max_retries": max_retries,
                "timeout_seconds": timeout_override,
            }
            if bool(options.get("dry_run"))
            else None
        ),
        write_targets=_sync_write_targets(include_exports=True),
        extra={
            "snapshot": snapshot,
            "idempotency_key": idempotency_key,
            "affected_capsules": changed_capsules,
            "short_circuit": short_circuit,
        },
    )


def _build_doctor_payload(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    status_payload = _build_status_payload(repo_root, options)
    drift = status_payload.get("drift") if isinstance(status_payload.get("drift"), dict) else {}
    integrity = status_payload.get("integrity") if isinstance(status_payload.get("integrity"), dict) else {}
    runtime = status_payload.get("runtime") if isinstance(status_payload.get("runtime"), dict) else {}
    freshness = status_payload.get("freshness") if isinstance(status_payload.get("freshness"), dict) else {}
    verification = status_payload.get("verification") if isinstance(status_payload.get("verification"), dict) else {}
    sync = freshness.get("sync") if isinstance(freshness.get("sync"), dict) else {}
    certificates = freshness.get("certificates") if isinstance(freshness.get("certificates"), dict) else {}
    policy = drift.get("policy") if isinstance(drift.get("policy"), dict) else {}
    daemon_payload = _daemon_status_payload(repo_root, *_daemon_running_state(repo_root))

    checks: list[dict[str, object]] = [
        {
            "name": "runtime",
            "status": status_payload.get("status", "ok"),
            "message": runtime.get("message", "runtime status unavailable"),
            "details": {"runtime": runtime},
        },
        {
            "name": "sync",
            "status": sync.get("state", sync.get("status", "unknown")),
            "message": sync.get("message", "sync freshness unavailable"),
            "details": {"sync": sync},
        },
        {
            "name": "verification",
            "status": verification.get("status", verification.get("state", "unknown")),
            "message": verification.get("message", "verification status unavailable"),
            "details": {"verification": verification},
        },
        {
            "name": "certificates",
            "status": certificates.get("state", certificates.get("status", "unknown")),
            "message": certificates.get("message", "certificate freshness unavailable"),
            "details": {"certificates": certificates},
        },
        {
            "name": "integrity",
            "status": integrity.get("state", integrity.get("status", "unknown")),
            "message": integrity.get("message", "integrity status unavailable"),
            "details": {"integrity": integrity},
        },
        {
            "name": "daemon",
            "status": daemon_payload.get("status", "warn"),
            "message": daemon_payload.get("message", "daemon status unavailable"),
            "details": {"daemon": daemon_payload.get("runtime", {})},
        },
    ]
    for raw_check in drift.get("checks", []) if isinstance(drift.get("checks"), list) else []:
        if not isinstance(raw_check, dict):
            continue
        checks.append(
            {
                "name": str(raw_check.get("type") or "drift"),
                "status": str(raw_check.get("status") or "warn"),
                "message": str(raw_check.get("message") or "drift check requires attention"),
                "remediation": raw_check.get("remediation", []),
                "details": raw_check.get("details", {}),
            }
        )
    for raw_check in policy.get("checks", []) if isinstance(policy.get("checks"), list) else []:
        if not isinstance(raw_check, dict):
            continue
        checks.append(
            {
                "name": f"policy:{raw_check.get('type') or 'check'}",
                "status": str(raw_check.get("status") or "warn"),
                "message": str(raw_check.get("message") or "policy check requires attention"),
                "remediation": raw_check.get("remediation", []),
                "details": raw_check,
            }
        )

    remediation: list[str] = []
    for item in status_payload.get("remediation", []):
        if isinstance(item, str):
            remediation.append(item)
    for check in checks:
        for item in check.get("remediation", []):
            if isinstance(item, str):
                remediation.append(item)

    payload = {
        "status": _preflight_status_for_checks(checks),
        "command": "doctor",
        "options": options,
        "checks": checks,
        "remediation": sorted(set(remediation)),
        "runtime_snapshot": status_payload,
        "message": "doctor diagnostics completed",
    }
    if payload["status"] == "ok":
        payload["message"] = "doctor found no blocking diagnostics"
    elif payload["status"] == "warn":
        payload["message"] = "doctor found warnings that may require operator attention"
    else:
        payload["message"] = "doctor found blocking diagnostics"
    return payload


def _render_doctor(payload: dict[str, object]) -> str:
    lines = [f"doctor: {payload.get('status', 'unknown')}", ""]
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        lines.append(f"{check.get('name', 'check')}: {check.get('status', 'unknown')} - {check.get('message', '')}")
    remediation = [item for item in payload.get("remediation", []) if isinstance(item, str)]
    if remediation:
        lines.extend(["", "remediation:"])
        lines.extend(f"- {item}" for item in remediation)
    return "\n".join(lines) + "\n"


def _render_status(payload: dict[str, object]) -> str:
    freshness = payload.get("freshness", {})
    sync = freshness.get("sync", {})
    certificates = freshness.get("certificates", {})
    drift = payload.get("drift", {})
    verification = payload.get("verification", {})
    integrity = payload.get("integrity", {})
    runtime = payload.get("runtime", {})
    issues = payload.get("issues", [])
    status = payload.get("status", "unknown")
    lock = runtime.get("lock", {})
    lines = [f"status: {status}", ""]
    lines.append(
        f"sync: {sync.get('state')} (run={sync.get('run_id') or 'none'}, age={sync.get('age_human', 'unknown')})"
    )
    lines.append(
        f"verification: {verification.get('state')} "
        f"(status={verification.get('status')}, age={verification.get('age_human', 'unknown')})"
    )
    lines.append(
        f"certificates: {certificates.get('state')} "
        f"(count={certificates.get('count')}, latest={certificates.get('newest') or 'none'})"
    )
    lines.append(f"drift: {drift.get('state')}")
    lines.append(f"integrity: {integrity.get('state')}")
    for check in drift.get("checks", []):
        check_state = check.get("status")
        if str(check_state) == "ok":
            continue
        lines.append(f"- drift [{check.get('type')}]: {check.get('message')}")
    lines.append(f"runtime: status={runtime.get('status')}, lock={lock.get('status')}")
    if runtime.get("pending"):
        source = runtime.get("pending_source") or "pending file"
        lines.append(f"pending: true ({source})")
    else:
        lines.append("pending: false")
    if issues:
        lines.append("")
        lines.append("issues:")
        for issue in issues:
            lines.append(f"- [{issue.get('type')}] {issue.get('message')}")
    return "\n".join(lines) + "\n"


def _render_verify(payload: dict[str, object]) -> str:
    lines = [f"verify: {payload.get('status', 'unknown')}", ""]
    changed_only = bool(payload.get("changed_only"))
    lines.append(f"scope: {'changed files only' if changed_only else 'all capsules'}")

    run_id = payload.get("run_id")
    if isinstance(run_id, str):
        lines.append(f"run_id: {run_id}")

    verified_capsules = payload.get("verified_capsules", [])
    if isinstance(verified_capsules, list):
        if verified_capsules:
            lines.append(f"verified capsules ({len(verified_capsules)}): {', '.join(sorted(verified_capsules))}")
        else:
            lines.append("verified capsules: none")

    oracle_count = payload.get("oracle_count")
    if isinstance(oracle_count, int):
        lines.append(f"oracles checked: {oracle_count}")

    certificate_refs = payload.get("certificate_refs", [])
    if isinstance(certificate_refs, list):
        lines.append(f"certificates written: {len(certificate_refs)}")

    failed_capsules = payload.get("failed_capsules", [])
    if isinstance(failed_capsules, list) and failed_capsules:
        lines.append(f"failed capsules: {', '.join(sorted(failed_capsules))}")
    else:
        lines.append("failed capsules: none")

    export_step = _recorded_export_step(payload)
    if isinstance(export_step, dict):
        updated_exports = export_step.get("updated_exports", [])
        unchanged_exports = export_step.get("unchanged_exports", [])
        if isinstance(updated_exports, list) and isinstance(unchanged_exports, list):
            lines.append(f"exports refreshed: {len(updated_exports)} updated, {len(unchanged_exports)} unchanged")

    errors = payload.get("errors", [])
    if errors:
        lines.append("")
        lines.append("errors:")
        for item in errors:
            if isinstance(item, str):
                lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def _render_drift(payload: dict[str, object]) -> str:
    drift = payload.get("drift", {})
    checks = drift.get("checks", [])
    state = drift.get("state", payload.get("status", "unknown"))
    lines = [f"drift: {state}", ""]
    for check in checks:
        lines.append(f"- [{check.get('type')}] {check.get('status')} — {check.get('message')}")
    for item in drift.get("remediation", []):
        if isinstance(item, str):
            lines.append(f"remediation: {item}")
    return "\n".join(lines) + "\n"


def _render_explain(payload: dict[str, object]) -> str:
    claims = payload.get("claims", [])
    certificates = payload.get("certificates", [])
    deltas = payload.get("deltas", [])
    errors = payload.get("errors", [])
    filters = payload.get("filters", {})
    status = payload.get("status", "ok")
    lines = [f"explain: {status}", ""]

    rendered_filters = [
        f"{key}={','.join(value)}" for key, value in filters.items() if isinstance(value, list) and value
    ]
    if rendered_filters:
        lines.append("filters: " + " ".join(rendered_filters))

    if payload.get("target_capsules"):
        target_capsules = payload.get("target_capsules")
        if isinstance(target_capsules, list) and target_capsules:
            lines.append("target capsules: " + ", ".join(target_capsules))

    if not claims and not certificates and not deltas:
        lines.append(payload.get("message", "No explain artifacts found."))
        if errors:
            lines.append("errors:")
            for error in errors:
                if isinstance(error, str):
                    lines.append(f"- {error}")
        return "\n".join(lines) + "\n"

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or "")
        capsule_id = str(claim.get("capsule_id") or "default")
        lines.append(f"- claim {claim_id} [capsule={capsule_id}]")
        text = str(claim.get("text") or "").strip()
        if text:
            lines.append(f"  text: {text}")
        category = str(claim.get("category") or "behavior")
        lines.append(f"  category: {category}")
        if claim.get("path"):
            lines.append(f"  path: {claim['path']}")

        linked_decisions = claim.get("linked_decisions", [])
        if linked_decisions:
            lines.append("  decisions:")
            for decision in linked_decisions:
                if not isinstance(decision, dict):
                    continue
                lines.append(
                    f"    - {decision.get('id')} "
                    f"({decision.get('status')}, capsule={decision.get('capsule_id')})"
                )
                statement = str(decision.get("statement") or "").strip()
                if statement:
                    lines.append(f"      statement: {statement}")
                evidence_refs = decision.get("evidence_refs")
                if isinstance(evidence_refs, list) and evidence_refs:
                    lines.append("      evidence refs:")
                    for item in evidence_refs:
                        lines.append(f"      - {item}")

        linked_certificates = claim.get("linked_certificates", [])
        if linked_certificates:
            lines.append("  certificates:")
            for certificate in linked_certificates:
                if not isinstance(certificate, dict):
                    continue
                lines.append(
                    f"    - {certificate.get('id')} "
                    f"({certificate.get('status')}, capsule={certificate.get('capsule_id')})"
                )
                if certificate.get("path"):
                    lines.append(f"      path: {certificate['path']}")

        claim_deltas = claim.get("deltas", [])
        if claim_deltas:
            lines.append("  deltas:")
            for delta in claim_deltas:
                if not isinstance(delta, dict):
                    continue
                lines.append(
                    f"    - {delta.get('capsule_id')}: {delta.get('status')} (run_id={delta.get('run_id')})"
                )
                changed_files = delta.get("changed_files")
                if isinstance(changed_files, list) and changed_files:
                    lines.append("      changed files:")
                    for item in changed_files:
                        lines.append(f"      - {item}")

    if certificates:
        lines.append("certificates:")
        for certificate in certificates:
            if not isinstance(certificate, dict):
                continue
            lines.append(
                f"- {certificate.get('id')} (capsule={certificate.get('capsule_id')}, status={certificate.get('status')})"
            )
            if certificate.get("path"):
                lines.append(f"  path: {certificate['path']}")

    if deltas:
        lines.append("latest sync deltas:")
        for delta in deltas:
            if not isinstance(delta, dict):
                continue
            lines.append(
                f"- {delta.get('capsule_id')}: {delta.get('status')} (run_id={delta.get('run_id')})"
            )

    if errors:
        lines.append("errors:")
        for error in errors:
            if isinstance(error, str):
                lines.append(f"- {error}")

    return "\n".join(lines) + "\n"

def _write_json_file(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        serialized = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True)
        handle.write(serialized)
        handle.write("\n")
    os.replace(tmp, path)


def _expected_canonical_artifact_type(relative_path: str) -> str | None:
    normalized = relative_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized == f"{OG_ROOT}/materials.lock":
        return "materials_lock"
    if not normalized.startswith(f"{OG_ROOT}/"):
        return None
    normalized = normalized[len(f"{OG_ROOT}/") :]
    scope = normalized.split("/", 1)[0]
    if not scope:
        return None
    return CANONICAL_PATH_ARTIFACT_TYPES.get(scope)


def _validate_canonical_payload(
    path: str,
    payload: dict,
    *,
    expected_artifact_type: str | None = None,
) -> dict[str, object]:
    schema_version = payload.get("schema_version")
    if schema_version != 2:
        raise ValueError(
            f"{path}: unsupported schema_version {schema_version!r}; expected 2"
        )

    artifact_type = payload.get("artifact_type")
    if not isinstance(artifact_type, str):
        raise ValueError(f"{path}: missing artifact_type")
    artifact_type = artifact_type.strip()
    if not artifact_type:
        raise ValueError(f"{path}: missing artifact_type")
    if artifact_type not in CANONICAL_ARTIFACT_TYPES:
        raise ValueError(f"{path}: unsupported artifact_type '{artifact_type}'")

    expected = expected_artifact_type or _expected_canonical_artifact_type(path)
    if expected is not None and artifact_type != expected:
        raise ValueError(
            f"{path}: unexpected artifact_type '{artifact_type}', expected '{expected}' for this canonical path"
        )

    return payload


def _read_canonical_artifact_payload(
    repo_root: str,
    relative_path: str,
    *,
    expected_artifact_type: str | None = None,
) -> dict[str, object]:
    full_path = os.path.join(repo_root, relative_path)
    payload = _read_json_file(full_path)
    if payload is None:
        raise ValueError(f"{relative_path}: file is not valid JSON")
    return _validate_canonical_payload(
        relative_path,
        payload,
        expected_artifact_type=expected_artifact_type,
    )


def _write_canonical_artifact(
    repo_root: str,
    relative_path: str,
    payload: dict[str, object],
) -> None:
    full_path = os.path.join(repo_root, relative_path)
    validated = _validate_canonical_payload(
        relative_path,
        payload,
        expected_artifact_type=_expected_canonical_artifact_type(relative_path),
    )
    _write_json_file(full_path, validated)


def _compute_payload_hash(payload: dict[str, object]) -> str:
    normalized = {k: payload.get(k) for k in sorted(payload) if k != "event_hash"}
    body = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _content_sha256(body)


def _build_integrity_state_payload(created_at: str, latest_event_id: str | None, latest_event_hash: str | None, latest_sequence: int) -> dict[str, object]:
    return {
        "schema_version": 2,
        "artifact_type": "integrity_state",
        "updated_at": created_at,
        "latest_event_id": latest_event_id,
        "latest_event_hash": latest_event_hash,
        "latest_event_sequence": latest_sequence,
    }


def _read_integrity_state(repo_root: str) -> dict[str, object]:
    path = os.path.join(repo_root, INTEGRITY_STATE_FILE)
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        return _build_integrity_state_payload(_utc_timestamp(), None, None, 0)
    if payload.get("schema_version") != 2:
        return _build_integrity_state_payload(_utc_timestamp(), None, None, 0)
    if not isinstance(payload.get("latest_event_sequence"), int):
        payload["latest_event_sequence"] = 0
    return payload


def _write_integrity_state(repo_root: str, payload: dict[str, object]) -> None:
    _write_json_file(os.path.join(repo_root, INTEGRITY_STATE_FILE), payload)


def _list_event_records(repo_root: str) -> list[tuple[int, str, datetime.datetime | None, dict[str, object]]]:
    events_path = os.path.join(repo_root, EVENTS_DIR)
    if not os.path.isdir(events_path):
        return []

    events: list[tuple[int, str, datetime.datetime | None, dict[str, object]]] = []
    for filename in sorted(os.listdir(events_path)):
        if not filename.endswith(".json"):
            continue
        file_path = os.path.join(events_path, filename)
        if not os.path.isfile(file_path):
            continue
        payload = _read_json_file(file_path)
        if not isinstance(payload, dict):
            continue
        event_raw_sequence = payload.get("event_sequence")
        event_sequence = event_raw_sequence if isinstance(event_raw_sequence, int) else 0
        raw_created_at = payload.get("created_at")
        created_at = _parse_utc_timestamp(raw_created_at) if isinstance(raw_created_at, str) else None
        events.append((event_sequence, filename, created_at, payload))
    events.sort(key=lambda item: (item[0], item[2] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), item[1]))
    return events


def _read_latest_integrity_checkpoint(repo_root: str) -> tuple[dict[str, object], str] | tuple[None, None]:
    checkpoint_path = os.path.join(repo_root, INTEGRITY_CHECKPOINT_DIR)
    if not os.path.isdir(checkpoint_path):
        return None, None
    candidates: list[tuple[int, str, dict[str, object]]] = []
    for filename in os.listdir(checkpoint_path):
        if not filename.endswith(".json"):
            continue
        full_path = os.path.join(checkpoint_path, filename)
        if not os.path.isfile(full_path):
            continue
        payload = _read_json_file(full_path)
        if not isinstance(payload, dict):
            continue
        raw_sequence = payload.get("end_sequence")
        sequence = raw_sequence if isinstance(raw_sequence, int) else 0
        candidates.append((sequence, filename, payload))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _, filename, payload = candidates[-1]
    return payload, os.path.join(checkpoint_path, filename)


def _collect_ledger_events_for_repair(repo_root: str) -> list[tuple[datetime.datetime | None, str, dict[str, object]]]:
    events_path = os.path.join(repo_root, EVENTS_DIR)
    if not os.path.isdir(events_path):
        return []

    records: list[tuple[datetime.datetime | None, str, dict[str, object]]] = []
    for filename in sorted(os.listdir(events_path)):
        if not filename.endswith(".json"):
            continue
        file_path = os.path.join(events_path, filename)
        if not os.path.isfile(file_path):
            continue
        payload = _read_json_file(file_path)
        if not isinstance(payload, dict):
            continue
        raw_created_at = payload.get("created_at")
        created_at = _parse_utc_timestamp(raw_created_at) if isinstance(raw_created_at, str) else None
        if created_at is None:
            try:
                created_at = datetime.datetime.fromtimestamp(
                    os.path.getmtime(file_path),
                    tz=datetime.timezone.utc,
                )
            except OSError:
                created_at = None
        artifact_type = payload.get("artifact_type")
        if artifact_type in {"integrity_checkpoint", "integrity_state"}:
            continue
        if not payload.get("id"):
            payload["id"] = os.path.splitext(filename)[0]
        if not isinstance(payload.get("id"), str):
            payload["id"] = os.path.splitext(filename)[0]
        records.append((created_at, file_path, payload))
    records.sort(key=lambda item: (item[0] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), item[1]))
    return records


def _clear_integrity_checkpoints(repo_root: str) -> None:
    checkpoint_path = os.path.join(repo_root, INTEGRITY_CHECKPOINT_DIR)
    if not os.path.isdir(checkpoint_path):
        return
    for filename in os.listdir(checkpoint_path):
        if not filename.endswith(".json"):
            continue
        full_path = os.path.join(checkpoint_path, filename)
        try:
            os.remove(full_path)
        except FileNotFoundError:
            pass


def _repair_integrity_index(repo_root: str) -> dict[str, object]:
    records = _collect_ledger_events_for_repair(repo_root)
    if not records:
        _clear_integrity_checkpoints(repo_root)
        _write_integrity_state(repo_root, _build_integrity_state_payload(_utc_timestamp(), None, None, 0))
        return {
            "status": "ok",
            "message": "integrity state rebuilt from empty ledger",
            "event_count": 0,
            "event_sequence": 0,
        }

    previous_hash: str | None = None
    latest_event_id = None
    latest_event_hash = None
    rebuilt = 0
    _clear_integrity_checkpoints(repo_root)

    for _, file_path, payload in records:
        event_payload = dict(payload)
        event_payload.pop("event_hash", None)
        event_payload["event_sequence"] = rebuilt + 1
        event_payload["previous_event_hash"] = previous_hash
        event_payload["event_hash"] = _compute_payload_hash({k: v for k, v in event_payload.items() if k != "event_hash"})
        _write_json_file(file_path, event_payload)
        previous_hash = str(event_payload["event_hash"])
        rebuilt += 1
        latest_event_id = event_payload.get("id")
        latest_event_hash = previous_hash

        if rebuilt % INTEGRITY_CHECKPOINT_INTERVAL == 0 and latest_event_id is not None and latest_event_hash is not None:
            _write_integrity_checkpoint(
                repo_root,
                rebuilt,
                str(latest_event_id),
                latest_event_hash,
                event_payload.get("previous_event_hash"),
            )

    _write_integrity_state(
        repo_root,
        _build_integrity_state_payload(_utc_timestamp(), latest_event_id, latest_event_hash, rebuilt),
    )
    return {
        "status": "ok",
        "message": f"integrity index rebuilt from {rebuilt} ledger event(s)",
        "event_count": rebuilt,
        "event_sequence": rebuilt,
    }


def _sign_integrity_checkpoint(repo_root: str, payload: dict[str, object]) -> dict[str, object] | None:
    signer = os.environ.get(INTEGRITY_SIGNER_ENV)
    if not signer:
        return None
    try:
        command = shlex.split(signer)
    except ValueError as exc:
        return {
            "status": "error",
            "command": signer,
            "message": f"invalid signer command: {exc}",
        }
    try:
        payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        proc = subprocess.run(
            command,
            input=payload_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception as exc:
        return {
            "status": "error",
            "command": signer,
            "message": f"signature command failed: {exc}",
        }
    if proc.returncode != 0:
        return {
            "status": "error",
            "command": signer,
            "return_code": proc.returncode,
            "message": proc.stderr.strip() or "signature command exited unsuccessfully",
        }
    signature = (proc.stdout or "").strip()
    if not signature:
        return {"status": "error", "command": signer, "message": "signature command returned empty output"}
    return {
        "status": "signed",
        "command": signer,
        "value": signature,
    }


def _write_integrity_checkpoint(
    repo_root: str,
    end_sequence: int,
    event_id: str,
    event_hash: str,
    previous_hash: str | None,
) -> str:
    path = os.path.join(repo_root, INTEGRITY_CHECKPOINT_DIR)
    os.makedirs(path, exist_ok=True)
    now = _utc_timestamp()
    payload: dict[str, object] = {
        "schema_version": 2,
        "artifact_type": "integrity_checkpoint",
        "id": f"checkpoint-{end_sequence:08d}",
        "created_at": now,
        "end_sequence": end_sequence,
        "end_event_id": event_id,
        "end_event_hash": event_hash,
        "previous_event_hash": previous_hash,
    }
    payload["checkpoint_hash"] = _compute_payload_hash(payload)
    signature = _sign_integrity_checkpoint(repo_root, payload)
    if signature is not None:
        payload["signature"] = signature
    checksum_path = os.path.join(path, f"{payload['id']}.json")
    _write_json_file(checksum_path, payload)
    return checksum_path


def _append_ledger_event(repo_root: str, payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    if not isinstance(payload, dict):
        raise TypeError("event payload must be a dict")
    event_id = payload.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event payload missing id")

    state = _read_integrity_state(repo_root)
    latest_sequence = int(state.get("latest_event_sequence", 0) or 0)
    latest_hash = state.get("latest_event_hash")
    if latest_hash is not None and not isinstance(latest_hash, str):
        latest_hash = None

    payload = dict(payload)
    payload["event_sequence"] = latest_sequence + 1
    payload["previous_event_hash"] = latest_hash
    payload["event_hash"] = _compute_payload_hash(payload)
    path = os.path.join(repo_root, EVENTS_DIR, f"{event_id}.json")
    _write_json_file(path, payload)

    state_payload = _build_integrity_state_payload(
        _utc_timestamp(),
        str(event_id),
        str(payload["event_hash"]),
        int(payload["event_sequence"]),
    )
    _write_integrity_state(repo_root, state_payload)

    if int(payload["event_sequence"]) % INTEGRITY_CHECKPOINT_INTERVAL == 0:
        event_hash = str(payload["event_hash"])
        _write_integrity_checkpoint(
            repo_root,
            int(payload["event_sequence"]),
            event_id,
            event_hash,
            latest_hash,
        )
    return path, payload


def _validate_event_chain(repo_root: str) -> dict[str, object]:
    events = _list_event_records(repo_root)
    if not events:
        return {
            "status": "ok",
            "state": "ok",
            "message": "integrity ledger has no events yet",
            "event_count": 0,
            "valid": True,
            "event_sequence": 0,
            "event_hash": None,
        }

    checkpoint, _ = _read_latest_integrity_checkpoint(repo_root)
    expected_sequence = int(checkpoint.get("end_sequence", 0) if isinstance(checkpoint, dict) else 0)
    checkpoint_available = isinstance(checkpoint, dict)
    previous_hash = checkpoint.get("end_event_hash") if isinstance(checkpoint, dict) else None
    previous_hash = previous_hash if isinstance(previous_hash, str) else None

    expected_next = expected_sequence + 1
    total = expected_sequence
    for raw_sequence, _, _, event in events:
        event_sequence = raw_sequence
        if event_sequence == 0:
            continue
        if event_sequence <= expected_sequence:
            if not checkpoint_available:
                return {
                    "status": "degraded",
                    "state": "degraded",
                    "valid": False,
                    "message": f"integrity duplicate/ordered event sequence #{event_sequence}",
                    "event_count": total,
                }
            continue
        if event_sequence != expected_next:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"integrity sequence gap detected at event #{event_sequence}",
                "event_count": total,
            }
        if "event_hash" not in event:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"integrity checksum missing for event #{event_sequence}",
                "event_count": total,
            }
        payload = dict(event)
        if payload.get("artifact_type") in {"integrity_checkpoint", "integrity_state"}:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"unexpected artifact type in ledger at event #{event_sequence}",
                "event_count": total,
            }
        actual_previous_hash = payload.get("previous_event_hash")
        if expected_sequence == 0 and actual_previous_hash is not None:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": "integrity genesis event has unexpected previous hash",
                "event_count": total,
            }
        if previous_hash is not None and actual_previous_hash != previous_hash:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"integrity link break at event #{event_sequence}",
                "event_count": total,
            }
        stored_hash = str(payload.get("event_hash"))
        computed = _compute_payload_hash({k: v for k, v in payload.items() if k != "event_hash"})
        if stored_hash != computed:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"integrity hash mismatch for event #{event_sequence}",
                "event_count": total,
            }
        expected_next += 1
        expected_sequence = event_sequence
        previous_hash = stored_hash
        total = event_sequence

    return {
        "status": "ok",
        "state": "ok",
        "valid": True,
        "message": "integrity ledger verified",
        "event_count": total,
        "event_sequence": expected_sequence,
        "event_hash": previous_hash,
    }


def _collect_integrity_state(repo_root: str) -> dict[str, object]:
    result = _validate_event_chain(repo_root)
    event_count = result.get("event_count")
    return {
        "state": "degraded" if result.get("status") != "ok" else "ok",
        "status": result.get("status"),
        "message": result.get("message"),
        "valid": bool(result.get("valid")),
        "event_count": event_count,
        "event_sequence": result.get("event_sequence"),
        "event_hash": result.get("event_hash"),
        "checkpoint": _read_latest_integrity_checkpoint(repo_root)[0],
    }


def _write_file_if_missing(path: str, content: str) -> bool:
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return True


def _write_text_file_if_changed(path: str, content: str) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    try:
        with open(path, "r", encoding="utf-8") as existing:
            existing_payload = existing.read()
        with open(tmp, "r", encoding="utf-8") as updated:
            updated_payload = updated.read()
        if existing_payload == updated_payload:
            os.remove(tmp)
            return False
    except FileNotFoundError:
        pass
    except OSError:
        pass
    os.replace(tmp, path)
    return True


def _content_sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _short_hash(value: str, length: int = 10) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _normalize_repo_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_sync_managed_generated_path(path: str) -> bool:
    normalized = _normalize_repo_relative_path(path)
    if not normalized:
        return False
    if normalized in SYNC_GENERATED_IGNORE_PATHS:
        return True
    return any(normalized.startswith(prefix) for prefix in SYNC_GENERATED_IGNORE_PREFIXES)


def _is_worker_unavailable_error(error: str) -> bool:
    lowered = error.lower()
    return WORKER_UNAVAILABLE_ERROR in lowered or "timed out" in lowered


def _safe_slug(value: str) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    sanitized = sanitized.strip("-")
    return sanitized or "item"


def _trace_segment(value: object, *, max_length: int = TRACE_SEGMENT_MAX_LENGTH) -> str:
    if value is None:
        raw_value = "item"
    else:
        raw_value = str(value)
        if not raw_value.strip():
            raw_value = "item"
    slug = _safe_slug(raw_value)
    if len(slug) <= max_length:
        return slug
    suffix = _short_hash(slug, length=10)
    head_length = max(max_length - len(suffix) - 1, 1)
    return f"{slug[:head_length].rstrip('-')}-{suffix}"


def _build_trace_path(*segments: object) -> str:
    normalized_segments: list[str] = []
    for segment in segments:
        if segment is None:
            continue
        if isinstance(segment, str) and not segment.strip():
            continue
        normalized_segments.append(_trace_segment(segment))
    if not normalized_segments:
        normalized_segments = ["trace"]
    return f"{OG_ROOT}/traces/{'-'.join(normalized_segments)}.json"


def _reject_invalid_control_characters(raw: str, field: str) -> str:
    if any((0 <= ord(char) <= 0x1F or ord(char) == 0x7F) for char in raw):
        raise ValueError(f"{field} contains control characters")
    return raw


def _reject_malformed_percent_encoding(raw: str, field: str) -> str:
    index = 0
    while index < len(raw):
        if raw[index] != "%":
            index += 1
            continue
        if index + 2 >= len(raw):
            raise ValueError(f"{field} contains malformed percent encoding")
        segment = raw[index + 1 : index + 3]
        if any(char not in string.hexdigits for char in segment):
            raise ValueError(f"{field} contains malformed percent encoding")
        raise ValueError(f"{field} contains percent-encoded input")
    return raw


def _normalize_agent_identifier(raw: object, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be a string")
    value = raw.strip().lower()
    if not value:
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > IDENTIFIER_MAX_LENGTH:
        raise ValueError(f"{field} exceeds maximum length of {IDENTIFIER_MAX_LENGTH}")
    value = _reject_invalid_control_characters(value, field)
    value = _reject_malformed_percent_encoding(value, field)
    for char in value:
        if char not in IDENTIFIER_ALLOWED_CHARS:
            raise ValueError(f"{field} contains unsupported characters; use [a-z0-9._-]")
    if not value[0].isalnum():
        raise ValueError(f"{field} must start with a letter or digit")
    return value


def _normalize_agent_identifier_csv(raw: str, field: str) -> list[str]:
    normalized: list[str] = []
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        normalized.append(_normalize_agent_identifier(candidate, field))
    if not normalized:
        raise ValueError(f"{field} must contain at least one identifier")
    return normalized


def _normalize_repo_relative_user_path(raw: object, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{field} must be a path string")
    path = raw.strip().replace("\\", "/")
    if not path:
        raise ValueError(f"{field} must be a non-empty path")
    path = _reject_invalid_control_characters(path, field)
    path = _reject_malformed_percent_encoding(path, field)
    if os.path.isabs(path):
        raise ValueError(f"{field} must be repository-relative")
    drive, _ = os.path.splitdrive(path)
    if drive:
        raise ValueError(f"{field} contains an invalid drive prefix")
    while path.startswith("./"):
        path = path[2:]
    if path in {"", ".", ".."}:
        raise ValueError(f"{field} must be a non-empty relative path")
    parts = [part for part in path.split("/") if part]
    if not parts or any(part == ".." or part in {"", "."} for part in parts):
        raise ValueError(f"{field} contains traversal segments")
    normalized = "/".join(parts)
    normalized = os.path.normpath(normalized).replace("\\", "/")
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ValueError(f"{field} resolves outside repository root")
    return normalized


def _write_text_payload(path: str, payload: object) -> bytes:
    if isinstance(payload, str):
        rendered = payload
    else:
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    encoded = rendered.encode("utf-8")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    return encoded


def _build_file_pointer(relative_path: str, rendered: bytes, media_type: str) -> dict[str, object]:
    return {
        "schema_version": 2,
        "type": TRACKED_EVIDENCE_TAG,
        "target": relative_path,
        "hash": _content_sha256(rendered),
        "media_type": media_type,
        "size": len(rendered),
    }


def _cas_object_path(repo_root: str, content_hash: str) -> str:
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
        raise ValueError("content hash must be sha256:...")
    digest = content_hash.split(":", 1)[1]
    if len(digest) != 64:
        raise ValueError("unsupported content hash length")
    return os.path.join(repo_root, CAS_DIR, digest[:2], digest[2:])


def _store_put(repo_root: str, payload: object, media_type: str = "application/json") -> dict[str, object]:
    if isinstance(payload, bytes):
        rendered = payload
    elif isinstance(payload, str):
        rendered = payload.encode("utf-8")
    else:
        rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    content_hash = _content_sha256(rendered)
    blob_path = _cas_object_path(repo_root, content_hash)
    os.makedirs(os.path.dirname(blob_path), exist_ok=True)
    if not os.path.exists(blob_path):
        tmp = f"{blob_path}.tmp"
        with open(tmp, "wb") as handle:
            handle.write(rendered)
        os.replace(tmp, blob_path)
    return {
        "schema_version": 2,
        "type": UNTRACKED_EVIDENCE_TAG,
        "target": content_hash,
        "hash": content_hash,
        "media_type": media_type,
        "size": len(rendered),
    }


def _store_exists(repo_root: str, content_hash: str) -> bool:
    try:
        return os.path.exists(_cas_object_path(repo_root, content_hash))
    except ValueError:
        return False


def _store_get(repo_root: str, content_hash: str) -> bytes | None:
    try:
        path = _cas_object_path(repo_root, content_hash)
    except ValueError:
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _worker_receipt_pointer_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "type", "target", "hash", "media_type", "size"],
        "properties": {
            "schema_version": {"type": "integer", "const": WORKER_SCHEMA_VERSION},
            "type": {"type": "string", "enum": [TRACKED_EVIDENCE_TAG, UNTRACKED_EVIDENCE_TAG]},
            "target": {"type": "string", "minLength": 1},
            "hash": {"type": ["string", "null"]},
            "media_type": {"type": ["string", "null"]},
            "size": {"type": ["integer", "null"], "minimum": 0},
        },
    }


def _worker_oracle_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "command", "reason", "scope"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "command": {"type": ["string", "null"]},
            "reason": {"type": ["string", "null"]},
            "scope": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    }


def _worker_claim_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "capsule_id", "category", "text", "receipt_pointers", "source_paths"],
        "properties": {
            "id": {"type": ["string", "null"]},
            "capsule_id": {"type": ["string", "null"]},
            "category": {"type": "string", "minLength": 1},
            "text": {"type": "string", "minLength": 1},
            "receipt_pointers": {
                "type": "array",
                "items": _worker_receipt_pointer_schema(),
            },
            "source_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    }


def _worker_decision_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["statement", "rationale", "status"],
        "properties": {
            "statement": {"type": "string", "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
            "status": {"type": "string", "minLength": 1},
        },
    }


def _worker_lineage_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["parent_capsule_ids"],
        "properties": {
            "parent_capsule_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    }


def _worker_replay_material_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "digest", "kind", "size"],
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "digest": {"type": "string", "minLength": 1},
            "kind": {"type": ["string", "null"]},
            "size": {"type": ["integer", "null"], "minimum": 0},
        },
    }


def _worker_replay_acceptance_check_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "oracle_name", "command", "expected_signal", "reason"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "oracle_name": {"type": ["string", "null"]},
            "command": {"type": ["string", "null"]},
            "expected_signal": {"type": "string", "minLength": 1},
            "reason": {"type": ["string", "null"]},
        },
    }


def _worker_replay_equivalence_inputs_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["baseline_hash", "oracle_names", "material_paths", "notes"],
        "properties": {
            "baseline_hash": {"type": ["string", "null"]},
            "oracle_names": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "material_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "notes": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
    }


def _worker_replay_parity_results_schema() -> dict[str, object]:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": [
            "match",
            "details",
            "baseline_hash",
            "observed_hash",
            "oracle_digest",
            "trace_count",
        ],
        "properties": {
            "match": {"type": ["boolean", "null"]},
            "details": {"type": ["string", "null"]},
            "baseline_hash": {"type": ["string", "null"]},
            "observed_hash": {"type": ["string", "null"]},
            "oracle_digest": {"type": ["string", "null"]},
            "trace_count": {"type": ["integer", "null"], "minimum": 0},
        },
    }


def _build_worker_output_schema(role: str) -> dict[str, object]:
    if role == "distill":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "interface_version", "run_id", "capsule_updates"],
            "properties": {
                "schema_version": {"type": "integer", "const": WORKER_SCHEMA_VERSION},
                "interface_version": {"type": "integer", "const": WORKER_INTERFACE_VERSION},
                "run_id": {"type": "string", "minLength": 1},
                "capsule_updates": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "id",
                            "status",
                            "goal",
                            "scope",
                            "behavior_claims",
                            "constraints",
                            "invariants",
                            "dependencies",
                            "oracles",
                            "claims",
                            "decision",
                            "lineage",
                            "unknowns",
                            "errors",
                            "receipts",
                            "changed_files",
                        ],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": ["success", "ok", "warn", "error", "pending"],
                            },
                            "goal": {"type": "string", "minLength": 1},
                            "scope": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                            "behavior_claims": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                            "constraints": {"type": "array", "items": {"type": "string", "minLength": 1}},
                            "invariants": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                            "dependencies": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                            "oracles": {
                                "type": "array",
                                "minItems": 1,
                                "items": _worker_oracle_schema(),
                            },
                            "claims": {
                                "type": "array",
                                "minItems": 1,
                                "items": _worker_claim_schema(),
                            },
                            "decision": _worker_decision_schema(),
                            "lineage": _worker_lineage_schema(),
                            "unknowns": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                            "errors": {"type": "array", "items": {"type": "string", "minLength": 1}},
                            "receipts": {
                                "type": "array",
                                "items": _worker_receipt_pointer_schema(),
                            },
                            "changed_files": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        }
    if role == "replay":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "interface_version",
                "run_id",
                "capsule_id",
                "capsule_scope",
                "material_inputs",
                "steps",
                "acceptance_checks",
                "equivalence_inputs",
                "status",
                "message",
                "failures",
                "parity_results",
            ],
            "properties": {
                "schema_version": {"type": "integer", "const": WORKER_SCHEMA_VERSION},
                "interface_version": {"type": "integer", "const": WORKER_INTERFACE_VERSION},
                "run_id": {"type": "string", "minLength": 1},
                "capsule_id": {"type": "string", "minLength": 1},
                "capsule_scope": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "material_inputs": {
                    "type": "array",
                    "items": _worker_replay_material_schema(),
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["command", "expected_exit_code", "timeout_s", "cwd"],
                        "properties": {
                            "command": {"type": "string", "minLength": 1},
                            "expected_exit_code": {"type": ["integer", "null"]},
                            "timeout_s": {"type": ["integer", "null"], "minimum": 1},
                            "cwd": {"type": ["string", "null"]},
                        },
                    },
                },
                "acceptance_checks": {
                    "type": "array",
                    "items": _worker_replay_acceptance_check_schema(),
                },
                "equivalence_inputs": _worker_replay_equivalence_inputs_schema(),
                "status": {"type": "string", "minLength": 1},
                "message": {"type": "string"},
                "failures": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "parity_results": _worker_replay_parity_results_schema(),
            },
        }
    raise WorkerAdapterError(f"unsupported worker role '{role}'")


def _normalize_worker_prompt_manifest_entry(
    raw: object,
    *,
    index: int,
    manifest_dir: str,
) -> dict[str, object]:
    field = f"worker prompt manifest prompts[{index}]"
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object")
    prompt_id = _required_str(raw.get("id"), f"{field}.id")
    version = _required_str(raw.get("version"), f"{field}.version")
    role = _required_str(raw.get("role"), f"{field}.role")
    if role not in WORKER_PROMPT_BINDINGS:
        expected_roles = ", ".join(sorted(WORKER_PROMPT_BINDINGS))
        raise WorkerAdapterError(f"{field}.role must be one of: {expected_roles}")
    try:
        relative_path = _normalize_repo_relative_user_path(raw.get("path"), f"{field}.path")
    except ValueError as exc:
        raise WorkerAdapterError(str(exc)) from exc
    required_variables = _string_list(raw.get("required_variables"), f"{field}.required_variables", required=True)
    return {
        "id": prompt_id,
        "version": version,
        "role": role,
        "path": relative_path,
        "source_path": os.path.normpath(os.path.join(manifest_dir, relative_path)),
        "required_variables": required_variables,
    }


def _read_worker_prompt_template(entry: dict[str, object]) -> str:
    prompt_label = f"{entry.get('id')}@{entry.get('version')}"
    source_path = str(entry.get("source_path") or "")
    asset_path = str(entry.get("path") or source_path)
    try:
        with open(source_path, "r", encoding="utf-8") as handle:
            template = handle.read()
    except FileNotFoundError:
        raise WorkerAdapterError(f"worker prompt asset {prompt_label} is missing: {asset_path}") from None
    except OSError as exc:
        raise WorkerAdapterError(f"worker prompt asset {prompt_label} could not be read: {exc}") from exc
    if not template.strip():
        raise WorkerAdapterError(f"worker prompt asset {prompt_label} is empty")
    return template


def _validate_worker_prompt_template(entry: dict[str, object]) -> str:
    prompt_label = f"{entry.get('id')}@{entry.get('version')}"
    template = _read_worker_prompt_template(entry)
    placeholders = set(WORKER_PROMPT_VARIABLE_PATTERN.findall(template))
    required_variables = set(str(item) for item in entry.get("required_variables", []))
    missing = sorted(required_variables - placeholders)
    if missing:
        raise WorkerAdapterError(
            f"worker prompt asset {prompt_label} does not reference required variables: {', '.join(missing)}"
        )
    undeclared = sorted(placeholders - required_variables)
    if undeclared:
        raise WorkerAdapterError(f"worker prompt asset {prompt_label} uses undeclared variables: {', '.join(undeclared)}")
    return template


def _normalize_prompt_provenance(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    prompt_id = str(raw.get("id") or "").strip()
    version = str(raw.get("version") or "").strip()
    source_path = _normalize_repo_relative_path(str(raw.get("source_path") or "").strip())
    if not prompt_id or not version or not source_path:
        return None
    return {
        "id": prompt_id,
        "version": version,
        "source_path": source_path,
    }


def _build_worker_prompt_provenance(entry: dict[str, object]) -> dict[str, str]:
    source_path = str(entry.get("source_path") or "").strip()
    if source_path:
        try:
            source_path = os.path.relpath(source_path, os.path.dirname(__file__))
        except ValueError:
            source_path = str(entry.get("path") or source_path)
    else:
        source_path = str(entry.get("path") or "")
    normalized = _normalize_prompt_provenance(
        {
            "id": entry.get("id"),
            "version": entry.get("version"),
            "source_path": source_path,
        }
    )
    if normalized is None:
        raise WorkerAdapterError("worker prompt provenance is incomplete")
    return normalized


def _collect_prompt_provenance_records(raw: object) -> list[dict[str, str]]:
    discovered: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            prompt_provenance = _normalize_prompt_provenance(value.get("prompt_provenance"))
            if prompt_provenance is not None:
                key = (
                    prompt_provenance["id"],
                    prompt_provenance["version"],
                    prompt_provenance["source_path"],
                )
                if key not in seen:
                    seen.add(key)
                    discovered.append(prompt_provenance)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    visit(nested)
            return
        if isinstance(value, list):
            for nested in value:
                if isinstance(nested, (dict, list)):
                    visit(nested)

    visit(raw)
    return discovered


def _load_worker_prompt_manifest() -> dict[str, dict[str, object]]:
    try:
        with open(WORKER_PROMPT_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            raw_manifest = json.load(handle)
    except FileNotFoundError:
        raise WorkerAdapterError(f"worker prompt manifest is missing: {WORKER_PROMPT_MANIFEST_PATH}") from None
    except json.JSONDecodeError as exc:
        raise WorkerAdapterError(f"worker prompt manifest is invalid JSON: {exc.msg}") from exc
    except OSError as exc:
        raise WorkerAdapterError(f"worker prompt manifest could not be read: {exc}") from exc

    if not isinstance(raw_manifest, dict):
        raise WorkerAdapterError("worker prompt manifest must be an object")
    if raw_manifest.get("schema_version") != WORKER_PROMPT_ASSET_SCHEMA_VERSION:
        raise WorkerAdapterError("worker prompt manifest schema_version mismatch")

    raw_prompts = raw_manifest.get("prompts")
    if not isinstance(raw_prompts, list) or not raw_prompts:
        raise WorkerAdapterError("worker prompt manifest prompts must be a non-empty list")

    manifest_dir = os.path.dirname(WORKER_PROMPT_MANIFEST_PATH)
    entries_by_role: dict[str, dict[str, object]] = {}
    seen_prompt_keys: set[tuple[str, str]] = set()
    for index, raw_entry in enumerate(raw_prompts):
        entry = _normalize_worker_prompt_manifest_entry(raw_entry, index=index, manifest_dir=manifest_dir)
        prompt_key = (str(entry["id"]), str(entry["version"]))
        if prompt_key in seen_prompt_keys:
            raise WorkerAdapterError(f"worker prompt manifest duplicates prompt id/version: {prompt_key[0]}@{prompt_key[1]}")
        seen_prompt_keys.add(prompt_key)
        role = str(entry["role"])
        if role in entries_by_role:
            raise WorkerAdapterError(f"worker prompt manifest duplicates role '{role}'")
        entry["template"] = _validate_worker_prompt_template(entry)
        entries_by_role[role] = entry

    expected_roles = set(WORKER_PROMPT_BINDINGS)
    observed_roles = set(entries_by_role)
    if observed_roles != expected_roles:
        issues: list[str] = []
        missing_roles = sorted(expected_roles - observed_roles)
        unexpected_roles = sorted(observed_roles - expected_roles)
        if missing_roles:
            issues.append(f"missing roles: {', '.join(missing_roles)}")
        if unexpected_roles:
            issues.append(f"unexpected roles: {', '.join(unexpected_roles)}")
        raise WorkerAdapterError(f"worker prompt manifest roles mismatch ({'; '.join(issues)})")

    for role, binding in WORKER_PROMPT_BINDINGS.items():
        entry = entries_by_role[role]
        if str(entry.get("id")) != binding["id"]:
            raise WorkerAdapterError(f"worker prompt manifest role '{role}' must use id '{binding['id']}'")
        if str(entry.get("version")) != binding["version"]:
            raise WorkerAdapterError(f"worker prompt manifest role '{role}' must use version '{binding['version']}'")
    return entries_by_role


def _render_worker_prompt_template(entry: dict[str, object], variables: dict[str, str]) -> str:
    prompt_label = f"{entry.get('id')}@{entry.get('version')}"
    required_variables = [str(item) for item in entry.get("required_variables", [])]
    missing_variables = sorted(name for name in required_variables if name not in variables)
    if missing_variables:
        raise WorkerAdapterError(
            f"worker prompt asset {prompt_label} is missing required variables: {', '.join(missing_variables)}"
        )

    template = str(entry.get("template") or "")

    def replace_variable(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        value = variables.get(variable_name)
        if not isinstance(value, str):
            raise WorkerAdapterError(f"worker prompt asset {prompt_label} variable '{variable_name}' must be a string")
        return value

    return WORKER_PROMPT_VARIABLE_PATTERN.sub(replace_variable, template)


def _resolve_worker_prompt(role: str, payload: dict[str, object]) -> tuple[str, dict[str, str]]:
    if role not in WORKER_PROMPT_BINDINGS:
        raise WorkerAdapterError(f"unsupported worker role '{role}'")
    payload_json = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    prompt_entry = _load_worker_prompt_manifest()[role]
    return (
        _render_worker_prompt_template(prompt_entry, {"payload_json": payload_json}),
        _build_worker_prompt_provenance(prompt_entry),
    )


def _build_worker_prompt(role: str, payload: dict[str, object]) -> str:
    prompt, _ = _resolve_worker_prompt(role, payload)
    return prompt


def _extract_json_object(raw: str) -> dict[str, object] | None:
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            fenced = "\n".join(lines[1:-1]).strip()
            try:
                parsed = json.loads(fenced)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def _is_worker_contract_payload(role: str, payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != WORKER_SCHEMA_VERSION:
        return False
    if payload.get("interface_version") != WORKER_INTERFACE_VERSION:
        return False
    if role == "distill":
        return isinstance(payload.get("capsule_updates"), list)
    if role == "replay":
        capsule_id = payload.get("capsule_id")
        return isinstance(capsule_id, str) and bool(capsule_id.strip())
    return False


def _extract_worker_payload_from_event(role: str, event: dict[str, object]) -> dict[str, object] | None:
    item = event.get("item")
    if isinstance(item, dict):
        text = item.get("text")
        if isinstance(text, str):
            parsed = _extract_json_object(text)
            if parsed is not None and _is_worker_contract_payload(role, parsed):
                return parsed
        content = item.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_text = part.get("text")
                if not isinstance(part_text, str):
                    continue
                parsed = _extract_json_object(part_text)
                if parsed is not None and _is_worker_contract_payload(role, parsed):
                    return parsed
    message = event.get("message")
    if isinstance(message, str):
        parsed = _extract_json_object(message)
        if parsed is not None and _is_worker_contract_payload(role, parsed):
            return parsed
    return None


def _extract_worker_exec_error(raw_stdout: str, raw_stderr: str) -> str | None:
    for line in raw_stdout.splitlines():
        parsed = _extract_json_object(line)
        if not isinstance(parsed, dict):
            continue
        if parsed.get("type") != "error":
            continue
        message = parsed.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    stderr = raw_stderr.strip()
    if stderr:
        return stderr
    return None


def _build_worker_command_variants(entrypoint: str, schema_path: str, last_message_path: str) -> list[list[str]]:
    resolved_entrypoint = str(entrypoint).strip()
    if "://" in resolved_entrypoint:
        resolved_entrypoint = resolved_entrypoint.split("://", 1)[0]
    command_root = shlex.split(resolved_entrypoint) if resolved_entrypoint else []
    if not command_root:
        command_root = ["codex"]
    normalized = [part for part in command_root if part]
    if not normalized:
        normalized = ["codex"]
    command_prefix = [
        *normalized,
        "exec",
        "--json",
        "--sandbox",
        "read-only",
    ]
    override_model = os.environ.get(WORKER_MODEL_OVERRIDE_ENV, "").strip()
    if override_model:
        command_prefix.extend(["--model", override_model])
    return [
        [
            *command_prefix,
            "--output-schema",
            schema_path,
            "--output-last-message",
            last_message_path,
            "-",
        ]
    ]


def _run_codex_worker(
    role: str,
    payload: dict[str, object],
    repo_root: str,
    trace_path: str,
    adapter: dict[str, object] | None = None,
    timeout_seconds: int = WORKER_ADAPTER_DEFAULT_TIMEOUT_SECONDS,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = (adapter or {}).get("manifest") if isinstance(adapter, dict) else _build_worker_manifest()
    if not isinstance(manifest, dict):
        manifest = _build_worker_manifest()
    if manifest.get("schema_version") != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError("worker manifest schema mismatch")
    if manifest.get("interface_version") != WORKER_INTERFACE_VERSION:
        raise WorkerAdapterError("worker interface version mismatch")
    entrypoint = manifest.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise WorkerAdapterError("worker manifest entrypoint missing")

    worker_prompt, prompt_provenance = _resolve_worker_prompt(role, payload)
    worker_schema = _build_worker_output_schema(role)
    last_error = "codex executable was not found"
    output = ""
    candidate_output = ""
    error_output = ""
    parsed: dict[str, object] | None = None
    selected_command: list[str] = []
    duration_ms = 0
    try:
        runtime_defaults = _load_runtime_defaults(repo_root)
    except ValueError as exc:
        raise WorkerAdapterError(f"invalid runtime defaults: {exc}") from exc
    worker_env = os.environ.copy()
    codex_home = runtime_defaults.get("codex_home_path")
    if isinstance(codex_home, str) and codex_home.strip():
        worker_env[CODEX_HOME_ENV] = codex_home

    with tempfile.TemporaryDirectory(prefix="og-worker-") as temp_dir:
        schema_path = os.path.join(temp_dir, f"{role}-schema.json")
        last_message_path = os.path.join(temp_dir, f"{role}-last-message.json")
        _write_text_payload(schema_path, json.dumps(worker_schema, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
        command_variants = _build_worker_command_variants(
            str(entrypoint),
            schema_path,
            last_message_path,
        )
        command = command_variants[0]
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                input=worker_prompt,
                text=True,
                capture_output=True,
                cwd=repo_root,
                timeout=timeout_seconds,
                env=worker_env,
            )
        except FileNotFoundError:
            raise WorkerAdapterError("codex executable was not found") from None
        except subprocess.TimeoutExpired as exc:
            raise WorkerAdapterError(f"codex exec timed out after {timeout_seconds}s ({role})") from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        output = proc.stdout or ""
        error_output = proc.stderr or ""
        if proc.returncode != 0:
            worker_error = _extract_worker_exec_error(output, error_output)
            if worker_error:
                last_error = f"codex exec failed for {role}: {worker_error}"
            else:
                last_error = f"codex exec failed for {role}: rc={proc.returncode}"
            raise WorkerAdapterError(last_error)

        if os.path.exists(last_message_path):
            try:
                with open(last_message_path, "r", encoding="utf-8") as handle:
                    candidate_output = handle.read()
            except OSError:
                candidate_output = ""
        if not candidate_output.strip():
            candidate_output = output
        parsed_output = _parse_worker_output(role, candidate_output)
        result_payload = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "role": role,
            "adapter": manifest.get("name"),
            "command": command,
            "duration_ms": duration_ms,
            "prompt_provenance": prompt_provenance,
            "configuration": {
                "codex_home": runtime_defaults.get("codex_home"),
                "resolved_from": cast(dict[str, str], runtime_defaults.get("resolved_from") or {}).get("codex_home"),
            },
            "output": parsed_output,
        }
        parsed = {
            **parsed_output,
            "prompt_provenance": prompt_provenance,
        }
        selected_command = command

    trace_base = trace_path.rsplit(".", 1)[0] if "." in trace_path else trace_path
    trace_input_path = f"{trace_base}-input.json"
    trace_result_path = f"{trace_base}-result.json"
    request_payload = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "role": role,
        "adapter": manifest.get("name"),
        "command": selected_command,
        "duration_ms": duration_ms,
        "configuration": {
            "codex_home": runtime_defaults.get("codex_home"),
            "resolved_from": cast(dict[str, str], runtime_defaults.get("resolved_from") or {}).get("codex_home"),
        },
        "input": payload,
        "prompt": worker_prompt,
        "prompt_provenance": prompt_provenance,
    }
    request_text = json.dumps(request_payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    request_bytes = request_text.encode("utf-8")
    output_bytes = output.encode("utf-8")
    result_text = json.dumps(result_payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    result_bytes = result_text.encode("utf-8")
    _write_text_payload(os.path.join(repo_root, trace_input_path), request_text)
    _write_text_payload(os.path.join(repo_root, trace_path), output)
    _write_text_payload(os.path.join(repo_root, trace_result_path), result_text)
    return parsed, [
        _build_file_pointer(trace_input_path, request_bytes, "application/json"),
        _store_put(repo_root, request_bytes, "application/json"),
        _build_file_pointer(trace_path, output_bytes, "application/x-ndjson"),
        _store_put(repo_root, output_bytes, "application/x-ndjson"),
        _build_file_pointer(trace_result_path, result_bytes, "application/json"),
        _store_put(repo_root, result_bytes, "application/json"),
    ]


def _parse_worker_output(role: str, raw: str) -> dict[str, object]:
    if raw is None or not raw.strip():
        raise WorkerAdapterError(f"codex output for {role} is empty")

    parsed_payload: dict[str, object] | None = None
    saw_json = False
    for line in raw.splitlines():
        parsed_line = _extract_json_object(line)
        if parsed_line is None:
            continue
        saw_json = True
        if _is_worker_contract_payload(role, parsed_line):
            parsed_payload = parsed_line
            continue
        nested_payload = _extract_worker_payload_from_event(role, parsed_line)
        if nested_payload is not None:
            parsed_payload = nested_payload

    if parsed_payload is not None:
        return parsed_payload

    parsed = _extract_json_object(raw)
    if parsed is not None:
        if _is_worker_contract_payload(role, parsed):
            return parsed
        nested_payload = _extract_worker_payload_from_event(role, parsed)
        if nested_payload is not None:
            return nested_payload
        saw_json = True

    if saw_json:
        raise WorkerAdapterError(f"codex output for {role} did not include a worker contract payload")
    raise WorkerAdapterError(f"codex output for {role} is not valid JSON")


def _normalize_receipt_pointer(raw: object, *, field: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object")
    schema_version = raw.get("schema_version")
    if schema_version != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError(f"{field} schema_version mismatch")
    pointer_type = raw.get("type")
    if pointer_type not in {TRACKED_EVIDENCE_TAG, UNTRACKED_EVIDENCE_TAG}:
        raise WorkerAdapterError(f"{field}.type must be file or cas")
    target = _required_str(raw.get("target"), f"{field}.target")
    normalized: dict[str, object] = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "type": pointer_type,
        "target": target,
    }
    value_hash = raw.get("hash")
    if isinstance(value_hash, str) and value_hash:
        normalized["hash"] = value_hash
    media_type = raw.get("media_type")
    if isinstance(media_type, str) and media_type:
        normalized["media_type"] = media_type
    size = raw.get("size")
    if isinstance(size, int):
        normalized["size"] = size
    return normalized


def _normalize_receipt_pointer_signature(pointer: dict[str, object]) -> str:
    normalized = {
        "schema_version": pointer.get("schema_version"),
        "type": pointer.get("type"),
        "target": pointer.get("target"),
        "hash": pointer.get("hash"),
        "media_type": pointer.get("media_type"),
        "size": pointer.get("size"),
    }
    return json.dumps(normalized, sort_keys=True, default=str)


def _deduplicate_receipt_pointers(receipt_pointers: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    seen_receipts: list[dict[str, object]] = []
    for pointer in sorted(receipt_pointers, key=lambda item: json.dumps(item, sort_keys=True, default=str)):
        if not isinstance(pointer, dict):
            continue
        signature = _normalize_receipt_pointer_signature(pointer)
        if signature in seen:
            continue
        seen.add(signature)
        seen_receipts.append(pointer)
    return seen_receipts


def _build_claim_fallback_receipt_pointer(claim_id: str) -> dict[str, object]:
    safe_claim_id = _safe_slug(claim_id)
    target = f"{OG_ROOT}/claims/{safe_claim_id}.json"
    return {
        "schema_version": WORKER_SCHEMA_VERSION,
        "type": TRACKED_EVIDENCE_TAG,
        "target": target,
    }


def _normalize_receipt_pointers(raw: object, *, field: str, required: bool = False) -> list[dict[str, object]]:
    if raw is None:
        if required:
            raise WorkerAdapterError(f"{field} is required")
        return []
    if not isinstance(raw, list):
        raise WorkerAdapterError(f"{field} must be a list")
    pointers = _deduplicate_receipt_pointers(
        [_normalize_receipt_pointer(pointer, field=f"{field}[{index}]") for index, pointer in enumerate(raw)]
    )
    if required and not pointers:
        raise WorkerAdapterError(f"{field} must include at least one pointer")
    return pointers


def _normalize_claim_payloads(
    raw: object,
    *,
    field: str,
    default_capsule_id: str | None = None,
    require_receipts: bool = False,
) -> list[dict[str, object]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise WorkerAdapterError(f"{field} must be a list")
    claims: list[dict[str, object]] = []
    for index, raw_claim in enumerate(raw):
        if not isinstance(raw_claim, dict):
            raise WorkerAdapterError(f"{field}[{index}] must be an object")
        claim_id = str(raw_claim.get("id") or "").strip()
        if not claim_id:
            claim_id = f"cl-{_short_hash(f'{field}:{index}', 10)}"
        raw_capsule_id = raw_claim.get("capsule_id")
        if raw_capsule_id is None and default_capsule_id is not None:
            capsule_id = default_capsule_id
        else:
            capsule_id = _required_str(raw_capsule_id, f"{field}[{index}].capsule_id")
        claim_receipts = _normalize_receipt_pointers(
            raw_claim.get("receipt_pointers"),
            field=f"{field}[{index}].receipt_pointers",
            required=require_receipts,
        )
        normalized_claim = {
            "id": claim_id,
            "capsule_id": capsule_id,
            "category": str(raw_claim.get("category") or "behavior").strip() or "behavior",
            "text": str(raw_claim.get("text") or "Claim derived from distill adapter output.").strip(),
            "receipt_pointers": claim_receipts,
        }
        source_paths = _safe_string_list(raw_claim.get("source_paths"))
        if source_paths:
            normalized_claim["source_paths"] = source_paths
        claims.append(normalized_claim)
    return claims


def _normalize_distill_oracles(raw: object, *, field: str) -> list[dict[str, object]]:
    if not isinstance(raw, list) or not raw:
        raise WorkerAdapterError(f"{field} must include at least one oracle")
    normalized: list[dict[str, object]] = []
    for index, raw_oracle in enumerate(raw):
        if not isinstance(raw_oracle, dict):
            raise WorkerAdapterError(f"{field}[{index}] must be an object")
        name = _required_str(raw_oracle.get("name"), f"{field}[{index}].name")
        raw_command = raw_oracle.get("command")
        if raw_command is None:
            command_value = None
        else:
            command_value = _required_str(raw_command, f"{field}[{index}].command")
        raw_reason = raw_oracle.get("reason")
        if raw_reason is None:
            reason_value = None
        else:
            reason_value = _required_str(raw_reason, f"{field}[{index}].reason")
        if command_value is None and reason_value is None:
            raise WorkerAdapterError(f"{field}[{index}].reason is required when command is null")
        normalized.append(
            {
                "name": name,
                "command": command_value,
                **({"reason": reason_value} if reason_value is not None else {}),
                "scope": _safe_string_list(raw_oracle.get("scope")),
            }
        )
    return normalized


def _normalize_distill_decision(raw: object, *, field: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object")
    return {
        "statement": _required_str(raw.get("statement"), f"{field}.statement"),
        "rationale": _required_str(raw.get("rationale"), f"{field}.rationale"),
        "status": _required_str(raw.get("status"), f"{field}.status"),
    }


def _normalize_distill_lineage(raw: object, *, field: str) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object")
    parent_capsule_ids = _safe_string_list(raw.get("parent_capsule_ids"))
    if not parent_capsule_ids:
        return {}
    return {"parent_capsule_ids": parent_capsule_ids}


def _normalize_distill_delta(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError("distill output must be an object")
    if raw.get("schema_version") != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError("distill output schema_version must be 2")
    if raw.get("interface_version") != WORKER_INTERFACE_VERSION:
        raise WorkerAdapterError("distill output interface_version mismatch")
    run_id = _required_str(raw.get("run_id"), "run_id")
    updates_raw = raw.get("capsule_updates")
    if not isinstance(updates_raw, list) or not updates_raw:
        raise WorkerAdapterError("distill output must include non-empty capsule_updates")
    updates: list[dict[str, object]] = []
    for index, raw_update in enumerate(updates_raw):
        if not isinstance(raw_update, dict):
            raise WorkerAdapterError(f"capsule_updates[{index}] must be an object")
        raw_id = raw_update.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raw_id = raw_update.get("capsule_id")
        normalized_claims = _normalize_claim_payloads(
            raw_update.get("claims"),
            field=f"capsule_updates[{index}].claims",
            default_capsule_id=_required_str(raw_id, f"capsule_updates[{index}].id"),
            require_receipts=False,
        )
        if not any(
            str(claim.get("category") or "").strip().lower() == "behavior" and str(claim.get("text") or "").strip()
            for claim in normalized_claims
        ):
            raise WorkerAdapterError(f"capsule_updates[{index}].claims must include at least one behavior claim")
        updates.append(
            {
                "id": _required_str(raw_id, f"capsule_updates[{index}].id"),
                "status": str(raw_update.get("status") or "success"),
                "goal": _required_str(raw_update.get("goal"), f"capsule_updates[{index}].goal"),
                "scope": _string_list(
                    raw_update.get("scope"),
                    f"capsule_updates[{index}].scope",
                    required=True,
                ),
                "behavior_claims": _string_list(
                    raw_update.get("behavior_claims"),
                    f"capsule_updates[{index}].behavior_claims",
                    required=True,
                ),
                "constraints": _safe_string_list(raw_update.get("constraints")),
                "invariants": _string_list(
                    raw_update.get("invariants"),
                    f"capsule_updates[{index}].invariants",
                    required=True,
                ),
                "dependencies": _string_list(
                    raw_update.get("dependencies"),
                    f"capsule_updates[{index}].dependencies",
                    required=True,
                ),
                "oracles": _normalize_distill_oracles(
                    raw_update.get("oracles"),
                    field=f"capsule_updates[{index}].oracles",
                ),
                "claims": normalized_claims,
                "decision": _normalize_distill_decision(
                    raw_update.get("decision"),
                    field=f"capsule_updates[{index}].decision",
                ),
                "lineage": _normalize_distill_lineage(
                    raw_update.get("lineage"),
                    field=f"capsule_updates[{index}].lineage",
                ),
                "unknowns": _string_list(
                    raw_update.get("unknowns"),
                    f"capsule_updates[{index}].unknowns",
                    required=True,
                ),
                "errors": _string_list(
                    raw_update.get("errors"),
                    f"capsule_updates[{index}].errors",
                ),
                "receipts": _normalize_receipt_pointers(
                    raw_update.get("receipts"),
                    field=f"capsule_updates[{index}].receipts",
                ),
                "changed_files": _string_list(
                    raw_update.get("changed_files"),
                    f"capsule_updates[{index}].changed_files",
                ),
            }
        )
    return {
        "schema_version": WORKER_SCHEMA_VERSION,
        "interface_version": WORKER_INTERFACE_VERSION,
        "run_id": run_id,
        "capsule_updates": updates,
    }


def _normalize_replay_material_inputs(raw: object, *, field: str) -> list[dict[str, object]]:
    if raw is None:
        raise WorkerAdapterError(f"{field} must be present and be a list")
    if not isinstance(raw, list):
        raise WorkerAdapterError(f"{field} must be a list")

    materials: list[dict[str, object]] = []
    for index, raw_material in enumerate(raw):
        if not isinstance(raw_material, dict):
            raise WorkerAdapterError(f"{field}[{index}] must be an object")
        path = _normalize_repo_relative_path(_required_str(raw_material.get("path"), f"{field}[{index}].path"))
        if not path:
            raise WorkerAdapterError(f"{field}[{index}].path must be a non-empty repository-relative path")
        digest = _required_str(raw_material.get("digest"), f"{field}[{index}].digest")
        material: dict[str, object] = {
            "path": path,
            "digest": digest,
        }
        kind = raw_material.get("kind")
        if kind is None:
            material["kind"] = None
        elif isinstance(kind, str):
            material["kind"] = kind.strip() or None
        else:
            raise WorkerAdapterError(f"{field}[{index}].kind must be a string or null")
        size = raw_material.get("size")
        if size is None:
            material["size"] = None
        elif isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise WorkerAdapterError(f"{field}[{index}].size must be a non-negative integer or null")
        else:
            material["size"] = size
        materials.append(material)
    return materials


def _normalize_replay_acceptance_checks(raw: object, *, field: str) -> list[dict[str, object]]:
    if raw is None:
        raise WorkerAdapterError(f"{field} must be present and be a list")
    if not isinstance(raw, list):
        raise WorkerAdapterError(f"{field} must be a list")

    checks: list[dict[str, object]] = []
    for index, raw_check in enumerate(raw):
        if not isinstance(raw_check, dict):
            raise WorkerAdapterError(f"{field}[{index}] must be an object")
        oracle_name_raw = raw_check.get("oracle_name")
        if oracle_name_raw is None:
            oracle_name = None
        elif isinstance(oracle_name_raw, str):
            oracle_name = oracle_name_raw.strip() or None
        else:
            raise WorkerAdapterError(f"{field}[{index}].oracle_name must be a string or null")

        command_raw = raw_check.get("command")
        if command_raw is None:
            command = None
        elif isinstance(command_raw, str):
            command = command_raw.strip() or None
        else:
            raise WorkerAdapterError(f"{field}[{index}].command must be a string or null")

        reason_raw = raw_check.get("reason")
        if reason_raw is None:
            reason = None
        elif isinstance(reason_raw, str):
            reason = reason_raw.strip() or None
        else:
            raise WorkerAdapterError(f"{field}[{index}].reason must be a string or null")

        checks.append(
            {
                "name": _required_str(raw_check.get("name"), f"{field}[{index}].name"),
                "oracle_name": oracle_name,
                "command": command,
                "expected_signal": _required_str(raw_check.get("expected_signal"), f"{field}[{index}].expected_signal"),
                "reason": reason,
            }
        )
    return checks


def _normalize_replay_equivalence_inputs(raw: object, *, field: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object")
    for required_key in ("baseline_hash", "oracle_names", "material_paths", "notes"):
        if required_key not in raw:
            raise WorkerAdapterError(f"{field}.{required_key} must be present")

    baseline_hash_raw = raw.get("baseline_hash")
    if baseline_hash_raw is None:
        baseline_hash = None
    elif isinstance(baseline_hash_raw, str):
        baseline_hash = baseline_hash_raw.strip() or None
    else:
        raise WorkerAdapterError(f"{field}.baseline_hash must be a string or null")

    return {
        "baseline_hash": baseline_hash,
        "oracle_names": _string_list(raw.get("oracle_names"), f"{field}.oracle_names"),
        "material_paths": _string_list(raw.get("material_paths"), f"{field}.material_paths"),
        "notes": _string_list(raw.get("notes"), f"{field}.notes"),
    }


def _normalize_replay_parity_results(raw: object, *, field: str) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise WorkerAdapterError(f"{field} must be an object or null")

    baseline_hash_raw = raw.get("baseline_hash")
    observed_hash_raw = raw.get("observed_hash")
    oracle_digest_raw = raw.get("oracle_digest")
    details_raw = raw.get("details")
    trace_count_raw = raw.get("trace_count")
    match = raw.get("match")
    if match is not None and not isinstance(match, bool):
        raise WorkerAdapterError(f"{field}.match must be a boolean or null")
    if baseline_hash_raw is not None and not isinstance(baseline_hash_raw, str):
        raise WorkerAdapterError(f"{field}.baseline_hash must be a string or null")
    if observed_hash_raw is not None and not isinstance(observed_hash_raw, str):
        raise WorkerAdapterError(f"{field}.observed_hash must be a string or null")
    if oracle_digest_raw is not None and not isinstance(oracle_digest_raw, str):
        raise WorkerAdapterError(f"{field}.oracle_digest must be a string or null")
    if details_raw is not None and not isinstance(details_raw, str):
        raise WorkerAdapterError(f"{field}.details must be a string or null")
    if trace_count_raw is not None and (isinstance(trace_count_raw, bool) or not isinstance(trace_count_raw, int) or trace_count_raw < 0):
        raise WorkerAdapterError(f"{field}.trace_count must be a non-negative integer or null")

    return {
        "match": match,
        "details": details_raw.strip() if isinstance(details_raw, str) and details_raw.strip() else None,
        "baseline_hash": baseline_hash_raw.strip() if isinstance(baseline_hash_raw, str) and baseline_hash_raw.strip() else None,
        "observed_hash": observed_hash_raw.strip() if isinstance(observed_hash_raw, str) and observed_hash_raw.strip() else None,
        "oracle_digest": oracle_digest_raw.strip() if isinstance(oracle_digest_raw, str) and oracle_digest_raw.strip() else None,
        "trace_count": trace_count_raw if isinstance(trace_count_raw, int) and trace_count_raw >= 0 else None,
    }


def _normalize_replay_plan(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError("replay output must be an object")
    if raw.get("schema_version") != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError("replay output schema_version must be 2")
    if raw.get("interface_version") != WORKER_INTERFACE_VERSION:
        raise WorkerAdapterError("replay output interface_version mismatch")
    run_id = _required_str(raw.get("run_id"), "run_id")
    capsule_id = _required_str(raw.get("capsule_id"), "capsule_id")
    if "capsule_scope" not in raw:
        raise WorkerAdapterError("replay output capsule_scope must be present and be a list")
    capsule_scope = _string_list(raw.get("capsule_scope"), "replay output capsule_scope")
    raw_steps = raw.get("steps")
    if raw_steps is None:
        steps: list[dict[str, object]] = []
    elif not isinstance(raw_steps, list):
        raise WorkerAdapterError("replay output steps must be a list")
    else:
        steps = []
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise WorkerAdapterError(f"replay steps[{index}] must be an object")
            command = _required_str(raw_step.get("command"), f"replay steps[{index}].command")
            step = {"command": command}
            expected_exit_code = _optional_int(
                raw_step.get("expected_exit_code"),
                f"replay steps[{index}].expected_exit_code",
                default=0,
            )
            if expected_exit_code is not None:
                step["expected_exit_code"] = expected_exit_code
            timeout_s = _optional_int(raw_step.get("timeout_s"), f"replay steps[{index}].timeout_s", default=None)
            if timeout_s is not None:
                step["timeout_s"] = timeout_s
            cwd = raw_step.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                step["cwd"] = cwd.strip()
            steps.append(step)
    parity_results = raw.get("parity_results")
    if parity_results is None:
        parity_results = raw.get("equivalence")
    if parity_results is None:
        parity_results = raw.get("parity")
    return {
        "schema_version": WORKER_SCHEMA_VERSION,
        "interface_version": WORKER_INTERFACE_VERSION,
        "run_id": run_id,
        "capsule_id": capsule_id,
        "capsule_scope": capsule_scope,
        "material_inputs": _normalize_replay_material_inputs(
            raw.get("material_inputs"),
            field="replay output material_inputs",
        ),
        "steps": steps,
        "acceptance_checks": _normalize_replay_acceptance_checks(
            raw.get("acceptance_checks"),
            field="replay output acceptance_checks",
        ),
        "equivalence_inputs": _normalize_replay_equivalence_inputs(
            raw.get("equivalence_inputs"),
            field="replay output equivalence_inputs",
        ),
        "status": str(raw.get("status") or "ok"),
        "message": str(raw.get("message") or ""),
        "parity_results": _normalize_replay_parity_results(
            parity_results,
            field="replay output parity_results",
        ),
        "failures": _safe_string_list(raw.get("failures")),
    }


def _normalize_claim_set(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError("claim set output must be an object")
    if raw.get("schema_version") != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError("claim set output schema_version must be 2")
    if raw.get("interface_version") != WORKER_INTERFACE_VERSION:
        raise WorkerAdapterError("claim set output interface_version mismatch")
    return {
        "schema_version": WORKER_SCHEMA_VERSION,
        "interface_version": WORKER_INTERFACE_VERSION,
        "claims": _normalize_claim_payloads(raw.get("claims"), field="claims"),
    }


def _build_distill_input(
    run_id: str,
    profile: str,
    mode: str,
    target_capsules: list[dict[str, object]],
    changed_paths: list[str],
    policy_ref: str = ".outcomegraph/policy.yaml",
    materials_lock_ref: str = ".outcomegraph/materials.lock",
) -> dict[str, object]:
    return {
        "interface_version": WORKER_INTERFACE_VERSION,
        "schema_version": WORKER_SCHEMA_VERSION,
        "adapter_profile": profile,
        "mode": mode,
        "target_capsules": target_capsules,
        "changed_paths": changed_paths,
        "policy_ref": policy_ref,
        "materials_lock_ref": materials_lock_ref,
        "run_id": run_id,
    }


def _build_replay_input(
    run_id: str,
    profile: str,
    mode: str,
    capsule_id: str,
    changed_materials: list[dict[str, object]],
    source_ref: str = "HEAD",
    materials_lock_ref: str = ".outcomegraph/materials.lock",
    capsule_payload: dict[str, object] | None = None,
    scope_materials: list[dict[str, object]] | None = None,
    baseline_equivalence: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "interface_version": WORKER_INTERFACE_VERSION,
        "schema_version": WORKER_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "adapter_profile": profile,
        "capsule_id": capsule_id,
        "source_ref": source_ref,
        "materials_lock_ref": materials_lock_ref,
        "changed_materials": changed_materials,
        "scope_materials": scope_materials or changed_materials,
        "capsule": capsule_payload or {},
        "baseline_equivalence": baseline_equivalence or {},
    }


def _build_explain_input(
    run_id: str,
    profile: str,
    mode: str,
    target_capsules: list[str],
) -> dict[str, object]:
    return {
        "interface_version": WORKER_INTERFACE_VERSION,
        "schema_version": WORKER_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "adapter_profile": profile,
        "target_capsules": [{"id": capsule} for capsule in target_capsules],
    }


def _build_claim_receipt_pointers(
    claim_id: str,
    receipt_pointers: list[dict[str, object]],
) -> list[dict[str, object]]:
    normalized = _deduplicate_receipt_pointers(receipt_pointers)
    if normalized:
        return normalized
    return [_build_claim_fallback_receipt_pointer(claim_id)]


def _build_claim_payload(
    claim_id: str,
    capsule_id: str,
    run_id: str,
    profile: str,
    mode: str,
    changed_files: list[str],
    receipt_pointers: list[dict[str, object]],
    text: str | None = None,
    category: str = "behavior",
) -> dict[str, object]:
    now = _utc_timestamp()
    claim_text = text or f"Claim for {capsule_id} captured during {profile} stage."
    return {
        "schema_version": 2,
        "artifact_type": "claim",
        "id": claim_id,
        "capsule_id": capsule_id,
        "text": claim_text,
        "category": category or "behavior",
        "receipt_pointers": _build_claim_receipt_pointers(claim_id, receipt_pointers),
        "origin": {
            "run_id": run_id,
            "profile": profile,
            "mode": mode,
            "changed_files": changed_files,
        },
        "created_at": now,
    }


def _build_certificate_payload(
    certificate_id: str,
    capsule_id: str,
    run_id: str,
    claim_refs: list[str],
    profile: str,
    mode: str,
    receipt_pointers: list[dict[str, object]],
    status: str = "success",
    source: str = "distill",
    adapter_name: str = "filesystem-store",
    adapter_version: str = "1.0.0",
    prompt_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    now = _utc_timestamp()
    normalized_refs: list[str] = []
    for raw_ref in claim_refs:
        if isinstance(raw_ref, str) and raw_ref:
            normalized_refs.append(raw_ref)
    payload = {
        "schema_version": 2,
        "artifact_type": "certificate",
        "id": certificate_id,
        "capsule_id": capsule_id,
        "run_id": run_id,
        "status": status,
        "adapter": {
            "name": adapter_name,
            "version": adapter_version,
        },
        "claim_refs": sorted(set(normalized_refs)),
        "receipt_pointers": receipt_pointers,
        "replay_context": {
            "run_id": run_id,
            "adapter_profile": profile,
            "mode": mode,
            "source": source,
        },
        "created_at": now,
        "updated_at": now,
    }
    normalized_prompt_provenance = _normalize_prompt_provenance(prompt_provenance)
    if normalized_prompt_provenance is not None:
        payload["prompt_provenance"] = normalized_prompt_provenance
    return payload


def _extract_artifact_field(line: str, field_name: str) -> str | None:
    key, sep, value = line.partition(":")
    if sep != ":":
        return None
    if key.strip() != field_name:
        return None
    clean = value.partition("#")[0].strip()
    if not clean:
        return None
    if clean.startswith(('"', "'")) and clean.endswith(('"', "'")) and len(clean) > 1:
        clean = clean[1:-1]
    return clean


def _read_artifact_record(repo_root: str, relative_path: str) -> dict[str, object]:
    full_path = os.path.join(repo_root, relative_path)
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            artifact_id = data.get("id")
            artifact_type = data.get("artifact_type")
            schema_version = data.get("schema_version")
            if isinstance(artifact_id, str) and artifact_id.strip():
                artifact_id = artifact_id.strip()
            else:
                artifact_id = None
            if isinstance(artifact_type, str) and artifact_type.strip():
                artifact_type = artifact_type.strip()
            else:
                artifact_type = None
            if isinstance(schema_version, int):
                schema_version = schema_version
            else:
                schema_version = None
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            return {
                "path": relative_path,
                "id": artifact_id,
                "artifact_type": artifact_type,
                "schema_version": schema_version,
                "size": size,
            }
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        pass

    artifact_id = None
    artifact_type = None
    schema_version = None
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.lstrip().startswith("-"):
                    continue
                value = _extract_artifact_field(raw_line, "id")
                if value and artifact_id is None:
                    artifact_id = value
                    continue
                value = _extract_artifact_field(raw_line, "artifact_type")
                if value and artifact_type is None:
                    artifact_type = value
                    continue
                value = _extract_artifact_field(raw_line, "schema_version")
                if value and schema_version is None:
                    try:
                        schema_version = int(value)
                    except ValueError:
                        schema_version = None
                if artifact_id is not None and artifact_type is not None and schema_version is not None:
                    break
    except OSError:
        return {"path": relative_path, "id": None, "artifact_type": None, "schema_version": None, "size": 0}

    try:
        size = os.path.getsize(full_path)
    except OSError:
        size = 0

    if artifact_id is None:
        base = os.path.basename(relative_path)
        artifact_id = base.split(".")[0]
    return {
        "path": relative_path,
        "id": artifact_id,
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "size": size,
    }


def _collect_canonical_artifact_files(repo_root: str) -> list[str]:
    canonical_roots = ("capsules", "refs", "decisions", "claims", "certificates")
    artifact_files: list[str] = []
    for root in canonical_roots:
        root_path = os.path.join(repo_root, OG_ROOT, root)
        if not os.path.isdir(root_path):
            continue
        for dirpath, _, filenames in os.walk(root_path):
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                if not filename.endswith((".json", ".yaml", ".yml")):
                    continue
                artifact_files.append(os.path.relpath(os.path.join(dirpath, filename), repo_root).replace("\\", "/"))
    materials_lock_path = f"{OG_ROOT}/materials.lock"
    if os.path.exists(os.path.join(repo_root, materials_lock_path)):
        artifact_files.append(materials_lock_path)
    return sorted(set(artifact_files))


def _collect_export_artifact_files(repo_root: str) -> list[str]:
    artifact_files: list[str] = []
    for root in CANONICAL_EXPORT_SCOPES:
        root_path = os.path.join(repo_root, OG_ROOT, root)
        if not os.path.isdir(root_path):
            continue
        for dirpath, _, filenames in os.walk(root_path):
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                if not filename.endswith((".json", ".yaml", ".yml")):
                    continue
                artifact_files.append(os.path.relpath(os.path.join(dirpath, filename), repo_root).replace("\\", "/"))
    materials_lock_path = f"{OG_ROOT}/materials.lock"
    if os.path.exists(os.path.join(repo_root, materials_lock_path)):
        artifact_files.append(materials_lock_path)
    return sorted(set(artifact_files))


def _read_file_content_hash(repo_root: str, relative_path: str) -> str:
    full_path = os.path.join(repo_root, relative_path)
    try:
        with open(full_path, "rb") as handle:
            return _content_sha256(handle.read())
    except OSError:
        return ""


def _artifact_scope(relative_path: str) -> str:
    normalized = _normalize_repo_relative_path(relative_path)
    if not normalized.startswith(f"{OG_ROOT}/"):
        return normalized.split("/", 1)[0] if "/" in normalized else normalized
    scope = normalized[len(f"{OG_ROOT}/") :]
    return scope.split("/", 1)[0]


def _read_export_record(repo_root: str, relative_path: str, scope: str) -> dict[str, object]:
    expected_artifact_type = _expected_canonical_artifact_type(relative_path)
    if relative_path.endswith(".json") and scope != "constitution":
        payload = _read_canonical_artifact_payload(
            repo_root,
            relative_path,
            expected_artifact_type=expected_artifact_type,
        )
        artifact_id = payload.get("id")
        artifact_type = payload.get("artifact_type")
        schema_version = payload.get("schema_version")
    else:
        fallback = _read_artifact_record(repo_root, relative_path)
        artifact_id = fallback.get("id")
        artifact_type = fallback.get("artifact_type")
        schema_version = fallback.get("schema_version")

    if scope == "constitution" and artifact_type is None:
        artifact_type = "constitution"
    if artifact_type is None and expected_artifact_type is not None:
        artifact_type = expected_artifact_type

    if not isinstance(artifact_id, str) or not artifact_id.strip():
        artifact_id = os.path.splitext(os.path.basename(relative_path))[0]

    return {
        "path": relative_path,
        "id": artifact_id,
        "artifact_type": artifact_type,
        "schema_version": schema_version,
    }


def _build_export_outputs(snapshot: dict[str, object]) -> dict[str, str]:
    outputs = {
        EXPORT_PATHS["agents"]: _render_agents_export(snapshot),
        EXPORT_PATHS["outcomes"]: _render_readme_outcomes(snapshot),
        EXPORT_PATHS["skill"]: _render_skill_export(snapshot),
        EXPORT_PATHS["mcp_resources"]: _render_mcp_resource_export(snapshot),
    }
    return {path: outputs[path] for path in sorted(outputs)}


def _render_context_contract() -> str:
    lines = [
        "# CONTEXT",
        "",
        "OutcomeGraph canonical agent guidance contract.",
        "",
        f"- Contract version: {AGENT_GUIDANCE_CONTRACT_VERSION}",
        f"- CLI version: {VERSION}",
        f"- JSON envelope schema_version: {COMMAND_RESULT_SCHEMA_VERSION}",
        f"- Canonical artifact schema_version: {CANONICAL_ARTIFACT_SCHEMA_VERSION}",
        f"- Generated projection: `{EXPORT_PATHS['agents']}`",
        "",
        "## Automation boundary",
        "- Use `og` as the stable interface for status, sync, verify, replay, export, and daemon flows.",
        "- Treat `.outcomegraph/**` as canonical truth and `.outcomegraph/export/**` as derived control surfaces.",
        "- Default automation mode is `observe`; do not edit product code unless command mode and policy explicitly allow it.",
        "- Discover machine contracts with `og schema` and `og describe <command>` before constructing unattended calls.",
        "",
        "## Required request patterns",
        "- Use `--json` for machine callers and branch on top-level `status`, `errors`, and `data`.",
        "- Narrow large payloads with `--fields`, `--limit`, `--offset`, or `--output jsonl` before requesting list-heavy data.",
        "- For mutating commands, run `--validate` or `--dry-run` when you need a no-write preview or recovery check.",
        "- Destructive or privileged actions require explicit confirmation flags such as `--yes`; never infer confirmation from context.",
        "- In `--strict` mode, unknown payload keys, lossy coercions, and missing required values are contract violations; fix the request instead of retrying loosely.",
        "- Use `--non-interactive` for unattended runs so commands fail instead of waiting for prompts.",
        "",
        "## Safe command sequence",
        "1. `og status --json`",
        "2. `og schema` or `og describe <command>`",
        "3. `og <command> --validate --json` or `og <command> --dry-run --json` before writes",
        "4. `og <command> --json`",
        "5. `og verify --changed --json` and `og replay --changed --json` for stronger confirmation when needed",
        "",
        "## Write boundaries",
        "- Safe by default: update `.outcomegraph/**`, refresh generated control surfaces, and run configured verification commands.",
        "- Require explicit policy or confirmation: hook changes, cleanup operations, daemon lifecycle actions, dependency changes, and application-code edits.",
        "- Never treat generated exports or skill files as canonical data sources.",
    ]
    return "\n".join(lines) + "\n"


def _validate_canonical_artifact_records(repo_root: str) -> None:
    for relative_path in _collect_canonical_artifact_files(repo_root):
        record = _read_artifact_record(repo_root, relative_path)
        expected_type = _expected_canonical_artifact_type(relative_path)
        artifact_type = record.get("artifact_type")
        schema_version = record.get("schema_version")
        if expected_type is None:
            continue
        if not isinstance(artifact_type, str) or not artifact_type.strip():
            raise ValueError(
                f"{relative_path}: missing artifact_type; expected '{expected_type}' for this path and schema_version 2"
            )
        if schema_version != 2:
            raise ValueError(
                f"{relative_path}: schema_version must be 2, detected {schema_version!r}; migrate artifact to schema_version 2"
            )
        if artifact_type.strip() != expected_type:
            raise ValueError(
                f"{relative_path}: artifact_type '{artifact_type.strip()}' does not match expected '{expected_type}' for this path"
            )
        if expected_type == "capsule" and record.get("kind") is not None and _normalize_capsule_kind(record.get("kind")) is None:
            raise ValueError(
                f"{relative_path}: capsule kind must be one of {sorted(CAPSULE_KIND_VALUES)}, detected {record.get('kind')!r}"
            )


def _canonical_export_snapshot(repo_root: str) -> dict[str, object]:
    artifact_files = _collect_export_artifact_files(repo_root)
    records: list[dict[str, object]] = []
    by_scope: dict[str, int] = {}
    ids_by_scope: dict[str, list[str]] = {}

    for path in artifact_files:
        scope = _artifact_scope(path)
        record = _read_export_record(repo_root, path, scope)
        content_hash = _read_file_content_hash(repo_root, path)
        record["content_hash"] = content_hash
        records.append(record)
        by_scope[scope] = by_scope.get(scope, 0) + 1
        artifact_id = record.get("id")
        if isinstance(artifact_id, str) and artifact_id:
            ids_by_scope.setdefault(scope, []).append(artifact_id)
    return {
        "generated_at": _utc_timestamp(),
        "artifacts": sorted(records, key=lambda record: record["path"]),
        "counts": {
            "total": len(artifact_files),
            "by_scope": by_scope,
        },
        "ids_by_scope": {scope: sorted(set(ids)) for scope, ids in ids_by_scope.items()},
        "artifact_hashes": {
            record["path"]: record["content_hash"]
            for record in sorted(records, key=lambda record: record["path"])
            if record["path"] is not None
        },
    }


def _render_agents_export(snapshot: dict[str, object]) -> str:
    counts = snapshot["counts"]
    by_scope = counts["by_scope"]
    lines = [
        _render_context_contract().rstrip(),
        "",
        "## Export snapshot",
        f"- Generated from `{TOP_LEVEL_AGENT_GUIDANCE_PATH}` by OutcomeGraph export stage.",
        "- Projection path: `.outcomegraph/export/AGENTS.md`",
        "",
        "## Command surface",
        "- og init",
        "- og sync",
        "- og verify --changed",
        "- og replay --changed",
        "- og status",
        "- og export",
        "- og clean [--scope runtime|generated|all] [--dry-run] [--yes]",
        "- og explain",
        "- og drift",
        "- og mcp-server",
        "- og optimize prompts",
        "- og autopilot init|disable",
        "- og daemon install|start|stop|status",
        "",
        f"- Canonical artifact directories tracked: {sorted(list(by_scope.keys()))}",
        f"- Total canonical artifacts: {counts['total']}",
        "",
    ]
    for scope in sorted(by_scope):
        lines.extend([f"- `{scope}`: {by_scope[scope]} item(s)"])
    lines.extend(
        [
            "",
            "## Export semantics",
            "- Exports are generated deterministically from canonical artifacts.",
            "- Writes are idempotent: unchanged content is not rewritten.",
            "- Control-surface files are projections only; canonical truth remains in `.outcomegraph` artifacts.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_readme_outcomes(snapshot: dict[str, object]) -> str:
    counts = snapshot["counts"]
    ids_by_scope = snapshot["ids_by_scope"]
    lines = [
        "# OutcomeGraph Export Snapshot",
        "",
        "Derived from `.outcomegraph` canonical artifacts at export time.",
        "",
        f"- Total artifacts observed: {counts['total']}",
        "",
        "## Scope breakdown",
    ]
    for scope in sorted(counts["by_scope"]):
        lines.append(f"- `{scope}`: {counts['by_scope'][scope]} file(s)")
    lines.append("")
    lines.append("## Artifact IDs")
    for scope in sorted(ids_by_scope):
        entries = sorted(ids_by_scope[scope])
        if not entries:
            continue
        lines.append(f"- {scope}:")
        for value in entries:
            lines.append(f"  - {value}")
    lines.extend(["", "## Files tracked for export", ""])
    for record in sorted(snapshot["artifacts"], key=lambda item: item["path"]):
        path = record["path"]
        artifact_type = record.get("artifact_type")
        schema_version = record.get("schema_version")
        if isinstance(artifact_type, str):
            tag = artifact_type
        elif isinstance(schema_version, int):
            tag = f"schema_version:{schema_version}"
        else:
            tag = "raw"
        lines.append(f"- `{path}` ({tag})")
    return "\n".join(lines) + "\n"


def _render_skill_export(snapshot: dict[str, object]) -> str:
    counts = snapshot["counts"]
    lines = [
        "# OutcomeGraph Steward Skill",
        "",
        "Scope: This skill documents canonical Steward workflows for bootstrap, sync, and control-surface updates.",
        "",
        "## 1) Bootstrap",
        "- Run `og init` to create required OutcomeGraph directories and baseline metadata.",
        "- Ensure `.outcomegraph/` exists with `constitution`, `capsules`, `refs`, `decisions`, `certificates`, `datasets`, `events`, `objects`, and `work`.",
        "",
        "## 2) Deterministic sync flow",
        "1. Run `og sync` for the canonical refresh loop.",
        "2. Distill changes into synthetic deltas.",
        "3. Apply deltas and refresh exports.",
        "4. Emit structured summary into `.outcomegraph/events`.",
        "",
        "## 3) Verification and replay expectations",
        "- Use `og verify --changed` after focused edits.",
        "- Use `og replay --changed` when behavior parity validation is required.",
        "- Handle verification failures by inspecting certificate and error signals before continuing.",
        "",
        "## 4) Failure handling",
        "- If lock contention occurs, treat command result as `pending` and rerun.",
        "- Preserve existing canonical artifacts when worker or oracle stages are unavailable.",
        "- Keep exporting control surfaces from available truth where possible.",
        "",
        "## 5) Artifact health",
        f"- Tracked canonical paths currently include {counts['total']} known artifact files.",
        "- Export refresh includes `export/AGENTS.md`, `export/README_OUTCOMES.md`, and `export/mcp-resources.json`.",
    ]
    return "\n".join(lines) + "\n"


def _render_mcp_resource_export(snapshot: dict[str, object]) -> str:
    resources = [
        {
            "uri": "outcomegraph://tools/sync",
            "name": "sync",
            "description": "Run autonomous reconcile pipeline.",
            "category": "tool",
        },
        {
            "uri": "outcomegraph://tools/verify",
            "name": "verify",
            "description": "Run fast verification on impacted capsules.",
            "category": "tool",
        },
        {
            "uri": "outcomegraph://tools/replay",
            "name": "replay",
            "description": "Run replay checks against canonical artifacts.",
            "category": "tool",
        },
        {
            "uri": "outcomegraph://tools/explain",
            "name": "explain",
            "description": "Explain claims and provenance pointers.",
            "category": "tool",
        },
        {
            "uri": "outcomegraph://tools/status",
            "name": "status",
            "description": "Read runtime and freshness summary.",
            "category": "tool",
        },
    ]
    resources.extend(
        {
            "uri": f"outcomegraph://{scope}",
            "name": scope,
            "description": f"Canonical artifact projection for {scope} scope.",
            "category": "artifact",
            "paths": [record["path"] for record in snapshot["artifacts"] if record["path"].startswith(f"{OG_ROOT}/{scope}")],
        }
        for scope in sorted(snapshot["counts"]["by_scope"])
    )
    payload = {
        "schema_version": 2,
        "artifact_type": "mcp_resource_export",
        "id": "mcp-export",
        "tools": sorted(resources[:5], key=lambda item: item["name"]),
        "resources": sorted(resources[5:], key=lambda item: item["uri"]),
        "prompts": [
            "bootstrap",
            "replay",
            "repair",
        ],
        "artifact_counts": {scope: snapshot["counts"]["by_scope"][scope] for scope in sorted(snapshot["counts"]["by_scope"])},
        "status": "ok",
    }
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _build_mcp_server_payload(snapshot: dict[str, object], options: dict[str, object]) -> dict[str, object]:
    artifact_counts = snapshot.get("counts", {}).get("by_scope", {}) if isinstance(snapshot.get("counts"), dict) else {}
    resources = [
        {
            "uri": f"outcomegraph://{scope}",
            "name": scope,
            "description": f"Canonical artifact projection for {scope} scope.",
            "category": "artifact",
            "paths": sorted(
                [
                    record["path"]
                    for record in snapshot.get("artifacts", [])
                    if isinstance(record, dict)
                    and str(record.get("path", "")).startswith(f"{OG_ROOT}/{scope}")
                ]
            ),
        }
        for scope in MCP_CONTROL_RESOURCES
    ]
    controls = {
        "tools": sorted(MCP_CONTROL_TOOL_DEFS, key=lambda item: item["name"]),
        "resources": resources,
        "prompts": list(MCP_CONTROL_PROMPTS),
    }
    return {
        "schema_version": 2,
        "command": "mcp-server",
        "options": options,
        "tools": controls["tools"],
        "resources": controls["resources"],
        "prompts": controls["prompts"],
        "artifact_counts": {scope: artifact_counts.get(scope, 0) for scope in MCP_CONTROL_RESOURCES},
        "status": "ok",
        "generated_at": snapshot.get("generated_at"),
        "message": "MCP control surface available from canonical artifact projections.",
    }


def _validate_mcp_control_surface_payload(payload: dict[str, object]) -> list[str]:
    issues: list[str] = []
    tools = payload.get("tools")
    if not isinstance(tools, list):
        issues.append("`tools` must be a list")
        tools = []
    resources = payload.get("resources")
    if not isinstance(resources, list):
        issues.append("`resources` must be a list")
        resources = []
    prompts = payload.get("prompts")
    if not isinstance(prompts, list):
        issues.append("`prompts` must be a list")
        prompts = []

    tool_names = sorted({str(item.get("name")) for item in tools if isinstance(item, dict) and str(item.get("name"))})
    resource_names = sorted({str(item.get("name")) for item in resources if isinstance(item, dict) and str(item.get("name"))})
    prompt_values = sorted(str(value) for value in prompts if str(value))

    expected_tool_names = sorted(MCP_CONTROL_TOOL_NAMES)
    expected_resource_names = sorted(MCP_CONTROL_RESOURCE_NAMES)
    expected_prompt_names = sorted(MCP_CONTROL_PROMPT_NAMES)
    if tool_names != expected_tool_names:
        issues.append(f"`tools` does not match contract: expected {expected_tool_names}, observed {tool_names}")
    if resource_names != expected_resource_names:
        issues.append(f"`resources` does not match contract: expected {expected_resource_names}, observed {resource_names}")
    if prompt_values != expected_prompt_names:
        issues.append(f"`prompts` does not match contract: expected {expected_prompt_names}, observed {prompt_values}")

    if str(payload.get("command")) != "mcp-server":
        issues.append("command field must be 'mcp-server'")
    if payload.get("schema_version") != 2:
        issues.append("schema_version must be 2")

    return issues


def _run_mcp_server_stage(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    try:
        snapshot = _canonical_export_snapshot(repo_root)
        payload = _build_mcp_server_payload(snapshot, options)
        issues = _validate_mcp_control_surface_payload(payload)
        if issues:
            return {
                "schema_version": 2,
                "status": "error",
                "code": CONTROL_SURFACE_MISMATCH_CODE,
                "command": "mcp-server",
                "options": options,
                "tools": [],
                "resources": [],
                "prompts": list(MCP_CONTROL_PROMPTS),
                "message": "Control-surface payload does not match canonical contract.",
                "details": {"issues": issues},
            }
        return payload
    except Exception as exc:
        return {
            "schema_version": 2,
            "status": "error",
            "command": "mcp-server",
            "options": options,
            "tools": [],
            "resources": [],
            "prompts": list(MCP_CONTROL_PROMPTS),
            "message": f"Unable to render mcp-server control surface: {exc}",
        }


def _render_mcp_server(payload: dict[str, object]) -> str:
    tools = payload.get("tools", [])
    resources = payload.get("resources", [])
    prompts = payload.get("prompts", [])
    lines = ["mcp-server control surface", ""]
    if payload.get("status") == "error":
        return f"{payload.get('status', 'error')}: {payload.get('message', 'unknown error')}\n"

    lines.append("tools:")
    for item in sorted(tools, key=lambda value: str(value.get("name", ""))):
        name = item.get("name") or item.get("uri")
        uri = item.get("uri", "outcomegraph://tools/unknown")
        description = item.get("description", "")
        lines.append(f"- {name}: {uri}")
        if description:
            lines.append(f"  {description}")

    lines.append("")
    lines.append("resources:")
    for item in sorted(resources, key=lambda value: str(value.get("name", ""))):
        name = item.get("name", "")
        count = len(item.get("paths", []))
        lines.append(f"- {name} ({count} file(s))")
        for path in sorted(item.get("paths", [])):
            lines.append(f"  - {path}")

    lines.append("")
    lines.append(f"prompts: {', '.join(str(value) for value in prompts)}")
    return "\n".join(lines) + "\n"


def _run_export_refresh(repo_root: str) -> tuple[list[str], list[str], dict[str, object]]:
    snapshot = _canonical_export_snapshot(repo_root)
    updated_exports: list[str] = []
    unchanged_exports: list[str] = []
    outputs = _build_export_outputs(snapshot)
    snapshot["export_hashes"] = {
        relative_path: _content_sha256(content.encode("utf-8")) for relative_path, content in outputs.items()
    }

    for relative_path, content in outputs.items():
        absolute_path = os.path.join(repo_root, relative_path)
        changed = _write_text_file_if_changed(absolute_path, content)
        rel = relative_path.replace("\\", "/")
        if changed:
            updated_exports.append(rel)
        else:
            unchanged_exports.append(rel)

    return updated_exports, unchanged_exports, snapshot


def _build_constitution_payload(created_at: str) -> str:
    return f"""schema_version: 2
created_at: "{created_at}"
mode: observe
policy:
  default_mode: observe
  allow:
    - ".outcomegraph/**"
    - "AGENTS.md"
    - "CONTEXT.md"
  deny:
    - "autonomous application code edits"
    - "dependency installation"
    - "network actions"
"""


def _build_policy_payload(created_at: str) -> str:
    return f"""schema_version: 2
created_at: "{created_at}"
name: observe-policy
mode: observe
allow:
  file_writes:
    - ".outcomegraph/**"
    - "export/**"
    - "skills/outcome-steward/**"
    - "AGENTS.md"
    - "CONTEXT.md"
  verify_commands:
    - "npm test --listTests"
    - "npm test"
    - "go test ./..."
    - "pytest -q"
  sandbox_operations:
    - create_isolated_worktree
    - read_repo_state
    - read_artifacts
deny:
  file_writes:
    - "src/**"
    - "lib/**"
    - "app/**"
    - "packages/**"
  network:
    - unrestricted
  dependencies:
    - "npm install"
    - "pip install"
    - "cargo add"
    - "go mod tidy"
  deployment:
    - push
    - git commit --amend
    - github pr create
    - gha workflow_dispatch
"""


def _build_config_payload(created_at: str) -> str:
    return f"""schema_version: 2
created_at: "{created_at}"
defaults:
  output: human
  profile: analyze
  mode: observe
worker:
  codex_home: ""
safety:
  policy_file: policy.yaml
  max_writes_per_run: 64
"""


def _build_outcome_gitignore_payload() -> str:
    return """# Auto-generated by OutcomeGraph runtime
cache/
traces/
objects/
events/
work/
"""


def _build_lock_record(
    created_at: str,
    status: str = LOCK_STATUS_UNLOCKED,
    holder: dict | None = None,
    session: dict[str, object] | None = None,
) -> dict:
    return {
        "schema_version": 2,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "holder": holder,
        "session": session,
    }


def _build_lock_payload(
    created_at: str,
    status: str = LOCK_STATUS_UNLOCKED,
    holder: dict | None = None,
    session: dict[str, object] | None = None,
) -> str:
    return json.dumps(_build_lock_record(created_at, status, holder, session), indent=2, sort_keys=True) + "\n"

def _build_state_record(created_at: str) -> dict:
    return {
        "schema_version": 2,
        "status": "initialized",
        "mode": "observe",
        "updated_at": created_at,
        "last_sync_id": None,
        "last_idempotency_key": None,
        "pending": False,
    }


def _build_state_payload(created_at: str) -> str:
    return json.dumps(_build_state_record(created_at), indent=2, sort_keys=True) + "\n"


def _build_work_payload(
    repo_root: str,
    *,
    pending: bool | None = None,
    status: str | None = None,
    last_sync_id: str | None = None,
    last_idempotency_key: str | None = None,
    last_message: str | None = None,
) -> dict:
    path = os.path.join(repo_root, WORK_STATE_FILE)
    state = _read_json_file(path) or _build_state_record(_utc_timestamp())
    if status is not None:
        state["status"] = status
    state["updated_at"] = _utc_timestamp()
    if pending is not None:
        state["pending"] = bool(pending)
    if last_sync_id is not None:
        state["last_sync_id"] = last_sync_id
    if last_idempotency_key is not None:
        state["last_idempotency_key"] = last_idempotency_key
    if last_message is not None:
        state["last_message"] = last_message
    _write_json_file(path, state)
    return state


def _read_work_state(repo_root: str) -> dict:
    path = os.path.join(repo_root, WORK_STATE_FILE)
    return _read_json_file(path) or _build_state_record(_utc_timestamp())


def _is_lock_stale(lock_payload: dict, now: datetime.datetime) -> bool:
    if lock_payload.get("status") != LOCK_STATUS_LOCKED:
        return True
    updated_at = lock_payload.get("updated_at")
    if not isinstance(updated_at, str):
        return True
    updated = _parse_utc_timestamp(updated_at)
    if updated is None:
        return True
    return (now - updated).total_seconds() > WORK_LOCK_STALE_SECONDS


def _acquire_work_lock(repo_root: str, holder: dict) -> tuple[bool, dict | None]:
    lock_path = os.path.join(repo_root, WORK_LOCK_FILE)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    while True:
        has_lock_file = os.path.exists(lock_path)
        lock_payload = _read_json_file(lock_path)
        if lock_payload is not None and not _is_lock_stale(lock_payload, now):
            return False, lock_payload
        if has_lock_file:
            try:
                os.remove(lock_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise RuntimeError(f"failed to remove stale lock: {exc}") from exc
        if not has_lock_file or lock_payload is None:
            holder_payload = {"pid": holder.get("pid"), "host": holder.get("host"), "command": holder.get("command")}
            created_at = _utc_timestamp()
            payload = _build_lock_record(
                created_at,
                LOCK_STATUS_LOCKED,
                holder_payload,
                _build_session_record(
                    SESSION_KIND_SYNC,
                    SESSION_LIFECYCLE_EPHEMERAL,
                    SESSION_STATE_ACTIVE,
                    created_at=created_at,
                    updated_at=created_at,
                    ttl_seconds=WORK_LOCK_STALE_SECONDS,
                ),
            )
            try:
                with open(lock_path, "x", encoding="utf-8", newline="\n") as handle:
                    json.dump(payload, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                return True, payload
            except FileExistsError:
                now = datetime.datetime.now(tz=datetime.timezone.utc)
                continue

        now = datetime.datetime.now(tz=datetime.timezone.utc)


def _release_work_lock(repo_root: str, holder: dict) -> None:
    lock_path = os.path.join(repo_root, WORK_LOCK_FILE)
    lock_payload = _read_json_file(lock_path)
    holder_payload = lock_payload.get("holder") if isinstance(lock_payload, dict) else None
    if isinstance(holder_payload, dict):
        if holder_payload.get("pid") != holder.get("pid") or holder_payload.get("host") != holder.get("host"):
            return
    released_session = _session_from_payload(lock_payload.get("session")) if isinstance(lock_payload, dict) else None
    if isinstance(released_session, dict):
        released_session = _set_session_state(released_session, SESSION_STATE_RELEASED, refresh_expiry=True)
    payload = _build_lock_record(_utc_timestamp(), LOCK_STATUS_UNLOCKED, None, released_session)
    _write_json_file(lock_path, payload)


def _set_pending_state(repo_root: str, source: str) -> dict:
    state = _build_work_payload(repo_root, pending=True)
    state["pending_source"] = source
    _write_json_file(os.path.join(repo_root, WORK_STATE_FILE), state)
    return state


def _consume_pending(repo_root: str) -> bool:
    state = _read_work_state(repo_root)
    if not state.get("pending", False):
        return False
    state["pending"] = False
    state.pop("pending_source", None)
    state["updated_at"] = _utc_timestamp()
    _write_json_file(os.path.join(repo_root, WORK_STATE_FILE), state)
    return True

def _build_materials_lock_payload(
    created_at: str,
    entries: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    normalized_entries: list[dict[str, object]] = []
    for raw_entry in entries or []:
        if not isinstance(raw_entry, dict):
            continue
        path = str(raw_entry.get("path") or "").strip()
        digest = str(raw_entry.get("digest") or "").strip()
        if not path or not digest:
            continue
        entry = {
            "path": path,
            "digest": digest,
        }
        kind = str(raw_entry.get("kind") or "file").strip() or "file"
        if kind:
            entry["kind"] = kind
        size = raw_entry.get("size")
        if isinstance(size, int) and size >= 0:
            entry["size"] = size
        normalized_entries.append(entry)

    return {
        "schema_version": 2,
        "artifact_type": "materials_lock",
        "id": "materials-lock",
        "captured_at": created_at,
        "created_at": created_at,
        "updated_at": created_at,
        "entries": normalized_entries,
    }


def _init_outcomegraph() -> dict[str, object]:
    repo_root = _git_root()
    created_dirs: list[str] = []
    existing_dirs: list[str] = []
    created_files: list[str] = []
    existing_files: list[str] = []

    for directory in OG_INIT_DIRS:
        target = os.path.join(repo_root, OG_ROOT, directory)
        if os.path.isdir(target):
            existing_dirs.append(f"{OG_ROOT}/{directory}")
        else:
            os.makedirs(target, exist_ok=True)
            created_dirs.append(f"{OG_ROOT}/{directory}")

    created_at = _utc_timestamp()
    baseline_files = {
        TOP_LEVEL_AGENT_GUIDANCE_PATH: _render_context_contract(),
        f"{OG_ROOT}/constitution/default.yaml": _build_constitution_payload(created_at),
        f"{WORK_STATE_FILE}": _build_state_payload(created_at),
        f"{WORK_LOCK_FILE}": _build_lock_payload(created_at),
        f"{OG_ROOT}/policy.yaml": _build_policy_payload(created_at),
        f"{OG_ROOT}/config.yaml": _build_config_payload(created_at),
        OUTCOME_GITIGNORE: _build_outcome_gitignore_payload(),
    }

    for relative_path, content in baseline_files.items():
        full_path = os.path.join(repo_root, relative_path)
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if _write_file_if_missing(full_path, content):
            created_files.append(relative_path)
        else:
            existing_files.append(relative_path)

    materials_lock_path = f"{OG_ROOT}/materials.lock"
    materials_lock_full_path = os.path.join(repo_root, materials_lock_path)
    if os.path.exists(materials_lock_full_path):
        existing_files.append(materials_lock_path)
    else:
        _write_canonical_artifact(repo_root, materials_lock_path, _build_materials_lock_payload(created_at))
        created_files.append(materials_lock_path)

    return {
        "status": "ok",
        "command": "init",
        "options": {},
        "created": {
            "directories": created_dirs,
            "files": created_files,
        },
        "existing": {
            "directories": existing_dirs,
            "files": existing_files,
        },
        "message": "OutcomeGraph init complete. Observe-mode bootstrap artifacts are in place.",
    }


def _hooks_path(repo_root: str) -> str | None:
    result = _run_git(repo_root, ["config", "--get", "core.hooksPath"])
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _set_hooks_path(repo_root: str, hooks_path: str | None) -> None:
    args = ["config", "core.hooksPath", hooks_path] if hooks_path else ["config", "--unset-all", "core.hooksPath"]
    result = _run_git(repo_root, args)
    if result.returncode != 0 and hooks_path is not None:
        emit_error(f"failed to set core.hooksPath: {result.stderr.strip()}", "autopilot", EXIT_RUNTIME, False)


def _resolve_path(repo_root: str, hooks_path: str) -> str:
    if os.path.isabs(hooks_path):
        return os.path.normpath(hooks_path)
    return os.path.normpath(os.path.join(repo_root, hooks_path))


def _is_managed_hook(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            header = handle.read(512)
        return "outcomegraph-autopilot-hook" in header
    except OSError:
        return False


def _mark_hook_pending(repo_root: str, hook_name: str) -> None:
    pending_dir = os.path.join(repo_root, ".outcomegraph", "work")
    os.makedirs(pending_dir, exist_ok=True)
    pending_file = os.path.join(pending_dir, "pending")
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(pending_file, "w", encoding="utf-8") as handle:
        handle.write(f'{{"hook":"{hook_name}","at":"{timestamp}"}}\\n')


def _hook_pending_script(repo_root: str, hook_name: str) -> str:
    pending_path = os.path.join(repo_root, ".outcomegraph", "work", "pending")
    return (
        f'PENDING_FILE="{pending_path}"\n'
        f'WORK_FILE="{pending_path}"\n'
        "mkdir -p \"$(dirname \"$WORK_FILE\")\"\n"
        'TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"\n'
        "cat > \"$WORK_FILE\" <<EOF\n"
        f'{{"hook":"{hook_name}","at":"$TIMESTAMP"}}\n'
        "EOF\n"
    )


def _hook_quality_gate_script(repo_root: str, hook_name: str) -> str:
    if hook_name != "pre-commit":
        return ""
    quality_pass_script = os.path.join(repo_root, AUTOPILOT_PRE_COMMIT_QUALITY_PASS)
    return (
        f'QUALITY_PASS_SCRIPT="{quality_pass_script}"\n'
        'if [ ! -f "$QUALITY_PASS_SCRIPT" ]; then\n'
        '  echo "og-autopilot: missing pre-commit quality pass script at $QUALITY_PASS_SCRIPT" >&2\n'
        "  exit 1\n"
        "fi\n"
        'if ! bash "$QUALITY_PASS_SCRIPT" "$REPO_ROOT"; then\n'
        '  echo "og-autopilot: pre-commit quality pass failed." >&2\n'
        "  exit 1\n"
        "fi\n"
    )


def _hook_script(repo_root: str, hook_name: str, original_hook: str | None) -> str:
    original_invocation = ""
    if original_hook:
        original_invocation = (
            f"if [ -x \"{original_hook}\" ]; then\n"
            f"  if ! \"{original_hook}\" \"$@\"; then\n"
            f"    echo \"og-autopilot: existing {hook_name} hook failed; continuing to avoid blocking local flow.\" >&2\n"
            f"  fi\n"
            f"fi\n"
        )
    pending_script = _hook_pending_script(repo_root, hook_name)
    quality_gate_script = _hook_quality_gate_script(repo_root, hook_name)
    if hook_name == "pre-commit":
        hook_body = f"{original_invocation}{quality_gate_script}{pending_script}"
    else:
        hook_body = f"{pending_script}{original_invocation}"
    return (
        "#!/usr/bin/env bash\n"
        "# outcomegraph-autopilot-hook\n"
        "set -euo pipefail\n"
        "\n"
        'if [ "${OG_AUTOPILOT:-}" = "1" ]; then\n'
        "  exit 0\n"
        "fi\n"
        "\n"
        f'REPO_ROOT="{repo_root}"\n'
        f"{hook_body}"
        "exit 0\n"
    )


def _install_bridge_hooks(repo_root: str, hooks_dir: str) -> list[dict[str, str | None]]:
    os.makedirs(hooks_dir, exist_ok=True)
    backup_dir = os.path.join(repo_root, AUTOPILOT_BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)
    installed: list[dict[str, str | None]] = []

    for hook_name in AUTOPILOT_HOOKS:
        target = os.path.join(hooks_dir, hook_name)
        backup: str | None = None

        if os.path.lexists(target):
            if _is_managed_hook(target):
                backup_candidate = os.path.join(backup_dir, f"{hook_name}.orig")
                if os.path.isfile(backup_candidate):
                    backup = backup_candidate
                with open(target, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(_hook_script(repo_root, hook_name, backup))
                os.chmod(target, 0o755)
                installed.append({"hook": hook_name, "path": target, "backup": backup, "status": "updated-managed"})
                continue

            backup = os.path.join(backup_dir, f"{hook_name}.orig")
            if os.path.islink(target) or os.path.isfile(target):
                try:
                    shutil.copy2(target, backup)
                except OSError as err:
                    emit_error(f"failed to back up existing {hook_name} hook: {err}", "autopilot", EXIT_RUNTIME, False)
            else:
                emit_error(f"existing {hook_name} hook path is not a file", "autopilot", EXIT_RUNTIME, False)
            os.remove(target)

        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_hook_script(repo_root, hook_name, backup))
        os.chmod(target, 0o755)
        installed.append({"hook": hook_name, "path": target, "backup": backup, "status": "installed"})

    return installed


def _autopilot_state_path(repo_root: str) -> str:
    return os.path.join(repo_root, AUTOPILOT_STATE_FILE)


def _cleanup_directory_if_empty(path: str) -> None:
    try:
        if not os.path.isdir(path):
            return
        if os.listdir(path):
            return
        os.rmdir(path)
    except OSError:
        return


def _disable_autopilot(session_id: str | None = None) -> dict[str, object]:
    repo_root = _git_root()
    state_path = _autopilot_state_path(repo_root)
    state = _read_json_file(state_path)
    session = _session_from_payload(state.get("session")) if isinstance(state, dict) else None
    resume_error = _validate_resumed_session("autopilot disable", session_id, session)
    if resume_error is not None:
        return {
            **resume_error,
            "options": {"session_id": session_id},
            "subcommand": "disable",
            "installed_hooks": [],
            "state_present": isinstance(state, dict),
        }

    if not isinstance(state, dict):
        return {
            "status": "ok",
            "command": "autopilot",
            "subcommand": "disable",
            "options": {"session_id": session_id},
            "installed_hooks": [],
            "state_present": False,
            "restored_core_hooks_path": _hooks_path(repo_root),
            "message": "No autopilot state found; nothing to disable.",
        }

    disabled_hooks: list[dict[str, str]] = []
    for raw_hook in state.get("installed_hooks", []):
        if not isinstance(raw_hook, dict):
            continue
        hook_name = raw_hook.get("hook")
        path = raw_hook.get("path")
        if not isinstance(path, str):
            continue
        backup = raw_hook.get("backup")

        status: list[str] = []
        target_restored = False
        if os.path.lexists(path):
            if _is_managed_hook(path):
                try:
                    os.remove(path)
                    status.append("removed")
                except OSError as exc:
                    emit_error(f"failed to remove managed hook '{path}': {exc}", "autopilot", EXIT_RUNTIME, False)
            else:
                status.append("preserved-non-autopilot")
        else:
            status.append("missing")

        if isinstance(backup, str) and os.path.isfile(backup):
            if os.path.lexists(path):
                status.append("backup-saved")
            else:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    shutil.move(backup, path)
                    target_restored = True
                    status.append("restored-backup")
                except OSError as exc:
                    emit_error(f"failed to restore backup for '{path}': {exc}", "autopilot", EXIT_RUNTIME, False)
        else:
            status.append("no-backup")

        disabled_hooks.append(
            {
                "hook": hook_name if isinstance(hook_name, str) else "",
                "path": path,
                "status": ",".join(status),
                "restored": target_restored,
            }
        )

    if "previous_core_hooks_path" in state:
        previous_core_hooks_path = state.get("previous_core_hooks_path")
        hooks_path = previous_core_hooks_path if isinstance(previous_core_hooks_path, str) else None
        _set_hooks_path(repo_root, hooks_path)
    else:
        hooks_path = _hooks_path(repo_root)

    try:
        os.remove(state_path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        emit_error(f"failed to remove autopilot state file: {exc}", "autopilot", EXIT_RUNTIME, False)

    _cleanup_directory_if_empty(os.path.join(repo_root, AUTOPILOT_BACKUP_DIR))
    _cleanup_directory_if_empty(os.path.join(repo_root, AUTOPILOT_MANAGED_HOOK_DIR))
    disabled_session = _set_session_state(session, SESSION_STATE_DISABLED, refresh_expiry=True)

    return {
        "status": "ok",
        "command": "autopilot",
        "subcommand": "disable",
        "options": {"session_id": session_id},
        "installed_hooks": disabled_hooks,
        "state_present": True,
        "restored_core_hooks_path": hooks_path,
        "session": disabled_session,
        "session_id": disabled_session.get("session_id") if isinstance(disabled_session, dict) else None,
        "message": "autopilot disable command executed.",
    }


def _confirm(message: str) -> bool:
    if not sys.stdin.isatty():
        return False
    while True:
        try:
            reply = input(f"{message} [y/N]: ").strip().lower()
        except EOFError:
            return False
        if reply in {"", "n", "no"}:
            return False
        if reply in {"y", "yes"}:
            return True
        print("Please answer y or n.")


def _init_autopilot(
    force_hooks_path: bool,
    confirmed: bool = False,
    *,
    non_interactive: bool = False,
    output_json: bool = False,
) -> dict[str, object]:
    repo_root = _git_root()
    state_path = os.path.join(repo_root, AUTOPILOT_STATE_FILE)
    existing_state = _read_json_file(state_path)
    existing_session = _session_from_payload(existing_state.get("session")) if isinstance(existing_state, dict) else None

    existing_path = _hooks_path(repo_root)
    mode = "bridge-existing"
    target = existing_path
    wrote_config = False

    if existing_path is None:
        target = AUTOPILOT_MANAGED_HOOK_DIR
        mode = "set-managed-path"
        _set_hooks_path(repo_root, target)
        wrote_config = True
    elif existing_path != AUTOPILOT_MANAGED_HOOK_DIR:
        if force_hooks_path and not confirmed:
            if non_interactive:
                emit_error(
                    "autopilot init requires --yes with --force-hooks-path when --non-interactive is set",
                    "autopilot",
                    EXIT_USAGE,
                    output_json,
                )
            emit_error(
                f"autopilot init requires --yes to replace existing core.hooksPath '{existing_path}'",
                "autopilot",
                EXIT_USAGE,
                output_json,
            )
        if force_hooks_path:
            target = AUTOPILOT_MANAGED_HOOK_DIR
            mode = "force-managed-path"
            _set_hooks_path(repo_root, target)
            wrote_config = True

    resolved_target = _resolve_path(repo_root, target)
    installed = _install_bridge_hooks(repo_root, resolved_target)

    state = {
        "version": 1,
        "installed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "repo_root": repo_root,
        "previous_core_hooks_path": existing_path,
        "installed_core_hooks_path": target if wrote_config else existing_path,
        "mode": mode,
        "force_hooks_path": force_hooks_path,
        "hooks_dir": target,
        "installed_hooks": installed,
        "session": _set_session_state(existing_session, SESSION_STATE_INSTALLED)
        if isinstance(existing_session, dict)
        else _build_session_record(
            SESSION_KIND_AUTOPILOT,
            SESSION_LIFECYCLE_RESUMABLE,
            SESSION_STATE_INSTALLED,
            resume_command="og autopilot disable --session-id <session_id>",
        ),
    }

    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)

    return {
        "status": "ok",
        "command": "autopilot",
        "subcommand": "init",
        "options": {"force_hooks_path": force_hooks_path},
        "state": state,
        "session": state.get("session"),
        "session_id": state.get("session", {}).get("session_id") if isinstance(state.get("session"), dict) else None,
        "message": "autopilot init complete",
    }


def _daemon_service_dir(repo_root: str) -> str:
    return os.path.join(repo_root, DAEMON_SERVICE_DIR)


def _daemon_script_path(repo_root: str) -> str:
    return os.path.join(_daemon_service_dir(repo_root), os.path.basename(DAEMON_SERVICE_SCRIPT))


def _daemon_state_path(repo_root: str) -> str:
    return os.path.join(_daemon_service_dir(repo_root), os.path.basename(DAEMON_SERVICE_STATE))


def _daemon_log_path(repo_root: str) -> str:
    return os.path.join(_daemon_service_dir(repo_root), os.path.basename(DAEMON_SERVICE_LOG))


def _daemon_read_state(repo_root: str) -> dict[str, object]:
    payload = _read_json_file(_daemon_state_path(repo_root))
    return payload if isinstance(payload, dict) else {}


def _daemon_write_state(repo_root: str, state: dict[str, object]) -> None:
    _daemon_state_dir = _daemon_service_dir(repo_root)
    os.makedirs(_daemon_state_dir, exist_ok=True)
    _write_json_file(_daemon_state_path(repo_root), state)


def _daemon_signal_stop(_sig: int, _frame) -> None:
    global _DAEMON_STOP_REQUESTED
    _DAEMON_STOP_REQUESTED = True


def _daemon_running(pid: object) -> bool:
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _current_python_bin() -> str:
    executable = str(sys.executable or "").strip()
    return executable or "python3"


def _daemon_build_script(repo_root: str) -> str:
    quoted_repo_root = shlex.quote(repo_root)
    python_bin = shlex.quote(_current_python_bin())
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "\n"
        f"REPO_ROOT={quoted_repo_root}\n"
        f"PYTHON_BIN={python_bin}\n"
        "\n"
        "cd \"$REPO_ROOT\"\n"
        'export OG_AUTOPILOT="1"\n'
        'exec "$PYTHON_BIN" -m og daemon run "$@"\n'
    )


def _daemon_install() -> dict[str, object]:
    repo_root = _git_root()
    script_path = _daemon_script_path(repo_root)
    state_path = _daemon_state_path(repo_root)
    log_path = _daemon_log_path(repo_root)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)

    with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_daemon_build_script(repo_root))
    os.chmod(script_path, 0o755)

    state = _daemon_read_state(repo_root)
    session = _session_from_payload(state.get("session"))
    if not isinstance(session, dict) or _session_is_expired(session):
        session = _build_session_record(
            SESSION_KIND_DAEMON,
            SESSION_LIFECYCLE_RESUMABLE,
            SESSION_STATE_INSTALLED,
            resume_command="og daemon status --session-id <session_id>",
        )
    elif not bool(state.get("running")):
        session = _set_session_state(session, SESSION_STATE_INSTALLED, refresh_expiry=True)
    state.update(
        {
            "status": "installed",
            "installed": True,
            "installed_at": _utc_timestamp(),
            "script_path": script_path,
            "state_path": state_path,
            "log_path": log_path,
            "updated_at": _utc_timestamp(),
            "watch_interval_seconds": DAEMON_WATCH_INTERVAL_SECONDS,
            "runtime": {
                "watch_interval_seconds": DAEMON_WATCH_INTERVAL_SECONDS,
            },
            "session": session,
        }
    )
    _daemon_write_state(repo_root, state)
    return {
        "status": "ok",
        "command": "daemon",
        "subcommand": "install",
        "options": {},
        "session": session,
        "session_id": session.get("session_id") if isinstance(session, dict) else None,
        "runtime": {
            "watch_interval_seconds": DAEMON_WATCH_INTERVAL_SECONDS,
            "script": script_path,
            "log_path": log_path,
        },
        "message": "daemon install script written.",
    }


def _daemon_is_installed(repo_root: str) -> bool:
    return os.path.exists(_daemon_script_path(repo_root))


def _daemon_running_state(repo_root: str) -> tuple[bool, dict[str, object]]:
    state = _daemon_read_state(repo_root)
    pid = state.get("pid")
    if isinstance(pid, int):
        running = _daemon_running(pid)
    elif isinstance(pid, str) and pid.isdigit():
        pid_value = int(pid)
        running = _daemon_running(pid_value)
        state["pid"] = pid_value
    else:
        running = False
    return running, state


def _daemon_wait_for_exit(pid: int, timeout_seconds: int = 5) -> bool:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        if not _daemon_running(pid):
            return True
        time.sleep(0.2)
    return False


def _daemon_stop_process(pid: int) -> bool:
    if not _daemon_running(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False

    if _daemon_wait_for_exit(pid):
        return True

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False

    if _daemon_wait_for_exit(pid, timeout_seconds=2):
        return True

    return not _daemon_running(pid)


def _daemon_collect_watched_changes(repo_root: str) -> list[str]:
    result = _run_git(repo_root, ["status", "--porcelain=v1", "-z"])
    if result.returncode != 0:
        return []
    entries = result.stdout.split("\0")
    changes: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry or len(entry) < 4 or entry[2] != " ":
            continue
        status = entry[:2]
        raw_path = entry[3:]
        if ("R" in status or "C" in status) and i < len(entries):
            renamed_path = entries[i]
            if renamed_path:
                raw_path = renamed_path
                i += 1
        elif " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        if not raw_path:
            continue
        candidate = _normalize_repo_relative_path(raw_path)
        if not candidate:
            continue
        if any(candidate.startswith(prefix) for prefix in DAEMON_WATCH_IGNORE_PREFIXES):
            continue
        changes.append(candidate)
    return sorted(set(changes))


def _daemon_changes_signature(changed: list[str]) -> str:
    return _short_hash("\n".join(changed), 16) if changed else ""


def _daemon_status_payload(repo_root: str, running: bool, state: dict[str, object]) -> dict[str, object]:
    installed = _daemon_is_installed(repo_root)
    if not installed:
        state.setdefault("installed", False)
        state.setdefault("status", "not_installed")
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    session = _session_from_payload(state.get("session"), now=now)
    runtime = {
        "installed": installed,
        "running": running,
        "pid": state.get("pid"),
        "script_path": _daemon_script_path(repo_root),
        "log_path": _daemon_log_path(repo_root),
        "watch_interval_seconds": DAEMON_WATCH_INTERVAL_SECONDS,
        "session": session,
        "state": state,
    }
    message = "daemon not installed."
    status = "ok" if installed else "warn"
    if installed and running:
        message = f"daemon running (pid={runtime['pid']})."
    elif installed and isinstance(session, dict) and str(session.get("state") or "") == SESSION_STATE_EXPIRED:
        message = f"daemon session '{session.get('session_id')}' expired."
        status = "warn"
    elif installed:
        message = "daemon installed but not running."
    return {
        "status": status,
        "command": "daemon",
        "subcommand": "status",
        "options": {},
        "session": session,
        "session_id": session.get("session_id") if isinstance(session, dict) else None,
        "runtime": runtime,
        "message": message,
    }


def _daemon_write_run_log(repo_root: str, payload: dict[str, object]) -> None:
    log_path = _daemon_log_path(repo_root)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        pass


def _daemon_run_sync(repo_root: str) -> dict[str, object]:
    started = time.perf_counter()
    env = os.environ.copy()
    env["OG_AUTOPILOT"] = "1"
    cmd = [_current_python_bin(), "-m", "og", "sync", "--json"]
    try:
        process = subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=DAEMON_SYNC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = {
            "status": "error",
            "command": "sync",
            "message": f"sync subprocess timed out after {DAEMON_SYNC_TIMEOUT_SECONDS}s",
            "runtime": {
                "daemon_sync_exit_code": None,
                "duration_ms": duration_ms,
                "timed_out": True,
            },
        }
        _daemon_write_run_log(repo_root, payload)
        return payload
    except OSError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = {
            "status": "error",
            "command": "sync",
            "message": f"sync subprocess failed to start: {exc}",
            "runtime": {
                "daemon_sync_exit_code": None,
                "duration_ms": duration_ms,
            },
        }
        _daemon_write_run_log(repo_root, payload)
        return payload
    duration_ms = int((time.perf_counter() - started) * 1000)

    raw_stdout = process.stdout if isinstance(process.stdout, str) else ""
    parsed = _extract_json_object(raw_stdout) if raw_stdout.strip() else {}
    if not isinstance(parsed, dict):
        parsed = {}
    parse_error_output = (
        process.stderr.strip()
        if isinstance(process.stderr, str)
        else ""
    )
    if not parse_error_output and raw_stdout.strip() and not parsed:
        parse_error_output = raw_stdout.strip()

    if process.returncode != 0:
        parsed["status"] = "error"
    elif not parsed.get("status"):
        message = parse_error_output or "sync subprocess returned malformed JSON payload"
        parsed["status"] = "error"
        message_value = parsed.get("message")
        if not isinstance(message_value, str) or not message_value.strip():
            parsed["message"] = message
    status_value = str(parsed.get("status") or "").strip().lower()
    if status_value not in {"ok", "warn", "error"}:
        status_value = "error"
        message_value = parsed.get("message")
        if not isinstance(message_value, str) or not message_value.strip():
            parsed["message"] = "sync subprocess returned invalid status payload"
    parsed["status"] = status_value
    command_value = parsed.get("command")
    if not isinstance(command_value, str) or not command_value.strip():
        parsed["command"] = "sync"
    if str(parsed.get("status") or "").lower() == "error":
        message_value = parsed.get("message")
        if not isinstance(message_value, str) or not message_value.strip():
            parsed["message"] = parse_error_output or "sync subprocess failed"
    parsed["runtime"] = {
        "daemon_sync_exit_code": process.returncode,
        "duration_ms": duration_ms,
    }
    _daemon_write_run_log(repo_root, parsed)
    return parsed


def _daemon_start(session_id: str | None = None) -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
    session = _session_from_payload(state.get("session"))
    resume_error = _validate_resumed_session("daemon start", session_id, session)
    if resume_error is not None:
        return {
            **resume_error,
            "options": {"session_id": session_id},
            "subcommand": "start",
            "runtime": {"installed": _daemon_is_installed(repo_root), "running": running, "pid": state.get("pid")},
        }
    if not _daemon_is_installed(repo_root):
        _daemon_install()
        running, state = _daemon_running_state(repo_root)
        session = _session_from_payload(state.get("session"))
    if running:
        if not isinstance(session, dict):
            session = _build_session_record(
                SESSION_KIND_DAEMON,
                SESSION_LIFECYCLE_RESUMABLE,
                SESSION_STATE_ACTIVE,
                ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
                resume_command="og daemon status --session-id <session_id>",
            )
        else:
            session = _set_session_state(
                session,
                SESSION_STATE_ACTIVE,
                ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
                refresh_expiry=True,
            )
        state["status"] = "running"
        state["running"] = True
        state["session"] = session
        _daemon_write_state(repo_root, state)
        return _daemon_status_payload(repo_root, True, state)

    script_path = _daemon_script_path(repo_root)
    log_path = _daemon_log_path(repo_root)
    process: subprocess.Popen[bytes] | None = None
    try:
        with open(log_path, "a", encoding="utf-8") as _:
            pass
        process = subprocess.Popen(
            [script_path],
            cwd=repo_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        emit_error(f"failed to start daemon: {exc}", "daemon", EXIT_RUNTIME, False)
    if process is None:
        raise RuntimeError("failed to start daemon process")

    if not isinstance(session, dict) or _session_is_expired(session):
        session = _build_session_record(
            SESSION_KIND_DAEMON,
            SESSION_LIFECYCLE_RESUMABLE,
            SESSION_STATE_ACTIVE,
            ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
            resume_command="og daemon status --session-id <session_id>",
        )
    else:
        session = _set_session_state(
            session,
            SESSION_STATE_ACTIVE,
            ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
            refresh_expiry=True,
        )
    state.update(
        {
            "status": "running",
            "running": True,
            "pid": process.pid,
            "started_at": _utc_timestamp(),
            "last_started_at": _utc_timestamp(),
            "last_restart_at": _utc_timestamp(),
            "session": session,
        }
    )
    _daemon_write_state(repo_root, state)
    return {
        "status": "ok",
        "command": "daemon",
        "subcommand": "start",
        "options": {"session_id": session_id},
        "session": session,
        "session_id": session.get("session_id") if isinstance(session, dict) else None,
        "runtime": {
            "installed": True,
            "running": True,
            "pid": process.pid,
            "script_path": script_path,
            "log_path": log_path,
        },
        "message": "daemon started.",
    }


def _daemon_stop(session_id: str | None = None) -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
    session = _session_from_payload(state.get("session"))
    resume_error = _validate_resumed_session("daemon stop", session_id, session)
    if resume_error is not None:
        return {
            **resume_error,
            "options": {"session_id": session_id},
            "subcommand": "stop",
            "runtime": {"installed": _daemon_is_installed(repo_root), "running": running, "pid": state.get("pid")},
        }
    pid = state.get("pid")
    stopped = True
    if running and isinstance(pid, int):
        stopped = _daemon_stop_process(pid)
    if not running and isinstance(pid, str) and pid.isdigit():
        pid_value = int(pid)
        stopped = _daemon_stop_process(pid_value)
    elif not running and isinstance(pid, int):
        stopped = True

    state.update(
        {
            "status": "stopped" if stopped else "error",
            "running": False,
            "last_stopped_at": _utc_timestamp(),
            "stopped": stopped,
            "session": _set_session_state(session, SESSION_STATE_STOPPED, refresh_expiry=True),
        }
    )
    state.pop("pid", None)
    _daemon_write_state(repo_root, state)

    return {
        "status": "ok" if stopped else "error",
        "command": "daemon",
        "subcommand": "stop",
        "options": {"session_id": session_id},
        "session": state.get("session"),
        "session_id": state.get("session", {}).get("session_id") if isinstance(state.get("session"), dict) else None,
        "runtime": {
            "installed": _daemon_is_installed(repo_root),
            "running": False,
            "pid": pid,
        },
        "message": "daemon stopped." if stopped else "failed to stop daemon process.",
    }


def _daemon_status(session_id: str | None = None) -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
    session = _session_from_payload(state.get("session"))
    resume_error = _validate_resumed_session("daemon status", session_id, session)
    if resume_error is not None:
        return {
            **resume_error,
            "options": {"session_id": session_id},
            "subcommand": "status",
            "runtime": {"installed": _daemon_is_installed(repo_root), "running": running, "pid": state.get("pid")},
        }
    if running:
        if not isinstance(session, dict):
            session = _build_session_record(
                SESSION_KIND_DAEMON,
                SESSION_LIFECYCLE_RESUMABLE,
                SESSION_STATE_ACTIVE,
                ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
                resume_command="og daemon status --session-id <session_id>",
            )
        else:
            session = _set_session_state(
                session,
                SESSION_STATE_ACTIVE,
                ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
                refresh_expiry=True,
            )
        state["session"] = session
    elif isinstance(session, dict) and _session_is_expired(session):
        state["session"] = _set_session_state(session, SESSION_STATE_EXPIRED)
    if running:
        state["status"] = "running"
    elif _daemon_is_installed(repo_root):
        state["status"] = "installed"
    else:
        state["status"] = "not_installed"
    if running:
        state["running"] = True
        state["last_check_at"] = _utc_timestamp()
    _daemon_write_state(repo_root, state)
    payload = _daemon_status_payload(repo_root, running, state)
    payload["options"] = {"session_id": session_id}
    return payload


def _daemon_run() -> int:
    repo_root = _git_root()
    last_signature = ""
    running, state = _daemon_running_state(repo_root)
    state_pid = state.get("pid")
    if running and state_pid != os.getpid():
        emit_error(
            "daemon run cannot start while daemon process is already managed",
            "daemon",
            EXIT_RUNTIME,
            False,
            error_code=SESSION_CONTENDED_CODE,
        )

    session = _session_from_payload(state.get("session"))
    if not isinstance(session, dict) or _session_is_expired(session):
        session = _build_session_record(
            SESSION_KIND_DAEMON,
            SESSION_LIFECYCLE_RESUMABLE,
            SESSION_STATE_ACTIVE,
            ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
            resume_command="og daemon status --session-id <session_id>",
        )
    else:
        session = _set_session_state(
            session,
            SESSION_STATE_ACTIVE,
            ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
            refresh_expiry=True,
        )

    state.update(
        {
            "status": "running",
            "running": True,
            "last_started_at": _utc_timestamp(),
            "pid": os.getpid(),
            "last_poll_at": _utc_timestamp(),
            "session": session,
        }
    )
    _daemon_write_state(repo_root, state)

    global _DAEMON_STOP_REQUESTED
    _DAEMON_STOP_REQUESTED = False
    signal.signal(signal.SIGTERM, _daemon_signal_stop)
    signal.signal(signal.SIGINT, _daemon_signal_stop)

    while not _DAEMON_STOP_REQUESTED:
        state = _daemon_read_state(repo_root)
        changed = _daemon_collect_watched_changes(repo_root)
        signature = _daemon_changes_signature(changed)
        trigger = []
        try:
            work_state = _read_work_state(repo_root)
            if bool(work_state.get("pending")):
                trigger.append("pending")
        except Exception:
            work_state = {"pending": False}

        if changed and signature != last_signature:
            trigger.append("filesystem")

        sync_payload: dict[str, object] = {}
        if trigger:
            sync_payload = _daemon_run_sync(repo_root)
            state["last_sync"] = {
                "at": _utc_timestamp(),
                "reason": sorted(set(trigger)),
                "status": sync_payload.get("status"),
                "run_id": sync_payload.get("run_id"),
                "session_id": sync_payload.get("session_id"),
            }
            state["last_sync_status"] = sync_payload.get("status")
        else:
            state["last_sync_status"] = "idle"
            state["last_sync"] = None

        state.update(
            {
                "status": "running",
                "running": True,
                "last_poll_at": _utc_timestamp(),
                "last_signature": signature,
                "last_changed_count": len(changed),
                "last_pending": bool(work_state.get("pending")),
                "last_trigger": trigger,
                "last_sync": state.get("last_sync"),
                "session": _set_session_state(
                    _session_from_payload(state.get("session")) or session,
                    SESSION_STATE_ACTIVE,
                    ttl_seconds=DAEMON_SESSION_STALE_SECONDS,
                    refresh_expiry=True,
                ),
            }
        )
        _daemon_write_state(repo_root, state)
        last_signature = signature

        if not _DAEMON_STOP_REQUESTED:
            time.sleep(DAEMON_WATCH_INTERVAL_SECONDS)

    state["status"] = "stopped"
    state["running"] = False
    state["last_stopped_at"] = _utc_timestamp()
    state["session"] = _set_session_state(_session_from_payload(state.get("session")) or session, SESSION_STATE_STOPPED, refresh_expiry=True)
    state.pop("pid", None)
    _daemon_write_state(repo_root, state)
    return EXIT_SUCCESS


def parse_command_flags(
    args: list[str],
    command: str,
    allow_changed: bool,
    allow_profile: bool,
    allow_mode: bool,
    output_json: bool,
    allow_force_hooks_path: bool = False,
    allow_force_full_sync: bool = False,
    allow_capsule_filter: bool = False,
    allow_ref_filter: bool = False,
    allow_certificate_filter: bool = False,
    allow_output_controls: bool = False,
    allow_yes: bool = False,
    allow_session_id: bool = False,
    allow_validate: bool = False,
    allow_dry_run: bool = False,
    allow_recovery_controls: bool = False,
    runtime_defaults: dict[str, object] | None = None,
    default_strict: bool = False,
) -> tuple[dict[str, object], list[str]]:
    changed = False
    resolved_defaults = runtime_defaults or {}
    resolved_sources = dict(cast(dict[str, str], resolved_defaults.get("resolved_from") or {}))
    profile = str(resolved_defaults.get("profile")).strip() if allow_profile and resolved_defaults.get("profile") else None
    profile_source = resolved_sources.get("profile", "built-in") if allow_profile else None
    mode = str(resolved_defaults.get("mode")).strip() if allow_mode and resolved_defaults.get("mode") else None
    mode_source = resolved_sources.get("mode", "built-in") if allow_mode else None
    force_hooks_path = False
    force_full_sync = False
    capsule_filters: list[str] = []
    ref_filters: list[str] = []
    certificate_filters: list[str] = []
    strict = bool(default_strict)
    output_mode = str(resolved_defaults.get("output_mode") or (OUTPUT_MODE_JSON if output_json else OUTPUT_MODE_HUMAN))
    output_source = resolved_sources.get("output_mode", "flag:--json" if output_json else "built-in")
    output_json = output_mode != OUTPUT_MODE_HUMAN
    fields: list[str] | None = None
    limit: int | None = None
    confirmed = False
    session_id: str | None = None
    offset = 0
    validate_only = False
    dry_run = False
    max_retries = 0
    timeout_seconds: int | None = None

    def normalize_identifier_csv(raw_value: str, field: str) -> list[str]:
        try:
            return _normalize_agent_identifier_csv(raw_value, field)
        except ValueError as exc:
            emit_error(str(exc), command, EXIT_USAGE, output_json)
            raise

    def normalize_output_fields(raw_value: str, field: str) -> list[str]:
        try:
            return _parse_csv_fields(raw_value, field)
        except ValueError as exc:
            emit_error(f"invalid {field}: {exc}", command, EXIT_USAGE, output_json)
            raise

    def parse_output_mode(raw_value: str) -> str:
        value = raw_value.lower().strip()
        if value not in {OUTPUT_MODE_HUMAN, OUTPUT_MODE_JSON, OUTPUT_MODE_JSONL}:
            emit_error(
                f"invalid --output value '{raw_value}', expected one of: {OUTPUT_MODE_HUMAN}, {OUTPUT_MODE_JSON}, {OUTPUT_MODE_JSONL}",
                command,
                EXIT_USAGE,
                output_json,
            )
        return value

    def parse_output_offset(raw_value: str) -> int:
        try:
            return parse_int_option(raw_value, "offset")
        except ValueError as exc:
            emit_error(f"invalid --offset value: {exc}", command, EXIT_USAGE, output_json)
            raise

    def parse_output_limit(raw_value: str) -> int:
        try:
            parsed = parse_int_option(raw_value, "limit")
        except ValueError as exc:
            emit_error(f"invalid --limit value: {exc}", command, EXIT_USAGE, output_json)
            raise
        if parsed == 0:
            emit_error("invalid --limit value: limit must be greater than 0", command, EXIT_USAGE, output_json)
        return parsed

    def parse_max_retries_value(raw_value: str) -> int:
        try:
            parsed = parse_int_option(raw_value, "max-retries")
        except ValueError as exc:
            emit_error(f"invalid --max-retries value: {exc}", command, EXIT_USAGE, output_json)
            raise
        if parsed < 0:
            emit_error("invalid --max-retries value: max-retries must be >= 0", command, EXIT_USAGE, output_json)
        if parsed > RECOVERY_MAX_RETRIES_LIMIT:
            emit_error(
                f"invalid --max-retries value: max-retries must be <= {RECOVERY_MAX_RETRIES_LIMIT}",
                command,
                EXIT_USAGE,
                output_json,
            )
        return parsed

    def parse_timeout_value(raw_value: str) -> int:
        try:
            parsed = parse_int_option(raw_value, "timeout")
        except ValueError as exc:
            emit_error(f"invalid --timeout value: {exc}", command, EXIT_USAGE, output_json)
            raise
        if parsed <= 0:
            emit_error("invalid --timeout value: timeout must be greater than 0", command, EXIT_USAGE, output_json)
        return parsed

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": command,
                    "status": "ok",
                    "message": _help_for_command(command),
                },
                output_json,
                command,
            )
            sys.exit(EXIT_SUCCESS)
        if arg == "--json":
            output_json = True
            output_mode = OUTPUT_MODE_JSON
            output_source = "flag:--json"
            i += 1
            continue
        if arg.startswith("--json="):
            try:
                output_json = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --json value: {exc}", command, EXIT_USAGE, output_json)
            output_mode = OUTPUT_MODE_JSON if output_json else OUTPUT_MODE_HUMAN
            output_source = "flag:--json" if output_json else "flag:--json=false"
            i += 1
            continue
        if arg == "--output":
            if not allow_output_controls:
                emit_error(f"{command} does not accept --output", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --output", command, EXIT_USAGE, output_json)
            output_mode = parse_output_mode(args[i + 1])
            output_json = output_mode != OUTPUT_MODE_HUMAN
            output_source = "flag:--output"
            i += 2
            continue
        if arg.startswith("--output="):
            if not allow_output_controls:
                emit_error(f"{command} does not accept --output", command, EXIT_USAGE, output_json)
            output_mode = parse_output_mode(arg.split("=", 1)[1])
            output_json = output_mode != OUTPUT_MODE_HUMAN
            output_source = "flag:--output"
            i += 1
            continue
        if arg == "--fields":
            if not allow_output_controls:
                emit_error(f"{command} does not accept --fields", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --fields", command, EXIT_USAGE, output_json)
            fields = normalize_output_fields(args[i + 1], "--fields")
            i += 2
            continue
        if arg.startswith("--fields="):
            if not allow_output_controls:
                emit_error(f"{command} does not accept --fields", command, EXIT_USAGE, output_json)
            fields = normalize_output_fields(arg.split("=", 1)[1], "--fields")
            i += 1
            continue
        if arg == "--limit":
            if not allow_output_controls:
                emit_error(f"{command} does not accept --limit", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --limit", command, EXIT_USAGE, output_json)
            limit = parse_output_limit(args[i + 1])
            i += 2
            continue
        if arg.startswith("--limit="):
            if not allow_output_controls:
                emit_error(f"{command} does not accept --limit", command, EXIT_USAGE, output_json)
            limit = parse_output_limit(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--offset":
            if not allow_output_controls:
                emit_error(f"{command} does not accept --offset", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --offset", command, EXIT_USAGE, output_json)
            offset = parse_output_offset(args[i + 1])
            i += 2
            continue
        if arg.startswith("--offset="):
            if not allow_output_controls:
                emit_error(f"{command} does not accept --offset", command, EXIT_USAGE, output_json)
            offset = parse_output_offset(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--strict":
            strict = True
            i += 1
            continue
        if arg.startswith("--strict="):
            try:
                strict = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --strict value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--changed":
            if not allow_changed:
                emit_error(f"{command} does not accept --changed", command, EXIT_USAGE, output_json)
            changed = True
            i += 1
            continue
        if arg.startswith("--changed="):
            if not allow_changed:
                emit_error(f"{command} does not accept --changed", command, EXIT_USAGE, output_json)
            try:
                changed = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --changed value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--yes":
            if not allow_yes:
                emit_error(f"{command} does not accept --yes", command, EXIT_USAGE, output_json)
            confirmed = True
            i += 1
            continue
        if arg.startswith("--yes="):
            if not allow_yes:
                emit_error(f"{command} does not accept --yes", command, EXIT_USAGE, output_json)
            try:
                confirmed = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --yes value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--session-id":
            if not allow_session_id:
                emit_error(f"{command} does not accept --session-id", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --session-id", command, EXIT_USAGE, output_json)
            try:
                session_id = _normalize_session_id(args[i + 1], "--session-id")
            except ValueError as exc:
                emit_error(str(exc), command, EXIT_USAGE, output_json)
            i += 2
            continue
        if arg.startswith("--session-id="):
            if not allow_session_id:
                emit_error(f"{command} does not accept --session-id", command, EXIT_USAGE, output_json)
            try:
                session_id = _normalize_session_id(arg.split("=", 1)[1], "--session-id")
            except ValueError as exc:
                emit_error(str(exc), command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--validate":
            if not allow_validate:
                emit_error(f"{command} does not accept --validate", command, EXIT_USAGE, output_json)
            validate_only = True
            i += 1
            continue
        if arg.startswith("--validate="):
            if not allow_validate:
                emit_error(f"{command} does not accept --validate", command, EXIT_USAGE, output_json)
            try:
                validate_only = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --validate value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--dry-run":
            if not allow_dry_run:
                emit_error(f"{command} does not accept --dry-run", command, EXIT_USAGE, output_json)
            dry_run = True
            i += 1
            continue
        if arg.startswith("--dry-run="):
            if not allow_dry_run:
                emit_error(f"{command} does not accept --dry-run", command, EXIT_USAGE, output_json)
            try:
                dry_run = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --dry-run value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--max-retries":
            if not allow_recovery_controls:
                emit_error(f"{command} does not accept --max-retries", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --max-retries", command, EXIT_USAGE, output_json)
            max_retries = parse_max_retries_value(args[i + 1])
            i += 2
            continue
        if arg.startswith("--max-retries="):
            if not allow_recovery_controls:
                emit_error(f"{command} does not accept --max-retries", command, EXIT_USAGE, output_json)
            max_retries = parse_max_retries_value(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--timeout":
            if not allow_recovery_controls:
                emit_error(f"{command} does not accept --timeout", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --timeout", command, EXIT_USAGE, output_json)
            timeout_seconds = parse_timeout_value(args[i + 1])
            i += 2
            continue
        if arg.startswith("--timeout="):
            if not allow_recovery_controls:
                emit_error(f"{command} does not accept --timeout", command, EXIT_USAGE, output_json)
            timeout_seconds = parse_timeout_value(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--profile":
            if not allow_profile:
                emit_error(f"{command} does not accept --profile", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --profile", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            if value not in PROFILE_VALUES:
                emit_error(
                    f"invalid --profile '{value}', expected one of: {', '.join(sorted(PROFILE_VALUES))}",
                    command,
                    EXIT_USAGE,
                    output_json,
                )
            profile = value
            profile_source = "flag:--profile"
            i += 2
            continue
        if arg.startswith("--profile="):
            if not allow_profile:
                emit_error(f"{command} does not accept --profile", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            if value not in PROFILE_VALUES:
                emit_error(
                    f"invalid --profile '{value}', expected one of: {', '.join(sorted(PROFILE_VALUES))}",
                    command,
                    EXIT_USAGE,
                    output_json,
                )
            profile = value
            profile_source = "flag:--profile"
            i += 1
            continue
        if arg == "--mode":
            if not allow_mode:
                emit_error(f"{command} does not accept --mode", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --mode", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            if value not in MODE_VALUES:
                emit_error(
                    f"invalid --mode '{value}', expected one of: {', '.join(sorted(MODE_VALUES))}",
                    command,
                    EXIT_USAGE,
                    output_json,
                )
            mode = value
            mode_source = "flag:--mode"
            i += 2
            continue
        if arg.startswith("--mode="):
            if not allow_mode:
                emit_error(f"{command} does not accept --mode", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            if value not in MODE_VALUES:
                emit_error(
                    f"invalid --mode '{value}', expected one of: {', '.join(sorted(MODE_VALUES))}",
                    command,
                    EXIT_USAGE,
                    output_json,
                )
            mode = value
            mode_source = "flag:--mode"
            i += 1
            continue
        if arg == "--capsule":
            if not allow_capsule_filter:
                emit_error(f"{command} does not accept --capsule", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --capsule", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            capsule_filters.extend(normalize_identifier_csv(value, "capsule"))
            i += 2
            continue
        if arg.startswith("--capsule="):
            if not allow_capsule_filter:
                emit_error(f"{command} does not accept --capsule", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            capsule_filters.extend(normalize_identifier_csv(value, "capsule"))
            i += 1
            continue
        if arg == "--ref":
            if not allow_ref_filter:
                emit_error(f"{command} does not accept --ref", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --ref", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            ref_filters.extend(normalize_identifier_csv(value, "ref"))
            i += 2
            continue
        if arg.startswith("--ref="):
            if not allow_ref_filter:
                emit_error(f"{command} does not accept --ref", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            ref_filters.extend(normalize_identifier_csv(value, "ref"))
            i += 1
            continue
        if arg == "--certificate":
            if not allow_certificate_filter:
                emit_error(f"{command} does not accept --certificate", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --certificate", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            certificate_filters.extend(normalize_identifier_csv(value, "certificate"))
            i += 2
            continue
        if arg.startswith("--certificate="):
            if not allow_certificate_filter:
                emit_error(f"{command} does not accept --certificate", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            certificate_filters.extend(normalize_identifier_csv(value, "certificate"))
            i += 1
            continue
        if arg == "--force-hooks-path":
            if not allow_force_hooks_path:
                emit_error(f"{command} does not accept --force-hooks-path", command, EXIT_USAGE, output_json)
            force_hooks_path = True
            i += 1
            continue
        if arg.startswith("--force-hooks-path="):
            if not allow_force_hooks_path:
                emit_error(f"{command} does not accept --force-hooks-path", command, EXIT_USAGE, output_json)
            try:
                force_hooks_path = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --force-hooks-path value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--force-full-sync":
            if not allow_force_full_sync:
                emit_error(f"{command} does not accept --force-full-sync", command, EXIT_USAGE, output_json)
            force_full_sync = True
            i += 1
            continue
        if arg.startswith("--force-full-sync="):
            if not allow_force_full_sync:
                emit_error(f"{command} does not accept --force-full-sync", command, EXIT_USAGE, output_json)
            try:
                force_full_sync = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --force-full-sync value: {exc}", command, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg.startswith("-"):
            emit_error(f"unknown option '{arg}' for {command}", command, EXIT_USAGE, output_json)
        emit_error(f"unexpected argument '{arg}' for {command}", command, EXIT_USAGE, output_json)

    if output_mode == OUTPUT_MODE_JSONL and not allow_output_controls:
        emit_error(f"{command} does not support output mode '{OUTPUT_MODE_JSONL}'", command, EXIT_USAGE, output_json)

    options: dict[str, object] = {
        "changed": changed,
        "profile": profile,
        "mode": mode,
        "force_hooks_path": force_hooks_path,
        "force_full_sync": force_full_sync,
        "output_mode": output_mode,
        "output_json": output_json,
        "strict": strict,
        "validate": validate_only,
        "dry_run": dry_run,
        "max_retries": max_retries,
        "timeout": timeout_seconds,
    }
    resolved_from: dict[str, object] = {"output_mode": output_source}
    if allow_profile:
        resolved_from["profile"] = profile_source or "built-in"
    if allow_mode:
        resolved_from["mode"] = mode_source or "built-in"
    if resolved_defaults.get("codex_home") is not None:
        resolved_from["codex_home"] = resolved_sources.get("codex_home", "unset")
    options["configuration"] = {
        "config_file": resolved_defaults.get("config_file"),
        "config_source": resolved_defaults.get("config_source"),
        "policy_file": resolved_defaults.get("policy_file"),
        "policy_source": resolved_defaults.get("policy_source"),
        "codex_home": resolved_defaults.get("codex_home"),
        "resolved_from": resolved_from,
    }
    if capsule_filters:
        options["capsule"] = capsule_filters
    if ref_filters:
        options["ref"] = ref_filters
    if certificate_filters:
        options["certificate"] = certificate_filters
    if fields is not None:
        options["fields"] = fields
    if limit is not None:
        options["limit"] = limit
    if offset:
        options["offset"] = offset
    if confirmed:
        options["yes"] = confirmed
    if session_id:
        options["session_id"] = session_id
    return options, []


def _clean_usage() -> str:
    return _help_for_command("clean")


def _parse_clean_flags(args: list[str], output_json: bool) -> dict[str, object]:
    scope = "runtime"
    dry_run = False
    confirmed = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "clean",
                    "status": "ok",
                    "message": _help_for_command("clean"),
                },
                output_json,
                "clean",
            )
            raise SystemExit(EXIT_SUCCESS)
        if arg == "--json":
            output_json = True
            i += 1
            continue
        if arg.startswith("--json="):
            try:
                output_json = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --json value: {exc}", "clean", EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--scope":
            if i + 1 >= len(args):
                emit_error("clean requires a value for --scope", "clean", EXIT_USAGE, output_json)
            scope = str(args[i + 1]).strip().lower()
            i += 2
            continue
        if arg.startswith("--scope="):
            scope = str(arg.split("=", 1)[1]).strip().lower()
            i += 1
            continue
        if arg == "--dry-run":
            dry_run = True
            i += 1
            continue
        if arg.startswith("--dry-run="):
            try:
                dry_run = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --dry-run value: {exc}", "clean", EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--yes":
            confirmed = True
            i += 1
            continue
        if arg.startswith("--yes="):
            try:
                confirmed = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --yes value: {exc}", "clean", EXIT_USAGE, output_json)
            i += 1
            continue
        emit_error(f"unknown option '{arg}' for clean", "clean", EXIT_USAGE, output_json)

    if scope not in CLEAN_SCOPES:
        emit_error(
            f"invalid --scope '{scope}', expected one of: runtime, generated, all",
            "clean",
            EXIT_USAGE,
            output_json,
        )
    if not dry_run and not confirmed:
        emit_error("clean requires --yes unless --dry-run is set", "clean", EXIT_USAGE, output_json)
    return {
        "scope": scope,
        "dry_run": dry_run,
        "yes": confirmed,
        "output_json": output_json,
    }


def _clean_targets_for_scope(scope: str) -> tuple[str, ...]:
    if scope == "runtime":
        return CLEAN_RUNTIME_TARGETS
    if scope == "generated":
        return CLEAN_GENERATED_TARGETS
    return CLEAN_ALL_TARGETS


def _remove_repo_target(repo_root: str, target: str) -> tuple[bool, str | None]:
    normalized = _normalize_repo_relative_path(str(target)).strip("/")
    if not normalized:
        return False, "invalid empty cleanup target"
    full_path = os.path.join(repo_root, normalized)
    repo_abs = os.path.abspath(repo_root)
    full_abs = os.path.abspath(full_path)
    if full_abs != repo_abs and not full_abs.startswith(repo_abs + os.sep):
        return False, "target resolves outside repository root"
    if not os.path.lexists(full_path):
        return False, None
    try:
        if os.path.islink(full_path) or os.path.isfile(full_path):
            os.remove(full_path)
        else:
            shutil.rmtree(full_path)
        return True, None
    except OSError as exc:
        return False, str(exc)


def _run_clean_job(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    scope = str(options.get("scope") or "runtime")
    dry_run = bool(options.get("dry_run"))
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    if scope == "all":
        if dry_run:
            warnings.append("dry-run: would stop daemon before cleanup")
            warnings.append("dry-run: would disable autopilot before cleanup")
        else:
            try:
                daemon_payload = _daemon_stop()
                if str(daemon_payload.get("status") or "").lower() == "error":
                    warnings.append(str(daemon_payload.get("message") or "daemon stop reported error"))
            except SystemExit as exc:
                errors.append(f"daemon stop failed with exit code {exc.code}")
            except Exception as exc:
                errors.append(f"daemon stop failed: {exc}")
            try:
                autopilot_payload = _disable_autopilot()
                if str(autopilot_payload.get("status") or "").lower() != "ok":
                    warnings.append(str(autopilot_payload.get("message") or "autopilot disable returned non-ok status"))
            except SystemExit as exc:
                errors.append(f"autopilot disable failed with exit code {exc.code}")
            except Exception as exc:
                errors.append(f"autopilot disable failed: {exc}")

    for target in sorted(set(_clean_targets_for_scope(scope))):
        normalized = _normalize_repo_relative_path(target).strip("/")
        full_path = os.path.join(repo_root, normalized)
        if not os.path.lexists(full_path):
            skipped.append(normalized)
            continue
        if dry_run:
            removed.append(normalized)
            continue
        removed_ok, error_message = _remove_repo_target(repo_root, normalized)
        if removed_ok:
            removed.append(normalized)
            continue
        if error_message is None:
            skipped.append(normalized)
            continue
        errors.append(f"{normalized}: {error_message}")

    status = "error" if errors else "ok"
    message = "cleanup completed."
    if dry_run:
        message = "cleanup dry-run completed."
    elif errors:
        message = "cleanup completed with errors."

    return {
        "status": status,
        "command": "clean",
        "scope": scope,
        "dry_run": dry_run,
        "options": options,
        "removed": sorted(set(removed)),
        "skipped": sorted(set(skipped)),
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "message": message,
    }


def _parse_optimize_prompts_flags(
    args: list[str],
    output_json: bool,
    default_strict: bool = False,
) -> dict[str, object]:
    strict = bool(default_strict)
    has_payload = False
    payload: dict[str, object] = {}
    flag_values: dict[str, object] = {}
    i = 0

    allowed_payload_fields = {"dataset", "candidate", "baseline", "metric", "min_improvement", "approve"}

    def normalize_dataset_input(raw_value: str, field: str) -> str:
        try:
            return _normalize_repo_relative_user_path(raw_value, field)
        except ValueError as exc:
            emit_error(str(exc), "optimize", EXIT_USAGE, output_json)
            raise

    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "optimize",
                    "subcommand": "prompts",
                    "status": "ok",
                    "message": _help_for_command("optimize prompts"),
                },
                output_json,
                "optimize",
            )
            sys.exit(EXIT_SUCCESS)
        if arg == "--json":
            output_json = True
            i += 1
            continue
        if arg == "--strict":
            strict = True
            i += 1
            continue
        if arg.startswith("--strict="):
            try:
                strict = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --strict value: {exc}", "optimize", EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--params":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --params", "optimize", EXIT_USAGE, output_json)
            if has_payload:
                emit_error("optimize prompts accepts only one --params argument", "optimize", EXIT_USAGE, output_json)
            payload = _read_json_payload_source(args[i + 1], command="optimize", output_json=output_json) or {}
            if strict:
                for key in payload.keys():
                    if key not in allowed_payload_fields:
                        emit_error(
                            f"strict mode rejects unknown params fields: {key}",
                            "optimize",
                            EXIT_USAGE,
                            output_json,
                        )
            has_payload = True
            i += 2
            continue
        if arg.startswith("--params="):
            if has_payload:
                emit_error("optimize prompts accepts only one --params argument", "optimize", EXIT_USAGE, output_json)
            payload = _read_json_payload_source(arg.split("=", 1)[1], command="optimize", output_json=output_json) or {}
            if strict:
                for key in payload.keys():
                    if key not in allowed_payload_fields:
                        emit_error(
                            f"strict mode rejects unknown params fields: {key}",
                            "optimize",
                            EXIT_USAGE,
                            output_json,
                        )
            has_payload = True
            i += 1
            continue
        if arg == "--dataset":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --dataset", "optimize", EXIT_USAGE, output_json)
            value = args[i + 1].strip()
            if not value:
                emit_error("optimize prompts requires --dataset", "optimize", EXIT_USAGE, output_json)
            flag_values["dataset"] = normalize_dataset_input(value, "dataset")
            i += 2
            continue
        if arg.startswith("--dataset="):
            value = arg.split("=", 1)[1].strip()
            if not value:
                emit_error("optimize prompts requires --dataset", "optimize", EXIT_USAGE, output_json)
            flag_values["dataset"] = normalize_dataset_input(value, "dataset")
            i += 1
            continue
        if arg == "--candidate":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --candidate", "optimize", EXIT_USAGE, output_json)
            value = args[i + 1].strip()
            if not value:
                emit_error("optimize prompts requires --candidate", "optimize", EXIT_USAGE, output_json)
            flag_values["candidate"] = normalize_dataset_input(value, "candidate")
            i += 2
            continue
        if arg.startswith("--candidate="):
            value = arg.split("=", 1)[1].strip()
            if not value:
                emit_error("optimize prompts requires --candidate", "optimize", EXIT_USAGE, output_json)
            flag_values["candidate"] = normalize_dataset_input(value, "candidate")
            i += 1
            continue
        if arg == "--baseline":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --baseline", "optimize", EXIT_USAGE, output_json)
            value = args[i + 1].strip()
            if not value:
                emit_error("optimize prompts requires --baseline", "optimize", EXIT_USAGE, output_json)
            flag_values["baseline"] = normalize_dataset_input(value, "baseline")
            i += 2
            continue
        if arg.startswith("--baseline="):
            value = arg.split("=", 1)[1].strip()
            if not value:
                emit_error("optimize prompts requires --baseline", "optimize", EXIT_USAGE, output_json)
            flag_values["baseline"] = normalize_dataset_input(value, "baseline")
            i += 1
            continue
        if arg == "--metric":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --metric", "optimize", EXIT_USAGE, output_json)
            value = args[i + 1].strip().lower()
            if value not in OPTIMIZATION_SUPPORTED_METRICS:
                emit_error(
                    f"invalid --metric '{value}', expected one of: {', '.join(sorted(OPTIMIZATION_SUPPORTED_METRICS))}",
                    "optimize",
                    EXIT_USAGE,
                    output_json,
                )
            flag_values["metric"] = value
            i += 2
            continue
        if arg.startswith("--metric="):
            value = arg.split("=", 1)[1].strip().lower()
            if value not in OPTIMIZATION_SUPPORTED_METRICS:
                emit_error(
                    f"invalid --metric '{value}', expected one of: {', '.join(sorted(OPTIMIZATION_SUPPORTED_METRICS))}",
                    "optimize",
                    EXIT_USAGE,
                    output_json,
                )
            flag_values["metric"] = value
            i += 1
            continue
        if arg == "--min-improvement":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --min-improvement", "optimize", EXIT_USAGE, output_json)
            try:
                flag_values["min_improvement"] = parse_float_option(args[i + 1], "min-improvement")
            except ValueError as exc:
                emit_error(f"invalid --min-improvement value: {exc}", "optimize", EXIT_USAGE, output_json)
            i += 2
            continue
        if arg.startswith("--min-improvement="):
            try:
                flag_values["min_improvement"] = parse_float_option(arg.split("=", 1)[1], "min-improvement")
            except ValueError as exc:
                emit_error(f"invalid --min-improvement value: {exc}", "optimize", EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--approve":
            flag_values["approve"] = True
            i += 1
            continue
        if arg.startswith("--approve="):
            try:
                flag_values["approve"] = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --approve value: {exc}", "optimize", EXIT_USAGE, output_json)
            i += 1
            continue
        emit_error(f"unknown option '{arg}' for optimize prompts", "optimize", EXIT_USAGE, output_json)

    def resolve_field(name: str, *, required: bool, default_value: object, field_type: str) -> object:
        if name in flag_values:
            raw_value = flag_values[name]
            from_payload = False
        elif has_payload and name in payload:
            raw_value = payload[name]
            from_payload = True
        else:
            if required:
                emit_error(
                    f"optimize prompts requires --{name.replace('_', '-')}",
                    "optimize",
                    EXIT_USAGE,
                    output_json,
                )
            if strict:
                emit_error(
                    f"optimize prompts strict mode requires --{name.replace('_', '-')}",
                    "optimize",
                    EXIT_USAGE,
                    output_json,
                )
            return default_value

        if field_type == "path":
            if not isinstance(raw_value, str):
                if strict and from_payload:
                    emit_error(
                        f"optimize prompts --{name.replace('_', '-')} must be a string in strict mode",
                        "optimize",
                        EXIT_USAGE,
                        output_json,
                    )
                raw_value = str(raw_value)
            return normalize_dataset_input(str(raw_value), name)

        if field_type == "metric":
            if not isinstance(raw_value, str):
                if strict and from_payload:
                    emit_error(
                        "optimize prompts --metric must be a string in strict mode",
                        "optimize",
                        EXIT_USAGE,
                        output_json,
                    )
                raw_value = str(raw_value)
            value = str(raw_value).strip().lower()
            if value not in OPTIMIZATION_SUPPORTED_METRICS:
                emit_error(
                    f"invalid --metric '{value}', expected one of: {', '.join(sorted(OPTIMIZATION_SUPPORTED_METRICS))}",
                    "optimize",
                    EXIT_USAGE,
                    output_json,
                )
            return value

        if field_type == "min_improvement":
            if strict and from_payload:
                if isinstance(raw_value, bool):
                    emit_error(
                        "optimize prompts --min-improvement must be a number in strict mode",
                        "optimize",
                        EXIT_USAGE,
                        output_json,
                    )
                if not isinstance(raw_value, (int, float)):
                    emit_error(
                        "optimize prompts --min-improvement must be a number in strict mode",
                        "optimize",
                        EXIT_USAGE,
                        output_json,
                    )
            if isinstance(raw_value, bool):
                emit_error("optimize prompts --min-improvement must be >= 0", "optimize", EXIT_USAGE, output_json)
            if isinstance(raw_value, (int, float)):
                return float(raw_value)
            if isinstance(raw_value, str):
                try:
                    return parse_float_option(raw_value, "min-improvement")
                except ValueError as exc:
                    emit_error(f"invalid --min-improvement value: {exc}", "optimize", EXIT_USAGE, output_json)
            emit_error("optimize prompts --min-improvement must be a number", "optimize", EXIT_USAGE, output_json)

        if field_type == "approve":
            if isinstance(raw_value, bool):
                return raw_value
            if strict and from_payload:
                emit_error("optimize prompts --approve must be boolean in strict mode", "optimize", EXIT_USAGE, output_json)
            if isinstance(raw_value, str):
                try:
                    return parse_bool_option(raw_value)
                except ValueError as exc:
                    emit_error(f"invalid --approve value: {exc}", "optimize", EXIT_USAGE, output_json)
            emit_error("optimize prompts --approve must be boolean", "optimize", EXIT_USAGE, output_json)
        return raw_value

    dataset = resolve_field("dataset", required=True, default_value=None, field_type="path")
    candidate = resolve_field("candidate", required=True, default_value=None, field_type="path")
    baseline = resolve_field("baseline", required=True, default_value=None, field_type="path")
    metric = resolve_field("metric", required=False, default_value="contains", field_type="metric")
    min_improvement = resolve_field("min_improvement", required=False, default_value=OPTIMIZATION_DEFAULT_MIN_IMPROVEMENT, field_type="min_improvement")
    approve = resolve_field("approve", required=False, default_value=False, field_type="approve")

    if not isinstance(min_improvement, (int, float)):
        emit_error("optimize prompts --min-improvement must be a number", "optimize", EXIT_USAGE, output_json)
    if min_improvement < 0:
        emit_error("--min-improvement must be >= 0", "optimize", EXIT_USAGE, output_json)
    if min_improvement > 1:
        min_improvement = min_improvement / 100.0
    if not isinstance(approve, bool):
        emit_error("optimize prompts --approve must be boolean", "optimize", EXIT_USAGE, output_json)

    return {
        "dataset": dataset,
        "candidate": candidate,
        "baseline": baseline,
        "metric": metric,
        "min_improvement": min_improvement,
        "approve": bool(approve),
        "strict": strict,
        "output_json": output_json,
    }


def _normalize_path_list(raw: str) -> list[str]:
    return sorted({entry.strip() for entry in raw.splitlines() if entry.strip()})


def _normalize_dataset_path(value: object, field: str) -> str:
    return _normalize_repo_relative_user_path(value, field)


def _load_text_artifact(repo_root: str, relative_path: str, label: str) -> str:
    path = os.path.join(repo_root, relative_path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ValueError(f"unable to read {label} from '{relative_path}': {exc}") from exc


def _build_optimization_case_payload(
    index: int,
    case_id: str,
    case_input: str,
    weight: float,
    baseline_score: float,
    candidate_score: float,
) -> dict[str, object]:
    winner = "tie"
    if candidate_score > baseline_score:
        winner = "candidate"
    elif baseline_score > candidate_score:
        winner = "baseline"
    return {
        "index": index,
        "id": case_id,
        "input": case_input,
        "weight": weight,
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
        "winner": winner,
    }


def _normalize_evaluation_cases(raw_cases: object, dataset_id: str) -> list[dict[str, object]]:
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"eval_dataset[{dataset_id}] must contain a non-empty 'cases' list")
    cases: list[dict[str, object]] = []
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] must be an object")
        case_input_raw = raw_case.get("input")
        if not isinstance(case_input_raw, str) or not case_input_raw.strip():
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] is missing non-empty 'input'")
        expected_raw = raw_case.get("expected")
        if expected_raw is None:
            expected_raw = raw_case.get("expected_contains")
        if expected_raw is None:
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] missing required 'expected'")
        if isinstance(expected_raw, str):
            expected = [expected_raw]
        elif isinstance(expected_raw, list):
            expected = [str(item) for item in expected_raw if isinstance(item, str)]
        else:
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] invalid 'expected'")
        expected = [item.strip() for item in expected if item.strip()]
        if not expected:
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] must include at least one expected token")
        must_not_raw = raw_case.get("must_not_contain", [])
        if isinstance(must_not_raw, str):
            must_not = [must_not_raw]
        elif isinstance(must_not_raw, list):
            must_not = [str(item) for item in must_not_raw if str(item).strip()]
        else:
            must_not = []

        weight_raw = raw_case.get("weight", 1.0)
        if isinstance(weight_raw, bool) or not isinstance(weight_raw, int | float):
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] has invalid weight")
        if weight_raw <= 0:
            raise ValueError(f"eval_dataset[{dataset_id}] case[{index}] weight must be greater than 0")

        case_id_raw = raw_case.get("id")
        case_id = str(case_id_raw).strip() if isinstance(case_id_raw, str) and case_id_raw.strip() else f"case-{index:03d}"

        cases.append(
            {
                "id": case_id,
                "input": case_input_raw.strip(),
                "expected": expected,
                "must_not_contain": [item.strip() for item in must_not],
                "weight": float(weight_raw),
            }
        )
    return cases


def _read_eval_dataset(repo_root: str, dataset_relative_path: str) -> dict[str, object]:
    payload = _read_json_file(os.path.join(repo_root, dataset_relative_path))
    if not isinstance(payload, dict):
        raise ValueError(f"dataset '{dataset_relative_path}' is not valid JSON")
    dataset_id = _required_str(payload.get("id"), f"eval_dataset[{dataset_relative_path}].id")
    schema_version = payload.get("schema_version")
    if schema_version != 2:
        raise ValueError(f"eval_dataset[{dataset_id}] must use schema_version 2")
    artifact_type = payload.get("artifact_type")
    if artifact_type != "eval_dataset":
        raise ValueError(f"eval_dataset[{dataset_id}] must have artifact_type 'eval_dataset'")
    cases_raw = payload.get("cases")
    cases = _normalize_evaluation_cases(cases_raw, dataset_id)
    return {
        "id": dataset_id,
        "name": str(payload.get("name") or dataset_id),
        "cases": cases,
        "schema_version": schema_version,
        "artifact_type": artifact_type,
        "description": payload.get("description"),
    }


def _build_prompt_execution_result(prompt: str, case: dict[str, object], metric: str) -> float:
    case_input = str(case.get("input") or "")
    expected = [
        " ".join(str(token).strip().lower().split()) for token in case.get("expected", []) if str(token).strip()
    ]
    if not expected:
        return 0.0
    forbidden = [
        " ".join(str(token).strip().lower().split()) for token in case.get("must_not_contain", []) if str(token).strip()
    ]
    response = f"{prompt} {case_input}".strip().lower()
    response_normalized = " ".join(response.split())
    if metric == "exact":
        matched = any(response_normalized == expected_value for expected_value in expected)
    else:
        matched = all(token in response_normalized for token in expected)
    if forbidden and any(token in response_normalized for token in forbidden):
        matched = False
    return 1.0 if matched else 0.0


def _evaluate_prompts(
    repo_root: str,
    dataset: dict[str, object],
    baseline_prompt: str,
    candidate_prompt: str,
    options: dict[str, object],
) -> dict[str, object]:
    metric = str(options.get("metric") or "contains").strip().lower()
    if metric not in OPTIMIZATION_SUPPORTED_METRICS:
        raise ValueError(f"unsupported metric '{metric}'")
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise ValueError("dataset is missing parsed cases")
    min_improvement = float(options.get("min_improvement") or 0.0)
    if min_improvement < 0:
        raise ValueError("min_improvement must be >= 0")
    total_weight = 0.0
    baseline_total = 0.0
    candidate_total = 0.0
    case_results: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"eval_dataset[{dataset['id']}] case[{index}] must be an object")
        weight = float(case.get("weight") or 1.0)
        baseline_score = _build_prompt_execution_result(baseline_prompt, case, metric)
        candidate_score = _build_prompt_execution_result(candidate_prompt, case, metric)
        candidate_total += candidate_score * weight
        total_weight += weight
        baseline_total += baseline_score * weight
        case_results.append(
            _build_optimization_case_payload(
                index=index,
                case_id=str(case.get("id") or f"case-{index:03d}"),
                case_input=str(case.get("input") or ""),
                weight=weight,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
            )
        )

    if total_weight <= 0:
        raise ValueError("dataset cases must have positive total weight")

    baseline_rate = baseline_total / total_weight
    candidate_rate = candidate_total / total_weight
    baseline_delta = candidate_rate - baseline_rate
    baseline = baseline_rate
    candidate = candidate_rate
    dataset_id = str(dataset["id"])
    created_at = _utc_timestamp()
    pass_threshold = candidate >= baseline + min_improvement
    result: dict[str, object] = {
        "schema_version": 2,
        "artifact_type": "optimization_eval_result",
        "id": f"opt-{dataset_id}-{_short_hash(f'{dataset_id}:{created_at}')}",
        "dataset_id": dataset_id,
        "created_at": created_at,
        "metric": metric,
        "min_improvement": min_improvement,
        "baseline_score": baseline,
        "candidate_score": candidate,
        "score_delta": baseline_delta,
        "status": "pass" if pass_threshold else "fail",
        "case_count": len(case_results),
        "cases": case_results,
    }
    result["dataset_path"] = options.get("dataset_path")
    result["baseline_prompt_path"] = options.get("baseline_path")
    result["candidate_prompt_path"] = options.get("candidate_path")
    return result


def _collect_all_non_runtime_files(repo_root: str) -> list[str]:
    tracked = _run_git(repo_root, ["ls-files"]).stdout
    untracked = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"]).stdout
    raw = _normalize_path_list(tracked + "\n" + untracked)
    normalized: list[str] = []
    for path in raw:
        candidate = _normalize_repo_relative_path(path)
        if any(candidate.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES):
            continue
        if _is_sync_managed_generated_path(candidate):
            continue
        normalized.append(candidate)
    return normalized


def _requires_bootstrap_full_snapshot(repo_root: str) -> bool:
    return not _list_known_capsules(repo_root)


def _collect_changed_paths(repo_root: str, baseline_ref: str) -> list[str]:
    unstaged = _run_git(repo_root, ["diff", "--name-only", baseline_ref]).stdout
    cached = _run_git(repo_root, ["diff", "--cached", "--name-only", baseline_ref]).stdout
    untracked = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"]).stdout
    raw = _normalize_path_list(unstaged + "\n" + cached + "\n" + untracked)
    normalized: list[str] = []
    for path in raw:
        candidate = _normalize_repo_relative_path(path)
        if any(candidate.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES):
            continue
        if _is_sync_managed_generated_path(candidate):
            continue
        normalized.append(candidate)
    return normalized


def _resolve_sync_baseline(repo_root: str) -> dict[str, object]:
    head_parent = _run_git(repo_root, ["rev-parse", "HEAD~1"])
    if head_parent.returncode == 0 and head_parent.stdout.strip():
        return {
            "strategy": "head~1",
            "reference": "HEAD~1",
            "resolved": head_parent.stdout.strip(),
            "details": "using previous commit parent",
        }

    orig_head = _run_git(repo_root, ["rev-parse", "ORIG_HEAD"])
    orig_head_value = orig_head.stdout.strip()
    if orig_head.returncode == 0 and orig_head_value:
        merge_base = _run_git(repo_root, ["merge-base", orig_head_value, "HEAD"])
        merge_base_value = merge_base.stdout.strip()
        if merge_base.returncode == 0 and merge_base_value:
            return {
                "strategy": "orig_head_merge_base",
                "reference": "merge-base(ORIG_HEAD,HEAD)",
                "resolved": merge_base_value,
                "details": "using merge-base from ORIG_HEAD",
            }

    return {
        "strategy": "empty_tree",
        "reference": "empty-tree",
        "resolved": EMPTY_TREE_OBJECT_ID,
        "details": "fallback full-tree comparison",
    }


def _collect_sync_snapshot(repo_root: str, profile: str, mode: str, *, force_full_sync: bool = False) -> dict[str, object]:
    head_result = _run_git(repo_root, ["rev-parse", "HEAD"])
    branch_result = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    baseline = _resolve_sync_baseline(repo_root)
    baseline_ref = str(baseline.get("resolved") or "")
    if baseline.get("strategy") == "empty_tree" or force_full_sync or _requires_bootstrap_full_snapshot(repo_root):
        changed_files = _collect_all_non_runtime_files(repo_root)
    else:
        changed_files = _collect_changed_paths(repo_root, baseline_ref)
    changed_files = sorted(set(changed_files))
    head = head_result.stdout.strip() if head_result.returncode == 0 else "HEAD_NOT_AVAILABLE"
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "detached"
    if branch == "HEAD":
        branch = "detached"
    return {
        "repository_head": head,
        "branch": branch,
        "changed_files": changed_files,
        "changed_count": len(changed_files),
        "has_changes": len(changed_files) > 0,
        "force_full_sync": force_full_sync,
        "diff_baseline": baseline,
        "profile": profile,
        "mode": mode,
        "captured_at": _utc_timestamp(),
    }


def _compute_idempotency_key(snapshot: dict[str, object], profile: str, mode: str) -> str:
    payload = {
        "head": snapshot["repository_head"],
        "branch": snapshot["branch"],
        "baseline": snapshot.get("diff_baseline", {}),
        "mode": mode,
        "profile": profile,
        "changed": snapshot["changed_files"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_oracle_entry(raw_oracle: object) -> dict[str, object] | None:
    if isinstance(raw_oracle, str):
        name = raw_oracle.strip()
        if not name:
            return None
        return {"name": name, "command": None, "scope": []}
    if not isinstance(raw_oracle, dict):
        return None

    name = raw_oracle.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    command = raw_oracle.get("command")
    command_value = command.strip() if isinstance(command, str) and command.strip() else None
    reason = raw_oracle.get("reason")
    reason_value = reason.strip() if isinstance(reason, str) and reason.strip() else None

    scope_raw = raw_oracle.get("scope")
    scope: list[str] = []
    if isinstance(scope_raw, str):
        if scope_raw.strip():
            scope = [scope_raw.strip()]
    elif isinstance(scope_raw, list):
        for raw_scope in scope_raw:
            if isinstance(raw_scope, str):
                cleaned = raw_scope.strip()
                if cleaned:
                    scope.append(cleaned)

    normalized = {"name": name.strip(), "command": command_value, "scope": scope}
    if reason_value is not None:
        normalized["reason"] = reason_value
    return normalized


def _load_capsule_oracles(repo_root: str, capsule_id: str) -> list[dict[str, object]]:
    yaml_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.yaml")
    json_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.json")

    for candidate in (json_path, yaml_path):
        if not os.path.isfile(candidate):
            continue
        try:
            payload = _read_structured_mapping_file(candidate)
        except ValueError as exc:
            relative_path = os.path.relpath(candidate, repo_root).replace("\\", "/")
            raise ValueError(f"{relative_path}: {exc}") from exc
        raw_oracles = payload.get("oracles")
        if not isinstance(raw_oracles, list):
            continue
        normalized: list[dict[str, object]] = []
        for raw_oracle in raw_oracles:
            normalized_oracle = _normalize_oracle_entry(raw_oracle)
            if normalized_oracle is not None:
                normalized.append(normalized_oracle)
        if normalized:
            return normalized

    return [
        {
            "name": f"{_safe_slug(capsule_id)}-verify",
            "command": None,
            "scope": [],
        }
    ]


def _load_capsule_payload(repo_root: str, capsule_id: str) -> dict[str, object]:
    json_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.json")
    yaml_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.yaml")
    for candidate in (json_path, yaml_path):
        if not os.path.isfile(candidate):
            continue
        try:
            payload = _read_structured_mapping_file(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _path_matches_capsule_scope(path: str, scope: list[str]) -> bool:
    normalized_path = _normalize_repo_relative_path(path).replace("\\", "/")
    if not normalized_path:
        return False
    if not scope:
        return True
    for raw_pattern in scope:
        pattern = _normalize_repo_relative_path(str(raw_pattern)).replace("\\", "/")
        if not pattern:
            continue
        if any(char in pattern for char in "*?[]"):
            if fnmatch.fnmatch(normalized_path, pattern):
                return True
            continue
        if normalized_path == pattern:
            return True
        if normalized_path.startswith(f"{pattern}/"):
            return True
    return False


def _oracle_scopes_match(oracle: dict[str, object], changed_paths: list[str]) -> bool:
    scope_raw = oracle.get("scope")
    if not isinstance(scope_raw, list):
        return True
    scope: list[str] = [str(entry) for entry in scope_raw if isinstance(entry, str)]
    if not scope:
        return True
    if not changed_paths:
        return True
    for changed_path in changed_paths:
        for glob in scope:
            if fnmatch.fnmatch(changed_path, glob):
                return True
    return False


def _run_oracle_check(
    repo_root: str,
    capsule_id: str,
    oracle: dict[str, object],
    changed_paths: list[str],
    run_id: str,
    mode: str,
    policy: dict[str, object] | None = None,
    exec_root: str | None = None,
    trace_label: str = "verify",
    timeout_seconds: int | None = None,
    max_retries: int = 0,
) -> dict[str, object]:
    oracle_name = str(oracle.get("name", "unknown-oracle"))
    command = oracle.get("command")
    command_text = command.strip() if isinstance(command, str) else None
    resolved_policy = policy or _default_policy()
    trace_path = _build_trace_path(capsule_id, run_id, oracle_name, trace_label)
    trace_write_check = _evaluate_policy_writes(
        resolved_policy,
        command="verify",
        mode=mode,
        targets=[trace_path, f"{OG_ROOT}/objects/**"],
    )
    if trace_write_check is not None:
        return {
            **trace_write_check,
            "schema_version": 2,
            "oracle_name": oracle_name,
            "capsule_id": capsule_id,
            "run_id": run_id,
            "mode": mode,
            "status": "error",
            "checked_at": _utc_timestamp(),
            "changed_paths": changed_paths,
            "command": command_text or "",
            "message": trace_write_check.get("message"),
            "trace": trace_path,
        }

    start = time.perf_counter()
    result_payload: dict[str, object] = {
        "schema_version": 2,
        "oracle_name": oracle_name,
        "capsule_id": capsule_id,
        "run_id": run_id,
        "mode": mode,
        "status": "skipped",
        "checked_at": _utc_timestamp(),
        "changed_paths": changed_paths,
        "command": command_text or "",
    }
    if command_text:
        denied = _ensure_policy_action_allowed(
            resolved_policy,
            command="verify",
            category="verify_commands",
            target=command_text,
            mode=mode,
        )
        if denied is not None:
            result_payload["status"] = "skipped"
            result_payload["code"] = denied.get("error_code") or denied.get("code") or POLICY_DENIED_CODE
            result_payload["message"] = str(denied.get("message") or "oracle command skipped by policy")
            result_payload["remediation"] = denied.get("remediation", [])
            payload_bytes = (
                json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
            result_payload["duration_ms"] = int((time.perf_counter() - start) * 1000)
            trace_full_path = os.path.join(repo_root, trace_path)
            os.makedirs(os.path.dirname(trace_full_path), exist_ok=True)
            _write_text_payload(trace_full_path, payload_bytes.decode("utf-8"))
            receipts = [
                _build_file_pointer(trace_path, payload_bytes, "application/json"),
                _store_put(repo_root, payload_bytes.decode("utf-8"), "application/json"),
            ]
            result_payload["receipt_pointers"] = receipts
            result_payload["trace"] = trace_path
            return result_payload

    resolved_timeout = timeout_seconds if isinstance(timeout_seconds, int) and timeout_seconds > 0 else ORACLE_COMMAND_DEFAULT_TIMEOUT_SECONDS
    if not command_text:
        result_payload["status"] = "pass"
        result_payload["observed_code"] = 0
        result_payload["message"] = "No oracle command configured; marked pass."
        result_payload["recovery"] = _build_recovery_record(
            f"oracle:{oracle_name}",
            attempts=1,
            max_retries=max_retries,
            timeout_seconds=resolved_timeout,
        )
        payload_bytes = (json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
    else:
        attempts = 0
        retryable_failures: list[dict[str, object]] = []
        executed: subprocess.CompletedProcess[str] | None = None
        final_error_message: str | None = None
        final_error_code: str | None = None
        while True:
            attempts += 1
            try:
                executed = subprocess.run(
                    command_text,
                    shell=True,
                    cwd=exec_root or repo_root,
                    capture_output=True,
                    text=True,
                    timeout=resolved_timeout,
                )
            except subprocess.TimeoutExpired:
                final_error_message = f"oracle command timed out after {resolved_timeout}s"
                final_error_code = TIMEOUT_EXPIRED_CODE
                if attempts <= max_retries:
                    retryable_failures.append(
                        {
                            "attempt": attempts,
                            "error_code": final_error_code,
                            "message": final_error_message,
                            "timed_out": True,
                        }
                    )
                    continue
                result_payload["status"] = "error"
                result_payload["code"] = RECOVERY_RETRY_EXHAUSTED_CODE if retryable_failures else final_error_code
                result_payload["observed_code"] = 124
                result_payload["error"] = final_error_message
                result_payload["message"] = final_error_message
                result_payload["recovery"] = _build_recovery_record(
                    f"oracle:{oracle_name}",
                    attempts=attempts,
                    max_retries=max_retries,
                    timeout_seconds=resolved_timeout,
                    exhausted=bool(retryable_failures),
                    retryable=True,
                    retryable_failures=retryable_failures,
                    error_code=result_payload["code"],
                    message=final_error_message,
                )
                break
            except Exception as exc:
                final_error_message = f"oracle command failed to execute: {exc}"
                final_error_code = RUNTIME_ERROR_CODE
                result_payload["status"] = "error"
                result_payload["code"] = final_error_code
                result_payload["observed_code"] = 1
                result_payload["error"] = final_error_message
                result_payload["message"] = final_error_message
                result_payload["recovery"] = _build_recovery_record(
                    f"oracle:{oracle_name}",
                    attempts=attempts,
                    max_retries=max_retries,
                    timeout_seconds=resolved_timeout,
                    retryable=False,
                    error_code=final_error_code,
                    message=final_error_message,
                )
                break
            else:
                result_payload["observed_code"] = executed.returncode
                result_payload["stdout"] = (executed.stdout or "").splitlines()[-5:]
                result_payload["stderr"] = (executed.stderr or "").splitlines()[-5:]
                result_payload["message"] = "oracle command executed."
                if executed.returncode == 0:
                    result_payload["status"] = "pass"
                    result_payload["recovery"] = _build_recovery_record(
                        f"oracle:{oracle_name}",
                        attempts=attempts,
                        max_retries=max_retries,
                        timeout_seconds=resolved_timeout,
                        recovered=bool(retryable_failures),
                        retryable_failures=retryable_failures,
                    )
                else:
                    result_payload["status"] = "fail"
                    result_payload["recovery"] = _build_recovery_record(
                        f"oracle:{oracle_name}",
                        attempts=attempts,
                        max_retries=max_retries,
                        timeout_seconds=resolved_timeout,
                        retryable_failures=retryable_failures,
                    )
                break

        payload_bytes = (
            json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        ).encode("utf-8")

    result_payload["duration_ms"] = int((time.perf_counter() - start) * 1000)
    trace_full_path = os.path.join(repo_root, trace_path)
    os.makedirs(os.path.dirname(trace_full_path), exist_ok=True)
    _write_text_payload(trace_full_path, payload_bytes.decode("utf-8"))
    receipts = [
        _build_file_pointer(trace_path, payload_bytes, "application/json"),
        _store_put(repo_root, payload_bytes.decode("utf-8"), "application/json"),
    ]
    result_payload["receipt_pointers"] = receipts
    result_payload["trace"] = trace_path
    return result_payload


def _collect_replay_equivalence_baseline_payload(repo_root: str, capsule_id: str) -> dict[str, object]:
    certificates = _collect_certificate_records(repo_root)
    if not certificates:
        return {}

    normalized_target = _safe_slug(capsule_id)
    latest_updated_at: datetime.datetime | None = None
    baseline_payload: dict[str, object] = {}
    for certificate in certificates:
        if _safe_slug(str(certificate.get("capsule_id") or "default")) != normalized_target:
            continue
        if str(certificate.get("status") or "").lower() != "success":
            continue
        raw = certificate.get("raw")
        if not isinstance(raw, dict):
            continue
        replay_context = raw.get("replay_context")
        if not isinstance(replay_context, dict):
            continue
        equivalence = replay_context.get("equivalence")
        if not isinstance(equivalence, dict):
            continue
        candidate_hash = equivalence.get("oracle_digest") or equivalence.get("observed_hash")
        if not isinstance(candidate_hash, str) or not candidate_hash:
            continue

        updated_at_raw = raw.get("updated_at")
        if isinstance(updated_at_raw, str):
            candidate_updated_at = _parse_utc_timestamp(updated_at_raw)
        else:
            candidate_updated_at = None

        if latest_updated_at is not None and candidate_updated_at is not None and candidate_updated_at <= latest_updated_at:
            continue
        latest_updated_at = candidate_updated_at or latest_updated_at
        baseline_payload = dict(equivalence)
    return baseline_payload


def _collect_replay_equivalence_baseline(repo_root: str, capsule_id: str) -> str | None:
    equivalence = _collect_replay_equivalence_baseline_payload(repo_root, capsule_id)
    candidate_hash = equivalence.get("oracle_digest") or equivalence.get("observed_hash")
    return candidate_hash if isinstance(candidate_hash, str) and candidate_hash else None


def _collect_scope_materials_from_repo(repo_root: str, scope: list[str]) -> list[dict[str, object]]:
    if not scope:
        return []

    selected: dict[str, dict[str, object]] = {}
    for current_root, dirnames, filenames in os.walk(repo_root):
        relative_root = os.path.relpath(current_root, repo_root).replace("\\", "/")
        if relative_root == ".":
            relative_root = ""

        kept_dirs: list[str] = []
        for dirname in dirnames:
            relative_dir = dirname if not relative_root else f"{relative_root}/{dirname}"
            normalized_dir = _normalize_repo_relative_path(relative_dir)
            if not normalized_dir:
                continue
            if normalized_dir == ".git" or normalized_dir.startswith(".git/"):
                continue
            if any(
                normalized_dir == prefix.rstrip("/") or normalized_dir.startswith(prefix)
                for prefix in RUNTIME_IGNORE_PREFIXES
            ):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            relative_path = filename if not relative_root else f"{relative_root}/{filename}"
            normalized_path = _normalize_repo_relative_path(relative_path)
            if not normalized_path:
                continue
            if normalized_path.startswith(".git/") or normalized_path == ".git":
                continue
            if any(normalized_path.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES):
                continue
            if not _path_matches_capsule_scope(normalized_path, scope):
                continue
            digest = _file_sha256(normalized_path, repo_root)
            if not digest:
                continue
            entry: dict[str, object] = {
                "path": normalized_path,
                "digest": digest,
                "kind": "file",
            }
            absolute_path = os.path.join(repo_root, normalized_path)
            try:
                entry["size"] = os.path.getsize(absolute_path)
            except OSError:
                pass
            selected[normalized_path] = entry
    return [selected[path] for path in sorted(selected)]


def _collect_capsule_scope_materials(
    repo_root: str,
    capsule_id: str,
    changed_materials: list[dict[str, object]],
) -> list[dict[str, object]]:
    capsule_payload = _load_capsule_payload(repo_root, capsule_id)
    scope = _safe_string_list(capsule_payload.get("scope"))
    material_records, _ = _read_material_lock_records(repo_root)
    selected: dict[str, dict[str, object]] = {}
    for path, record in material_records.items():
        if _path_matches_capsule_scope(path, scope):
            selected[path] = dict(record)
    for raw_material in changed_materials:
        if not isinstance(raw_material, dict):
            continue
        path = str(raw_material.get("path") or "").strip()
        digest = str(raw_material.get("digest") or "").strip()
        if not path or not digest:
            continue
        if _path_matches_capsule_scope(path, scope):
            selected[path] = {"path": path, "digest": digest}
    for material in _collect_scope_materials_from_repo(repo_root, scope):
        path = str(material.get("path") or "").strip()
        if path and path not in selected:
            selected[path] = dict(material)
    return [selected[path] for path in sorted(selected)]


def _collect_executable_oracle_map(oracles: list[dict[str, object]]) -> dict[str, str]:
    executable: dict[str, str] = {}
    for oracle in oracles:
        if not isinstance(oracle, dict):
            continue
        name = str(oracle.get("name") or "").strip()
        command = str(oracle.get("command") or "").strip()
        if not name or not command:
            continue
        executable[name] = command
    return executable


def _validate_replay_plan_contract(
    run_id: str,
    capsule_id: str,
    plan: dict[str, object],
    capsule_payload: dict[str, object],
    scope_materials: list[dict[str, object]],
    capsule_oracles: list[dict[str, object]],
    baseline_equivalence: dict[str, object],
) -> list[str]:
    failures: list[str] = []
    expected_scope = _safe_string_list(capsule_payload.get("scope"))
    if not expected_scope:
        failures.append(f"Replay capsule {capsule_id} lacks capsule scope needed for regeneration proof.")

    if str(plan.get("run_id") or "") != run_id:
        failures.append(f"Replay plan for {capsule_id} returned run_id '{plan.get('run_id')}' instead of '{run_id}'.")
    if str(plan.get("capsule_id") or "") != capsule_id:
        failures.append(
            f"Replay plan for {capsule_id} returned capsule_id '{plan.get('capsule_id')}' instead of '{capsule_id}'."
        )

    plan_scope = _safe_string_list(plan.get("capsule_scope"))
    if not plan_scope:
        failures.append(f"Replay plan for {capsule_id} must declare capsule_scope.")
    elif expected_scope:
        scope_overlap = any(scope_item in expected_scope for scope_item in plan_scope)
        if not scope_overlap:
            plan_scope_patterns = plan_scope
            expected_scope_paths = [str(item.get("path") or "") for item in scope_materials if isinstance(item, dict)]
            scope_overlap = any(
                _path_matches_capsule_scope(path, plan_scope_patterns)
                for path in expected_scope_paths
                if path
            )
        if not scope_overlap:
            failures.append(f"Replay plan for {capsule_id} must stay within the recorded capsule scope.")

    scope_materials_by_path: dict[str, dict[str, object]] = {}
    for material in scope_materials:
        if not isinstance(material, dict):
            continue
        path = str(material.get("path") or "").strip()
        if not path:
            continue
        scope_materials_by_path[path] = material
    if not scope_materials_by_path:
        failures.append(f"Replay capsule {capsule_id} lacks scoped material inputs for regeneration proof.")

    material_inputs = _safe_object_list(plan.get("material_inputs"))
    if not material_inputs:
        failures.append(f"Replay plan for {capsule_id} must declare material_inputs.")
    for material in material_inputs:
        path = str(material.get("path") or "").strip()
        digest = str(material.get("digest") or "").strip()
        if not path or not digest:
            failures.append(f"Replay plan for {capsule_id} includes an incomplete material input.")
            continue
        expected_material = scope_materials_by_path.get(path)
        if expected_material is None:
            failures.append(f"Replay plan for {capsule_id} references scoped material '{path}' that was not materialized.")
            continue
        expected_digest = str(expected_material.get("digest") or "").strip()
        if expected_digest and digest != expected_digest:
            failures.append(
                f"Replay plan for {capsule_id} uses digest '{digest}' for '{path}', expected '{expected_digest}'."
            )

    executable_oracles = _collect_executable_oracle_map(capsule_oracles)
    if not executable_oracles:
        failures.append(f"Replay capsule {capsule_id} lacks executable acceptance oracles for regeneration proof.")

    acceptance_checks = _safe_object_list(plan.get("acceptance_checks"))
    if not acceptance_checks:
        failures.append(f"Replay plan for {capsule_id} must declare acceptance_checks.")

    acceptance_oracle_names: list[str] = []
    for index, raw_check in enumerate(acceptance_checks):
        oracle_name = str(raw_check.get("oracle_name") or "").strip()
        command = str(raw_check.get("command") or "").strip()
        if not oracle_name:
            failures.append(
                f"Replay plan for {capsule_id} acceptance_checks[{index}] must reference an executable capsule oracle."
            )
            continue
        expected_command = executable_oracles.get(oracle_name)
        if expected_command is None:
            failures.append(
                f"Replay plan for {capsule_id} acceptance_checks[{index}] references unknown oracle '{oracle_name}'."
            )
            continue
        if not command:
            failures.append(
                f"Replay plan for {capsule_id} acceptance_checks[{index}] must include the oracle command for '{oracle_name}'."
            )
            continue
        if command != expected_command:
            failures.append(
                f"Replay plan for {capsule_id} acceptance_checks[{index}] command does not match oracle '{oracle_name}'."
            )
            continue
        acceptance_oracle_names.append(oracle_name)

    equivalence_inputs = plan.get("equivalence_inputs") if isinstance(plan.get("equivalence_inputs"), dict) else {}
    planned_material_paths = _safe_string_list(equivalence_inputs.get("material_paths"))
    if not planned_material_paths:
        failures.append(f"Replay plan for {capsule_id} must declare equivalence_inputs.material_paths.")
    else:
        planned_material_set = {str(item.get("path") or "").strip() for item in material_inputs if isinstance(item, dict)}
        for path in planned_material_paths:
            if path not in planned_material_set:
                failures.append(
                    f"Replay plan for {capsule_id} equivalence_inputs.material_paths references '{path}' outside material_inputs."
                )

    planned_oracle_names = _safe_string_list(equivalence_inputs.get("oracle_names"))
    baseline_hash = equivalence_inputs.get("baseline_hash")
    expected_baseline_hash = baseline_equivalence.get("oracle_digest") or baseline_equivalence.get("observed_hash")
    normalized_expected_baseline = expected_baseline_hash if isinstance(expected_baseline_hash, str) and expected_baseline_hash else None
    normalized_planned_baseline = baseline_hash if isinstance(baseline_hash, str) and baseline_hash else None
    if normalized_expected_baseline is not None and normalized_planned_baseline != normalized_expected_baseline:
        failures.append(
            f"Replay plan for {capsule_id} must carry baseline hash '{normalized_expected_baseline}' in equivalence_inputs."
        )
    if normalized_expected_baseline is None and normalized_planned_baseline is not None:
        failures.append(f"Replay plan for {capsule_id} must not invent a baseline hash when no prior replay baseline exists.")

    if not planned_oracle_names and normalized_expected_baseline is None:
        failures.append(
            f"Replay plan for {capsule_id} must declare executable oracle-based equivalence inputs or an existing baseline hash."
        )
    for oracle_name in planned_oracle_names:
        if oracle_name not in acceptance_oracle_names:
            failures.append(
                f"Replay plan for {capsule_id} equivalence_inputs.oracle_names must match declared acceptance checks."
            )
            break

    return failures


def _collect_replay_sandbox_paths(
    repo_root: str,
    capsule_id: str,
    changed_materials: list[dict[str, object]],
) -> list[str]:
    paths: set[str] = set()
    scope_materials = _collect_capsule_scope_materials(repo_root, capsule_id, changed_materials)
    selected_changed_paths = [str(item.get("path") or "") for item in scope_materials if isinstance(item, dict)]

    for raw_path in selected_changed_paths:
        normalized = _normalize_repo_relative_path(str(raw_path)).replace("\\", "/")
        normalized = os.path.normpath(normalized)
        if not normalized or normalized == ".":
            continue
        if os.path.isabs(normalized) or normalized.startswith("../"):
            continue
        if normalized.startswith(f"{OG_ROOT}/work") or normalized.startswith(f"{OG_ROOT}/events") or normalized.startswith(
            f"{OG_ROOT}/traces"
        ):
            continue
        if normalized.startswith(".git"):
            continue
        paths.add(normalized.replace("\\", "/"))

    runtime_metadata = (
        f"{OG_ROOT}/materials.lock",
        f"{OG_ROOT}/policy.yaml",
        f"{OG_ROOT}/constitution/default.yaml",
    )
    for metadata_path in runtime_metadata:
        absolute = os.path.join(repo_root, metadata_path)
        if os.path.exists(absolute):
            paths.add(metadata_path)

    return sorted(paths)


def _materialize_replay_sandbox(
    repo_root: str,
    sandbox_root: str,
    capsule_id: str,
    changed_materials: list[dict[str, object]],
) -> list[str]:
    os.makedirs(os.path.join(repo_root, sandbox_root), exist_ok=True)
    selected_paths = _collect_replay_sandbox_paths(repo_root, capsule_id, changed_materials)
    sandbox_root_abs = os.path.join(repo_root, sandbox_root)
    missing_paths: list[str] = []

    for relative_path in selected_paths:
        source = os.path.join(repo_root, relative_path)
        if not os.path.isfile(source):
            if os.path.exists(source):
                continue
            missing_paths.append(relative_path)
            continue
        destination = os.path.join(sandbox_root_abs, relative_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        try:
            shutil.copy2(source, destination)
        except OSError:
            missing_paths.append(relative_path)

    return missing_paths


def _compute_replay_observed_hash(step_results: list[dict[str, object]]) -> str:
    observed: list[dict[str, object]] = []
    for raw_result in step_results:
        observed.append(
            {
                "step": str(raw_result.get("step") or ""),
                "command": str(raw_result.get("command") or ""),
                "status": str(raw_result.get("status") or ""),
                "expected_exit_code": raw_result.get("expected_exit_code"),
                "observed_exit_code": raw_result.get("observed_exit_code"),
                "stdout": _safe_string_list(raw_result.get("stdout")),
                "stderr": _safe_string_list(raw_result.get("stderr")),
            }
        )
    rendered = json.dumps(observed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _content_sha256(rendered.encode("utf-8"))


def _compute_oracle_observed_hash(checks: list[dict[str, object]]) -> str:
    observed: list[dict[str, object]] = []
    for check in checks:
        observed.append(
            {
                "oracle_name": str(check.get("oracle_name") or ""),
                "status": str(check.get("status") or ""),
                "observed_code": check.get("observed_code"),
                "stdout": _safe_string_list(check.get("stdout")),
                "stderr": _safe_string_list(check.get("stderr")),
                "message": str(check.get("message") or ""),
            }
        )
    rendered = json.dumps(observed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _content_sha256(rendered.encode("utf-8"))


def _run_replay_step(
    repo_root: str,
    sandbox_root: str,
    run_id: str,
    capsule_id: str,
    step_index: int,
    step: dict[str, object],
    *,
    timeout_seconds: int | None = None,
    max_retries: int = 0,
) -> dict[str, object]:
    command = str(step.get("command") or "").strip()
    expected_exit_code = step.get("expected_exit_code")
    if not isinstance(expected_exit_code, int):
        expected_exit_code = 0
    timeout_s = timeout_seconds if isinstance(timeout_seconds, int) and timeout_seconds > 0 else step.get("timeout_s")
    if not isinstance(timeout_s, int) or timeout_s <= 0:
        timeout_s = REPLAY_STEP_DEFAULT_TIMEOUT_SECONDS
    raw_cwd = step.get("cwd")
    cwd = str(raw_cwd).strip() if isinstance(raw_cwd, str) else "."
    if not cwd:
        cwd = "."
    normalized_cwd = os.path.normpath(_normalize_repo_relative_path(cwd).replace("\\", "/").strip("./"))
    if not normalized_cwd or normalized_cwd == ".":
        normalized_cwd = "."
    if os.path.isabs(normalized_cwd):
        normalized_cwd = "."
    sandbox_root_abs = os.path.abspath(os.path.join(repo_root, sandbox_root))
    step_cwd = os.path.abspath(os.path.join(sandbox_root_abs, normalized_cwd))
    try:
        if os.path.commonpath([sandbox_root_abs, step_cwd]) != sandbox_root_abs:
            step_cwd = sandbox_root_abs
    except ValueError:
        step_cwd = sandbox_root_abs

    start_at = time.perf_counter()
    result_payload: dict[str, object] = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "role": "replay",
        "run_id": run_id,
        "capsule_id": capsule_id,
        "step": step_index,
        "command": command,
        "expected_exit_code": expected_exit_code,
        "timeout_s": timeout_s,
        "requested_cwd": cwd,
        "resolved_cwd": os.path.relpath(step_cwd, sandbox_root_abs).replace("\\", "/"),
    }

    if not command:
        result_payload["status"] = "fail"
        result_payload["observed_exit_code"] = 1
        result_payload["message"] = "Replay step has no command."
        result_payload["failures"] = ["Replay step has no command."]
        result_payload["recovery"] = _build_recovery_record(
            f"replay-step:{capsule_id}:{step_index}",
            attempts=1,
            max_retries=max_retries,
            timeout_seconds=timeout_s,
        )
    else:
        attempts = 0
        retryable_failures: list[dict[str, object]] = []
        while True:
            attempts += 1
            try:
                executed = subprocess.run(
                    ["bash", "-lc", command],
                    cwd=step_cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
                observed_exit_code = executed.returncode
                result_payload["observed_exit_code"] = observed_exit_code
                result_payload["status"] = "pass" if observed_exit_code == expected_exit_code else "fail"
                result_payload["stdout"] = (executed.stdout or "").splitlines()[-5:]
                result_payload["stderr"] = (executed.stderr or "").splitlines()[-5:]
                result_payload["message"] = "replay step executed."
                if result_payload["status"] != "pass":
                    result_payload["failures"] = [
                        f"Replay step {step_index} failed with code {observed_exit_code}, expected {expected_exit_code}."
                    ]
                else:
                    result_payload["failures"] = []
                result_payload["recovery"] = _build_recovery_record(
                    f"replay-step:{capsule_id}:{step_index}",
                    attempts=attempts,
                    max_retries=max_retries,
                    timeout_seconds=timeout_s,
                    recovered=bool(retryable_failures) and result_payload["status"] == "pass",
                    retryable_failures=retryable_failures,
                )
                break
            except subprocess.TimeoutExpired as exc:
                if attempts <= max_retries:
                    retryable_failures.append(
                        {
                            "attempt": attempts,
                            "error_code": TIMEOUT_EXPIRED_CODE,
                            "message": f"Replay step {step_index} timed out after {timeout_s}s",
                            "timed_out": True,
                        }
                    )
                    continue
                result_payload["status"] = "fail"
                result_payload["code"] = RECOVERY_RETRY_EXHAUSTED_CODE if retryable_failures else TIMEOUT_EXPIRED_CODE
                result_payload["observed_exit_code"] = -1
                result_payload["message"] = f"Replay step timed out after {timeout_s}s"
                result_payload["failures"] = [f"Replay step {step_index} timed out after {timeout_s}s"]
                result_payload["timeout_error"] = str(exc)
                result_payload["recovery"] = _build_recovery_record(
                    f"replay-step:{capsule_id}:{step_index}",
                    attempts=attempts,
                    max_retries=max_retries,
                    timeout_seconds=timeout_s,
                    exhausted=bool(retryable_failures),
                    retryable=True,
                    retryable_failures=retryable_failures,
                    error_code=result_payload["code"],
                    message=result_payload["message"],
                )
                break
            except Exception as exc:
                result_payload["status"] = "fail"
                result_payload["code"] = RUNTIME_ERROR_CODE
                result_payload["observed_exit_code"] = 1
                result_payload["message"] = "Replay step failed to execute"
                result_payload["failures"] = [f"Replay step {step_index} failed: {exc}"]
                result_payload["recovery"] = _build_recovery_record(
                    f"replay-step:{capsule_id}:{step_index}",
                    attempts=attempts,
                    max_retries=max_retries,
                    timeout_seconds=timeout_s,
                    retryable=False,
                    error_code=RUNTIME_ERROR_CODE,
                    message=str(result_payload["failures"][0]),
                )
                break

    result_payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
    trace_path = _build_trace_path(run_id, capsule_id, "replay-step", step_index)
    trace_payload_bytes = json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    full_trace_path = os.path.join(repo_root, trace_path)
    os.makedirs(os.path.dirname(full_trace_path), exist_ok=True)
    _write_text_payload(full_trace_path, trace_payload_bytes.decode("utf-8"))
    result_payload["trace"] = trace_path
    result_payload["receipt_pointers"] = [
        _build_file_pointer(trace_path, trace_payload_bytes, "application/json"),
        _store_put(repo_root, trace_payload_bytes, "application/json"),
    ]
    return result_payload


def _collect_affected_capsules(changed_files: list[str]) -> list[str]:
    return sorted(_group_changed_files_by_capsule(changed_files))


def _artifact_filename_capsule_id(relative_path: str, prefix: str | None = None) -> str | None:
    filename = os.path.basename(relative_path)
    stem = os.path.splitext(filename)[0]
    if prefix is not None:
        if not stem.startswith(prefix):
            return None
        remainder = stem[len(prefix) :]
        if not remainder:
            return None
        capsule_part, separator, _ = remainder.rpartition("-")
        stem = capsule_part if separator else remainder
    else:
        stem = stem.lstrip(".")
    normalized = _safe_slug(stem)
    return normalized or None


def _capsule_id_for_canonical_internal_path(relative_path: str) -> str | None:
    internal = _normalize_repo_relative_path(relative_path)
    if not internal:
        return None
    if internal.startswith("capsules/"):
        return _artifact_filename_capsule_id(internal) or "default"
    if internal.startswith("decisions/"):
        return _artifact_filename_capsule_id(internal) or "default"
    if internal.startswith("refs/"):
        return _artifact_filename_capsule_id(internal) or "default"
    if internal.startswith("claims/"):
        return _artifact_filename_capsule_id(internal, "cl-") or "default"
    if internal.startswith("certificates/"):
        return _artifact_filename_capsule_id(internal, "cert-") or "default"
    if internal == "materials.lock":
        return "materials"
    if internal == "policy.yaml":
        return "policy"
    if internal == "config.yaml":
        return "config"
    if internal == ".gitignore":
        return "runtime"
    if internal.startswith("constitution/"):
        return "constitution"
    if internal.startswith("export/"):
        return "export"
    return None


def _capsule_id_for_repo_path(relative_path: str) -> str:
    normalized = _normalize_repo_relative_path(relative_path)
    if normalized.startswith(f"{OG_ROOT}/"):
        internal = normalized[len(OG_ROOT) + 1 :]
        canonical_capsule = _capsule_id_for_canonical_internal_path(internal)
        if canonical_capsule is not None:
            return canonical_capsule
        internal_top = internal.split("/", 1)[0]
        return _safe_slug(internal_top) or "default"

    canonical_capsule = _capsule_id_for_canonical_internal_path(normalized)
    if canonical_capsule is not None:
        return canonical_capsule

    parts = normalized.split("/")
    top = parts[0]
    if len(parts) > 1:
        if top == "skills" and len(parts) > 2:
            skill_name = _safe_slug(parts[1])
            if skill_name:
                return f"skill-{skill_name}"
        if top.startswith("."):
            hidden = _safe_slug(top.lstrip("."))
            if hidden:
                return hidden
        return _safe_slug(top) or "default"

    if top.startswith("."):
        hidden_name = os.path.splitext(top.lstrip("."))[0]
        return _safe_slug(hidden_name) or "repo-config"
    return _artifact_filename_capsule_id(top) or "default"


def _group_changed_files_by_capsule(changed_files: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for raw_path in changed_files:
        if not isinstance(raw_path, str):
            continue
        normalized = _normalize_repo_relative_path(raw_path)
        if not normalized:
            continue
        capsule_id = _capsule_id_for_repo_path(normalized)
        grouped.setdefault(capsule_id, []).append(normalized)
    return {
        capsule_id: sorted(set(paths))
        for capsule_id, paths in grouped.items()
    }


def _normalize_capsule_kind(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return value if value in CAPSULE_KIND_VALUES else None


def _classify_path_capsule_kind(relative_path: str) -> str | None:
    normalized = _normalize_repo_relative_path(relative_path)
    if not normalized:
        return None

    lower = normalized.lower()
    basename = os.path.basename(lower)
    stem, extension = os.path.splitext(basename)
    if normalized in {".gitignore", OUTCOME_GITIGNORE} or normalized.startswith(RUNTIME_IGNORE_PREFIXES):
        return CAPSULE_KIND_RUNTIME
    if normalized.startswith(f"{OG_ROOT}/"):
        internal = normalized[len(OG_ROOT) + 1 :]
        if internal in {"config.yaml", "materials.lock", "policy.yaml"}:
            return CAPSULE_KIND_CONFIG
        if internal.startswith(("cache/", "events/", "objects/", "traces/", "work/")):
            return CAPSULE_KIND_RUNTIME
    if normalized.startswith(CAPSULE_KIND_TEST_PATH_PREFIXES):
        return CAPSULE_KIND_TEST
    if basename.startswith("test_") or any(basename.endswith(suffix) for suffix in CAPSULE_KIND_TEST_FILENAME_SUFFIXES):
        return CAPSULE_KIND_TEST
    if normalized.startswith(CAPSULE_KIND_DOC_PATH_PREFIXES) or extension in CAPSULE_KIND_DOC_EXTENSIONS:
        return CAPSULE_KIND_DOC
    if normalized.startswith(CAPSULE_KIND_CONFIG_PATH_PREFIXES):
        return CAPSULE_KIND_CONFIG
    if basename in CAPSULE_KIND_CONFIG_FILENAMES or extension in CAPSULE_KIND_CONFIG_EXTENSIONS:
        return CAPSULE_KIND_CONFIG
    if basename in CAPSULE_KIND_CODE_FILENAMES or extension in CAPSULE_KIND_CODE_EXTENSIONS:
        return CAPSULE_KIND_CODE
    if stem in {"readme", "changelog", "license"}:
        return CAPSULE_KIND_DOC
    return None


def _classify_capsule_kind(
    capsule_id: str,
    changed_files: list[str],
    scope: list[str],
    existing_payload: dict[str, object] | None = None,
) -> str:
    existing_kind = _normalize_capsule_kind(existing_payload.get("kind")) if isinstance(existing_payload, dict) else None
    if existing_kind is not None:
        return existing_kind

    normalized_capsule_id = _safe_slug(capsule_id) or "default"
    if normalized_capsule_id == "runtime":
        return CAPSULE_KIND_RUNTIME
    if normalized_capsule_id in {"test", "tests"}:
        return CAPSULE_KIND_TEST

    observed_paths: list[str] = []
    for raw_path in [*changed_files, *scope]:
        normalized = _normalize_repo_relative_path(str(raw_path))
        if normalized and normalized not in observed_paths:
            observed_paths.append(normalized)

    observed_kinds = {
        kind
        for kind in (_classify_path_capsule_kind(path) for path in observed_paths)
        if kind is not None
    }
    if not observed_kinds:
        if normalized_capsule_id in {"config", "materials", "policy"}:
            return CAPSULE_KIND_CONFIG
        return CAPSULE_KIND_CODE
    if CAPSULE_KIND_CODE in observed_kinds:
        return CAPSULE_KIND_CODE
    if observed_kinds <= {CAPSULE_KIND_TEST, CAPSULE_KIND_DOC} and CAPSULE_KIND_TEST in observed_kinds:
        return CAPSULE_KIND_TEST
    if observed_kinds == {CAPSULE_KIND_RUNTIME}:
        return CAPSULE_KIND_RUNTIME
    if observed_kinds <= {CAPSULE_KIND_CONFIG, CAPSULE_KIND_RUNTIME}:
        return CAPSULE_KIND_CONFIG if CAPSULE_KIND_CONFIG in observed_kinds else CAPSULE_KIND_RUNTIME
    if observed_kinds <= {CAPSULE_KIND_DOC, CAPSULE_KIND_CONFIG}:
        return CAPSULE_KIND_DOC if CAPSULE_KIND_DOC in observed_kinds else CAPSULE_KIND_CONFIG
    if CAPSULE_KIND_TEST in observed_kinds:
        return CAPSULE_KIND_TEST
    if CAPSULE_KIND_DOC in observed_kinds:
        return CAPSULE_KIND_DOC
    if CAPSULE_KIND_CONFIG in observed_kinds:
        return CAPSULE_KIND_CONFIG
    return CAPSULE_KIND_CODE


def _normalize_distill_status(status: object) -> str:
    value = str(status or "success").strip().lower()
    if value == "ok":
        return "success"
    if value == "warning":
        return "warn"
    return value or "success"


def _apply_kind_specific_success_policy(
    capsule_id: str,
    capsule_kind: str,
    status: str,
    oracle_summary: dict[str, object],
) -> tuple[str, list[str]]:
    normalized_status = _normalize_distill_status(status)
    if capsule_kind not in {CAPSULE_KIND_CODE, CAPSULE_KIND_TEST}:
        return normalized_status, []

    explicit_commands = _safe_string_list(oracle_summary.get("explicit_executable_commands"))
    blocked_commands = _safe_string_list(oracle_summary.get("policy_blocked_commands"))

    if normalized_status != "success":
        return normalized_status, []
    if explicit_commands:
        return normalized_status, []

    warning = f"{capsule_kind} capsule {capsule_id} requires explicit executable oracle evidence for success"
    if blocked_commands:
        warning = f"{warning}; policy blocked {', '.join(blocked_commands)}"
    return "warn", [warning]


def _apply_recreation_brief_success_policy(
    capsule_id: str,
    status: str,
    claims: list[dict[str, object]],
    behavior_claims: list[str],
    invariants: list[str],
    dependencies: list[str],
    unknowns: list[str],
    oracles: list[dict[str, object]],
) -> tuple[str, list[str]]:
    normalized_status = _normalize_distill_status(status)
    if normalized_status != "success":
        return normalized_status, []

    warnings: list[str] = []
    if not behavior_claims:
        warnings.append(f"capsule {capsule_id} requires explicit behavior_claims for success")
    if not any(
        isinstance(claim, dict)
        and str(claim.get("category") or "").strip().lower() == "behavior"
        and str(claim.get("text") or "").strip()
        for claim in claims
    ):
        warnings.append(f"capsule {capsule_id} requires at least one evidence-backed behavior claim for success")
    if not invariants:
        warnings.append(f"capsule {capsule_id} requires explicit invariants for success")
    if not dependencies:
        warnings.append(f"capsule {capsule_id} requires explicit dependencies for success")
    if not unknowns:
        warnings.append(f"capsule {capsule_id} requires explicit unknowns for success")

    executable_oracles = [
        oracle
        for oracle in oracles
        if isinstance(oracle, dict) and str(oracle.get("command") or "").strip()
    ]
    advisory_reasons = [
        str(oracle.get("reason") or "").strip()
        for oracle in oracles
        if isinstance(oracle, dict)
        and not str(oracle.get("command") or "").strip()
        and str(oracle.get("reason") or "").strip()
    ]
    if not executable_oracles and not advisory_reasons:
        warnings.append(f"capsule {capsule_id} requires an acceptance oracle or explicit oracle gap reason for success")

    if warnings:
        return "warn", warnings
    return normalized_status, []


def _safe_string_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if value:
            values.append(value)
    return values


def _safe_object_list(raw: object) -> list[dict[str, object]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    values: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            values.append(cast(dict[str, object], item))
    return values


def _normalize_artifact_id(payload: dict[str, object], path: str, fallback_key: str | None = None) -> str:
    raw = payload.get(fallback_key or "id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return os.path.splitext(os.path.basename(path))[0]


def _normalize_reference_to_id(reference: object) -> str | None:
    if not isinstance(reference, str):
        return None
    text = reference.strip()
    if not text:
        return None
    return os.path.splitext(os.path.basename(text))[0]


def _collect_artifact_payloads(
    repo_root: str,
    relative_dir: str,
    *,
    strict: bool = False,
) -> list[tuple[str, dict[str, object]]]:
    root = os.path.join(repo_root, relative_dir)
    if not os.path.isdir(root):
        return []
    expected_type = _expected_canonical_artifact_type(relative_dir)
    payloads: list[tuple[str, dict[str, object]]] = []
    for dirpath, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            if not filename.endswith(".json"):
                continue
            full_path = os.path.join(dirpath, filename)
            if strict:
                payload = _read_canonical_artifact_payload(
                    repo_root,
                    os.path.relpath(full_path, repo_root).replace("\\", "/"),
                    expected_artifact_type=expected_type,
                )
            else:
                payload = _read_json_file(full_path)
                if not isinstance(payload, dict):
                    continue
            relative_path = os.path.relpath(full_path, repo_root).replace("\\", "/")
            payloads.append((relative_path, payload))
    return payloads


def _collect_latest_sync_deltas(repo_root: str) -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    latest_event, _ = _read_latest_sync_event(repo_root)
    if not isinstance(latest_event, dict):
        return [], {}
    deltas: list[dict[str, object]] = []
    by_capsule: dict[str, list[dict[str, object]]] = {}
    for raw_step in latest_event.get("steps", []) if isinstance(latest_event.get("steps"), list) else []:
        if not isinstance(raw_step, dict) or raw_step.get("name") != "distill":
            continue
        generated_deltas = raw_step.get("generated_deltas")
        if not isinstance(generated_deltas, list):
            continue
        for raw_delta in generated_deltas:
            if not isinstance(raw_delta, dict):
                continue
            capsule_id = str(raw_delta.get("capsule_id") or raw_delta.get("id") or "").strip()
            entry: dict[str, object] = {
                "capsule_id": capsule_id or "default",
                "status": str(raw_delta.get("status") or raw_step.get("status") or "unknown"),
                "decision_refs": _safe_string_list(raw_delta.get("decision_refs")),
                "changed_files": _safe_string_list(raw_delta.get("changed_files")),
                "claims": [],
                "run_id": str(latest_event.get("run_id") or ""),
                "step_status": str(raw_step.get("status") or ""),
            }
            if isinstance(raw_delta.get("claims"), list):
                entry["claims"] = [str(item.get("id")) for item in raw_delta.get("claims") if isinstance(item, dict) and isinstance(item.get("id"), str)]
            deltas.append(entry)
            by_capsule.setdefault(entry["capsule_id"], []).append(entry)
    return deltas, by_capsule


def _collect_claim_records(repo_root: str) -> list[dict[str, object]]:
    claims: list[dict[str, object]] = []
    for path, payload in _collect_artifact_payloads(
        repo_root,
        f"{OG_ROOT}/claims",
        strict=True,
    ):
        claims.append(
            {
                "path": path,
                "id": _normalize_artifact_id(payload, path, "id"),
                "capsule_id": str(payload.get("capsule_id") or "default"),
                "text": str(payload.get("text") or ""),
                "category": str(payload.get("category") or "behavior"),
                "origin": payload.get("origin"),
                "run_id": str(payload.get("run_id") or ""),
                "receipt_pointers": _safe_object_list(payload.get("receipt_pointers")),
                "raw": payload,
            }
        )
    return claims


def _collect_certificate_records(repo_root: str) -> list[dict[str, object]]:
    certificates: list[dict[str, object]] = []
    for path, payload in _collect_artifact_payloads(
        repo_root,
        f"{OG_ROOT}/certificates",
        strict=True,
    ):
        certificates.append(
            {
                "path": path,
                "id": _normalize_artifact_id(payload, path, "id"),
                "capsule_id": str(payload.get("capsule_id") or "default"),
                "claim_refs": _safe_string_list(payload.get("claim_refs")),
                "receipt_pointers": _safe_object_list(payload.get("receipt_pointers")),
                "status": str(payload.get("status") or "unknown"),
                "run_id": str(payload.get("run_id") or ""),
                "raw": payload,
            }
        )
    return certificates


def _collect_successful_certificate_refs_by_capsule(repo_root: str) -> dict[str, list[str]]:
    default_timestamp = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
    certificates = _collect_certificate_records(repo_root)
    grouped: dict[str, list[tuple[datetime.datetime, str]]] = {}
    for raw in certificates:
        if str(raw.get("status") or "").lower() != "success":
            continue
        path = str(raw.get("path") or "").strip()
        if not path:
            continue
        capsule_id = _safe_slug(str(raw.get("capsule_id") or "default"))
        raw_payload = raw.get("raw") if isinstance(raw.get("raw"), dict) else None
        updated_at_raw = ""
        if isinstance(raw_payload, dict):
            raw_updated_at = raw_payload.get("updated_at")
            if isinstance(raw_updated_at, str):
                updated_at_raw = raw_updated_at
        updated_at = _parse_utc_timestamp(updated_at_raw) or default_timestamp
        grouped.setdefault(capsule_id, []).append((updated_at, path))
    success_refs: dict[str, list[str]] = {}
    for capsule_id, refs in grouped.items():
        refs = sorted(refs, key=lambda item: (item[0], item[1]), reverse=True)
        seen_paths: set[str] = set()
        ordered_paths: list[str] = []
        for _, path in refs:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            ordered_paths.append(path)
        if ordered_paths:
            success_refs[capsule_id] = ordered_paths
    return success_refs


def _collect_decision_records(repo_root: str) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for path, payload in _collect_artifact_payloads(
        repo_root,
        f"{OG_ROOT}/decisions",
        strict=True,
    ):
        decisions.append(
            {
                "path": path,
                "id": _normalize_artifact_id(payload, path, "id"),
                "capsule_id": str(payload.get("capsule_id") or "default"),
                "claim_refs": _safe_string_list(payload.get("claim_refs")),
                "evidence_refs": _safe_string_list(payload.get("evidence_refs")),
                "statement": str(payload.get("statement") or ""),
                "status": str(payload.get("status") or "unknown"),
                "raw": payload,
            }
        )
    return decisions


def _collect_ref_records(repo_root: str) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for path, payload in _collect_artifact_payloads(
        repo_root,
        f"{OG_ROOT}/refs",
        strict=True,
    ):
        refs.append(
            {
                "path": path,
                "id": _normalize_artifact_id(payload, path, "id"),
                "capsule_id": str(payload.get("capsule_id") or "default"),
                "raw": payload,
            }
        )
    return refs


def _collect_capsule_quality_records(repo_root: str) -> list[dict[str, object]]:
    capsules: list[dict[str, object]] = []
    for path, payload in _collect_artifact_payloads(
        repo_root,
        f"{OG_ROOT}/capsules",
        strict=True,
    ):
        capsule_id = _normalize_artifact_id(payload, path, "id")
        scope = _safe_string_list(payload.get("scope"))
        capsules.append(
            {
                "path": path,
                "id": capsule_id,
                "kind": _classify_capsule_kind(capsule_id, [], scope, payload),
                "status": _normalize_distill_status(payload.get("status")),
                "scope": scope,
                "invariants": _safe_string_list(payload.get("invariants")),
                "behavior_claims": _safe_string_list(payload.get("behavior_claims")),
                "oracles": _safe_object_list(payload.get("oracles")),
                "decision_refs": _normalize_artifact_path_refs(payload.get("decision_refs"), "decisions"),
                "raw": payload,
            }
        )
    return capsules


def _index_artifact_records_by_reference(
    records: list[dict[str, object]],
    scope: str,
) -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        candidates = [
            _normalize_canonical_artifact_reference(str(record.get("path") or ""), scope),
            _normalize_canonical_artifact_reference(str(record.get("id") or ""), scope),
        ]
        for candidate in candidates:
            if candidate and candidate not in index:
                index[candidate] = record
    return index


def _capsule_has_executable_oracle(capsule_record: dict[str, object]) -> bool:
    for oracle in _safe_object_list(capsule_record.get("oracles")):
        if str(oracle.get("command") or "").strip():
            return True
    return False


def _capsule_is_advisory_only(capsule_record: dict[str, object]) -> bool:
    oracles = _safe_object_list(capsule_record.get("oracles"))
    if not oracles:
        return False
    if _capsule_has_executable_oracle(capsule_record):
        return False
    for oracle in oracles:
        if str(oracle.get("reason") or "").strip() or str(oracle.get("name") or "").strip():
            return True
    return False


def _collect_capsule_linked_claims(
    capsule_record: dict[str, object],
    decisions_by_capsule: dict[str, list[dict[str, object]]],
    decision_index: dict[str, dict[str, object]],
    claim_index: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    capsule_id = _safe_slug(str(capsule_record.get("id") or "default")) or "default"
    decision_refs = _safe_string_list(capsule_record.get("decision_refs"))
    if not decision_refs:
        decision_refs = [
            str(record.get("path") or "")
            for record in decisions_by_capsule.get(capsule_id, [])
            if isinstance(record, dict)
        ]

    claims: list[dict[str, object]] = []
    seen_claims: set[str] = set()
    for raw_ref in decision_refs:
        normalized_decision_ref = _normalize_canonical_artifact_reference(raw_ref, "decisions")
        if not normalized_decision_ref:
            continue
        decision = decision_index.get(normalized_decision_ref)
        if not isinstance(decision, dict):
            continue
        for claim_ref in _safe_string_list(decision.get("claim_refs")):
            normalized_claim_ref = _normalize_canonical_artifact_reference(claim_ref, "claims")
            if not normalized_claim_ref or normalized_claim_ref in seen_claims:
                continue
            claim = claim_index.get(normalized_claim_ref)
            if not isinstance(claim, dict):
                continue
            seen_claims.add(normalized_claim_ref)
            claims.append(claim)
    return claims


def _capsule_has_receipt_backed_behavior_claim(
    capsule_record: dict[str, object],
    decisions_by_capsule: dict[str, list[dict[str, object]]],
    decision_index: dict[str, dict[str, object]],
    claim_index: dict[str, dict[str, object]],
) -> bool:
    for claim in _collect_capsule_linked_claims(capsule_record, decisions_by_capsule, decision_index, claim_index):
        if str(claim.get("category") or "").strip().lower() != "behavior":
            continue
        if not str(claim.get("text") or "").strip():
            continue
        if _safe_object_list(claim.get("receipt_pointers")):
            return True
    return False


def _normalize_artifact_quality_case(raw_case: object) -> dict[str, object] | None:
    if not isinstance(raw_case, dict):
        return None
    case_id = _safe_slug(str(raw_case.get("id") or ""))
    if not case_id:
        return None
    capsule_ids = sorted(
        {
            capsule_id
            for capsule_id in (
                _safe_slug(str(item))
                for item in raw_case.get("capsule_ids", [])
                if isinstance(raw_case.get("capsule_ids"), list)
            )
            if capsule_id
        }
    )
    required_terms = [
        str(item).strip().lower()
        for item in raw_case.get("required_terms", [])
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(raw_case.get("required_terms"), list) else []
    if not capsule_ids or not required_terms:
        return None
    return {
        "id": case_id,
        "description": str(raw_case.get("description") or "").strip(),
        "capsule_ids": capsule_ids,
        "required_terms": required_terms,
    }


def _evaluate_stale_doc_truth_case(
    case: dict[str, object],
    decisions_by_capsule: dict[str, list[dict[str, object]]],
    claim_index: dict[str, dict[str, object]],
) -> dict[str, object]:
    capsule_ids = _safe_string_list(case.get("capsule_ids"))
    required_terms = [term.lower() for term in _safe_string_list(case.get("required_terms"))]
    decision_ids: list[str] = []
    claim_ids: list[str] = []
    accepted_text_parts: list[str] = []

    for capsule_id in capsule_ids:
        for decision in decisions_by_capsule.get(capsule_id, []):
            if not isinstance(decision, dict):
                continue
            decision_status = str(decision.get("status") or "").strip().lower()
            if decision_status not in ARTIFACT_QUALITY_ACCEPTED_DECISION_STATUSES:
                continue
            decision_id = str(decision.get("id") or "").strip()
            if decision_id and decision_id not in decision_ids:
                decision_ids.append(decision_id)
            statement = str(decision.get("statement") or "").strip()
            rationale = str(decision.get("rationale") or "").strip()
            if statement:
                accepted_text_parts.append(statement)
            if rationale:
                accepted_text_parts.append(rationale)
            for claim_ref in _safe_string_list(decision.get("claim_refs")):
                normalized_claim_ref = _normalize_canonical_artifact_reference(claim_ref, "claims")
                if not normalized_claim_ref:
                    continue
                claim = claim_index.get(normalized_claim_ref)
                if not isinstance(claim, dict):
                    continue
                claim_id = str(claim.get("id") or "").strip()
                if claim_id and claim_id not in claim_ids:
                    claim_ids.append(claim_id)
                claim_text = str(claim.get("text") or "").strip()
                if claim_text:
                    accepted_text_parts.append(claim_text)

    accepted_truth = " ".join(accepted_text_parts).lower()
    matched_terms = [term for term in required_terms if term in accepted_truth]
    missing_terms = [term for term in required_terms if term not in accepted_truth]
    status = "pass" if not missing_terms else "fail"
    return {
        "id": str(case.get("id") or ""),
        "description": str(case.get("description") or ""),
        "capsule_ids": capsule_ids,
        "status": status,
        "required_terms": required_terms,
        "matched_terms": matched_terms,
        "missing_terms": missing_terms,
        "decision_ids": decision_ids,
        "claim_ids": claim_ids,
    }


def _build_artifact_quality_metric(
    metric_id: str,
    *,
    numerator: int,
    denominator: int,
    min_ratio: float | None = None,
    max_ratio: float | None = None,
    passing_items: list[str] | None = None,
    failing_items: list[str] | None = None,
) -> dict[str, object]:
    ratio = 1.0 if denominator <= 0 else numerator / denominator
    status = "pass"
    threshold: dict[str, float] = {}
    if min_ratio is not None:
        threshold["min_ratio"] = float(min_ratio)
        if denominator > 0 and ratio + 1e-9 < float(min_ratio):
            status = "fail"
    if max_ratio is not None:
        threshold["max_ratio"] = float(max_ratio)
        if denominator > 0 and ratio - 1e-9 > float(max_ratio):
            status = "fail"
    return {
        "id": metric_id,
        "status": status,
        "numerator": numerator,
        "denominator": denominator,
        "ratio": ratio,
        "threshold": threshold,
        "passing_items": sorted(set(passing_items or [])),
        "failing_items": sorted(set(failing_items or [])),
    }


def _evaluate_artifact_quality(
    repo_root: str,
    *,
    contradiction_cases: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    capsule_records = _collect_capsule_quality_records(repo_root)
    decision_records = _collect_decision_records(repo_root)
    claim_records = _collect_claim_records(repo_root)

    decisions_by_capsule: dict[str, list[dict[str, object]]] = {}
    for decision in decision_records:
        capsule_id = _safe_slug(str(decision.get("capsule_id") or "default")) or "default"
        decisions_by_capsule.setdefault(capsule_id, []).append(decision)

    decision_index = _index_artifact_records_by_reference(decision_records, "decisions")
    claim_index = _index_artifact_records_by_reference(claim_records, "claims")

    code_or_test_capsules = [
        record
        for record in capsule_records
        if str(record.get("kind") or "") in {CAPSULE_KIND_CODE, CAPSULE_KIND_TEST}
    ]
    code_capsules = [
        record
        for record in capsule_records
        if str(record.get("kind") or "") == CAPSULE_KIND_CODE
    ]
    success_code_capsules = [
        record
        for record in code_capsules
        if str(record.get("status") or "").strip().lower() == "success"
    ]

    executable_oracle_capsules = [
        str(record.get("id") or "")
        for record in code_or_test_capsules
        if _capsule_has_executable_oracle(record)
    ]
    missing_executable_oracle_capsules = [
        str(record.get("id") or "")
        for record in code_or_test_capsules
        if not _capsule_has_executable_oracle(record)
    ]
    invariant_covered_capsules = [
        str(record.get("id") or "")
        for record in code_capsules
        if _safe_string_list(record.get("invariants"))
    ]
    missing_invariant_capsules = [
        str(record.get("id") or "")
        for record in code_capsules
        if not _safe_string_list(record.get("invariants"))
    ]
    evidence_backed_capsules = [
        str(record.get("id") or "")
        for record in code_capsules
        if _capsule_has_receipt_backed_behavior_claim(record, decisions_by_capsule, decision_index, claim_index)
    ]
    weak_evidence_capsules = [
        str(record.get("id") or "")
        for record in code_capsules
        if not _capsule_has_receipt_backed_behavior_claim(record, decisions_by_capsule, decision_index, claim_index)
    ]
    advisory_only_success_capsules = [
        str(record.get("id") or "")
        for record in success_code_capsules
        if _capsule_is_advisory_only(record)
    ]
    executable_success_code_capsules = [
        str(record.get("id") or "")
        for record in success_code_capsules
        if not _capsule_is_advisory_only(record)
    ]

    normalized_cases = [
        normalized
        for normalized in (_normalize_artifact_quality_case(raw_case) for raw_case in contradiction_cases or [])
        if normalized is not None
    ]
    stale_doc_results = [
        _evaluate_stale_doc_truth_case(case, decisions_by_capsule, claim_index)
        for case in normalized_cases
    ]
    resolved_contradiction_ids = [
        str(result.get("id") or "")
        for result in stale_doc_results
        if str(result.get("status") or "") == "pass"
    ]
    unresolved_contradiction_ids = [
        str(result.get("id") or "")
        for result in stale_doc_results
        if str(result.get("status") or "") != "pass"
    ]

    metrics = {
        "code_test_executable_oracle_coverage": _build_artifact_quality_metric(
            "code_test_executable_oracle_coverage",
            numerator=len(executable_oracle_capsules),
            denominator=len(code_or_test_capsules),
            min_ratio=ARTIFACT_QUALITY_MIN_EXECUTABLE_ORACLE_COVERAGE,
            passing_items=executable_oracle_capsules,
            failing_items=missing_executable_oracle_capsules,
        ),
        "code_invariant_coverage": _build_artifact_quality_metric(
            "code_invariant_coverage",
            numerator=len(invariant_covered_capsules),
            denominator=len(code_capsules),
            min_ratio=ARTIFACT_QUALITY_MIN_CODE_INVARIANT_COVERAGE,
            passing_items=invariant_covered_capsules,
            failing_items=missing_invariant_capsules,
        ),
        "code_receipt_backed_behavior_claim_coverage": _build_artifact_quality_metric(
            "code_receipt_backed_behavior_claim_coverage",
            numerator=len(evidence_backed_capsules),
            denominator=len(code_capsules),
            min_ratio=ARTIFACT_QUALITY_MIN_CODE_EVIDENCE_COVERAGE,
            passing_items=evidence_backed_capsules,
            failing_items=weak_evidence_capsules,
        ),
        "success_code_advisory_only_rate": _build_artifact_quality_metric(
            "success_code_advisory_only_rate",
            numerator=len(advisory_only_success_capsules),
            denominator=len(success_code_capsules),
            max_ratio=ARTIFACT_QUALITY_MAX_SUCCESS_CODE_ADVISORY_ONLY_RATE,
            passing_items=executable_success_code_capsules,
            failing_items=advisory_only_success_capsules,
        ),
        "stale_doc_accepted_truth_capture": _build_artifact_quality_metric(
            "stale_doc_accepted_truth_capture",
            numerator=len(resolved_contradiction_ids),
            denominator=len(stale_doc_results),
            min_ratio=ARTIFACT_QUALITY_MIN_STALE_DOC_CAPTURE_RATE,
            passing_items=resolved_contradiction_ids,
            failing_items=unresolved_contradiction_ids,
        ),
    }

    failed_metrics = [
        metric_id
        for metric_id, metric in metrics.items()
        if isinstance(metric, dict) and str(metric.get("status") or "") == "fail"
    ]
    capsule_kind_counts: dict[str, int] = {}
    for record in capsule_records:
        kind = str(record.get("kind") or "").strip() or "unknown"
        capsule_kind_counts[kind] = capsule_kind_counts.get(kind, 0) + 1

    return {
        "schema_version": ARTIFACT_QUALITY_SCHEMA_VERSION,
        "artifact_type": "artifact_quality_evaluation",
        "status": "pass" if not failed_metrics else "fail",
        "capsule_counts": {
            "total": len(capsule_records),
            "by_kind": capsule_kind_counts,
            "code_or_test": len(code_or_test_capsules),
            "code": len(code_capsules),
            "success_code": len(success_code_capsules),
        },
        "metrics": metrics,
        "failures": failed_metrics,
        "capsules": {
            "code_or_test": sorted(str(record.get("id") or "") for record in code_or_test_capsules),
            "code": sorted(str(record.get("id") or "") for record in code_capsules),
            "success_code": sorted(str(record.get("id") or "") for record in success_code_capsules),
        },
        "stale_doc_contradictions": stale_doc_results,
    }


def _list_known_capsules(repo_root: str) -> list[str]:
    capsules_dir = os.path.join(repo_root, OG_ROOT, "capsules")
    if not os.path.isdir(capsules_dir):
        return []
    capsules = set()
    for filename in sorted(os.listdir(capsules_dir)):
        if not filename.endswith((".json", ".yaml", ".yml")):
            continue
        if filename.startswith("."):
            continue
        capsules.add(os.path.splitext(filename)[0])
    return sorted(capsules)


def _merge_repo_relative_paths(*path_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in path_groups:
        for raw_path in group:
            normalized = _normalize_repo_relative_path(str(raw_path))
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def _distill_feature_tokens(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for raw_path in paths:
        normalized = _normalize_repo_relative_path(str(raw_path)).lower()
        if not normalized:
            continue
        for segment in normalized.split("/"):
            stem, _ = os.path.splitext(segment)
            for candidate in re.findall(r"[a-z0-9]+", stem):
                if len(candidate) < 2 or candidate.isdigit() or candidate in DISTILL_FEATURE_TOKEN_STOPWORDS:
                    continue
                if candidate in seen:
                    continue
                seen.add(candidate)
                tokens.append(candidate)
    return tokens


def _should_skip_related_context_dir(relative_dir: str) -> bool:
    normalized = _normalize_repo_relative_path(relative_dir)
    if not normalized:
        return False
    ignored_segments = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        OG_ROOT,
    }
    segments = {segment for segment in normalized.split("/") if segment}
    if normalized in ignored_segments or segments.intersection(ignored_segments):
        return True
    if normalized.startswith(f"{OG_ROOT}/"):
        return True
    return any(normalized.startswith(prefix.rstrip("/")) for prefix in RUNTIME_IGNORE_PREFIXES)


def _iter_repo_context_candidate_paths(repo_root: str) -> list[str]:
    candidates: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        relative_dir = os.path.relpath(dirpath, repo_root).replace("\\", "/")
        if relative_dir == ".":
            relative_dir = ""
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _should_skip_related_context_dir(f"{relative_dir}/{dirname}" if relative_dir else dirname)
        ]
        for filename in sorted(filenames):
            relative_path = f"{relative_dir}/{filename}" if relative_dir else filename
            normalized = _normalize_repo_relative_path(relative_path)
            if (
                not normalized
                or normalized.startswith(".git/")
                or normalized.startswith(f"{OG_ROOT}/")
                or any(normalized.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES)
            ):
                continue
            full_path = os.path.join(repo_root, normalized)
            if os.path.isfile(full_path):
                candidates.append(normalized)
    return candidates


def _discover_related_scope_paths(
    repo_root: str,
    seed_paths: list[str],
    excluded_paths: set[str],
    *,
    prefer_kind: str | None = None,
    candidate_paths: list[str] | None = None,
    limit: int = DISTILL_RELATED_HINT_LIMIT,
) -> list[str]:
    if limit <= 0:
        return []
    seed_tokens = set(_distill_feature_tokens(seed_paths))
    if not seed_tokens:
        return []

    seed_directories = {
        os.path.dirname(_normalize_repo_relative_path(path)) or "."
        for path in seed_paths
        if _normalize_repo_relative_path(path)
    }
    seed_top_levels = {
        _normalize_repo_relative_path(path).split("/", 1)[0]
        for path in seed_paths
        if _normalize_repo_relative_path(path)
    }
    ranked: list[tuple[int, str]] = []
    for candidate in candidate_paths or _iter_repo_context_candidate_paths(repo_root):
        if candidate in excluded_paths:
            continue
        candidate_kind = _classify_path_capsule_kind(candidate)
        if candidate_kind is None:
            continue
        if prefer_kind is not None and candidate_kind != prefer_kind:
            continue
        candidate_tokens = set(_distill_feature_tokens([candidate]))
        overlap = seed_tokens & candidate_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        candidate_directory = os.path.dirname(candidate) or "."
        if candidate_directory in seed_directories:
            score += 4
        candidate_top_level = candidate.split("/", 1)[0]
        if candidate_top_level in seed_top_levels:
            score += 2
        basename = os.path.splitext(os.path.basename(candidate))[0].lower()
        if any(token == basename or token in basename for token in overlap):
            score += 2
        if prefer_kind is not None:
            score += 3
        ranked.append((-score, candidate))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _, candidate in ranked[:limit]]


def _truncate_context_text(raw: object, *, limit: int = 240) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 1)].rstrip()}..."


def _summarize_oracle_payloads(raw_oracles: list[dict[str, object]], *, limit: int = DISTILL_RELATED_HINT_LIMIT) -> list[dict[str, object]]:
    summarized: list[dict[str, object]] = []
    for raw_oracle in raw_oracles:
        normalized_oracle = _normalize_oracle_entry(raw_oracle)
        if normalized_oracle is None:
            continue
        summarized.append(
            {
                "name": str(normalized_oracle.get("name") or ""),
                "command": normalized_oracle.get("command"),
                **({"reason": str(normalized_oracle.get("reason") or "")} if normalized_oracle.get("reason") else {}),
                "scope": _safe_string_list(normalized_oracle.get("scope")),
            }
        )
        if len(summarized) >= limit:
            break
    return summarized


def _build_changed_region_context(changed_file_snapshots: list[dict[str, object]]) -> list[dict[str, object]]:
    context: list[dict[str, object]] = []
    for snapshot in changed_file_snapshots:
        if not isinstance(snapshot, dict):
            continue
        entry: dict[str, object] = {
            "path": str(snapshot.get("path") or ""),
            "selection": str(snapshot.get("selection") or "full"),
            "partial": bool(snapshot.get("partial")),
            "truncated": bool(snapshot.get("truncated")),
        }
        line_count = snapshot.get("line_count")
        if isinstance(line_count, int) and line_count >= 0:
            entry["line_count"] = line_count
        raw_snippets = snapshot.get("snippets")
        if isinstance(raw_snippets, list):
            entry["snippets"] = [
                {
                    "start_line": int(raw_snippet.get("start_line") or 0),
                    "end_line": int(raw_snippet.get("end_line") or 0),
                }
                for raw_snippet in raw_snippets
                if isinstance(raw_snippet, dict)
            ]
            entry["snippets_truncated"] = bool(snapshot.get("snippets_truncated"))
        context.append(entry)
    return context


def _collect_materials_for_scope(
    repo_root: str,
    scope_patterns: list[str],
    changed_materials: list[dict[str, object]],
) -> list[dict[str, object]]:
    material_records, _ = _read_material_lock_records(repo_root)
    selected: dict[str, dict[str, object]] = {}
    for path, record in material_records.items():
        if _path_matches_capsule_scope(path, scope_patterns):
            selected[path] = dict(record)
    for raw_material in changed_materials:
        if not isinstance(raw_material, dict):
            continue
        path = str(raw_material.get("path") or "").strip()
        digest = str(raw_material.get("digest") or "").strip()
        if not path or not digest:
            continue
        if _path_matches_capsule_scope(path, scope_patterns):
            selected[path] = {"path": path, "digest": digest}
            if isinstance(raw_material.get("kind"), str):
                selected[path]["kind"] = str(raw_material.get("kind") or "file")
            if isinstance(raw_material.get("size"), int) and int(raw_material.get("size")) >= 0:
                selected[path]["size"] = int(raw_material.get("size"))
    return [selected[path] for path in sorted(selected)]


def _summarize_material_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    summarized: list[dict[str, object]] = []
    for raw_record in records[:DISTILL_MATERIAL_LIMIT]:
        if not isinstance(raw_record, dict):
            continue
        entry: dict[str, object] = {
            "path": str(raw_record.get("path") or ""),
            "digest": str(raw_record.get("digest") or ""),
        }
        if isinstance(raw_record.get("kind"), str):
            entry["kind"] = str(raw_record.get("kind") or "file")
        size = raw_record.get("size")
        if isinstance(size, int) and size >= 0:
            entry["size"] = size
        summarized.append(entry)
    return summarized


def _build_materials_context(
    scope_patterns: list[str],
    changed_materials: list[dict[str, object]],
    scope_materials: list[dict[str, object]],
    *,
    materials_lock_ref: str = f"{OG_ROOT}/materials.lock",
) -> dict[str, object]:
    return {
        "materials_lock_ref": materials_lock_ref,
        "scope_patterns": scope_patterns,
        "changed_material_count": len(changed_materials),
        "changed_materials_truncated": len(changed_materials) > DISTILL_MATERIAL_LIMIT,
        "changed_materials": _summarize_material_records(changed_materials),
        "scope_material_count": len(scope_materials),
        "scope_materials_truncated": len(scope_materials) > DISTILL_MATERIAL_LIMIT,
        "scope_materials": _summarize_material_records(scope_materials),
    }


def _build_existing_capsule_summary(
    capsule_id: str,
    capsule_kind: str,
    existing_capsule: dict[str, object] | None,
    claims_by_capsule: dict[str, list[dict[str, object]]],
    decisions_by_capsule: dict[str, list[dict[str, object]]],
    certificate_refs_by_capsule: dict[str, list[str]],
) -> dict[str, object] | None:
    if not isinstance(existing_capsule, dict):
        return None
    normalized_capsule_id = _safe_slug(capsule_id) or "default"
    scope = _safe_string_list(existing_capsule.get("scope"))
    return {
        "id": str(existing_capsule.get("id") or normalized_capsule_id),
        "kind": capsule_kind,
        "status": str(existing_capsule.get("status") or ""),
        "goal": str(existing_capsule.get("goal") or ""),
        "scope": scope,
        "behavior_claims": _safe_string_list(existing_capsule.get("behavior_claims")),
        "constraints": _safe_string_list(existing_capsule.get("constraints")),
        "invariants": _safe_string_list(existing_capsule.get("invariants")),
        "dependencies": _safe_string_list(existing_capsule.get("dependencies")),
        "oracles": _summarize_oracle_payloads(_safe_object_list(existing_capsule.get("oracles"))),
        "unknowns": _safe_string_list(existing_capsule.get("unknowns")),
        "lineage": existing_capsule.get("lineage") if isinstance(existing_capsule.get("lineage"), dict) else {},
        "claim_highlights": [
            {
                "id": str(claim.get("id") or ""),
                "category": str(claim.get("category") or "behavior"),
                "text": _truncate_context_text(claim.get("text")),
                "source_paths": _safe_string_list(claim.get("raw", {}).get("source_paths") if isinstance(claim.get("raw"), dict) else claim.get("source_paths")),
            }
            for claim in claims_by_capsule.get(normalized_capsule_id, [])[:DISTILL_EXISTING_CLAIM_LIMIT]
        ],
        "decision_highlights": [
            {
                "id": str(decision.get("id") or ""),
                "status": str(decision.get("status") or ""),
                "statement": _truncate_context_text(decision.get("statement")),
                "claim_refs": _safe_string_list(decision.get("claim_refs")),
                "evidence_refs": _safe_string_list(decision.get("evidence_refs")),
            }
            for decision in decisions_by_capsule.get(normalized_capsule_id, [])[:DISTILL_EXISTING_DECISION_LIMIT]
        ],
        "successful_certificate_refs": certificate_refs_by_capsule.get(normalized_capsule_id, [])[:DISTILL_EXISTING_CERTIFICATE_LIMIT],
    }


def _build_related_test_hints(
    existing_scope: list[str],
    supporting_scope_paths: list[str],
    discovered_supporting_paths: list[str],
) -> list[dict[str, object]]:
    hints: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for path in supporting_scope_paths:
        if _classify_path_capsule_kind(path) != CAPSULE_KIND_TEST or path in seen_paths:
            continue
        seen_paths.add(path)
        reason = "existing capsule scope" if path in existing_scope else "discovered from changed-file feature tokens"
        if path in discovered_supporting_paths:
            reason = "discovered from changed-file feature tokens"
        hints.append({"path": path, "reason": reason})
        if len(hints) >= DISTILL_RELATED_HINT_LIMIT:
            break
    return hints


def _build_related_oracle_hints(
    capsule_id: str,
    changed_files: list[str],
    supporting_scope_paths: list[str],
    capsule_payloads: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    normalized_capsule_id = _safe_slug(capsule_id) or "default"
    relevant_paths = _merge_repo_relative_paths(changed_files, supporting_scope_paths)
    hints: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for related_capsule_id in sorted(capsule_payloads):
        payload = capsule_payloads[related_capsule_id]
        raw_oracles = _safe_object_list(payload.get("oracles"))
        if not raw_oracles:
            continue
        scope = _safe_string_list(payload.get("scope"))
        related_kind = _classify_capsule_kind(related_capsule_id, [], scope, payload)
        if related_capsule_id != normalized_capsule_id and not any(
            _path_matches_capsule_scope(path, scope) for path in relevant_paths
        ):
            continue
        for raw_oracle in raw_oracles:
            normalized_oracle = _normalize_oracle_entry(raw_oracle)
            if normalized_oracle is None:
                continue
            oracle_scope = _safe_string_list(normalized_oracle.get("scope"))
            if related_capsule_id != normalized_capsule_id and oracle_scope and not any(
                _path_matches_capsule_scope(path, oracle_scope) for path in relevant_paths
            ):
                continue
            name = str(normalized_oracle.get("name") or "").strip()
            command = str(normalized_oracle.get("command") or "").strip()
            key = (related_capsule_id, name, command)
            if key in seen:
                continue
            seen.add(key)
            reason = "existing capsule oracle"
            if related_capsule_id != normalized_capsule_id:
                reason = "scope overlap with changed files"
                if related_kind == CAPSULE_KIND_TEST:
                    reason = "scope overlap with related test context"
            hints.append(
                {
                    "capsule_id": related_capsule_id,
                    "name": name,
                    "command": normalized_oracle.get("command"),
                    "scope": oracle_scope,
                    "reason": reason,
                }
            )
            if len(hints) >= DISTILL_RELATED_HINT_LIMIT:
                return hints
    return hints


def _build_distill_target_capsules(
    repo_root: str,
    changed_capsules: list[str],
    changed_files_by_capsule: dict[str, list[str]],
    *,
    diff_baseline: str | None = None,
    force_full_sync: bool = False,
    changed_materials: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    resolved_changed_materials = (
        [item for item in changed_materials if isinstance(item, dict)]
        if isinstance(changed_materials, list)
        else _collect_changed_materials(
            repo_root,
            sorted({path for paths in changed_files_by_capsule.values() for path in paths}),
        )
    )
    claims_by_capsule: dict[str, list[dict[str, object]]] = {}
    for claim in _collect_claim_records(repo_root):
        normalized_capsule_id = _safe_slug(str(claim.get("capsule_id") or "default")) or "default"
        claims_by_capsule.setdefault(normalized_capsule_id, []).append(claim)
    decisions_by_capsule: dict[str, list[dict[str, object]]] = {}
    for decision in _collect_decision_records(repo_root):
        normalized_capsule_id = _safe_slug(str(decision.get("capsule_id") or "default")) or "default"
        decisions_by_capsule.setdefault(normalized_capsule_id, []).append(decision)
    certificate_refs_by_capsule = _collect_successful_certificate_refs_by_capsule(repo_root)
    capsule_payloads: dict[str, dict[str, object]] = {}
    for known_capsule_id in _list_known_capsules(repo_root):
        payload = _load_capsule_payload(repo_root, known_capsule_id)
        if payload:
            capsule_payloads[_safe_slug(known_capsule_id) or "default"] = payload
    context_candidate_paths = _iter_repo_context_candidate_paths(repo_root)
    targets: list[dict[str, object]] = []
    for capsule_id in changed_capsules:
        normalized_capsule_id = _safe_slug(capsule_id) or "default"
        existing_capsule = _load_capsule_payload(repo_root, normalized_capsule_id) or None
        changed_files = changed_files_by_capsule.get(normalized_capsule_id, [])
        existing_scope = _safe_string_list(existing_capsule.get("scope")) if existing_capsule else []
        capsule_kind = _classify_capsule_kind(
            normalized_capsule_id,
            changed_files,
            existing_scope,
            existing_capsule,
        )
        supporting_scope_paths = _collect_supporting_scope_paths(
            repo_root,
            existing_scope,
            changed_files,
        )
        preferred_related_kind = (
            CAPSULE_KIND_TEST
            if capsule_kind == CAPSULE_KIND_CODE
            else CAPSULE_KIND_CODE if capsule_kind == CAPSULE_KIND_TEST else None
        )
        discovered_supporting_paths = _discover_related_scope_paths(
            repo_root,
            _merge_repo_relative_paths(changed_files, existing_scope),
            set(_merge_repo_relative_paths(changed_files, supporting_scope_paths)),
            prefer_kind=preferred_related_kind,
            candidate_paths=context_candidate_paths,
            limit=max(DISTILL_SUPPORTING_SNAPSHOT_LIMIT - len(supporting_scope_paths), 0),
        )
        supporting_scope_paths = _merge_repo_relative_paths(
            supporting_scope_paths,
            discovered_supporting_paths,
        )[:DISTILL_SUPPORTING_SNAPSHOT_LIMIT]
        changed_file_snapshots = [
            snapshot
            for snapshot in (
                _read_repo_file_snapshot(
                    repo_root,
                    path,
                    diff_baseline=diff_baseline,
                    force_full=force_full_sync,
                )
                for path in changed_files
            )
            if snapshot
        ]
        effective_scope_patterns = _merge_repo_relative_paths(
            existing_scope,
            changed_files,
            supporting_scope_paths,
        )
        scope_materials = _collect_materials_for_scope(
            repo_root,
            effective_scope_patterns or changed_files,
            resolved_changed_materials,
        )
        capsule_changed_materials = _collect_materials_for_scope(
            repo_root,
            changed_files,
            resolved_changed_materials,
        )
        capsule_payloads.setdefault(normalized_capsule_id, existing_capsule or {})
        targets.append(
            {
                "id": normalized_capsule_id,
                "kind": capsule_kind,
                "changed_files": changed_files,
                "changed_file_snapshots": changed_file_snapshots,
                "changed_region_context": _build_changed_region_context(changed_file_snapshots),
                "supporting_scope_paths": supporting_scope_paths,
                "supporting_file_snapshots": [
                    snapshot
                    for snapshot in (_read_repo_file_snapshot(repo_root, path) for path in supporting_scope_paths)
                    if snapshot
                ],
                "existing_capsule": (
                    {
                        "id": str(existing_capsule.get("id") or normalized_capsule_id),
                        "kind": capsule_kind,
                        "goal": str(existing_capsule.get("goal") or ""),
                        "scope": existing_scope,
                        "behavior_claims": _safe_string_list(existing_capsule.get("behavior_claims")),
                        "constraints": _safe_string_list(existing_capsule.get("constraints")),
                        "invariants": _safe_string_list(existing_capsule.get("invariants")),
                        "dependencies": _safe_string_list(existing_capsule.get("dependencies")),
                        "oracles": _safe_object_list(existing_capsule.get("oracles")),
                        "unknowns": _safe_string_list(existing_capsule.get("unknowns")),
                        "lineage": existing_capsule.get("lineage") if isinstance(existing_capsule.get("lineage"), dict) else {},
                    }
                    if existing_capsule
                    else None
                ),
                "existing_capsule_summary": _build_existing_capsule_summary(
                    normalized_capsule_id,
                    capsule_kind,
                    existing_capsule,
                    claims_by_capsule,
                    decisions_by_capsule,
                    certificate_refs_by_capsule,
                ),
                "related_test_hints": _build_related_test_hints(
                    existing_scope,
                    supporting_scope_paths,
                    discovered_supporting_paths,
                ),
                "related_oracle_hints": _build_related_oracle_hints(
                    normalized_capsule_id,
                    changed_files,
                    supporting_scope_paths,
                    capsule_payloads,
                ),
                "materials_context": _build_materials_context(
                    effective_scope_patterns or changed_files,
                    capsule_changed_materials,
                    scope_materials,
                ),
            }
        )
    return targets


def _snapshot_char_limit(relative_path: str) -> int:
    normalized_path = _normalize_repo_relative_path(relative_path)
    _, extension = os.path.splitext(normalized_path.lower())
    if extension in {".md", ".txt", ".rst"}:
        return 40000
    if extension in {".json", ".yaml", ".yml", ".toml", ".lock"}:
        return 48000
    if extension in {".py", ".sh"}:
        return 12000
    return 6000


def _snapshot_partial_char_limit(relative_path: str) -> int:
    normalized_path = _normalize_repo_relative_path(relative_path)
    _, extension = os.path.splitext(normalized_path.lower())
    if extension in {".md", ".txt", ".rst"}:
        return 32000
    if extension in {".json", ".yaml", ".yml", ".toml", ".lock"}:
        return 28000
    if extension in {".py", ".sh"}:
        return 20000
    return 16000


_DIFF_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _merge_line_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return merged


def _collect_changed_line_ranges(diff_text: str, *, line_count: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    max_line = max(line_count, 1)
    for line in diff_text.splitlines():
        match = _DIFF_HUNK_HEADER_RE.match(line)
        if match is None:
            continue
        changed_start = int(match.group(1))
        changed_count = int(match.group(2) or "1")
        if changed_count <= 0:
            changed_count = 1
        changed_end = changed_start + changed_count - 1
        ranges.append(
            (
                max(1, changed_start - SNAPSHOT_DIFF_CONTEXT_LINES),
                min(max_line, changed_end + SNAPSHOT_DIFF_CONTEXT_LINES),
            )
        )
    return _merge_line_ranges(ranges)


def _build_partial_file_snapshot(
    repo_root: str,
    normalized_path: str,
    full_path: str,
    *,
    diff_baseline: str,
) -> dict[str, object] | None:
    diff_result = _run_git(repo_root, ["diff", "--unified=0", diff_baseline, "--", normalized_path])
    diff_text = diff_result.stdout if diff_result.returncode == 0 else ""
    if not diff_text.strip():
        return None
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, UnicodeDecodeError):
        return None

    line_ranges = _collect_changed_line_ranges(diff_text, line_count=len(lines))
    if not line_ranges:
        return None

    snippets: list[dict[str, object]] = []
    rendered_sections: list[str] = []
    chars_remaining = _snapshot_partial_char_limit(normalized_path)
    truncated = False

    for start_line, end_line in line_ranges:
        if len(snippets) >= SNAPSHOT_DIFF_MAX_SNIPPETS:
            truncated = True
            break
        if chars_remaining <= 0:
            truncated = True
            break

        selected_lines: list[str] = []
        included_end_line = start_line - 1
        for line_number in range(start_line, end_line + 1):
            source_line = lines[line_number - 1]
            if selected_lines and len(source_line) > chars_remaining:
                truncated = True
                break
            if not selected_lines and len(source_line) > chars_remaining:
                selected_lines.append(source_line[:chars_remaining])
                included_end_line = line_number
                chars_remaining = 0
                truncated = True
                break
            if len(source_line) > chars_remaining:
                truncated = True
                break
            selected_lines.append(source_line)
            included_end_line = line_number
            chars_remaining -= len(source_line)

        if not selected_lines:
            truncated = True
            break

        snippet_text = "".join(selected_lines)
        snippets.append(
            {
                "path": normalized_path,
                "start_line": start_line,
                "end_line": included_end_line,
                "content": snippet_text,
            }
        )
        rendered_sections.append(f"@@ lines {start_line}-{included_end_line} @@\n{snippet_text}")
        if included_end_line < end_line:
            truncated = True
            break

    return {
        "path": normalized_path,
        "digest": _file_sha256(normalized_path, repo_root),
        "kind": "symlink_file" if os.path.islink(full_path) else "file",
        "content": "\n\n".join(rendered_sections),
        "truncated": False,
        "partial": True,
        "selection": "diff_hunks",
        "line_count": len(lines),
        "snippets": snippets,
        "snippets_truncated": truncated,
    }


def _collect_supporting_scope_paths(repo_root: str, scope: list[str], changed_files: list[str]) -> list[str]:
    changed = {item for item in changed_files if item}
    supporting: list[str] = []
    seen: set[str] = set()
    for raw_path in scope:
        candidate = _normalize_repo_relative_path(raw_path)
        if not candidate or candidate in seen or candidate in changed:
            continue
        if any(candidate.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES):
            continue
        full_path = os.path.join(repo_root, candidate)
        if not (os.path.isfile(full_path) or os.path.isdir(full_path)):
            continue
        supporting.append(candidate)
        seen.add(candidate)
        if len(supporting) >= DISTILL_SUPPORTING_SNAPSHOT_LIMIT:
            break
    return supporting


def _read_repo_file_snapshot(
    repo_root: str,
    relative_path: str,
    max_chars: int | None = None,
    *,
    diff_baseline: str | None = None,
    force_full: bool = False,
) -> dict[str, object] | None:
    normalized_path = _normalize_repo_relative_path(relative_path)
    if not normalized_path:
        return None
    if max_chars is None:
        max_chars = _snapshot_char_limit(normalized_path)
    full_path = os.path.join(repo_root, normalized_path)
    if os.path.isdir(full_path):
        try:
            entries = sorted(os.listdir(full_path))
        except OSError:
            return None
        truncated = len(entries) > 20
        return {
            "path": normalized_path,
            "digest": None,
            "kind": "symlink_directory" if os.path.islink(full_path) else "directory",
            "entries": entries[:20],
            "truncated": truncated,
            **({"symlink_target": os.readlink(full_path)} if os.path.islink(full_path) else {}),
        }
    if not os.path.isfile(full_path):
        return None
    if not force_full and diff_baseline and diff_baseline != EMPTY_TREE_OBJECT_ID:
        partial_snapshot = _build_partial_file_snapshot(
            repo_root,
            normalized_path,
            full_path,
            diff_baseline=diff_baseline,
        )
        if partial_snapshot is not None:
            if os.path.islink(full_path):
                try:
                    partial_snapshot["symlink_target"] = os.readlink(full_path)
                except OSError:
                    pass
            return partial_snapshot
    try:
        with open(full_path, "r", encoding="utf-8") as handle:
            content = handle.read(max_chars + 1)
    except (OSError, UnicodeDecodeError):
        return None
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    snapshot = {
        "path": normalized_path,
        "digest": _file_sha256(normalized_path, repo_root),
        "kind": "symlink_file" if os.path.islink(full_path) else "file",
        "content": content,
        "truncated": truncated,
    }
    if os.path.islink(full_path):
        try:
            snapshot["symlink_target"] = os.readlink(full_path)
        except OSError:
            pass
    return snapshot


def _file_sha256(relative_path: str, repo_root: str) -> str | None:
    candidate = os.path.join(repo_root, relative_path)
    try:
        with open(candidate, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        return f"sha256:{digest}"
    except OSError:
        return None


def _collect_changed_materials(repo_root: str, changed_files: list[str]) -> list[dict[str, object]]:
    materials: list[dict[str, object]] = []
    for path in changed_files:
        digest = _file_sha256(path, repo_root)
        if digest is None:
            continue
        materials.append({"path": path, "digest": digest})
    return materials


def _collect_changed_material_updates(
    repo_root: str,
    changed_files: list[str],
) -> tuple[list[dict[str, object]], list[str]]:
    updates: dict[str, dict[str, object]] = {}
    removed: list[str] = []
    for path in changed_files:
        normalized = _normalize_repo_relative_path(str(path))
        digest = _file_sha256(normalized, repo_root)
        if digest is None:
            if normalized:
                removed.append(normalized)
            continue
        absolute_path = os.path.join(repo_root, normalized)
        try:
            size = os.path.getsize(absolute_path)
        except OSError:
            size = None
        updates[normalized] = {
            "path": normalized,
            "kind": "file",
            "digest": digest,
        }
        if isinstance(size, int) and size >= 0:
            updates[normalized]["size"] = size

    return sorted(updates.values(), key=lambda item: item["path"]), sorted(set(removed))


def _normalize_canonical_artifact_reference(raw: str, scope: str) -> str:
    normalized = str(raw or "").strip().replace("\\", "/")
    if normalized.startswith(f"{OG_ROOT}/"):
        normalized = normalized[len(f"{OG_ROOT}/") :]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = "/".join(part for part in normalized.split("/") if part and part not in {"."})
    if not normalized:
        return ""
    if not normalized.startswith(f"{scope}/") and "/" not in normalized:
        normalized = f"{scope}/{normalized}"
    base, extension = os.path.splitext(normalized)
    if extension.lower() not in {".json", ".yaml", ".yml"}:
        normalized = f"{base}.json"
    return normalized


def _read_material_lock_records(repo_root: str) -> tuple[dict[str, dict[str, object]], str]:
    path = os.path.join(repo_root, OG_ROOT, "materials.lock")
    payload = _read_json_file(path)
    created_at = _utc_timestamp()
    if not isinstance(payload, dict):
        return {}, created_at

    existing_created_at = payload.get("created_at")
    captured_at = payload.get("captured_at")
    if isinstance(existing_created_at, str):
        created_at = existing_created_at
    elif isinstance(captured_at, str):
        created_at = captured_at

    records: dict[str, dict[str, object]] = {}
    raw_entries = payload.get("entries") if isinstance(payload.get("entries"), list) else payload.get("material_paths")
    if not isinstance(raw_entries, list):
        return records, created_at

    if isinstance(payload.get("entries"), list):
        source = payload.get("entries")
    else:
        source = payload.get("material_paths")

    for raw_entry in source or []:
        if isinstance(raw_entry, dict):
            path = str(raw_entry.get("path") or "").strip()
            digest = str(raw_entry.get("digest") or "").strip()
            if not path or not digest:
                continue
            normalized = _normalize_repo_relative_path(path)
            if not normalized:
                continue
            entry = {
                "path": normalized,
                "digest": digest,
                "kind": str(raw_entry.get("kind") or "file").strip() or "file",
            }
            size = raw_entry.get("size")
            if isinstance(size, int) and size >= 0:
                entry["size"] = size
            records[normalized] = entry
            continue
        if isinstance(raw_entry, str):
            normalized = _normalize_repo_relative_path(raw_entry)
            if not normalized:
                continue
            digest = _file_sha256(normalized, repo_root)
            if not digest:
                continue
            absolute_path = os.path.join(repo_root, normalized)
            entry = {
                "path": normalized,
                "digest": digest,
                "kind": "file",
            }
            try:
                entry["size"] = os.path.getsize(absolute_path)
            except OSError:
                pass
            records[normalized] = entry
    return records, created_at


def _merge_materials_lock_records(
    existing: dict[str, dict[str, object]],
    updated: list[dict[str, object]],
    removed: list[str],
) -> dict[str, dict[str, object]]:
    merged = dict(existing)
    for path in removed:
        merged.pop(path, None)
    for item in updated:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        digest = str(item.get("digest") or "").strip()
        if not digest:
            continue
        record = {
            "path": path,
            "digest": digest,
            "kind": str(item.get("kind") or "file").strip() or "file",
        }
        size = item.get("size")
        if isinstance(size, int) and size >= 0:
            record["size"] = size
        merged[path] = record
    return merged


def _materials_lock_state_is_valid(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != 2:
        return False
    if str(payload.get("artifact_type") or "") != "materials_lock":
        return False
    if not isinstance(payload.get("entries"), list):
        return False
    return True


def _material_lock_path() -> str:
    return f"{OG_ROOT}/materials.lock"


def _read_json_file_dict(path: str) -> dict[str, object] | None:
    payload = _read_json_file(path)
    return payload if isinstance(payload, dict) else None


def _build_capsule_payload(
    capsule_id: str,
    changed_files: list[str],
    decision_refs: list[str],
    existing_payload: dict[str, object] | None,
    created_at_default: str,
    goal: str | None = None,
    scope: list[str] | None = None,
    kind: str | None = None,
    behavior_claims: list[str] | None = None,
    constraints: list[str] | None = None,
    invariants: list[str] | None = None,
    dependencies: list[str] | None = None,
    oracles: list[dict[str, object]] | None = None,
    lineage: dict[str, object] | None = None,
    unknowns: list[str] | None = None,
    status: str = "active",
) -> dict[str, object]:
    now = _utc_timestamp()
    existing = existing_payload or {}
    existing_scope = _safe_string_list(existing.get("scope")) if isinstance(existing, dict) else []
    resolved_scope = [str(item) for item in scope or [] if str(item).strip()]
    if not resolved_scope:
        resolved_scope = existing_scope if existing_scope else []
    if not resolved_scope:
        for item in _safe_string_list(changed_files):
            normalized = _normalize_repo_relative_path(item)
            if normalized.startswith(f"{OG_ROOT}/"):
                continue
            if not normalized:
                continue
            top = normalized.split("/", 1)[0]
            if top and top not in resolved_scope:
                resolved_scope.append(top)
    if not resolved_scope:
        resolved_scope = ["."]
    resolved_kind = (
        _normalize_capsule_kind(kind)
        or _normalize_capsule_kind(existing.get("kind"))
        or _classify_capsule_kind(capsule_id, changed_files, resolved_scope, existing if isinstance(existing, dict) else None)
    )

    existing_oracles = _safe_object_list(existing.get("oracles"))
    if oracles is None:
        resolved_oracles = existing_oracles
    else:
        resolved_oracles = [oracle for oracle in oracles if isinstance(oracle, dict)]
    if not resolved_oracles:
        resolved_oracles = [
            {
                "name": f"{_safe_slug(capsule_id)}-verify",
                "command": None,
                "reason": "No explicit executable oracle was recorded for this capsule.",
                "scope": [],
            }
        ]

    merged_decision_refs = _normalize_artifact_path_refs(existing.get("decision_refs"), "decisions") if isinstance(existing, dict) else []
    merged_decision_refs.extend(_safe_string_list(decision_refs))
    merged_decision_refs = sorted({item for item in merged_decision_refs if isinstance(item, str)})
    created_at = str(existing.get("created_at") or created_at_default)
    if behavior_claims is None:
        resolved_behavior_claims = _safe_string_list(existing.get("behavior_claims"))
    else:
        resolved_behavior_claims = _safe_string_list(behavior_claims)
    if constraints is None:
        resolved_constraints = _safe_string_list(existing.get("constraints"))
    else:
        resolved_constraints = _safe_string_list(constraints)
    if invariants is None:
        resolved_invariants = _safe_string_list(existing.get("invariants"))
    else:
        resolved_invariants = _safe_string_list(invariants)
    if dependencies is None:
        resolved_dependencies = _safe_string_list(existing.get("dependencies"))
    else:
        resolved_dependencies = _safe_string_list(dependencies)
    if unknowns is None:
        resolved_unknowns = _safe_string_list(existing.get("unknowns"))
    else:
        resolved_unknowns = _safe_string_list(unknowns)
    resolved_status = str(status).strip() if str(status).strip() else str(existing.get("status") or "active")
    return {
        "schema_version": 2,
        "artifact_type": "capsule",
        "id": _safe_slug(capsule_id),
        "kind": resolved_kind,
        "goal": str(goal or existing.get("goal") or f"OutcomeGraph capsule for {capsule_id}"),
        "scope": resolved_scope,
        "behavior_claims": resolved_behavior_claims,
        "constraints": resolved_constraints,
        "invariants": resolved_invariants,
        "dependencies": resolved_dependencies,
        "oracles": resolved_oracles,
        "unknowns": resolved_unknowns,
        "materials_lock_ref": f"{OG_ROOT}/materials.lock",
        "decision_refs": merged_decision_refs,
        "lineage": lineage if isinstance(lineage, dict) and lineage else existing.get("lineage") or {},
        "status": resolved_status,
        "created_at": created_at,
        "updated_at": now,
    }


def _policy_allows_verify_command(policy: dict[str, object], mode: str, command: str) -> bool:
    normalized_command = command.strip()
    if not normalized_command:
        return False
    denied = _ensure_policy_action_allowed(
        policy,
        command="verify",
        category="verify_commands",
        target=normalized_command,
        mode=mode,
    )
    return denied is None


def _normalize_capsule_oracles_for_apply(
    capsule_id: str,
    oracles: list[dict[str, object]],
    changed_files: list[str],
    scope: list[str],
    status: str,
    policy: dict[str, object],
    mode: str,
) -> tuple[list[dict[str, object]], str, dict[str, object]]:
    normalized: list[dict[str, object]] = []
    explicit_executable_commands: set[str] = set()
    policy_blocked_commands: set[str] = set()
    oracle_scope = sorted(
        {
            _normalize_repo_relative_path(str(item))
            for item in [*changed_files, *scope]
            if _normalize_repo_relative_path(str(item))
        }
    )

    for raw_oracle in oracles:
        normalized_oracle = _normalize_oracle_entry(raw_oracle)
        if normalized_oracle is None:
            continue
        command_value = str(normalized_oracle.get("command") or "").strip()
        if command_value and not _policy_allows_verify_command(policy, mode, command_value):
            normalized_oracle["command"] = None
            normalized_oracle["name"] = f"{normalized_oracle['name']} (advisory only in {mode} mode)"
            policy_reason = f"Command '{command_value}' is not allowed by policy in {mode} mode."
            existing_reason = str(normalized_oracle.get("reason") or "").strip()
            normalized_oracle["reason"] = f"{existing_reason} {policy_reason}".strip() if existing_reason else policy_reason
            policy_blocked_commands.add(command_value)
        command_after = str(normalized_oracle.get("command") or "").strip()
        if command_after:
            if command_value:
                explicit_executable_commands.add(command_after)
        normalized.append(normalized_oracle)

    if not normalized:
        normalized = [
            {
                "name": f"{_safe_slug(capsule_id)}-verify",
                "command": None,
                "reason": "No explicit executable oracle was available from distill evidence.",
                "scope": oracle_scope,
            }
        ]
    return (
        normalized,
        _normalize_distill_status(status),
        {
            "explicit_executable_commands": sorted(explicit_executable_commands),
            "policy_blocked_commands": sorted(policy_blocked_commands),
        },
    )


def _normalize_artifact_path_refs(raw_refs: object, scope: str) -> list[str]:
    normalized: list[str] = []
    if not isinstance(raw_refs, list):
        return normalized
    for raw_ref in raw_refs:
        item = _normalize_canonical_artifact_reference(str(raw_ref), scope)
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _build_ref_payload(
    ref_id: str,
    capsule_id: str,
    existing_payload: dict[str, object] | None,
) -> dict[str, object]:
    now = _utc_timestamp()
    existing = existing_payload or {}
    created_at = str(existing.get("created_at") or now)
    return {
        "schema_version": 2,
        "artifact_type": "ref",
        "id": _safe_slug(ref_id),
        "capsule_id": _safe_slug(capsule_id),
        "created_at": created_at,
        "updated_at": now,
    }


def _build_decision_payload(
    decision_id: str,
    capsule_id: str,
    claim_refs: list[str],
    evidence_refs: list[str],
    existing_payload: dict[str, object] | None,
    statement: str | None = None,
    rationale: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    now = _utc_timestamp()
    existing = existing_payload or {}
    created_at = str(existing.get("created_at") or now)
    merged_claim_refs = sorted(set(_safe_string_list(existing.get("claim_refs")) + [item for item in claim_refs if item]))
    merged_evidence_refs = sorted(set(_safe_string_list(existing.get("evidence_refs")) + [item for item in evidence_refs if item]))
    return {
        "schema_version": 2,
        "artifact_type": "decision",
        "id": _safe_slug(decision_id),
        "capsule_id": _safe_slug(capsule_id),
        "statement": str(statement or existing.get("statement") or f"Decision for {capsule_id} derived from sync outcome."),
        "rationale": str(rationale or existing.get("rationale") or "Computed from distill/apply stage evidence."),
        "claim_refs": merged_claim_refs,
        "status": str(status or existing.get("status") or "accepted"),
        "evidence_refs": merged_evidence_refs,
        "created_at": created_at,
        "updated_at": now,
    }


def _repair_materials_lock(repo_root: str, changed_files: list[str] | None = None) -> str:
    changed_files = changed_files or []
    normalized_changed = sorted({_normalize_repo_relative_path(str(item)) for item in changed_files if str(item).strip()})
    updates, removed = _collect_changed_material_updates(repo_root, changed_files)
    existing_records, created_at = _read_material_lock_records(repo_root)
    merged_records = _merge_materials_lock_records(existing_records, updates, removed)
    existing_payload = _read_json_file_dict(os.path.join(repo_root, _material_lock_path()))
    needs_repair = not _materials_lock_state_is_valid(existing_payload)
    if not normalized_changed and not updates and not removed and not needs_repair:
        if existing_payload is None:
            needs_repair = True
        else:
            return _material_lock_path()

    entries = [record for record in merged_records.values()]
    entries.sort(key=lambda item: item.get("path") or "")
    payload = _build_materials_lock_payload(_utc_timestamp(), entries)
    payload["created_at"] = created_at
    payload["updated_at"] = _utc_timestamp()
    payload["captured_at"] = payload["updated_at"]
    relative_path = _material_lock_path()
    _write_canonical_artifact(repo_root, relative_path, payload)
    return relative_path


def _run_distill_stage(
    repo_root: str,
    snapshot: dict[str, object],
    run_id: str,
    profile: str,
    mode: str,
    *,
    max_retries: int = 0,
    timeout_seconds: int | None = None,
) -> dict[str, object]:
    adapter_errors = _initialize_adapter_runtime(repo_root)
    if adapter_errors:
        first_error = adapter_errors[0]
        return {
            "name": "distill",
            "status": "error",
            "code": str(first_error.get("code") or ADAPTER_INTERFACE_MISMATCH_CODE),
            "message": str(first_error.get("message") or "adapter initialization failed"),
            "profile": profile,
            "mode": mode,
            "affected_capsules": [],
            "generated_deltas": [],
            "errors": [
                str(first_error.get("message") or "adapter initialization failed"),
            ],
            **({"remediation": first_error.get("remediation", [])} if isinstance(first_error.get("remediation"), list) else {}),
        }
    changed = snapshot["changed_files"]
    changed_capsules = _collect_affected_capsules(changed if isinstance(changed, list) else [])
    if not changed_capsules:
        return {
            "name": "distill",
            "status": "skipped",
            "message": "No meaningful working-tree changes detected.",
            "profile": profile,
            "mode": mode,
            "affected_capsules": [],
            "generated_deltas": [],
        }

    if not isinstance(changed, list):
        changed = []
    changed_files = [str(entry) for entry in changed]
    changed_materials = _collect_changed_materials(repo_root, changed_files)
    changed_files_by_capsule = _group_changed_files_by_capsule(changed_files)
    try:
        worker_adapter = adapter_get("worker")
    except AdapterRegistryError as exc:
        return {
            "name": "distill",
            "status": "error",
            "code": ADAPTER_INTERFACE_MISMATCH_CODE,
            "message": str(exc),
            "profile": profile,
            "mode": mode,
            "affected_capsules": changed_capsules,
            "generated_deltas": [],
            "errors": [str(exc)],
        }
    distill_timeout_seconds = int(timeout_seconds) if isinstance(timeout_seconds, int) and timeout_seconds > 0 else _select_distill_worker_timeout(repo_root, snapshot)
    diff_baseline = None
    if isinstance(snapshot, dict):
        baseline = snapshot.get("diff_baseline")
        if isinstance(baseline, dict):
            resolved_baseline = baseline.get("resolved")
            if isinstance(resolved_baseline, str) and resolved_baseline.strip():
                diff_baseline = resolved_baseline.strip()
    target_capsules = _build_distill_target_capsules(
        repo_root,
        changed_capsules,
        changed_files_by_capsule,
        diff_baseline=diff_baseline,
        force_full_sync=bool(snapshot.get("force_full_sync")) if isinstance(snapshot, dict) else False,
        changed_materials=changed_materials,
    )
    try:
        deltas = []
        distill_prompt_provenance: dict[str, str] | None = None
        batch_specs: list[tuple[int, list[dict[str, object]], list[str], str]] = []
        for batch_index in range(0, len(target_capsules), WORKER_ADAPTER_DISTILL_BATCH_SIZE):
            batch_capsules = target_capsules[batch_index : batch_index + WORKER_ADAPTER_DISTILL_BATCH_SIZE]
            batch_changed_files: list[str] = []
            for capsule_descriptor in batch_capsules:
                if not isinstance(capsule_descriptor, dict):
                    continue
                batch_changed_files.extend(_safe_string_list(capsule_descriptor.get("changed_files")))
            if not batch_changed_files:
                batch_changed_files = changed_files
            trace_path = _build_trace_path(run_id, "distill-batch", batch_index // WORKER_ADAPTER_DISTILL_BATCH_SIZE)
            batch_specs.append((batch_index, batch_capsules, sorted(set(batch_changed_files)), trace_path))

        completed_batches: dict[int, tuple[dict[str, object], list[dict[str, object]], dict[str, object]]] = {}
        max_workers = min(WORKER_ADAPTER_DISTILL_MAX_WORKERS, max(len(batch_specs), 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {}
            for batch_index, batch_capsules, batch_changed_files, trace_path in batch_specs:
                distill_input = _build_distill_input(
                    run_id=run_id,
                    profile=profile,
                    mode=mode,
                    target_capsules=batch_capsules,
                    changed_paths=batch_changed_files,
                    policy_ref=f"{OG_ROOT}/policy.yaml",
                    materials_lock_ref=f"{OG_ROOT}/materials.lock",
                )
                future = executor.submit(
                    _run_worker_with_retries,
                    "distill",
                    distill_input,
                    repo_root,
                    trace_path,
                    worker_adapter,
                    timeout_seconds=distill_timeout_seconds,
                    max_retries=max_retries,
                )
                future_map[future] = batch_index
            for future in as_completed(future_map):
                batch_index = future_map[future]
                completed_batches[batch_index] = future.result()

        recovery_records: list[dict[str, object]] = []
        for batch_index, batch_capsules, _, _ in batch_specs:
            output, receipts, recovery = completed_batches[batch_index]
            recovery_records.append(recovery)
            batch_prompt_provenance = _normalize_prompt_provenance(output.get("prompt_provenance"))
            if batch_prompt_provenance is not None and distill_prompt_provenance is None:
                distill_prompt_provenance = batch_prompt_provenance
            delta_payload = _normalize_distill_delta(output)
            for update in delta_payload["capsule_updates"]:
                raw_delta = update if isinstance(update, dict) else {}
                capsule_id = _safe_slug(str(raw_delta.get("id") or "")) or "default"
                raw_changed_files = raw_delta.get("changed_files")
                if isinstance(raw_changed_files, list) and raw_changed_files:
                    delta_changed_files = [str(item) for item in raw_changed_files if str(item)]
                else:
                    delta_changed_files = changed_files_by_capsule.get(capsule_id, changed_files)
                deltas.append(
                    {
                        "capsule_id": capsule_id,
                        "status": str(raw_delta.get("status") or "success"),
                        "goal": raw_delta.get("goal"),
                        "scope": raw_delta.get("scope"),
                        "behavior_claims": raw_delta.get("behavior_claims"),
                        "constraints": raw_delta.get("constraints"),
                        "invariants": raw_delta.get("invariants"),
                        "dependencies": raw_delta.get("dependencies"),
                        "oracles": raw_delta.get("oracles"),
                        "claims": raw_delta.get("claims"),
                        "decision": raw_delta.get("decision"),
                        "lineage": raw_delta.get("lineage"),
                        "unknowns": raw_delta.get("unknowns"),
                        "errors": raw_delta.get("errors"),
                        "receipts": raw_delta.get("receipts") if isinstance(raw_delta.get("receipts"), list) else [],
                        "changed_files": delta_changed_files,
                        "adapter_receipts": receipts,
                        **({"prompt_provenance": batch_prompt_provenance} if batch_prompt_provenance is not None else {}),
                    }
                )
        adapter_name = str(worker_adapter.get("name", WORKER_ADAPTER_NAME))
        for delta in deltas:
            delta["adapter_name"] = adapter_name
    except WorkerAdapterError as exc:
        error_message = str(exc)
        recovery = cast(dict[str, object] | None, getattr(exc, "recovery", None))
        if _is_worker_unavailable_error(error_message):
            _set_pending_state(repo_root, f"worker runtime unavailable during distill: {error_message}")
            error_code = WORKER_RUNTIME_UNAVAILABLE_CODE
            status = "pending"
        else:
            error_code = RUNTIME_ERROR_CODE
            status = "error"
        return {
            "name": "distill",
            "status": status,
            "code": error_code,
            "message": error_message,
            "profile": profile,
            "mode": mode,
            "affected_capsules": changed_capsules,
            "generated_deltas": [],
            "errors": [{"error_code": error_code, "message": error_message}],
            "adapter_name": str(worker_adapter.get("name", WORKER_ADAPTER_NAME)),
            "recovery": recovery
            or _build_recovery_record(
                "worker:distill",
                attempts=1,
                max_retries=max_retries,
                timeout_seconds=distill_timeout_seconds,
                retryable=_is_worker_unavailable_error(error_message),
                error_code=_recovery_error_code_for_message(error_message),
                message=error_message,
            ),
        }
    return {
        "name": "distill",
        "status": "ok",
        "message": "Distill adapter produced normalized deltas.",
        "profile": profile,
        "mode": mode,
        "affected_capsules": changed_capsules,
        "adapter_name": str(worker_adapter.get("name", WORKER_ADAPTER_NAME)),
        "generated_deltas": deltas,
        "recovery": _summarize_recovery_records(recovery_records),
        **({"prompt_provenance": distill_prompt_provenance} if distill_prompt_provenance is not None else {}),
    }


def _select_distill_worker_timeout(repo_root: str, snapshot: dict[str, object]) -> int:
    if _requires_bootstrap_full_snapshot(repo_root):
        return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS

    if bool(snapshot.get("force_full_sync", False)):
        return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS

    diff_baseline = snapshot.get("diff_baseline")
    if isinstance(diff_baseline, dict) and str(diff_baseline.get("strategy") or "") == "empty_tree":
        return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS

    changed_files = snapshot.get("changed_files")
    if isinstance(changed_files, list):
        normalized = [_normalize_repo_relative_path(str(item)) for item in changed_files if str(item).strip()]
        if len(normalized) >= WORKER_ADAPTER_COMPLEX_TIMEOUT_FILE_COUNT:
            return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS

        observed_bytes = 0
        for relative_path in normalized:
            if relative_path.startswith("tests/"):
                return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS
            if os.path.splitext(relative_path)[1].lower() in WORKER_ADAPTER_COMPLEX_TIMEOUT_EXTENSIONS:
                return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS
            full_path = os.path.join(repo_root, relative_path)
            try:
                if os.path.isfile(full_path):
                    observed_bytes += os.path.getsize(full_path)
            except OSError:
                continue
            if observed_bytes >= WORKER_ADAPTER_COMPLEX_TIMEOUT_BYTES:
                return WORKER_ADAPTER_BOOTSTRAP_TIMEOUT_SECONDS

    return WORKER_ADAPTER_DEFAULT_TIMEOUT_SECONDS


def _run_apply_stage(
    repo_root: str,
    distill_result: dict[str, object],
    run_id: str,
    mode: str,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root, policy)
    if policy_error:
        return {
            "name": "apply",
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "mode": mode,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "applied_capsules": [],
            "applied_refs": [],
            "applied_decisions": [],
            "errors": [_normalize_error_record(policy_error, fallback_code=POLICY_CONFIG_ERROR_CODE)],
        }

    autonomous_block = _build_autonomous_write_block_payload(
        repo_root,
        mode,
        name="apply",
        command="apply",
    )
    if autonomous_block is not None:
        autonomous_block = {
            **autonomous_block,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "applied_capsules": [],
            "applied_refs": [],
            "applied_decisions": [],
        }
        return autonomous_block

    deny_payload = _evaluate_policy_writes(
        policy_payload,
        command="sync",
        mode=mode,
        targets=[
            f"{OG_ROOT}/capsules",
            f"{OG_ROOT}/refs",
            f"{OG_ROOT}/decisions",
            f"{OG_ROOT}/claims",
            f"{OG_ROOT}/certificates",
        ],
    )
    if deny_payload is not None:
        deny_payload = {
            **deny_payload,
            "name": "apply",
            "code": deny_payload.get("error_code") or deny_payload.get("code") or POLICY_DENIED_CODE,
            "mode": mode,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "applied_capsules": [],
            "applied_refs": [],
            "applied_decisions": [],
            "errors": [_normalize_error_record(deny_payload, fallback_code=POLICY_DENIED_CODE)],
            "message": str(deny_payload.get("message", "policy denied apply action")),
        }
        return deny_payload

    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        error_message = f"Canonical artifact validation failed: {exc}"
        return {
            "name": "apply",
            "status": "error",
            "code": RUNTIME_ERROR_CODE,
            "message": error_message,
            "mode": mode,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "errors": [{"error_code": RUNTIME_ERROR_CODE, "message": error_message}],
        }

    if distill_result.get("status") != "ok":
        return {
            "name": "apply",
            "status": "skipped",
            "message": "Distill was skipped; no structured deltas to apply.",
            "mode": mode,
            "applied_changes": 0,
        }
    deltas = distill_result.get("generated_deltas") or []
    if not isinstance(deltas, list):
        error_message = "Distill result contained malformed deltas."
        return {
            "name": "apply",
            "status": "error",
            "code": RUNTIME_ERROR_CODE,
            "message": error_message,
            "mode": mode,
            "applied_changes": 0,
            "errors": [
                {
                    "error_code": RUNTIME_ERROR_CODE,
                    "message": error_message,
                    "hint": "Review worker output and retry after fixing distill artifact schema.",
                }
            ],
        }

    affected_capsules = _safe_string_list(distill_result.get("affected_capsules"))
    if not affected_capsules:
        affected_capsules = ["default"]

    applied_claims: list[str] = []
    applied_certs: list[str] = []
    applied_capsules: list[str] = []
    applied_refs: list[str] = []
    applied_decisions: list[str] = []
    processed_capsules: set[str] = set()
    errors: list[str] = []
    warnings: list[str] = []

    def _normalize_capsule_id(raw: object, fallback: str = "default") -> str:
        if not isinstance(raw, str):
            return fallback
        text = raw.strip()
        if not text:
            return fallback
        slug = _safe_slug(text)
        return slug if slug else fallback

    def _safe_evidence_refs(raw: object) -> list[str]:
        seen: set[str] = set()
        refs: list[str] = []
        if not isinstance(raw, list):
            return refs
        for pointer in raw:
            if isinstance(pointer, str):
                value = pointer.strip()
                if value and value not in seen:
                    seen.add(value)
                    refs.append(value)
                continue
            if isinstance(pointer, dict):
                target = pointer.get("target")
                if isinstance(target, str):
                    value = target.strip()
                    if value and value not in seen:
                        seen.add(value)
                        refs.append(value)
        return refs

    normalized_discovered_capsules = sorted({_normalize_capsule_id(capsule_id) for capsule_id in affected_capsules})
    distill_prompt_provenance = _normalize_prompt_provenance(distill_result.get("prompt_provenance"))

    for delta in deltas:
        if not isinstance(delta, dict):
            errors.append("Invalid delta entry")
            continue
        capsule_id = _normalize_capsule_id(delta.get("capsule_id"), "default")
        delta_status = _normalize_distill_status(delta.get("status"))
        if delta_status in {"error", "failed", "fail"}:
            delta_errors = delta.get("errors")
            if isinstance(delta_errors, list):
                warnings.extend([str(item) for item in delta_errors if str(item)])
            warnings.append(f"distill reported non-success for capsule {capsule_id}")
            continue
        receipt_pointers = delta.get("receipt_pointers")
        if not isinstance(receipt_pointers, list):
            receipt_pointers = []
        raw_receipts = delta.get("receipts")
        if isinstance(raw_receipts, list):
            receipt_pointers.extend(raw_receipts)
        for pointer in delta.get("adapter_receipts", []):
            if isinstance(pointer, dict):
                receipt_pointers.append(pointer)
        receipt_paths = []
        for pointer in sorted(receipt_pointers, key=lambda item: json.dumps(item, sort_keys=True, default=str)):
            if isinstance(pointer, dict):
                receipt_paths.append(pointer)

        changed_files = delta.get("changed_files")
        if not isinstance(changed_files, list):
            changed_files = []
        normalized_changed_files = [str(path) for path in changed_files]
        delta_prompt_provenance = _normalize_prompt_provenance(delta.get("prompt_provenance")) or distill_prompt_provenance
        claims = delta.get("claims")
        if isinstance(claims, list):
            raw_claims = claims
        else:
            raw_claims = []

        delta_goal = str(delta.get("goal") or "").strip()
        delta_scope = _safe_string_list(delta.get("scope"))
        delta_behavior_claims = _safe_string_list(delta.get("behavior_claims"))
        delta_constraints = _safe_string_list(delta.get("constraints"))
        delta_invariants = _safe_string_list(delta.get("invariants"))
        delta_dependencies = _safe_string_list(delta.get("dependencies"))
        delta_oracles = _safe_object_list(delta.get("oracles"))
        delta_decision = delta.get("decision") if isinstance(delta.get("decision"), dict) else {}
        delta_lineage = delta.get("lineage") if isinstance(delta.get("lineage"), dict) else {}
        delta_unknowns = _safe_string_list(delta.get("unknowns"))
        existing_payload = _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "capsules", f"{capsule_id}.json"))
        capsule_kind = _classify_capsule_kind(
            capsule_id,
            normalized_changed_files,
            delta_scope,
            existing_payload,
        )
        delta_oracles, delta_status, oracle_summary = _normalize_capsule_oracles_for_apply(
            capsule_id,
            delta_oracles,
            normalized_changed_files,
            delta_scope,
            delta_status,
            policy_payload,
            mode,
        )
        delta_status, recreation_warnings = _apply_recreation_brief_success_policy(
            capsule_id,
            delta_status,
            raw_claims,
            delta_behavior_claims,
            delta_invariants,
            delta_dependencies,
            delta_unknowns,
            delta_oracles,
        )
        warnings.extend(recreation_warnings)
        delta_status, kind_warnings = _apply_kind_specific_success_policy(
            capsule_id,
            capsule_kind,
            delta_status,
            oracle_summary,
        )
        warnings.extend(kind_warnings)
        if delta_status in {"pending", "warn", "warning"}:
            delta_errors = delta.get("errors")
            if isinstance(delta_errors, list):
                warnings.extend([str(item) for item in delta_errors if str(item)])
            warnings.append(f"distill recorded {delta_status} status for capsule {capsule_id}")

        if not raw_claims:
            warnings.append(f"distill produced no evidence-backed claims for capsule {capsule_id}")
            continue
        if not delta_goal:
            warnings.append(f"distill produced no goal for capsule {capsule_id}")
            continue
        if not delta_scope:
            warnings.append(f"distill produced no scope for capsule {capsule_id}")
            continue
        if not delta_oracles:
            warnings.append(f"distill produced no oracles for capsule {capsule_id}")
            continue
        if not delta_decision:
            warnings.append(f"distill produced no decision payload for capsule {capsule_id}")
            continue

        try:
            claim_refs = []
            generated_claims = []
            for claim in raw_claims:
                if not isinstance(claim, dict):
                    warnings.append(f"distill produced malformed claim payload for capsule {capsule_id}")
                    continue
                claim_capsule = _safe_slug(str(claim.get("capsule_id") or capsule_id))
                if claim.get("capsule_id") and claim_capsule != capsule_id:
                    warnings.append(
                        f"distill produced claim for capsule {claim_capsule or '<unknown>'} while applying {capsule_id}"
                    )
                    continue
                claim_category = str(claim.get("category") or "").strip()
                claim_text = str(claim.get("text") or "").strip()
                if not claim_category or not claim_text:
                    warnings.append(f"distill produced incomplete claim data for capsule {capsule_id}")
                    continue
                claim_receipts = claim.get("receipt_pointers") if isinstance(claim.get("receipt_pointers"), list) else []
                if not claim_receipts:
                    claim_receipts = receipt_paths
                generated_claims.append(
                    {
                        "id": str(
                            claim.get("id")
                            or f"cl-{_safe_slug(capsule_id)}-{_short_hash(f'{run_id}:{capsule_id}:{len(generated_claims)}')}"
                        ),
                        "capsule_id": claim_capsule,
                        "category": claim_category,
                        "text": claim_text,
                        "receipt_pointers": claim_receipts,
                    }
                )
            if not generated_claims:
                errors.append(f"distill claims for capsule {capsule_id} could not be normalized")
                continue
            for generated_claim in generated_claims:
                claim_payload = _build_claim_payload(
                    str(generated_claim["id"]),
                    str(generated_claim["capsule_id"]),
                    run_id,
                    str(distill_result.get("profile") or "analyze"),
                    mode,
                    changed_files if isinstance(changed_files, list) else [],
                    _normalize_receipt_pointers(
                        generated_claim.get("receipt_pointers"),
                        field="generated_claim.receipt_pointers",
                    ),
                    text=str(generated_claim["text"]),
                    category=str(generated_claim["category"]),
                )
                claim_path = os.path.join(repo_root, OG_ROOT, "claims", f"{generated_claim['id']}.json")
                os.makedirs(os.path.dirname(claim_path), exist_ok=True)
                _write_canonical_artifact(
                    repo_root,
                    f"{OG_ROOT}/claims/{generated_claim['id']}.json",
                    claim_payload,
                )
                applied_claims.append(f"{OG_ROOT}/claims/{generated_claim['id']}.json")
                claim_refs.append(f"{OG_ROOT}/claims/{generated_claim['id']}.json")
        except Exception as exc:
            errors.append(f"Failed to write claim for {capsule_id}: {exc}")
            continue

        try:
            decision_id = f"dec-{_safe_slug(capsule_id)}-{_short_hash(f'{run_id}:{capsule_id}:{len(applied_decisions)}')}"
            decision_path = f"{OG_ROOT}/decisions/{decision_id}.json"
            decision_payload = _build_decision_payload(
                decision_id,
                capsule_id,
                claim_refs,
                list(_safe_evidence_refs(receipt_paths)),
                _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "decisions", f"{decision_id}.json")),
                statement=str(delta_decision.get("statement") or ""),
                rationale=str(delta_decision.get("rationale") or ""),
                status=str(delta_decision.get("status") or ""),
            )
            os.makedirs(os.path.dirname(os.path.join(repo_root, OG_ROOT, "decisions", f"{decision_id}.json")), exist_ok=True)
            _write_canonical_artifact(
                repo_root,
                decision_path,
                decision_payload,
            )
            decision_ref = _normalize_canonical_artifact_reference(decision_path, "decisions")
            applied_decisions.append(decision_ref)
        except Exception as exc:
            errors.append(f"Failed to write decision for {capsule_id}: {exc}")
            continue

        try:
            capsule_path = f"{OG_ROOT}/capsules/{capsule_id}.json"
            decision_refs = [decision_ref]
            capsule_payload = _build_capsule_payload(
                capsule_id,
                normalized_changed_files,
                decision_refs,
                existing_payload,
                _utc_timestamp(),
                goal=delta_goal,
                scope=delta_scope,
                kind=capsule_kind,
                behavior_claims=delta_behavior_claims,
                constraints=delta_constraints,
                invariants=delta_invariants,
                dependencies=delta_dependencies,
                oracles=delta_oracles,
                lineage=delta_lineage,
                unknowns=delta_unknowns,
                status=delta_status,
            )
            _write_canonical_artifact(
                repo_root,
                capsule_path,
                capsule_payload,
            )
            applied_capsules.append(capsule_path)
            processed_capsules.add(capsule_id)

            ref_path = f"{OG_ROOT}/refs/{capsule_id}.json"
            ref_payload = _build_ref_payload(
                capsule_id,
                capsule_id,
                _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "refs", f"{capsule_id}.json")),
            )
            _write_canonical_artifact(
                repo_root,
                ref_path,
                ref_payload,
            )
            applied_refs.append(ref_path)
        except Exception as exc:
            errors.append(f"Failed to write capsule/ref state for {capsule_id}: {exc}")
            continue

        try:
            certificate_id = f"cert-{_safe_slug(capsule_id)}-{_short_hash(f'{run_id}:{capsule_id}:certificate')}"
            cert_receipts = list(receipt_paths)
            cert_payload = _build_certificate_payload(
                certificate_id,
                capsule_id,
                run_id,
                claim_refs,
                str(distill_result.get("profile") or "analyze"),
                mode,
                cert_receipts,
                status=delta_status,
                adapter_name=str(distill_result.get("adapter_name") or WORKER_ADAPTER_NAME),
                prompt_provenance=delta_prompt_provenance,
            )
            if not claim_refs:
                raise RuntimeError("no claim refs produced")
            cert_path = os.path.join(repo_root, OG_ROOT, "certificates", f"{certificate_id}.json")
            os.makedirs(os.path.dirname(cert_path), exist_ok=True)
            _write_canonical_artifact(
                repo_root,
                f"{OG_ROOT}/certificates/{certificate_id}.json",
                cert_payload,
            )
            applied_certs.append(f"{OG_ROOT}/certificates/{certificate_id}.json")
        except Exception as exc:
            errors.append(f"Failed to write certificate for {capsule_id}: {exc}")

    baseline_capsules = normalized_discovered_capsules
    for capsule_id in sorted(set(baseline_capsules)):
        if capsule_id in processed_capsules:
            continue
        try:
            existing_payload = _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "capsules", f"{capsule_id}.json"))
            if not existing_payload:
                continue
            capsule_payload = _build_capsule_payload(
                capsule_id,
                [],
                [],
                existing_payload,
                _utc_timestamp(),
            )
            capsule_path = f"{OG_ROOT}/capsules/{capsule_id}.json"
            _write_canonical_artifact(
                repo_root,
                capsule_path,
                capsule_payload,
            )
            applied_capsules.append(capsule_path)

            ref_payload = _build_ref_payload(
                capsule_id,
                capsule_id,
                _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "refs", f"{capsule_id}.json")),
            )
            ref_path = f"{OG_ROOT}/refs/{capsule_id}.json"
            _write_canonical_artifact(
                repo_root,
                ref_path,
                ref_payload,
            )
            applied_refs.append(ref_path)
        except Exception as exc:
            errors.append(f"Failed to materialize baseline capsule state for {capsule_id}: {exc}")

    if errors:
        return {
            "name": "apply",
            "status": "error",
            "message": "Failed to persist one or more artifacts.",
            "mode": mode,
            "applied_changes": len(applied_claims),
            "applied_claims": applied_claims,
            "applied_certificates": applied_certs,
            "applied_capsules": applied_capsules,
            "applied_refs": applied_refs,
            "applied_decisions": applied_decisions,
            "errors": errors,
            "warnings": warnings,
        }

    if warnings:
        return {
            "name": "apply",
            "status": "warn",
            "message": "Applied usable distill deltas with warnings.",
            "mode": mode,
            "applied_changes": len(applied_claims),
            "applied_claims": applied_claims,
            "applied_certificates": applied_certs,
            "applied_capsules": applied_capsules,
            "applied_refs": applied_refs,
            "applied_decisions": applied_decisions,
            "applied_deltas": deltas,
            "errors": [],
            "warnings": warnings,
        }

    return {
        "name": "apply",
        "status": "ok",
        "message": "Applied distill deltas to canonical artifacts.",
        "mode": mode,
        "applied_changes": len(applied_claims),
        "applied_claims": applied_claims,
        "applied_certificates": applied_certs,
        "applied_capsules": applied_capsules,
        "applied_refs": applied_refs,
        "applied_decisions": applied_decisions,
        "applied_deltas": deltas,
        "warnings": [],
    }


def _run_replay_stage(
    repo_root: str,
    snapshot: dict[str, object],
    run_id: str,
    profile: str,
    mode: str,
    changed_only: bool = True,
    policy: dict[str, object] | None = None,
    *,
    timeout_seconds: int | None = None,
    max_retries: int = 0,
) -> dict[str, object]:
    def _preserve_certificate_refs(capsule_ids: list[str] | None = None) -> list[str]:
        try:
            successful_certificate_refs = _collect_successful_certificate_refs_by_capsule(repo_root)
        except Exception:
            successful_certificate_refs = {}
        preserved: list[str] = []
        seen: set[str] = set()
        if capsule_ids is None:
            for refs in successful_certificate_refs.values():
                for ref in refs:
                    if ref not in seen:
                        seen.add(ref)
                        preserved.append(ref)
            return sorted(preserved)
        for raw_capsule_id in capsule_ids:
            normalized_capsule = _safe_slug(str(raw_capsule_id))
            for ref in successful_certificate_refs.get(normalized_capsule, []):
                if ref not in seen:
                    seen.add(ref)
                    preserved.append(ref)
        return sorted(preserved)

    adapter_errors = _initialize_adapter_runtime(repo_root)
    if adapter_errors:
        first_error = adapter_errors[0]
        return {
            "name": "replay",
            "status": "error",
            "code": str(first_error.get("code") or ADAPTER_INTERFACE_MISMATCH_CODE),
            "message": str(first_error.get("message") or "adapter initialization failed"),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(first_error.get("message") or "adapter initialization failed")],
            **({"remediation": first_error.get("remediation", [])} if isinstance(first_error.get("remediation"), list) else {}),
        }

    try:
        worker_adapter = adapter_get("worker")
    except AdapterRegistryError as exc:
        return {
            "name": "replay",
            "status": "error",
            "code": ADAPTER_INTERFACE_MISMATCH_CODE,
            "message": str(exc),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(exc)],
        }

    policy_payload, policy_error = _resolve_policy_for_repo(repo_root, policy)
    if policy_error:
        return {
            "name": "replay",
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "message": policy_error.get("message", "policy configuration is invalid"),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [policy_error.get("message", "policy configuration is invalid")],
        }

    autonomous_block = _build_autonomous_write_block_payload(
        repo_root,
        mode,
        name="replay",
        command="replay",
    )
    if autonomous_block is not None:
        return {
            **autonomous_block,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
        }

    sandbox_check = _ensure_policy_action_allowed(
        policy_payload,
        command="replay",
        category="sandbox_operations",
        target="create_isolated_worktree",
        mode=mode,
    )
    if sandbox_check is None:
        sandbox_check = _ensure_policy_action_allowed(
            policy_payload,
            command="replay",
            category="sandbox_operations",
            target="read_artifacts",
            mode=mode,
        )
    if sandbox_check is not None:
        return {
            "name": "replay",
            "status": "error",
            "code": str(sandbox_check.get("error_code") or sandbox_check.get("code") or POLICY_DENIED_CODE),
            "message": str(sandbox_check.get("message", "policy denied sandbox operation")),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [_normalize_error_record(sandbox_check, fallback_code=POLICY_DENIED_CODE)],
            **sandbox_check,
        }

    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        error_message = f"Canonical artifact validation failed: {exc}"
        return {
            "name": "replay",
            "status": "error",
            "code": RUNTIME_ERROR_CODE,
            "message": error_message,
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [{"error_code": RUNTIME_ERROR_CODE, "message": error_message}],
        }

    if not isinstance(snapshot, dict):
        error_message = "Invalid snapshot payload"
        return {
            "name": "replay",
            "status": "error",
            "code": RUNTIME_ERROR_CODE,
            "message": error_message,
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [{"error_code": RUNTIME_ERROR_CODE, "message": error_message}],
        }
    changed_files = snapshot.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = []

    changed_files = [str(item) for item in changed_files]
    targets = _collect_affected_capsules(changed_files) if changed_only else _list_known_capsules(repo_root)
    if not targets:
        targets = ["default"]

    predicted_write_targets = _command_write_targets("replay")
    for capsule in targets:
        claim_id = f"cl-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"
        certificate_id = f"cert-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"
        predicted_write_targets.extend(
            [
                f"{OG_ROOT}/claims/{claim_id}.json",
                f"{OG_ROOT}/certificates/{certificate_id}.json",
            ]
        )
    write_check = _evaluate_policy_writes(
        policy_payload,
        command="replay",
        mode=mode,
        targets=predicted_write_targets,
    )
    if write_check is not None:
        return {
            "name": "replay",
            "status": "error",
            "code": str(write_check.get("error_code") or write_check.get("code") or POLICY_DENIED_CODE),
            "message": str(write_check.get("message", "policy denied write")),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [_normalize_error_record(write_check, fallback_code=POLICY_DENIED_CODE)],
            **write_check,
        }

    changed_materials = _collect_changed_materials(repo_root, changed_files if changed_only else [])
    plans: list[dict[str, object]] = []
    replay_results: list[dict[str, object]] = []
    certificate_ids: list[str] = []
    certificate_refs: list[str] = []
    failed_capsules: list[str] = []
    errors: list[object] = []
    overall_failed = False
    replay_error_code: str | None = None
    recovery_records: list[dict[str, object]] = []
    replay_prompt_provenance: dict[str, str] | None = None

    for capsule in targets:
        trace_path = _build_trace_path(capsule, run_id, "replay")
        capsule_payload = _load_capsule_payload(repo_root, capsule)
        scope_materials = _collect_capsule_scope_materials(repo_root, capsule, changed_materials)
        capsule_oracles = _load_capsule_oracles(repo_root, capsule)
        baseline_equivalence = _collect_replay_equivalence_baseline_payload(repo_root, capsule)
        try:
            input_payload = _build_replay_input(
                run_id=run_id,
                profile=profile,
                mode=mode,
                capsule_id=capsule,
                changed_materials=scope_materials,
                capsule_payload=capsule_payload,
                scope_materials=scope_materials,
                baseline_equivalence=baseline_equivalence,
            )
            output, receipts, worker_recovery = _run_worker_with_retries(
                "replay",
                input_payload,
                repo_root,
                trace_path,
                worker_adapter,
                timeout_seconds=int(timeout_seconds) if isinstance(timeout_seconds, int) and timeout_seconds > 0 else WORKER_ADAPTER_DEFAULT_TIMEOUT_SECONDS,
                max_retries=max_retries,
            )
            recovery_records.append(worker_recovery)
            plan = _normalize_replay_plan(output)
            plan_prompt_provenance = _normalize_prompt_provenance(output.get("prompt_provenance"))
            if plan_prompt_provenance is not None:
                plan["prompt_provenance"] = plan_prompt_provenance
                if replay_prompt_provenance is None:
                    replay_prompt_provenance = plan_prompt_provenance
            plan["adapter_receipts"] = receipts
            plans.append(plan)
        except WorkerAdapterError as exc:
            error_message = str(exc)
            recovery = cast(dict[str, object] | None, getattr(exc, "recovery", None))
            if _is_worker_unavailable_error(error_message):
                _set_pending_state(repo_root, f"worker runtime unavailable during replay: {error_message}")
                replay_error_code = WORKER_RUNTIME_UNAVAILABLE_CODE
                replay_status = "pending"
            else:
                replay_error_code = str((recovery or {}).get("error_code") or RUNTIME_ERROR_CODE)
                replay_status = "error"
            if recovery:
                recovery_records.append(recovery)
            errors.append({"error_code": replay_error_code, "message": error_message})
            overall_failed = True
            failed_capsules.append(capsule)
            replay_results.append(
                {
                    "capsule_id": capsule,
                    "status": replay_status,
                    "plan_status": "error",
                    "certificate_id": None,
                    "trace": trace_path,
                    "failures": [error_message],
                    "parity_results": None,
                    "recovery": recovery,
                }
            )
            continue

        step_status = str(plan.get("status") or "ok")
        lower_status = step_status.lower()
        plan_contract_failures = _validate_replay_plan_contract(
            run_id,
            capsule,
            plan,
            capsule_payload,
            scope_materials,
            capsule_oracles,
            baseline_equivalence,
        )
        acceptance_checks = _safe_object_list(plan.get("acceptance_checks"))
        acceptance_oracle_names: list[str] = []
        acceptance_oracle_seen: set[str] = set()
        for raw_check in acceptance_checks:
            oracle_name = str(raw_check.get("oracle_name") or "").strip()
            if oracle_name and oracle_name not in acceptance_oracle_seen:
                acceptance_oracle_seen.add(oracle_name)
                acceptance_oracle_names.append(oracle_name)
        replay_status = "success"
        replay_failures = _safe_string_list(plan.get("failures"))
        replay_steps: list[dict[str, object]] = []
        replay_receipts: list[dict[str, object]] = _safe_object_list(plan.get("adapter_receipts"))
        materialized_paths = _collect_replay_sandbox_paths(repo_root, capsule, scope_materials)
        sandbox_root = f"{OG_ROOT}/work/replay/{_safe_slug(run_id)}/{_safe_slug(capsule)}"
        replay_result: dict[str, object] = {
            "capsule_id": capsule,
            "status": replay_status,
            "plan_status": step_status,
            "certificate_id": None,
            "trace": trace_path,
            "failures": replay_failures,
            "capsule_scope": _safe_string_list(plan.get("capsule_scope")),
            "material_inputs": _safe_object_list(plan.get("material_inputs")),
            "acceptance_checks": acceptance_checks,
            "equivalence_inputs": dict(plan.get("equivalence_inputs")) if isinstance(plan.get("equivalence_inputs"), dict) else {},
            "parity_results": plan.get("parity_results"),
            "replay_steps": replay_steps,
            "equivalence": None,
            "materialized_paths": materialized_paths,
            "oracle_results": [],
            **({"prompt_provenance": plan_prompt_provenance} if plan_prompt_provenance is not None else {}),
        }

        if lower_status in {"error", "failed", "fail", "warn", "pending"}:
            replay_status = "failed"
            overall_failed = True
            replay_failures.append(f"Replay plan rejected with status '{step_status}'.")
        if plan_contract_failures:
            replay_status = "failed"
            overall_failed = True
            replay_failures.extend(plan_contract_failures)

        certificate_id = f"cert-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"
        claim_id = f"cl-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"

        if replay_status == "success":
            missing_paths = _materialize_replay_sandbox(repo_root, sandbox_root, capsule, scope_materials)
            if missing_paths:
                replay_status = "failed"
                overall_failed = True
                replay_failures.append(
                    "Replay sandbox materialization missing required paths: " + ", ".join(missing_paths)
                )
            else:
                planned_material_paths = {
                    str(item.get("path") or "").strip()
                    for item in _safe_object_list(plan.get("material_inputs"))
                    if str(item.get("path") or "").strip()
                }
                missing_planned_paths = sorted(path for path in planned_material_paths if path not in materialized_paths)
                if missing_planned_paths:
                    replay_status = "failed"
                    overall_failed = True
                    replay_failures.append(
                        "Replay sandbox did not materialize planned inputs: " + ", ".join(missing_planned_paths)
                    )

                sandbox_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
                if replay_status == "success" and not sandbox_steps:
                    replay_status = "failed"
                    overall_failed = True
                    replay_failures.append("Replay plan omitted executable steps.")
                if replay_status == "success":
                    for step_index, raw_step in enumerate(sandbox_steps):
                        if not isinstance(raw_step, dict):
                            replay_status = "failed"
                            overall_failed = True
                            replay_failures.append(f"Replay step {step_index} was not a valid object.")
                            break
                        step_result = _run_replay_step(
                            repo_root=repo_root,
                            sandbox_root=sandbox_root,
                            run_id=run_id,
                            capsule_id=capsule,
                            step_index=step_index,
                            step=raw_step,
                            timeout_seconds=timeout_seconds if isinstance(timeout_seconds, int) and timeout_seconds > 0 else None,
                            max_retries=max_retries,
                        )
                        replay_steps.append(step_result)
                        replay_result["replay_steps"] = replay_steps
                        recovery = step_result.get("recovery")
                        if isinstance(recovery, dict):
                            recovery_records.append(recovery)
                        replay_receipts.extend(_safe_object_list(step_result.get("receipt_pointers")))
                        if str(step_result.get("status") or "") != "pass":
                            replay_status = "failed"
                            overall_failed = True
                            replay_failures.extend(_safe_string_list(step_result.get("failures")))
                            if str(step_result.get("code") or "") in {TIMEOUT_EXPIRED_CODE, RECOVERY_RETRY_EXHAUSTED_CODE}:
                                replay_error_code = str(step_result.get("code"))
                            break

                oracle_checks: list[dict[str, object]] = []
                if replay_status == "success":
                    selected_oracles = [
                        oracle
                        for oracle in capsule_oracles
                        if str(oracle.get("name") or "").strip() in acceptance_oracle_names
                    ]
                    if not selected_oracles:
                        replay_status = "failed"
                        overall_failed = True
                        replay_failures.append("Replay plan did not bind any executable acceptance oracles.")
                    else:
                        sandbox_exec_root = os.path.join(repo_root, sandbox_root)
                        for oracle in selected_oracles:
                            check = _run_oracle_check(
                                repo_root,
                                capsule,
                                oracle,
                                materialized_paths,
                                run_id,
                                mode,
                                policy=policy_payload,
                                exec_root=sandbox_exec_root,
                                trace_label="replay",
                                timeout_seconds=timeout_seconds,
                                max_retries=max_retries,
                            )
                            oracle_checks.append(check)
                            recovery = check.get("recovery")
                            if isinstance(recovery, dict):
                                recovery_records.append(recovery)
                            replay_receipts.extend(_safe_object_list(check.get("receipt_pointers")))
                            if str(check.get("status") or "") not in {"pass", "skipped"}:
                                replay_status = "failed"
                                overall_failed = True
                                replay_failures.append(
                                    f"Replay oracle {check.get('oracle_name', 'unknown-oracle')} finished with status {check.get('status', 'unknown')}."
                                )
                                if str(check.get("code") or "") in {TIMEOUT_EXPIRED_CODE, RECOVERY_RETRY_EXHAUSTED_CODE}:
                                    replay_error_code = str(check.get("code"))
                    replay_result["oracle_results"] = oracle_checks

                if replay_status == "success":
                    baseline_hash = _collect_replay_equivalence_baseline(repo_root, capsule)
                    observed_hash = _compute_oracle_observed_hash(oracle_checks)
                    plan_hash = _compute_replay_observed_hash(replay_steps)
                    equivalence = {
                        "baseline_hash": baseline_hash,
                        "observed_hash": observed_hash,
                        "oracle_digest": observed_hash,
                        "plan_digest": plan_hash,
                        "match": baseline_hash is None or baseline_hash == observed_hash,
                        "materialized_path_count": len(materialized_paths),
                        "trace_count": len(replay_steps),
                        "oracle_count": len(oracle_checks),
                    }
                    replay_result["equivalence"] = equivalence
                    if baseline_hash is not None and not equivalence["match"]:
                        replay_status = "failed"
                        overall_failed = True
                        replay_failures.append("Replay output did not match baseline equivalence hash.")

        replay_result["status"] = replay_status
        replay_result["failures"] = replay_failures

        try:
            claim_payload = _build_claim_payload(
                claim_id,
                capsule,
                run_id,
                "replay",
                mode,
                materialized_paths,
                _normalize_receipt_pointers(replay_receipts, field=f"replay_plans[{len(replay_results)}].receipts"),
                text=f"Replay stage for {capsule} completed with plan status '{step_status}'.",
            )
            claim_path = os.path.join(repo_root, OG_ROOT, "claims", f"{claim_id}.json")
            os.makedirs(os.path.dirname(claim_path), exist_ok=True)
            _write_canonical_artifact(
                repo_root,
                f"{OG_ROOT}/claims/{claim_id}.json",
                claim_payload,
            )
        except Exception as exc:
            errors.append({"error_code": RUNTIME_ERROR_CODE, "message": f"Failed to write replay claim for {capsule}: {exc}"})
            overall_failed = True
            failed_capsules.append(capsule)
            replay_result["status"] = "error"
            replay_failures.append(f"claim persistence failed: {exc}")
            replay_result["failures"] = replay_failures
            replay_results.append(replay_result)
            continue

        if replay_status != "success":
            replay_results.append(replay_result)
            continue

        try:
            cert_payload = _build_certificate_payload(
                certificate_id,
                capsule,
                run_id,
                [f"{OG_ROOT}/claims/{claim_id}.json"],
                "replay",
                mode,
                replay_receipts,
                status="success",
                source="replay",
                adapter_name=str(worker_adapter.get("name", WORKER_ADAPTER_NAME)),
                prompt_provenance=plan_prompt_provenance,
            )
            cert_payload["replay_context"] = {
                "run_id": run_id,
                "adapter_profile": profile,
                "source_ref": "HEAD",
                "sandbox_root": sandbox_root,
                "capsule_scope": replay_result.get("capsule_scope"),
                "material_inputs": replay_result.get("material_inputs"),
                "acceptance_checks": replay_result.get("acceptance_checks"),
                "equivalence_inputs": replay_result.get("equivalence_inputs"),
                "changed_materials": scope_materials,
                "materialized_paths": materialized_paths,
                "oracle_results": replay_result.get("oracle_results"),
                "equivalence": replay_result.get("equivalence"),
            }
            certificate_path = os.path.join(repo_root, OG_ROOT, "certificates", f"{certificate_id}.json")
            os.makedirs(os.path.dirname(certificate_path), exist_ok=True)
            _write_canonical_artifact(
                repo_root,
                f"{OG_ROOT}/certificates/{certificate_id}.json",
                cert_payload,
            )
            certificate_ids.append(certificate_id)
            certificate_refs.append(f"{OG_ROOT}/certificates/{certificate_id}.json")
            replay_result["certificate_id"] = certificate_id
        except Exception as exc:
            errors.append({"error_code": RUNTIME_ERROR_CODE, "message": f"Failed to write replay certificate for {capsule}: {exc}"})
            overall_failed = True
            failed_capsules.append(capsule)
            replay_result["status"] = "error"
            replay_failures.append(f"certificate persistence failed: {exc}")
            replay_result["failures"] = replay_failures
        replay_results.append(replay_result)

        if replay_status != "success" and capsule not in failed_capsules:
            failed_capsules.append(capsule)

    final_certificate_refs = set(certificate_refs)
    if overall_failed:
        for ref in _preserve_certificate_refs(failed_capsules):
            final_certificate_refs.add(ref)

    if not errors and overall_failed:
        for replay_result in replay_results:
            if not isinstance(replay_result, dict):
                continue
            failures = _safe_string_list(replay_result.get("failures"))
            if not failures:
                continue
            errors.append(
                {
                    "error_code": replay_error_code or RUNTIME_ERROR_CODE,
                    "message": failures[0],
                }
            )
            break

    return {
        "name": "replay",
        "status": "error" if overall_failed else "ok",
        "code": replay_error_code or (RUNTIME_ERROR_CODE if overall_failed else None),
        "message": "Replay adapter completed with failures." if overall_failed else "Replay adapter produced executable plans.",
        "mode": mode,
        "replay_plans": plans,
        "replay_results": replay_results,
        "certificate_ids": certificate_ids,
        "certificate_refs": sorted(final_certificate_refs),
        "failed_capsules": sorted(set(failed_capsules)),
        "errors": errors,
        "recovery": _summarize_recovery_records(recovery_records),
        **({"prompt_provenance": replay_prompt_provenance} if replay_prompt_provenance is not None else {}),
    }


def _run_verify_job(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    changed_only = bool(options.get("changed"))
    snapshot = _collect_sync_snapshot(repo_root, profile, mode)
    changed_files = snapshot.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = []
    changed_files = [str(item) for item in changed_files]
    if changed_only:
        changed_capsules = _collect_affected_capsules(changed_files)
    else:
        changed_capsules = _list_known_capsules(repo_root)
    if not changed_capsules and not changed_only:
        changed_only = True
        changed_capsules = ["default"]

    run_id = _build_run_id("verify", _short_hash(f"{profile}:{mode}:{'changed' if changed_only else 'all'}", 10))
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error is None:
        follow_up_write_check = _evaluate_policy_writes(
            policy_payload,
            command="verify",
            mode=mode,
            targets=[*_event_write_targets(run_id), *sorted(EXPORT_PATHS.values())],
        )
        if follow_up_write_check is not None:
            return {
                "status": "error",
                "command": "verify",
                "options": options,
                "run_id": run_id,
                "snapshot": snapshot,
                "steps": [],
                "message": str(follow_up_write_check.get("message", "policy denied write")),
                "changed_only": changed_only,
                "changed_files": changed_files if changed_only else [],
                "verified_capsules": [],
                "oracle_count": 0,
                "certificate_refs": [],
                "receipt_pointers": {},
                "oracle_results": {},
                "failed_capsules": [],
                "errors": [_normalize_error_record(follow_up_write_check, fallback_code=POLICY_DENIED_CODE)],
                **follow_up_write_check,
            }

    start_at = time.perf_counter()
    verify = _run_verify_stage(
        repo_root=repo_root,
        changed_capsules=changed_capsules,
        changed_paths=changed_files if changed_only else [],
        run_id=run_id,
        mode=mode,
        policy=policy_payload if policy_error is None else None,
        timeout_seconds=cast(int | None, options.get("timeout")),
        max_retries=int(options.get("max_retries") or 0),
    )
    verify_status = str(verify.get("status") or "error").lower()

    failed_capsules: list[str] = []
    for capsule, checks in verify.get("oracle_results", {}).items():
        for raw_result in checks:
            status = str(raw_result.get("status", "skipped")).lower()
            if status in {"fail", "error"}:
                failed_capsules.append(capsule)
                break

    payload_status = "error"
    if verify_status in {"ok", "skipped"}:
        payload_status = "ok"
    elif verify_status == "warn":
        payload_status = "warn"

    payload = {
        "status": payload_status,
        "command": "verify",
        "code": verify.get("code"),
        "options": options,
        "run_id": run_id,
        "snapshot": snapshot,
        "steps": [verify],
        "message": verify.get("message", "verify adapter completed"),
        "changed_only": changed_only,
        "changed_files": changed_files if changed_only else [],
        "verified_capsules": verify.get("verified_capsules", []),
        "oracle_count": verify.get("oracle_count", 0),
        "certificate_refs": verify.get("certificate_refs", []),
        "receipt_pointers": verify.get("receipt_pointers", {}),
        "oracle_results": verify.get("oracle_results", {}),
        "failed_capsules": sorted(set(failed_capsules)),
        "errors": verify.get("errors", []),
        "warnings": verify.get("warnings", []),
        "recovery": verify.get("recovery", {}),
    }

    if policy_error is None and verify_status == "ok":
        _append_export_refresh_step(payload, repo_root, mode, policy_payload)
    payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
    payload["summary_event"] = _record_verify_summary_event(repo_root, payload, payload["duration_ms"], snapshot)
    return payload


def _run_replay_job(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    changed_only = bool(options.get("changed"))
    snapshot = _collect_sync_snapshot(repo_root, profile, mode)
    run_id = _build_run_id("replay", _short_hash(f"{profile}:{mode}:{snapshot.get('changed_count', 0)}", 8))
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error is None:
        follow_up_write_check = _evaluate_policy_writes(
            policy_payload,
            command="replay",
            mode=mode,
            targets=[*_event_write_targets(run_id), *sorted(EXPORT_PATHS.values())],
        )
        if follow_up_write_check is not None:
            return {
                "status": "error",
                "command": "replay",
                "options": options,
                "run_id": run_id,
                "steps": [],
                "message": str(follow_up_write_check.get("message", "policy denied write")),
                "replay_plans": [],
                "replay_results": [],
                "certificate_ids": [],
                "certificate_refs": [],
                "errors": [_normalize_error_record(follow_up_write_check, fallback_code=POLICY_DENIED_CODE)],
                **follow_up_write_check,
            }

    start_at = time.perf_counter()
    replay = _run_replay_stage(
        repo_root=repo_root,
        snapshot=snapshot,
        run_id=run_id,
        profile=profile,
        mode=mode,
        changed_only=changed_only,
        policy=policy_payload if policy_error is None else None,
        timeout_seconds=cast(int | None, options.get("timeout")),
        max_retries=int(options.get("max_retries") or 0),
    )
    payload = {
        "status": "ok" if replay.get("status") == "ok" else "error",
        "command": "replay",
        "code": replay.get("code"),
        "options": options,
        "run_id": run_id,
        "steps": [replay],
        "message": replay.get("message", "replay adapter completed"),
        "replay_plans": replay.get("replay_plans", []),
        "replay_results": replay.get("replay_results", []),
        "certificate_ids": replay.get("certificate_ids", []),
        "certificate_refs": replay.get("certificate_refs", []),
        "errors": replay.get("errors", []),
        "recovery": replay.get("recovery", {}),
    }
    if policy_error is None and str(replay.get("status") or "").lower() == "ok":
        _append_export_refresh_step(payload, repo_root, mode, policy_payload)
    payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
    payload["summary_event"] = _record_replay_summary_event(repo_root, payload, payload["duration_ms"], snapshot)
    return payload


def _run_explain_stage(
    repo_root: str,
    profile: str,
    mode: str,
    run_id: str,
    *,
    capsule_filters: list[str] | None = None,
    ref_filters: list[str] | None = None,
    certificate_filters: list[str] | None = None,
) -> dict[str, object]:
    def normalize_identifier(value: object) -> str:
        if not isinstance(value, str):
            return ""
        try:
            return _normalize_agent_identifier(value, "filter")
        except ValueError:
            return ""

    def format_certificate(cert: dict[str, object]) -> dict[str, object]:
        return {
            "id": cert.get("id"),
            "path": cert.get("path"),
            "capsule_id": cert.get("capsule_id"),
            "status": cert.get("status"),
            "run_id": cert.get("run_id"),
            "claim_refs": cert.get("claim_refs"),
            "receipt_pointers": cert.get("receipt_pointers"),
        }

    def format_decision(decision: dict[str, object]) -> dict[str, object]:
        return {
            "id": str(decision.get("id")),
            "path": decision.get("path"),
            "capsule_id": decision.get("capsule_id"),
            "statement": decision.get("statement"),
            "status": decision.get("status"),
            "claim_refs": decision.get("claim_refs"),
            "evidence_refs": decision.get("evidence_refs"),
        }

    claims = _collect_claim_records(repo_root)
    certificates = _collect_certificate_records(repo_root)
    decisions = _collect_decision_records(repo_root)
    refs = _collect_ref_records(repo_root)
    deltas, deltas_by_capsule = _collect_latest_sync_deltas(repo_root)

    capsule_filters = [item.strip() for item in capsule_filters or [] if item.strip()]
    ref_filters = [item.strip() for item in ref_filters or [] if item.strip()]
    certificate_filters = [item.strip() for item in certificate_filters or [] if item.strip()]

    requested_capsules = {normalize_identifier(item) for item in capsule_filters}
    requested_capsules = {item for item in requested_capsules if item}
    requested_refs = {normalize_identifier(item) for item in ref_filters}
    requested_refs = {item for item in requested_refs if item}
    requested_certificates = {normalize_identifier(item) for item in certificate_filters}
    requested_certificates = {item for item in requested_certificates if item}

    all_capsules: set[str] = set()
    for claim in claims:
        all_capsules.add(normalize_identifier(claim.get("capsule_id") or "default"))
    for certificate in certificates:
        all_capsules.add(normalize_identifier(certificate.get("capsule_id") or "default"))
    for decision in decisions:
        all_capsules.add(normalize_identifier(decision.get("capsule_id") or "default"))
    for capsule_id in deltas_by_capsule:
        all_capsules.add(normalize_identifier(capsule_id))

    if not all_capsules:
        all_capsules.add("default")

    selected_ref_capsules: set[str] = set()
    if requested_refs:
        for raw_ref in refs:
            if normalize_identifier(raw_ref.get("id")) in requested_refs:
                selected_ref_capsules.add(normalize_identifier(raw_ref.get("capsule_id") or "default"))
        if not selected_ref_capsules:
            return {
                "name": "explain",
                "status": "error",
                "message": "No refs found for --ref filter.",
                "mode": mode,
                "profile": profile,
                "run_id": run_id,
                "claims": [],
                "certificates": [],
                "decisions": [],
                "deltas": [],
                "errors": [f"--ref filter values were not found: {', '.join(sorted(requested_refs))}"],
                "target_capsules": [],
                "filters": {
                    "capsule": capsule_filters,
                    "ref": ref_filters,
                    "certificate": certificate_filters,
                },
            }

    if requested_certificates:
        selected_certificates = [
            cert for cert in certificates
            if normalize_identifier(cert.get("id")) in requested_certificates
        ]
        if not selected_certificates:
            return {
                "name": "explain",
                "status": "error",
                "message": "No certificates found for --certificate filter.",
                "mode": mode,
                "profile": profile,
                "run_id": run_id,
                "claims": [],
                "certificates": [],
                "decisions": [],
                "deltas": [],
                "errors": [
                    f"--certificate filter values were not found: {', '.join(sorted(requested_certificates))}"
                ],
                "target_capsules": [],
                "filters": {
                    "capsule": capsule_filters,
                    "ref": ref_filters,
                    "certificate": certificate_filters,
                },
            }
    else:
        selected_certificates = certificates

    selected_certificate_capsules = {
        normalize_identifier(cert.get("capsule_id") or "default") for cert in selected_certificates
    }

    constraints: list[set[str]] = []
    if requested_capsules:
        constraints.append(requested_capsules)
    if requested_refs:
        constraints.append(selected_ref_capsules)
    if requested_certificates:
        constraints.append(selected_certificate_capsules)

    if constraints:
        target_capsules = set.intersection(*constraints)
    else:
        target_capsules = set(all_capsules)

    if not target_capsules:
        return {
            "name": "explain",
            "status": "error",
            "message": "No explain records matched the requested filters.",
            "mode": mode,
            "profile": profile,
            "run_id": run_id,
            "claims": [],
            "certificates": [],
            "decisions": [],
            "deltas": [],
            "errors": [
                "Filters were provided but no matching capsules were found in explain artifacts.",
            ],
            "target_capsules": [],
            "filters": {
                "capsule": capsule_filters,
                "ref": ref_filters,
                "certificate": certificate_filters,
            },
        }

    deltas_by_capsule_normalized: dict[str, list[dict[str, object]]] = {}
    for raw_capsule_id, raw_steps in deltas_by_capsule.items():
        normalized_capsule = normalize_identifier(raw_capsule_id)
        if not normalized_capsule:
            normalized_capsule = "default"
        deltas_by_capsule_normalized.setdefault(normalized_capsule, []).extend(raw_steps)

    decisions_by_claim: dict[str, list[dict[str, object]]] = {}
    for decision in decisions:
        decision_capsule = normalize_identifier(decision.get("capsule_id") or "default")
        if decision_capsule not in target_capsules:
            continue
        for claim_ref in _safe_string_list(decision.get("claim_refs")):
            claim_id = normalize_identifier(claim_ref)
            if claim_id:
                decisions_by_claim.setdefault(claim_id, []).append(decision)

    certificates_by_claim: dict[str, list[dict[str, object]]] = {}
    for certificate in selected_certificates:
        certificate_capsule = normalize_identifier(certificate.get("capsule_id") or "default")
        if certificate_capsule not in target_capsules:
            continue
        for claim_ref in _safe_string_list(certificate.get("claim_refs")):
            claim_id = normalize_identifier(claim_ref)
            if claim_id:
                certificates_by_claim.setdefault(claim_id, []).append(certificate)

    selected_claims: list[dict[str, object]] = []
    for claim in claims:
        claim_capsule = normalize_identifier(claim.get("capsule_id") or "default")
        if claim_capsule not in target_capsules:
            continue
        claim_id = normalize_identifier(claim.get("id"))
        if not claim_id:
            continue
        linked_decisions = [format_decision(item) for item in decisions_by_claim.get(claim_id, [])]
        linked_certificates = [format_certificate(item) for item in certificates_by_claim.get(claim_id, [])]
        if requested_certificates and not linked_certificates:
            continue
        selected_claims.append(
            {
                "id": claim.get("id"),
                "path": claim.get("path"),
                "capsule_id": claim.get("capsule_id") or "default",
                "text": claim.get("text") or "",
                "category": claim.get("category") or "behavior",
                "receipt_pointers": claim.get("receipt_pointers") or [],
                "linked_decisions": linked_decisions,
                "linked_certificates": linked_certificates,
                "deltas": deltas_by_capsule_normalized.get(claim_capsule, []),
                "run_id": claim.get("run_id") or "",
            }
        )

    selected_claims.sort(key=lambda item: (str(item.get("capsule_id") or ""), str(item.get("id") or "")))

    selected_certificates_payload = [
        format_certificate(certificate)
        for certificate in selected_certificates
        if normalize_identifier(certificate.get("capsule_id") or "default") in target_capsules
    ]
    filtered_deltas = [
        delta for delta in deltas
        if normalize_identifier(delta.get("capsule_id") or "default") in target_capsules
    ]

    selected_decisions: list[dict[str, object]] = []
    seen_decision_ids: set[str] = set()
    for decision in decisions:
        decision_capsule = normalize_identifier(decision.get("capsule_id") or "default")
        if decision_capsule not in target_capsules:
            continue
        decision_id = normalize_identifier(decision.get("id"))
        if decision_id and decision_id not in seen_decision_ids:
            seen_decision_ids.add(decision_id)
            selected_decisions.append(format_decision(decision))

    if not selected_claims and not selected_certificates_payload and not selected_decisions and not filtered_deltas:
        if requested_capsules or requested_refs or requested_certificates:
            message = "No explain data found for requested filters."
            return {
                "name": "explain",
                "status": "error",
                "code": RUNTIME_ERROR_CODE,
                "message": message,
                "mode": mode,
                "profile": profile,
                "run_id": run_id,
                "claims": [],
                "certificates": [],
                "decisions": [],
                "deltas": [],
                "errors": [{"error_code": RUNTIME_ERROR_CODE, "message": message}],
                "target_capsules": sorted(target_capsules),
                "filters": {
                    "capsule": capsule_filters,
                    "ref": ref_filters,
                    "certificate": certificate_filters,
                },
            }
        return {
            "name": "explain",
            "status": "ok",
            "message": "No explain artifacts found.",
            "mode": mode,
            "profile": profile,
            "run_id": run_id,
            "claims": [],
            "certificates": [],
            "decisions": [],
            "deltas": filtered_deltas,
            "errors": [],
            "target_capsules": sorted(target_capsules),
            "filters": {
                "capsule": capsule_filters,
                "ref": ref_filters,
                "certificate": certificate_filters,
            },
        }

    return {
        "name": "explain",
        "status": "ok",
        "message": "Explain trace assembled from claims, decisions, certificates, and delta evidence.",
        "mode": mode,
        "profile": profile,
        "run_id": run_id,
        "claims": selected_claims,
        "certificates": selected_certificates_payload,
        "decisions": selected_decisions,
        "deltas": filtered_deltas,
        "target_capsules": sorted(target_capsules),
        "filters": {
            "capsule": capsule_filters,
            "ref": ref_filters,
            "certificate": certificate_filters,
        },
        "errors": [],
    }


def _build_prompt_pack_payload(
    dataset_id: str,
    dataset_path: str,
    baseline_prompt: str,
    candidate_prompt: str,
    approved_at: str,
    result_ref: str,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "artifact_type": "prompt_pack",
        "id": f"{_safe_slug(dataset_id)}-active-pack",
        "status": "active",
        "dataset_id": dataset_id,
        "dataset_ref": dataset_path,
        "baseline_prompt": baseline_prompt,
        "candidate_prompt": candidate_prompt,
        "active_from": approved_at,
        "run_id": os.path.splitext(os.path.basename(result_ref))[0],
        "result_ref": result_ref,
        "message": "Prompt pack is active for experimental offline evaluations.",
    }


def _record_optimize_prompts_event(repo_root: str, payload: dict[str, object], total_ms: int) -> str:
    event_payload = {
        "schema_version": 2,
        "artifact_type": "optimize_prompt_eval",
        "id": payload["run_id"],
        "status": payload["status"],
        "command": "optimize",
        "subcommand": "prompts",
        "duration_ms": total_ms,
        "created_at": _utc_timestamp(),
        "dataset": payload.get("dataset_id"),
        "options": payload.get("options"),
        "summary": payload.get("summary"),
        "result_path": payload.get("result_path"),
        "promotion": payload.get("promotion"),
        "errors": payload.get("errors", []),
        "steps": [payload.get("result")],
    }
    path, _ = _append_ledger_event(repo_root, event_payload)
    return path


def _run_optimize_prompts_stage(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    start_at = time.perf_counter()
    try:
        dataset_path = _normalize_dataset_path(options.get("dataset"), "dataset")
        candidate_path = _normalize_dataset_path(options.get("candidate"), "candidate")
        baseline_path = _normalize_dataset_path(options.get("baseline"), "baseline")
        metric = str(options.get("metric") or "contains").strip().lower()
        min_improvement = float(options.get("min_improvement") or OPTIMIZATION_DEFAULT_MIN_IMPROVEMENT)
        approve = bool(options.get("approve"))

        dataset = _read_eval_dataset(repo_root, dataset_path)
        baseline_prompt = _load_text_artifact(repo_root, baseline_path, "baseline prompt")
        candidate_prompt = _load_text_artifact(repo_root, candidate_path, "candidate prompt")
        dataset_with_refs: dict[str, object] = dict(dataset)
        dataset_with_refs["dataset_path"] = dataset_path
        dataset_with_refs["candidate_path"] = candidate_path
        dataset_with_refs["baseline_path"] = baseline_path
        eval_options = {
            "metric": metric,
            "min_improvement": min_improvement,
            "dataset_path": dataset_path,
            "candidate_path": candidate_path,
            "baseline_path": baseline_path,
        }

        evaluation = _evaluate_prompts(
            repo_root,
            dataset_with_refs,
            baseline_prompt,
            candidate_prompt,
            eval_options,
        )
        result_path = f"{OG_ROOT}/datasets/{evaluation['id']}.json"
        absolute_result_path = os.path.join(repo_root, result_path)
        os.makedirs(os.path.dirname(absolute_result_path), exist_ok=True)
        _write_canonical_artifact(repo_root, result_path, evaluation)

        summary = {
            "dataset_id": dataset["id"],
            "dataset_path": dataset_path,
            "baseline_path": baseline_path,
            "candidate_path": candidate_path,
            "metric": metric,
            "cases": evaluation["case_count"],
            "baseline_score": evaluation["baseline_score"],
            "candidate_score": evaluation["candidate_score"],
            "score_delta": evaluation["score_delta"],
            "passes_threshold": evaluation["status"] == "pass",
            "require_approval": evaluation["status"] == "pass" and not approve,
        }
        promotion_errors: list[str] = []
        if evaluation["status"] != "pass":
            promotion_state = "blocked_by_threshold"
            promotion_error = (
                f"candidate score {evaluation['candidate_score']} did not beat baseline {evaluation['baseline_score']} "
                f"by minimum improvement {min_improvement}"
            )
            promotion_errors.append(promotion_error)
        elif not approve:
            promotion_state = "requires_manual_approval"
            promotion_error = "promotion gate requires --approve"
            promotion_errors.append(promotion_error)
        else:
            promotion_state = "promoted"
            promotion_error = None
        payload = {
            "status": "ok",
            "command": "optimize",
            "subcommand": "prompts",
            "run_id": evaluation["id"],
            "options": {
                "dataset": dataset_path,
                "candidate": candidate_path,
                "baseline": baseline_path,
                "metric": metric,
                "min_improvement": min_improvement,
                "approve": approve,
            },
            "dataset_id": dataset["id"],
            "result_path": result_path,
            "result": evaluation,
            "summary": summary,
            "errors": promotion_errors,
            "promotion": {
                "state": promotion_state,
                "message": promotion_error,
                "approved": approve,
            },
        }
        payload["message"] = (
            "Candidate is ready for manual approval."
            if promotion_state == "requires_manual_approval"
            else "Candidate promotion completed." if promotion_state == "promoted" else "Optimization result did not meet threshold."
        )

        if evaluation["status"] == "pass" and approve:
            pack_path = f"{OG_ROOT}/datasets/{_safe_slug(dataset['id'])}-prompt-pack.json"
            pack_payload = _build_prompt_pack_payload(
                dataset_id=str(dataset["id"]),
                dataset_path=dataset_path,
                baseline_prompt=baseline_path,
                candidate_prompt=candidate_path,
                approved_at=_utc_timestamp(),
                result_ref=result_path,
            )
            _write_canonical_artifact(repo_root, pack_path, pack_payload)
            payload["promotion"]["pack_path"] = pack_path
            payload["message"] = "Candidate prompts approved and promoted to active pack."
            summary["pack_path"] = pack_path

        payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
        payload["summary_event"] = _record_optimize_prompts_event(repo_root, payload, payload["duration_ms"])
        return payload
    except ValueError as exc:
        duration_ms = int((time.perf_counter() - start_at) * 1000)
        return {
            "status": "error",
            "command": "optimize",
            "subcommand": "prompts",
            "options": options,
            "message": str(exc),
            "duration_ms": duration_ms,
        }


def _render_optimize_prompts(payload: dict[str, object]) -> str:
    summary = payload.get("summary") or {}
    promotion = payload.get("promotion") or {}
    lines = [
        f"Optimize prompts result: {payload.get('status', 'unknown')}",
        f"run_id: {payload.get('run_id', 'unknown')}",
        f"dataset: {summary.get('dataset_id', 'unknown')} ({summary.get('dataset_path', 'unknown')})",
        f"baseline: {summary.get('baseline_path', 'unknown')}",
        f"candidate: {summary.get('candidate_path', 'unknown')}",
        f"metric: {summary.get('metric', 'unknown')}",
        f"baseline score: {summary.get('baseline_score', 0)}",
        f"candidate score: {summary.get('candidate_score', 0)}",
        f"score delta: {summary.get('score_delta', 0)}",
        f"cases: {summary.get('cases', 0)}",
        f"promotion: {promotion.get('state', 'unknown')}",
    ]
    if promotion.get("message"):
        lines.append(f"promotion note: {promotion.get('message')}")
    if payload.get("result_path"):
        lines.append(f"result file: {payload['result_path']}")
    return "\n".join(lines) + "\n"


def _run_verify_stage(
    repo_root: str,
    changed_capsules: list[str],
    changed_paths: list[str],
    run_id: str,
    mode: str,
    policy: dict[str, object] | None = None,
    *,
    timeout_seconds: int | None = None,
    max_retries: int = 0,
) -> dict[str, object]:
    def _preserve_certificate_refs(capsule_ids: list[str] | None = None) -> list[str]:
        try:
            successful_certificate_refs = _collect_successful_certificate_refs_by_capsule(repo_root)
        except Exception:
            successful_certificate_refs = {}
        preserved: list[str] = []
        seen: set[str] = set()
        if capsule_ids is None:
            for refs in successful_certificate_refs.values():
                for ref in refs:
                    if ref not in seen:
                        seen.add(ref)
                        preserved.append(ref)
            return sorted(preserved)

        for raw_capsule_id in capsule_ids:
            normalized_capsule = _safe_slug(str(raw_capsule_id))
            for ref in successful_certificate_refs.get(normalized_capsule, []):
                if ref not in seen:
                    seen.add(ref)
                    preserved.append(ref)
        return sorted(preserved)

    policy_payload, policy_error = _resolve_policy_for_repo(repo_root, policy)
    if policy_error:
        return {
            "name": "verify",
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "mode": mode,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [policy_error.get("message", "policy configuration is invalid")],
            "policy": policy_error,
        }

    autonomous_block = _build_autonomous_write_block_payload(
        repo_root,
        mode,
        name="verify",
        command="verify",
    )
    if autonomous_block is not None:
        return {
            **autonomous_block,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
        }

    sandbox_check = _ensure_policy_action_allowed(
        policy_payload,
        command="verify",
        category="sandbox_operations",
        target="read_artifacts",
        mode=mode,
    )
    if sandbox_check is not None:
        return {
            "name": "verify",
            "status": "error",
            "mode": mode,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(sandbox_check.get("message", "policy denied sandbox operation"))],
            **sandbox_check,
        }

    predicted_write_targets = _command_write_targets("verify")
    for capsule in changed_capsules:
        claim_id = f"cl-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:verify')}"
        certificate_id = f"cert-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:verify')}"
        predicted_write_targets.extend(
            [
                f"{OG_ROOT}/claims/{claim_id}.json",
                f"{OG_ROOT}/certificates/{certificate_id}.json",
            ]
        )
    write_check = _evaluate_policy_writes(
        policy_payload,
        command="verify",
        mode=mode,
        targets=predicted_write_targets,
    )
    if write_check is not None:
        return {
            "name": "verify",
            "status": "error",
            "mode": mode,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(write_check.get("message", "policy denied file write"))],
            **write_check,
        }

    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        return {
            "name": "verify",
            "status": "error",
            "message": f"Canonical artifact validation failed: {exc}",
            "mode": mode,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [f"Canonical artifact validation failed: {exc}"],
        }

    if not changed_capsules:
        return {
            "name": "verify",
            "status": "skipped",
            "message": "No affected capsules; verification deferred.",
            "mode": mode,
            "verified_capsules": [],
            "receipt_pointers": {},
            "oracle_results": {},
            "certificate_refs": _preserve_certificate_refs(),
        }

    changed_paths = changed_paths if isinstance(changed_paths, list) else []
    normalized_changed_paths = [str(path) for path in changed_paths]
    receipts: dict[str, list[dict[str, object]]] = {}
    oracle_results: dict[str, list[dict[str, object]]] = {}
    certificate_refs: list[str] = []
    overall_failed = False
    failed_capsules: list[str] = []
    errors: list[object] = []
    configuration_failed = False
    recovery_records: list[dict[str, object]] = []
    timed_out = False

    for capsule in changed_capsules:
        try:
            capsule_oracles = _load_capsule_oracles(repo_root, capsule)
        except ValueError as exc:
            error_message = f"Failed to load capsule oracle configuration for {capsule}: {exc}"
            errors.append(error_message)
            overall_failed = True
            configuration_failed = True
            failed_capsules.append(capsule)
            receipts[capsule] = []
            oracle_results[capsule] = [
                {
                    "schema_version": 2,
                    "oracle_name": f"{_safe_slug(capsule)}-verify",
                    "capsule_id": capsule,
                    "run_id": run_id,
                    "mode": mode,
                    "status": "error",
                    "checked_at": _utc_timestamp(),
                    "changed_paths": normalized_changed_paths,
                    "command": "",
                    "message": error_message,
                    "error": error_message,
                }
            ]
            continue
        impacted_oracles = [
            oracle
            for oracle in capsule_oracles
            if isinstance(oracle, dict) and _oracle_scopes_match(oracle, normalized_changed_paths)
        ]
        if not impacted_oracles:
            impacted_oracles = capsule_oracles[:1]

        checks = []
        for oracle in impacted_oracles:
            checks.append(
                _run_oracle_check(
                    repo_root,
                    capsule,
                    oracle,
                    normalized_changed_paths,
                    run_id,
                    mode,
                    policy_payload,
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                )
            )

        receipt_records: list[dict[str, object]] = []
        for check in checks:
            recovery = check.get("recovery")
            if isinstance(recovery, dict):
                recovery_records.append(recovery)
                timed_out = timed_out or bool(recovery.get("timed_out"))
            for pointer in check.get("receipt_pointers", []):
                if isinstance(pointer, dict):
                    receipt_records.append(pointer)

        receipts[capsule] = receipt_records
        oracle_results[capsule] = checks
        capsule_status = "success"
        for raw_result in checks:
            status = str(raw_result.get("status", "skipped"))
            if status in {"fail", "error"}:
                capsule_status = "failed"
                overall_failed = True
                failed_capsules.append(capsule)
                if str(raw_result.get("code") or "") in {TIMEOUT_EXPIRED_CODE, RECOVERY_RETRY_EXHAUSTED_CODE}:
                    timed_out = True
                break

        claim_id = f"cl-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:verify')}"
        receipt_pointers = receipt_records
        claim_text = (
            f"Verification checkpoints for {capsule} on {len(checks)} oracle checks."
            if capsule_status == "success"
            else f"Verification failed for {capsule}; previous valid certificates preserved."
        )
        claim_path = os.path.join(repo_root, OG_ROOT, "claims", f"{claim_id}.json")
        try:
            os.makedirs(os.path.dirname(claim_path), exist_ok=True)
            claim_payload = _build_claim_payload(
                claim_id,
                capsule,
                run_id,
                "verify",
                mode,
                normalized_changed_paths,
                receipt_pointers,
                text=claim_text,
            )
            _write_canonical_artifact(
                repo_root,
                f"{OG_ROOT}/claims/{claim_id}.json",
                claim_payload,
            )
        except Exception as exc:
            error_message = f"Failed to write verify claim for {capsule}: {exc}"
            errors.append({"error_code": RUNTIME_ERROR_CODE, "message": error_message})
            overall_failed = True
            failed_capsules.append(capsule)
            continue

        claim_ref = f"{OG_ROOT}/claims/{claim_id}.json"
        if capsule_status == "success":
            certificate_id = f"cert-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:verify')}"
            cert_payload = _build_certificate_payload(
                certificate_id,
                capsule,
                run_id,
                [claim_ref],
                "verify",
                mode,
                receipt_pointers,
                status="success",
                source="oracle-loop",
            )
            cert_path = os.path.join(repo_root, OG_ROOT, "certificates", f"{certificate_id}.json")
            try:
                os.makedirs(os.path.dirname(cert_path), exist_ok=True)
                _write_canonical_artifact(
                    repo_root,
                    f"{OG_ROOT}/certificates/{certificate_id}.json",
                    cert_payload,
                )
                certificate_refs.append(f"{OG_ROOT}/certificates/{certificate_id}.json")
            except Exception as exc:
                error_message = f"Failed to write verify certificate for {capsule}: {exc}"
                errors.append({"error_code": RUNTIME_ERROR_CODE, "message": error_message})
                overall_failed = True
                failed_capsules.append(capsule)

    final_certificate_refs = set(certificate_refs)
    if overall_failed:
        for ref in _preserve_certificate_refs(failed_capsules):
            final_certificate_refs.add(ref)

    policy_denied = False
    policy_denied_messages: list[str] = []
    for check_group in oracle_results.values():
        for raw_result in check_group:
            if str(raw_result.get("code") or "") == POLICY_DENIED_CODE:
                policy_denied = True
                message = str(raw_result.get("message") or "").strip()
                if message and message not in policy_denied_messages:
                    policy_denied_messages.append(message)
                break
        if policy_denied:
            break

    status = "ok"
    warnings: list[str] = []
    if overall_failed or configuration_failed:
        status = "error"
    elif policy_denied:
        status = "warn"
        warnings.extend(policy_denied_messages)

    if not errors:
        for check_group in oracle_results.values():
            for raw_result in check_group:
                if str(raw_result.get("status") or "") in {"error", "fail"}:
                    message = str(raw_result.get("message") or raw_result.get("error") or "oracle execution failed")
                    code = str(raw_result.get("code") or (TIMEOUT_EXPIRED_CODE if timed_out else RUNTIME_ERROR_CODE))
                    errors.append({"error_code": code, "message": message})
                    break
            if errors:
                break

    return {
        "name": "verify",
        "status": status,
        "code": TIMEOUT_EXPIRED_CODE if timed_out and status == "error" else (RUNTIME_ERROR_CODE if status == "error" else None),
        "message": (
            "Oracle-driven verify loop completed with policy-skipped oracles."
            if policy_denied and not (overall_failed or configuration_failed)
            else "Oracle-driven verify loop blocked by policy."
            if policy_denied
            else "Oracle-driven verify loop failed due to invalid oracle configuration."
            if configuration_failed
            else "Oracle-driven verify loop completed with failures."
            if overall_failed
            else "Oracle-driven verify loop completed for affected capsules."
        ),
        "mode": mode,
        "verified_capsules": changed_capsules,
        "oracle_count": sum(len(values) for values in oracle_results.values()) if oracle_results else 0,
        "certificate_refs": sorted(final_certificate_refs),
        "oracle_results": oracle_results,
        "receipt_pointers": receipts,
        "failed_capsules": sorted(set(failed_capsules)),
        "errors": errors,
        "warnings": warnings,
        "recovery": _summarize_recovery_records(recovery_records),
    }


def _run_export_stage(
    repo_root: str,
    mode: str,
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root, policy)
    if policy_error:
        return {
            "name": "export",
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "message": policy_error.get("message", "policy configuration is invalid"),
            "mode": mode,
            "updated_exports": [],
            "unchanged_exports": [],
            "errors": [policy_error.get("message", "policy configuration is invalid")],
        }

    autonomous_block = _build_autonomous_write_block_payload(
        repo_root,
        mode,
        name="export",
        command="export",
    )
    if autonomous_block is not None:
        return {
            **autonomous_block,
            "updated_exports": [],
            "unchanged_exports": [],
        }

    write_check = _evaluate_policy_writes(
        policy_payload,
        command="export",
        mode=mode,
        targets=list(EXPORT_PATHS.values()),
    )
    if write_check is not None:
        return {
            "name": "export",
            "status": "error",
            "message": str(write_check.get("message", "policy denied write")),
            "mode": mode,
            "updated_exports": [],
            "unchanged_exports": [],
            "errors": [str(write_check.get("message", "policy denied write"))],
            **write_check,
        }

    try:
        updated_exports, unchanged_exports, snapshot = _run_export_refresh(repo_root)
        message = "Export refresh completed."
        if not updated_exports:
            message = "Export refresh completed with no content changes."
        return {
            "name": "export",
            "status": "ok",
            "message": message,
            "mode": mode,
            "updated_exports": sorted(updated_exports),
            "unchanged_exports": sorted(unchanged_exports),
            "artifact_total": snapshot["counts"]["total"],
            "artifact_counts": snapshot["counts"]["by_scope"],
            "snapshot_generated_at": snapshot["generated_at"],
        }
    except Exception as exc:
        return {
            "name": "export",
            "status": "error",
            "message": f"Export refresh failed: {exc}",
            "mode": mode,
            "updated_exports": [],
            "unchanged_exports": [],
        }


def _record_sync_summary_event(repo_root: str, payload: dict[str, object], total_ms: int) -> str:
    prompt_provenance = _collect_prompt_provenance_records(payload.get("steps"))
    session_id = payload.get("session_id")
    event_payload = {
        "schema_version": 2,
        "artifact_type": "sync_summary",
        "id": payload["run_id"],
        "status": payload["status"],
        "command": "sync",
        "subcommand": None,
        "idempotency_key": payload["idempotency_key"],
        "duration_ms": total_ms,
        "created_at": _utc_timestamp(),
        "snapshot": payload["snapshot"],
        "steps": payload["steps"],
        "recovery": payload.get("recovery", {}),
        **({"worker_prompt_provenance": prompt_provenance} if prompt_provenance else {}),
        **({"session_id": session_id} if isinstance(session_id, str) and session_id.strip() else {}),
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _record_replay_summary_event(repo_root: str, payload: dict[str, object], total_ms: int, snapshot: dict[str, object]) -> str:
    prompt_provenance = _collect_prompt_provenance_records(payload.get("steps"))
    session_id = payload.get("session_id")
    event_payload = {
        "schema_version": 2,
        "artifact_type": "replay_summary",
        "id": payload["run_id"],
        "status": payload["status"],
        "command": "replay",
        "subcommand": None,
        "duration_ms": total_ms,
        "created_at": _utc_timestamp(),
        "snapshot": snapshot,
        "steps": payload.get("steps", []),
        "recovery": payload.get("recovery", {}),
        **({"worker_prompt_provenance": prompt_provenance} if prompt_provenance else {}),
        **({"session_id": session_id} if isinstance(session_id, str) and session_id.strip() else {}),
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _record_verify_summary_event(repo_root: str, payload: dict[str, object], total_ms: int, snapshot: dict[str, object]) -> str:
    prompt_provenance = _collect_prompt_provenance_records(payload.get("steps"))
    session_id = payload.get("session_id")
    event_payload = {
        "schema_version": 2,
        "artifact_type": "verify_summary",
        "id": payload["run_id"],
        "status": payload["status"],
        "command": "verify",
        "subcommand": None,
        "duration_ms": total_ms,
        "created_at": _utc_timestamp(),
        "snapshot": snapshot,
        "steps": payload.get("steps", []),
        "recovery": payload.get("recovery", {}),
        **({"worker_prompt_provenance": prompt_provenance} if prompt_provenance else {}),
        **({"session_id": session_id} if isinstance(session_id, str) and session_id.strip() else {}),
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _build_drift_payload(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    drift_state = _collect_drift_state(repo_root, now)
    status = "ok" if drift_state["state"] == "ok" else drift_state["state"]
    return {
        "status_schema_version": DRIFT_REPORT_SCHEMA_VERSION,
        "status": status,
        "command": "drift",
        "options": options,
        "generated_at": _utc_timestamp(),
        "remediation": drift_state.get("remediation", []),
        "message": "drift detection completed",
        "checks": drift_state["checks"],
        "drift": drift_state,
    }


def _record_drift_report_event(repo_root: str, payload: dict[str, object], total_ms: int) -> str:
    run_id = _build_run_id("drift", _short_hash(f"drift:{total_ms}:{len(payload.get('checks', []))}", 10))
    session_id = payload.get("session_id")
    event_payload = {
        "schema_version": 2,
        "artifact_type": "drift_report",
        "id": run_id,
        "status": payload.get("status", "ok"),
        "command": "drift",
        "duration_ms": total_ms,
        "created_at": payload.get("generated_at", _utc_timestamp()),
        "checks": payload.get("checks", []),
        "drift": payload.get("drift", {}),
        "remediation": payload.get("drift", {}).get("remediation", []),
        **({"session_id": session_id} if isinstance(session_id, str) and session_id.strip() else {}),
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _run_sync_job(repo_root: str, options: dict[str, object], session: dict[str, object] | None = None) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    force_full_sync = bool(options.get("force_full_sync", False))
    snapshot = _collect_sync_snapshot(repo_root, profile, mode, force_full_sync=force_full_sync)
    idempotency_key = _compute_idempotency_key(snapshot, profile, mode)
    run_id = f"sync-{_utc_timestamp().replace(':', '').replace('-', '')}-{idempotency_key[:10]}"
    session = _session_from_payload(session)
    session_id = session.get("session_id") if isinstance(session, dict) else None
    sync_options: dict[str, object] = dict(options)
    sync_options.update(
        {
            "changed": options.get("changed", False),
            "profile": profile,
            "mode": mode,
            "force_full_sync": force_full_sync,
            "max_retries": int(options.get("max_retries") or 0),
            "timeout": options.get("timeout"),
        }
    )
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        payload = {
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "command": "sync",
            "subcommand": None,
            "run_id": run_id,
            "session_id": session_id,
            "session": session,
            "idempotency_key": idempotency_key,
            "snapshot": snapshot,
            "pending": False,
            "pending_consumed": False,
            "short_circuit": False,
            "steps": [
                {
                    "name": "policy",
                    "status": "error",
                    **policy_error,
                    "message": str(policy_error.get("message", "policy configuration is invalid")),
                }
            ],
            "message": str(policy_error.get("message", "policy configuration is invalid")),
            "options": sync_options,
            "diff_baseline": snapshot.get("diff_baseline"),
            "force_full_sync": force_full_sync,
        }
        _record_sync_summary_event(repo_root, payload, 0)
        _build_work_payload(
            repo_root,
            status="degraded",
            last_sync_id=run_id,
            last_idempotency_key=idempotency_key,
            last_message="sync failed policy validation",
        )
        return payload


    try:
        _validate_canonical_artifact_records(repo_root)
        changed_files = snapshot.get("changed_files")
        if not isinstance(changed_files, list):
            changed_files = []
        snapshot["materials_lock_ref"] = _repair_materials_lock(repo_root, [str(item) for item in changed_files])
    except ValueError as exc:
        payload = {
            "status": "error",
            "command": "sync",
            "subcommand": None,
            "run_id": run_id,
            "session_id": session_id,
            "session": session,
            "idempotency_key": idempotency_key,
            "snapshot": snapshot,
            "pending": False,
            "pending_consumed": False,
            "short_circuit": False,
            "steps": [
                {
                    "name": "validate",
                    "status": "error",
                    "message": f"Canonical artifact validation failed: {exc}",
                }
            ],
            "message": "sync validation failed before apply.",
            "options": sync_options,
            "diff_baseline": snapshot.get("diff_baseline"),
            "force_full_sync": force_full_sync,
        }
        _record_sync_summary_event(repo_root, payload, 0)
        _build_work_payload(
            repo_root,
            status="degraded",
            last_sync_id=run_id,
            last_idempotency_key=idempotency_key,
            last_message="sync failed canonical validation",
        )
        return payload
    except Exception as exc:
        payload = {
            "status": "error",
            "command": "sync",
            "subcommand": None,
            "run_id": run_id,
            "session_id": session_id,
            "session": session,
            "idempotency_key": idempotency_key,
            "snapshot": snapshot,
            "pending": False,
            "pending_consumed": False,
            "short_circuit": False,
            "steps": [
                {
                    "name": "materials_lock",
                    "status": "error",
                    "message": f"Failed to repair materials lock: {exc}",
                }
            ],
            "message": "sync failed during materials lock repair.",
            "options": sync_options,
            "diff_baseline": snapshot.get("diff_baseline"),
            "force_full_sync": force_full_sync,
        }
        _record_sync_summary_event(repo_root, payload, 0)
        _build_work_payload(
            repo_root,
            status="degraded",
            last_sync_id=run_id,
            last_idempotency_key=idempotency_key,
            last_message="sync failed materials lock repair",
        )
        return payload

    pending = _consume_pending(repo_root)
    was_short_circuit = False
    steps: list[dict[str, object]] = []
    current_state = _read_work_state(repo_root)

    if not force_full_sync and current_state.get("last_idempotency_key") == idempotency_key:
        was_short_circuit = True
        steps.append(
            {
                "name": "short_circuit",
                "status": "ok",
                "message": "Idempotent key unchanged; sync skipped.",
                "idempotency_key": idempotency_key,
            }
        )
        payload = {
            "status": "ok",
            "command": "sync",
            "subcommand": None,
            "run_id": run_id,
            "session_id": session_id,
            "session": session,
            "idempotency_key": idempotency_key,
            "snapshot": snapshot,
            "pending": False,
            "pending_consumed": pending,
            "short_circuit": True,
            "steps": steps,
            "message": "sync short-circuit: idempotent state already materialized.",
            "options": sync_options,
            "diff_baseline": snapshot.get("diff_baseline"),
            "force_full_sync": force_full_sync,
        }
        _record_sync_summary_event(repo_root, payload, 0)
        _build_work_payload(
            repo_root,
            status="idle",
            last_sync_id=run_id,
            last_idempotency_key=idempotency_key,
            last_message="sync short-circuited by idempotency key",
        )
        return payload

    def _time_step(name: str, stage_fn) -> dict[str, object]:
        start = time.perf_counter()
        result = stage_fn()
        duration_ms = int((time.perf_counter() - start) * 1000)
        if isinstance(result, dict):
            result["duration_ms"] = duration_ms
            return result
        return {
            "name": name,
            "status": "error",
            "message": f"sync stage {name} returned invalid result",
            "duration_ms": duration_ms,
        }

    start_at = time.perf_counter()
    _build_work_payload(repo_root, status="distill", last_message="starting distill", last_idempotency_key=idempotency_key)
    distill = _time_step(
        "distill",
        lambda: _run_distill_stage(
            repo_root,
            snapshot,
            run_id,
            profile=profile,
            mode=mode,
            max_retries=int(options.get("max_retries") or 0),
            timeout_seconds=cast(int | None, options.get("timeout")),
        ),
    )
    steps.append(distill)

    _build_work_payload(repo_root, status="apply", last_message="starting apply")
    apply_result = _time_step(
        "apply",
        lambda: _run_apply_stage(
            repo_root=repo_root,
            distill_result=distill,
            run_id=run_id,
            mode=mode,
            policy=policy_payload,
        ),
    )
    steps.append(apply_result)

    affected_capsules = distill.get("affected_capsules", []) if distill.get("status") == "ok" else []
    _build_work_payload(repo_root, status="verify", last_message="starting verify")
    verify = _time_step(
        "verify",
        lambda: _run_verify_stage(
            repo_root,
            affected_capsules,
            snapshot.get("changed_files", []) if isinstance(snapshot, dict) else [],
            run_id,
            mode=mode,
            policy=policy_payload,
            max_retries=int(options.get("max_retries") or 0),
            timeout_seconds=cast(int | None, options.get("timeout")),
        ),
    )
    steps.append(verify)

    _build_work_payload(repo_root, status="export", last_message="starting export")
    export = _time_step(
        "export",
        lambda: _run_export_stage(repo_root, mode=mode, policy=policy_payload),
    )
    steps.append(export)

    step_statuses = {
        str(item.get("status") or "").lower()
        for item in steps
        if isinstance(item, dict)
    }
    run_status = "ok"
    if step_statuses.intersection({"error", "pending", "failed", "fail"}):
        run_status = "error"
    else:
        blocking_warn_steps = {
            str(item.get("name") or "").lower()
            for item in steps
            if isinstance(item, dict) and str(item.get("status") or "").lower() == "warn"
        } - {"apply"}
        if blocking_warn_steps:
            run_status = "warn"
    sync_message = "sync workflow completed"
    if run_status == "warn":
        sync_message = "sync workflow completed with warnings"
    elif run_status == "error":
        sync_message = "sync workflow failed"
    payload = {
        "status": run_status,
        "command": "sync",
        "code": next(
            (
                str(step.get("code"))
                for step in steps
                if isinstance(step, dict) and str(step.get("status") or "").lower() == "error" and step.get("code")
            ),
            None,
        ),
        "subcommand": None,
        "run_id": run_id,
        "session_id": session_id,
        "session": session,
        "idempotency_key": idempotency_key,
        "snapshot": snapshot,
        "pending": False,
        "pending_consumed": pending,
        "short_circuit": was_short_circuit,
        "steps": steps,
        "message": sync_message,
        "options": sync_options,
        "diff_baseline": snapshot.get("diff_baseline"),
        "force_full_sync": force_full_sync,
        "recovery": _summarize_recovery_records(
            [
                recovery
                for step in steps
                for recovery in ([step.get("recovery")] if isinstance(step, dict) and isinstance(step.get("recovery"), dict) else [])
            ]
        ),
        "errors": [
            error
            for step in steps
            if isinstance(step, dict)
            for error in (
                step.get("errors")
                if isinstance(step.get("errors"), list)
                else ([{"error_code": step.get("code") or RUNTIME_ERROR_CODE, "message": step.get("message")}]
                      if str(step.get("status") or "").lower() == "error"
                      else [])
            )
        ],
    }
    duration_ms = int((time.perf_counter() - start_at) * 1000)
    summary_path = _record_sync_summary_event(repo_root, payload, duration_ms)
    _build_work_payload(
        repo_root,
        status="idle" if run_status in {"ok", "warn"} else "degraded",
        last_sync_id=run_id,
        last_idempotency_key=idempotency_key,
        last_message=f"sync finished ({run_status})",
    )
    payload["summary_event"] = summary_path
    payload["duration_ms"] = duration_ms
    return payload


def build_payload(
    command: str,
    subcommand: str | None = None,
    *,
    changed: bool = False,
    profile: str | None = None,
    mode: str | None = None,
    force_hooks_path: bool = False,
    output_json: bool = False,
) -> dict[str, object]:
    options: dict[str, object] = {
        "changed": changed,
        "profile": profile,
        "mode": mode,
    }
    if force_hooks_path:
        options["force_hooks_path"] = force_hooks_path
    payload: dict[str, object] = {
        "status": "ok",
        "command": command,
        "options": options,
    }
    if subcommand:
        payload["subcommand"] = subcommand
    payload["message"] = f"{command} command accepted."
    if output_json:
        payload["structured"] = True
    return payload


def _payload_has_code(payload: dict[str, object], code: str) -> bool:
    if str(payload.get("code") or "") == code:
        return True
    target = str(code)
    if str(payload.get("error_code") or "") == target:
        return True

    for value in payload.values():
        if isinstance(value, dict):
            if _payload_has_code(value, code):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _payload_has_code(item, code):
                    return True
    return False


def _payload_has_error_class(payload: dict[str, object], error_class: str) -> bool:
    target = str(error_class)
    if str(payload.get("error_class") or _error_class_for_code(str(payload.get("error_code") or payload.get("code") or ""))) == target:
        return True
    for key in ["code", "error_code"]:
        if key in payload and str(payload.get("error_class") or _error_class_for_code(str(payload.get(key) or ""))) == target:
            return True
    for value in payload.values():
        if isinstance(value, dict):
            if _payload_has_error_class(value, error_class):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _payload_has_error_class(item, error_class):
                    return True
    return False


def _command_exit_code(payload: dict[str, object]) -> int:
    if str(payload.get("status") or "").lower() != "error":
        return EXIT_SUCCESS
    if _payload_has_error_class(payload, ERROR_CLASS_USAGE):
        return EXIT_USAGE
    if _payload_has_code(payload, POLICY_CONFIG_ERROR_CODE):
        return EXIT_USAGE
    return EXIT_RUNTIME


def _schema_command_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "command": "schema",
        "schema_version": COMMAND_INTROSPECTION_SCHEMA_VERSION,
        "cli_version": VERSION,
        "command_count": len(_CLI_COMMAND_SIGNATURE_BY_NAME),
        "commands": _CLI_COMMAND_SIGNATURES,
    }


_OG_TYPER_APP = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
)


@_OG_TYPER_APP.callback()
def _og_typer_root() -> None:
    return None


@_OG_TYPER_APP.command("schema")
def _schema_typer_command() -> None:
    context = _current_typer_command_context()
    payload = _schema_command_payload()
    if not context["output_json"]:
        payload["message"] = _render_schema_overview(payload)
    emit_command_result(payload, bool(context["output_json"]))
    raise typer.Exit(code=_command_exit_code(payload))


_OG_TYPER_CLICK_COMMAND = typer_get_command(_OG_TYPER_APP)


def _invoke_typer_command(command_path: list[str], *, output_json: bool) -> int:
    token = _ACTIVE_TYPER_COMMAND_CONTEXT.set({"output_json": output_json})
    try:
        _OG_TYPER_CLICK_COMMAND.main(
            args=command_path,
            prog_name="og",
            standalone_mode=False,
        )
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.exceptions.ClickException as exc:
        emit_error(exc.format_message(), command_path[0] if command_path else None, EXIT_USAGE, output_json)
    finally:
        _ACTIVE_TYPER_COMMAND_CONTEXT.reset(token)
    return EXIT_SUCCESS


def run_command(
    args: list[str],
    output_json_override: bool | None,
    strict: bool = False,
    non_interactive: bool = False,
) -> int:
    try:
        command_runtime_defaults = _apply_output_json_override(_load_runtime_defaults(_maybe_git_root()), output_json_override)
    except ValueError as exc:
        emit_error(f"invalid runtime defaults: {exc}", None, EXIT_USAGE, bool(output_json_override))
    output_json = str(command_runtime_defaults.get("output_mode") or OUTPUT_MODE_HUMAN) != OUTPUT_MODE_HUMAN

    if not args:
        emit_error("missing command\n\n" + emit_usage(), None, EXIT_USAGE, output_json)

    command = args[0]
    rest = args[1:]
    output_json = str(command_runtime_defaults.get("output_mode") or OUTPUT_MODE_HUMAN) != OUTPUT_MODE_HUMAN
    for arg in rest:
        if arg == "--json":
            output_json = True
            continue
        if arg.startswith("--json="):
            try:
                output_json = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --json value: {exc}", command, EXIT_USAGE, output_json)

    if command == "init":
        options, _ = parse_command_flags(
            rest,
            "init",
            False,
            False,
            False,
            output_json,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        emit_command_result(_init_outcomegraph(), output_json)
        return EXIT_SUCCESS

    if command == "sync":
        options, _ = parse_command_flags(
            rest,
            "sync",
            False,
            True,
            True,
            output_json,
            allow_force_full_sync=True,
            allow_validate=True,
            allow_dry_run=True,
            allow_recovery_controls=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        if bool(options.get("validate")) or bool(options.get("dry_run")):
            payload = _run_sync_preflight(repo_root, options)
            emit_command_result(payload, output_json)
            return _command_exit_code(payload)
        integrity = _validate_event_chain(repo_root)
        if integrity.get("status") != "ok":
            repair = _repair_integrity_index(repo_root)
            if repair.get("status") == "ok":
                integrity = _validate_event_chain(repo_root)
            if integrity.get("status") != "ok":
                _build_work_payload(
                    repo_root,
                    status="degraded",
                    last_message="integrity ledger validation failed",
                )
                payload = {
                    "status": "error",
                    "command": "sync",
                    "code": INTEGRITY_CHECK_FAILED_CODE,
                    "options": options,
                    "integrity": integrity,
                    "repair": repair,
                    "message": f"integrity check failed: {integrity.get('message', 'ledger validation error')}",
                }
                emit_command_result(payload, output_json)
                return _command_exit_code(payload)
        holder = {"pid": os.getpid(), "host": socket.gethostname(), "command": "og sync"}
        lock_acquired, lock_payload = _acquire_work_lock(repo_root, holder)
        if not lock_acquired:
            active_session = _session_from_payload(lock_payload.get("session")) if isinstance(lock_payload, dict) else None
            active_session_id = active_session.get("session_id") if isinstance(active_session, dict) else None
            contended_payload = {
                "status": "warn",
                "command": "sync",
                "options": options,
                "lock": {
                    "status": "contended",
                    "holder": lock_payload.get("holder") if isinstance(lock_payload, dict) else None,
                    "session": active_session,
                },
                "session": active_session,
                "session_id": active_session_id,
                "pending": True,
                "errors": [
                    _build_session_error(
                        SESSION_CONTENDED_CODE,
                        f"sync session '{active_session_id or 'unknown'}' is already active; pending work recorded.",
                        command="sync",
                        session=active_session,
                    )
                ],
                "message": "sync session is already running; pending work recorded.",
            }
            _set_pending_state(
                repo_root,
                f"lock contended by {active_session_id or lock_payload.get('holder', {}).get('pid') if lock_payload else 'unknown'}",
            )
            emit_command_result(contended_payload, output_json)
            return _command_exit_code(contended_payload)
        try:
            active_session = _session_from_payload(lock_payload.get("session")) if isinstance(lock_payload, dict) else None
            payload = _run_sync_job(repo_root, options, active_session)
            payload["lock"] = {"status": LOCK_STATUS_LOCKED, "payload": lock_payload, "session": active_session}
            emit_command_result(payload, output_json)
            return _command_exit_code(payload)
        finally:
            _release_work_lock(repo_root, holder)
        return EXIT_SUCCESS

    if command == "verify":
        options, _ = parse_command_flags(
            rest,
            "verify",
            True,
            True,
            True,
            output_json,
            allow_output_controls=True,
            allow_validate=True,
            allow_dry_run=True,
            allow_recovery_controls=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        output_mode = str(options.get("output_mode") or OUTPUT_MODE_JSON)
        if bool(options.get("validate")) or bool(options.get("dry_run")):
            payload = _run_verify_preflight(repo_root, options)
            if output_mode == OUTPUT_MODE_HUMAN:
                payload["message"] = str(payload.get("message") or "verify preflight completed")
                emit_command_result(payload, False)
            else:
                emit_command_result(payload, True)
            return _command_exit_code(payload)
        payload = _run_verify_job(repo_root, options)
        payload = _apply_output_controls(payload, options, output_mode=output_mode)
        if output_mode == OUTPUT_MODE_HUMAN:
            payload["message"] = _render_verify(payload)
        if output_mode == OUTPUT_MODE_JSONL:
            emit_command_result_jsonl(payload, "verify")
            return _command_exit_code(payload)
        emit_command_result(payload, output_mode != OUTPUT_MODE_HUMAN)
        return _command_exit_code(payload)

    if command == "replay":
        options, _ = parse_command_flags(
            rest,
            "replay",
            True,
            True,
            True,
            output_json,
            allow_output_controls=True,
            allow_validate=True,
            allow_dry_run=True,
            allow_recovery_controls=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        output_mode = str(options.get("output_mode") or OUTPUT_MODE_JSON)
        if bool(options.get("validate")) or bool(options.get("dry_run")):
            payload = _run_replay_preflight(repo_root, options)
            emit_command_result(payload, output_mode != OUTPUT_MODE_HUMAN)
            return _command_exit_code(payload)
        payload = _run_replay_job(repo_root, options)
        payload = _apply_output_controls(payload, options, output_mode=output_mode)
        if output_mode == OUTPUT_MODE_JSONL:
            emit_command_result_jsonl(payload, "replay")
            return _command_exit_code(payload)
        emit_command_result(payload, output_mode != OUTPUT_MODE_HUMAN)
        return _command_exit_code(payload)

    if command == "status":
        options, _ = parse_command_flags(
            rest,
            "status",
            False,
            False,
            False,
            output_json,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        payload = _build_status_payload(repo_root, options)
        if not output_json:
            payload["message"] = _render_status(payload)
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "doctor":
        options, _ = parse_command_flags(
            rest,
            "doctor",
            False,
            False,
            False,
            output_json,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        payload = _build_doctor_payload(repo_root, options)
        if not output_json:
            payload["message"] = _render_doctor(payload)
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "export":
        options, _ = parse_command_flags(
            rest,
            "export",
            False,
            False,
            False,
            output_json,
            allow_validate=True,
            allow_dry_run=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        if bool(options.get("validate")) or bool(options.get("dry_run")):
            payload = _run_export_preflight(repo_root, options)
            emit_command_result(payload, output_json)
            return _command_exit_code(payload)
        export = _run_export_stage(repo_root, mode="observe")
        status = "ok" if export.get("status") == "ok" else "error"
        payload = {
            "status": status,
            "command": "export",
            "options": options,
            "steps": [export],
            "message": export.get("message", "export completed"),
            "updated_exports": export.get("updated_exports", []),
            "unchanged_exports": export.get("unchanged_exports", []),
            "snapshot_generated_at": export.get("snapshot_generated_at"),
            "artifact_total": export.get("artifact_total", 0),
            "artifact_counts": export.get("artifact_counts", {}),
        }
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "explain":
        options, _ = parse_command_flags(
            rest,
            "explain",
            False,
            True,
            True,
            output_json,
            allow_output_controls=True,
            allow_capsule_filter=True,
            allow_ref_filter=True,
            allow_certificate_filter=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        profile = str(options.get("profile") or "analyze")
        mode = str(options.get("mode") or "observe")
        run_id = _build_run_id("explain", _short_hash(f"{profile}:{mode}", 8))
        explain = _run_explain_stage(
            repo_root=repo_root,
            profile=profile,
            mode=mode,
            run_id=run_id,
            capsule_filters=options.get("capsule"),
            ref_filters=options.get("ref"),
            certificate_filters=options.get("certificate"),
        )
        payload = {
            "status": "ok" if explain.get("status") == "ok" else "error",
            "command": "explain",
            "options": options,
            "run_id": run_id,
            "message": explain.get("message", "explain adapter completed"),
            "claims": explain.get("claims", []),
            "certificates": explain.get("certificates", []),
            "decisions": explain.get("decisions", []),
            "deltas": explain.get("deltas", []),
            "target_capsules": explain.get("target_capsules", []),
            "filters": explain.get("filters", {}),
            "errors": explain.get("errors", []),
        }
        output_mode = str(options.get("output_mode") or OUTPUT_MODE_JSON)
        payload = _apply_output_controls(payload, options, output_mode=output_mode)
        if output_mode == OUTPUT_MODE_HUMAN:
            payload["message"] = _render_explain(payload)
        if output_mode == OUTPUT_MODE_JSONL:
            emit_command_result_jsonl(payload, "explain")
            return _command_exit_code(payload)
        emit_command_result(payload, output_mode != OUTPUT_MODE_HUMAN)
        return _command_exit_code(payload)

    if command == "drift":
        options, _ = parse_command_flags(
            rest,
            "drift",
            False,
            False,
            False,
            output_json,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        start = time.perf_counter()
        payload = _build_drift_payload(repo_root, options)
        duration_ms = int((time.perf_counter() - start) * 1000)
        summary_event = _record_drift_report_event(repo_root, payload, duration_ms)
        payload["duration_ms"] = duration_ms
        payload["summary_event"] = summary_event
        if not output_json:
            payload["message"] = _render_drift(payload)
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "mcp-server":
        options, _ = parse_command_flags(
            rest,
            "mcp-server",
            False,
            False,
            False,
            output_json,
            allow_output_controls=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        repo_root = _git_root()
        payload = _run_mcp_server_stage(repo_root, options)
        output_mode = str(options.get("output_mode") or OUTPUT_MODE_JSON)
        payload = _apply_output_controls(payload, options, output_mode=output_mode)
        if output_mode == OUTPUT_MODE_HUMAN and payload.get("status") == "ok":
            payload["message"] = _render_mcp_server(payload)
        if output_mode == OUTPUT_MODE_JSONL:
            emit_command_result_jsonl(payload, "mcp-server")
            return _command_exit_code(payload)
        emit_command_result(payload, output_mode != OUTPUT_MODE_HUMAN)
        return _command_exit_code(payload)

    if command == "optimize":
        if rest and rest[0] in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "optimize",
                    "status": "ok",
                    "message": _help_for_command("optimize"),
                },
                output_json,
                "optimize",
            )
            return EXIT_SUCCESS
        if not rest:
            emit_error("missing optimize subcommand\n\nAvailable: prompts", "optimize", EXIT_USAGE, output_json)
        sub = rest[0]
        if sub != "prompts":
            emit_error(
                f"unknown optimize subcommand '{sub}'\n\nAvailable: prompts",
                "optimize",
                EXIT_USAGE,
                output_json,
            )
        options = _parse_optimize_prompts_flags(rest[1:], output_json, default_strict=strict)
        repo_root = _git_root()
        payload = _run_optimize_prompts_stage(repo_root, options)
        if not output_json:
            payload["message"] = _render_optimize_prompts(payload) if payload.get("status") == "ok" else payload.get(
                "message", "optimize prompts execution failed"
            )
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "autopilot":
        if rest and rest[0] in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "autopilot",
                    "status": "ok",
                    "message": _help_for_command("autopilot"),
                },
                output_json,
                "autopilot",
            )
            return EXIT_SUCCESS
        if not rest:
            emit_error("missing autopilot subcommand\n\nAvailable: init, disable", "autopilot", EXIT_USAGE, output_json)
        sub = rest[0]
        if sub not in {"init", "disable"}:
            emit_error(
                f"unknown autopilot subcommand '{sub}'\n\nAvailable: init, disable",
                "autopilot",
                EXIT_USAGE,
                output_json,
            )
        options, _ = parse_command_flags(
            rest[1:],
            "autopilot " + sub,
            False,
            False,
            False,
            output_json,
            allow_force_hooks_path=sub == "init",
            allow_yes=sub == "init",
            allow_session_id=sub == "disable",
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        if sub == "init":
            state = _init_autopilot(
                bool(options.get("force_hooks_path", False)),
                bool(options.get("yes", False)),
                non_interactive=non_interactive,
                output_json=output_json,
            )
            state["message"] = "autopilot init command executed."
            emit_command_result(state, output_json)
            return EXIT_SUCCESS
        if sub == "disable":
            state = _disable_autopilot(cast(str | None, options.get("session_id")))
            emit_command_result(state, output_json)
            return _command_exit_code(state)
        emit_command_result(build_payload("autopilot", sub, **options), output_json)
        return EXIT_SUCCESS

    if command == "daemon":
        if rest and rest[0] in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "daemon",
                    "status": "ok",
                    "message": _help_for_command("daemon"),
                },
                output_json,
                "daemon",
            )
            return EXIT_SUCCESS
        if not rest:
            emit_error("missing daemon action\n\nAvailable: install, start, stop, status, run", "daemon", EXIT_USAGE, output_json)
        sub = rest[0]
        if sub not in {"install", "start", "stop", "status", "run"}:
            emit_error(
                f"unknown daemon action '{sub}'\n\nAvailable: install, start, stop, status, run",
                "daemon",
                EXIT_USAGE,
                output_json,
            )
        if sub == "run":
            parse_command_flags(
                rest[1:],
                "daemon run",
                False,
                False,
                False,
                output_json,
                runtime_defaults=command_runtime_defaults,
                default_strict=strict,
            )
            return _daemon_run()
        if sub == "install":
            options, _ = parse_command_flags(
                rest[1:],
                "daemon install",
                False,
                False,
                False,
                output_json,
                runtime_defaults=command_runtime_defaults,
                default_strict=strict,
            )
            payload = _daemon_install()
            payload["options"] = options
            emit_command_result(payload, output_json)
            return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS
        if sub == "start":
            options, _ = parse_command_flags(
                rest[1:],
                "daemon start",
                False,
                False,
                False,
                output_json,
                allow_session_id=True,
                runtime_defaults=command_runtime_defaults,
                default_strict=strict,
            )
            payload = _daemon_start(cast(str | None, options.get("session_id")))
            payload["options"] = options
            emit_command_result(payload, output_json)
            return _command_exit_code(payload)
        if sub == "stop":
            options, _ = parse_command_flags(
                rest[1:],
                "daemon stop",
                False,
                False,
                False,
                output_json,
                allow_session_id=True,
                runtime_defaults=command_runtime_defaults,
                default_strict=strict,
            )
            payload = _daemon_stop(cast(str | None, options.get("session_id")))
            payload["options"] = options
            emit_command_result(payload, output_json)
            return _command_exit_code(payload)
        options, _ = parse_command_flags(
            rest[1:],
            "daemon status",
            False,
            False,
            False,
            output_json,
            allow_session_id=True,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        payload = _daemon_status(cast(str | None, options.get("session_id")))
        payload["options"] = options
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "schema":
        parse_command_flags(
            rest,
            "schema",
            False,
            False,
            False,
            output_json,
            runtime_defaults=command_runtime_defaults,
            default_strict=strict,
        )
        return _invoke_typer_command(["schema"], output_json=output_json)

    if command == "describe":
        if rest and rest[0] in {"-h", "--help"}:
            emit_command_result(
                {
                    "command": "describe",
                    "status": "ok",
                    "message": _help_for_command("describe"),
                },
                output_json,
                "describe",
            )
            return EXIT_SUCCESS

        if not rest:
            emit_error(
                "missing command argument; usage: og describe <command>\n\nAvailable commands: "
                + ", ".join(sorted(_CLI_COMMAND_SIGNATURE_BY_NAME)),
                "describe",
                EXIT_USAGE,
                output_json,
            )

        normalized_rest: list[str] = []
        for arg in rest:
            if arg == "--json":
                output_json = True
                continue
            if arg.startswith("--json="):
                try:
                    output_json = parse_bool_option(arg.split("=", 1)[1])
                except ValueError as exc:
                    emit_error(f"invalid --json value for describe: {exc}", "describe", EXIT_USAGE, output_json)
                continue
            if arg == "--strict":
                continue
            if arg.startswith("--strict="):
                try:
                    _ = parse_bool_option(arg.split("=", 1)[1])
                except ValueError as exc:
                    emit_error(f"invalid --strict value for describe: {exc}", "describe", EXIT_USAGE, output_json)
                continue
            if arg.startswith("-"):
                emit_error(
                    f"describe does not accept option '{arg}'",
                    "describe",
                    EXIT_USAGE,
                    output_json,
                )
            normalized_rest.append(arg)
        if not normalized_rest:
            emit_error(
                "missing command argument; usage: og describe <command>\n\nAvailable commands: "
                + ", ".join(sorted(_CLI_COMMAND_SIGNATURE_BY_NAME)),
                "describe",
                EXIT_USAGE,
                output_json,
            )
        target_command = _normalize_command_signature_target(" ".join(normalized_rest))
        signature = _CLI_COMMAND_SIGNATURE_BY_NAME.get(target_command)
        if not signature:
            emit_error(
                f"unknown command '{target_command}'\n\nAvailable commands: " + ", ".join(sorted(_CLI_COMMAND_SIGNATURE_BY_NAME)),
                "describe",
                EXIT_USAGE,
                output_json,
            )
        payload = {
            "status": "ok",
            "command": "describe",
            "schema_version": COMMAND_INTROSPECTION_SCHEMA_VERSION,
            "requested_command": target_command,
            "signature": signature,
        }
        if not output_json:
            payload["message"] = _render_command_signature(signature)
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    if command == "clean":
        options = _parse_clean_flags(rest, output_json)
        repo_root = _git_root()
        payload = _run_clean_job(repo_root, options)
        emit_command_result(payload, output_json)
        return _command_exit_code(payload)

    emit_error(f"unknown command '{command}'\n\n" + emit_usage(), None, EXIT_USAGE, output_json)
    return EXIT_USAGE


def main(argv: list[str]) -> int:
    output_json_override: bool | None = None
    strict = False
    non_interactive = False
    try:
        runtime_defaults = _load_runtime_defaults(_maybe_git_root())
    except ValueError as exc:
        emit_error(f"invalid runtime defaults: {exc}", None, EXIT_USAGE, False)
    output_json = str(runtime_defaults.get("output_mode") or OUTPUT_MODE_HUMAN) != OUTPUT_MODE_HUMAN
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            output_json_override = True
            output_json = True
            i += 1
            continue
        if arg.startswith("--json="):
            try:
                output_json_override = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --json value: {exc}", None, EXIT_USAGE, bool(output_json_override))
            output_json = bool(output_json_override)
            i += 1
            continue
        if arg == "--strict":
            strict = True
            i += 1
            continue
        if arg.startswith("--strict="):
            try:
                strict = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --strict value: {exc}", None, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg == "--non-interactive":
            non_interactive = True
            i += 1
            continue
        if arg.startswith("--non-interactive="):
            try:
                non_interactive = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --non-interactive value: {exc}", None, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg in {"-h", "--help"}:
            print(emit_usage())
            return EXIT_SUCCESS
        if arg in {"-v", "--version"}:
            if output_json:
                emit_command_result(
                    {
                        "command": "version",
                        "status": "ok",
                        "version": VERSION,
                    },
                    True,
                    "version",
                )
            else:
                print(f"og {VERSION}")
            return EXIT_SUCCESS
        if arg.startswith("-"):
            emit_error(f"unknown global option '{arg}'", None, EXIT_USAGE, output_json)
        break

    command_args = argv[i:]
    return run_command(command_args, output_json_override, strict, non_interactive)


def og_cli() -> None:
    raise SystemExit(main(sys.argv[1:]))


def ogd_cli() -> None:
    raise SystemExit(main(["daemon", *sys.argv[1:]]))


if __name__ == "__main__":
    try:
        og_cli()
    except Exception as exc:
        emit_error(f"internal error: {exc}", None, EXIT_RUNTIME, False)
