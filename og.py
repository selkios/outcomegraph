#!/usr/bin/env python3
"""OutcomeGraph stable CLI contract scaffold."""

from __future__ import annotations

import json
import fnmatch
import math
import os
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


VERSION = "0.1.0-dev"

EXIT_SUCCESS = 0
EXIT_USAGE = 64
EXIT_RUNTIME = 1
POLICY_SCHEMA_VERSION = 2
POLICY_DENIED_CODE = "POLICY_DENIED"
POLICY_CONFIG_ERROR_CODE = "POLICY_CONFIG_ERROR"
AUTONOMOUS_WRITE_BLOCKED_CODE = "AUTONOMOUS_WRITE_BLOCKED"
POLICY_ALLOW_CATEGORIES = {"file_writes", "verify_commands", "sandbox_operations"}
POLICY_DENY_CATEGORIES = {"file_writes", "verify_commands", "sandbox_operations", "network", "dependencies", "deployment"}

PROFILE_VALUES = {"analyze", "propose", "apply"}
MODE_VALUES = {"observe", "autonomous"}
AUTOPILOT_HOOKS = ("pre-commit", "post-commit", "post-merge", "post-checkout", "post-rewrite", "pre-push")
AUTOPILOT_STATE_FILE = ".outcomegraph/autopilot/state.json"
AUTOPILOT_MANAGED_HOOK_DIR = ".outcomegraph/hooks"
AUTOPILOT_BACKUP_DIR = ".outcomegraph/autopilot/backups"
OG_ROOT = ".outcomegraph"
OUTCOME_GITIGNORE = f"{OG_ROOT}/.gitignore"
WORK_STATE_FILE = ".outcomegraph/work/state.json"
WORK_LOCK_FILE = ".outcomegraph/work/lock"
WORK_PENDING_FILE = ".outcomegraph/work/pending"
EVENTS_DIR = ".outcomegraph/events"
INTEGRITY_CHECKPOINT_DIR = f"{EVENTS_DIR}/checkpoints"
INTEGRITY_STATE_FILE = f"{EVENTS_DIR}/integrity_state.json"
INTEGRITY_CHECKPOINT_INTERVAL = 32
INTEGRITY_SIGNER_ENV = "OG_INTEGRITY_CHECKPOINT_SIGNER"
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
WORK_LOCK_STALE_SECONDS = 300
OPTIMIZATION_DEFAULT_MIN_IMPROVEMENT = 0.02
OPTIMIZATION_SUPPORTED_METRICS = ("contains", "exact")
LOCK_STATUS_LOCKED = "locked"
LOCK_STATUS_UNLOCKED = "unlocked"
STATUS_SCHEMA_VERSION = 1
DRIFT_REPORT_SCHEMA_VERSION = 1
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
WORKER_ADAPTER_DEFAULT_TIMEOUT_SECONDS = 120
REPLAY_STEP_DEFAULT_TIMEOUT_SECONDS = 120
ADAPTER_SCHEMA_VERSION = 2
ADAPTER_INTERFACE_MISMATCH_CODE = "ADAPTER_INTERFACE_MISMATCH"
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
_ADAPTER_BOOTSTRAP_STATE: dict[str, object] = {
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
DAEMON_UVX_SOURCE = "git+https://github.com/selkios/outcomegraph"
DAEMON_SYNC_TIMEOUT_SECONDS = 300
DAEMON_WATCH_INTERVAL_SECONDS = 2
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

    for deny in _policy_string_list(deny_rules.get(category)) if isinstance(deny_rules, dict) else []:
        if _policy_pattern_matches(deny, normalized_target):
            return _build_policy_deny_payload(command, mode, category, normalized_target)

    for allow in _policy_string_list(rules.get(category)) if isinstance(rules, dict) else []:
        if _policy_pattern_matches(allow, normalized_target):
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
            "code": "ADAPTER_MANIFEST_INVALID",
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
                "code": "ADAPTER_MANIFEST_INVALID",
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
                "code": "ADAPTER_DUPLICATE",
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
    if _ADAPTER_BOOTSTRAP_STATE.get("initialized") and _ADAPTER_BOOTSTRAP_STATE.get("repo_root") == repo_root:
        if _ADAPTER_BOOTSTRAP_STATE.get("errors"):
            return _ADAPTER_BOOTSTRAP_STATE["errors"]  # type: ignore[return-value]
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
    initialized_errors = _ADAPTER_BOOTSTRAP_STATE["errors"][:]  # type: ignore[index]
    _set_adapter_bootstrap_result(
        repo_root,
        errors=_ADAPTER_BOOTSTRAP_STATE["errors"],
        warnings=_ADAPTER_BOOTSTRAP_STATE["warnings"],
    )
    return initialized_errors  # type: ignore[return-value]


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


def emit_usage() -> str:
    return """Usage: og [--json] [--profile analyze|propose|apply] [--mode observe|autonomous] <command>

Core commands:
  og init
  og sync
  og verify [--changed]
  og replay [--changed]
  og status
  og export
  og explain [--capsule <id>[,<id>...]] [--ref <id>[,<id>...]] [--certificate <id>[,<id>...]]
  og drift
  og mcp-server
  og optimize prompts
  og autopilot init|disable
  og daemon install|start|stop|status
"""


def emit_error(message: str, command: str | None, code: int, output_json: bool = False) -> None:
    if output_json:
        payload = {
            "status": "error",
            "code": code,
            "command": command,
            "message": message,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"og: {message}", file=sys.stderr)
    sys.exit(code)


def emit_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def emit_command_result(payload: dict, output_json: bool) -> None:
    if output_json:
        emit_json(payload)
        return
    print(payload["message"])


def parse_bool_option(raw: str) -> bool:
    value = raw.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value '{raw}'")


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


def _utc_timestamp() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_timestamp(raw: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
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

def _read_json_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


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

        if status_lower == "error":
            state = "degraded"
            if step_name == "replay":
                message = "replay failures detected in last replay event"
            else:
                message = "verification failures detected in last sync"
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
    lines = raw.splitlines()

    def _normalize_scalar(raw_value: str) -> str:
        value = raw_value.strip()
        if (value.startswith("\"") and value.endswith("\"")) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value

    parsed: dict[str, object] = {}
    containers: list[object] = [parsed]
    indent_levels: list[int] = [-1]

    def _next_significant_line(index: int) -> str | None:
        next_index = index + 1
        while next_index < len(lines):
            candidate = lines[next_index].strip()
            if candidate and not candidate.lstrip().startswith("#"):
                return candidate
            next_index += 1
        return None

    for line_index, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        while indent <= indent_levels[-1] and len(containers) > 1:
            containers.pop()
            indent_levels.pop()

        container = containers[-1]

        if stripped.startswith("-"):
            value = stripped[1:].strip()
            if isinstance(container, list):
                container.append(_normalize_scalar(value))
            continue

        if ":" not in line:
            continue

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value:
            if isinstance(container, dict):
                container[key] = _normalize_scalar(value)
            continue

        next_line = _next_significant_line(line_index)
        if next_line is None or next_line.startswith("-"):
            if isinstance(container, dict):
                child = []
                container[key] = child
                containers.append(child)
                indent_levels.append(indent)
            continue

        if not isinstance(container, dict):
            continue

        if next_line and ":" in next_line and not next_line.startswith("-"):
            child: object = {}
        else:
            child = []
        container[key] = child
        containers.append(child)
        indent_levels.append(indent)

    return parsed


def _collect_policy_checks(repo_root: str) -> dict[str, object]:
    policy_path = os.path.join(repo_root, OG_ROOT, "policy.yaml")
    payload: dict[str, object] = {
        "path": f"{OG_ROOT}/policy.yaml",
        "present": False,
        "status": "ok",
        "message": "policy file is not explicit; built-in defaults apply",
        "checks": [],
        "policy": _default_policy(),
        "status_counts": {"error": 0, "warn": 0},
        "parsed": {},
    }
    if not os.path.exists(policy_path):
        return payload

    try:
        with open(policy_path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        payload["present"] = True
        payload["status"] = "error"
        payload["message"] = f"cannot read policy file: {exc}"
        payload["checks"] = [
            {
                "type": "policy_file_read",
                "status": "error",
                "message": payload["message"],
                "remediation": ["Fix permissions on `.outcomegraph/policy.yaml` to readable state."],
            }
        ]
        return payload

    payload["present"] = True
    parsed = _parse_yaml_style_fields(raw)
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
                "remediation": ["Add `schema_version: 2` to `.outcomegraph/policy.yaml`."],
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
                    "remediation": ["Add `schema_version: 2` to `.outcomegraph/policy.yaml`."],
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
                "remediation": ["Use YAML map syntax for `allow` in `.outcomegraph/policy.yaml`."],
            }
        )

    if deny_raw is not None and not isinstance(deny_raw, dict):
        errors += 1
        checks.append(
            {
                "type": "policy_deny",
                "status": "error",
                "message": "policy field `deny` must be an object",
                "remediation": ["Use YAML map syntax for `deny` in `.outcomegraph/policy.yaml`."],
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
        return policy, None
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

    payload: dict[str, object] = {
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "status": overall_status,
        "command": "status",
        "options": {
            "changed": options.get("changed", False),
            "profile": options.get("profile"),
            "mode": options.get("mode"),
        },
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
            },
            "message": runtime_message,
        },
    }
    if overall_status == "warn":
        payload["message"] = "status dashboard indicates warnings"
    if overall_status == "error":
        payload["message"] = "status dashboard indicates degraded sync/verification state"
    return payload


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
        _write_integrity_checkpoint(
            repo_root,
            int(payload["event_sequence"]),
            event_id,
            payload["event_hash"],  # type: ignore[arg-type]
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
    previous_hash = checkpoint.get("end_event_hash") if isinstance(checkpoint, dict) else None
    previous_hash = previous_hash if isinstance(previous_hash, str) else None

    expected_next = expected_sequence + 1
    total = 0
    for raw_sequence, _, _, event in events:
        event_sequence = raw_sequence
        if event_sequence == 0:
            continue
        if event_sequence <= expected_sequence:
            return {
                "status": "degraded",
                "state": "degraded",
                "valid": False,
                "message": f"integrity duplicate/ordered event sequence #{event_sequence}",
                "event_count": total,
            }
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


def _is_worker_unavailable_error(error: str) -> bool:
    lowered = error.lower()
    return WORKER_UNAVAILABLE_ERROR in lowered or "timed out" in lowered


def _safe_slug(value: str) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    sanitized = sanitized.strip("-")
    return sanitized or "item"


def _write_text_payload(path: str, payload: object) -> bytes:
    if isinstance(payload, str):
        rendered = payload
    else:
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    encoded = rendered.encode("utf-8")
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


def _build_worker_output_schema(role: str) -> dict[str, object]:
    if role == "distill":
        return {
            "type": "object",
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
                        "required": ["id", "status", "claims", "decision_refs", "errors", "receipts", "changed_files"],
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": ["success", "ok", "warn", "error", "pending"],
                            },
                            "claims": {"type": "array", "maxItems": 0},
                            "decision_refs": {"type": "array", "items": {"type": "string"}},
                            "errors": {"type": "array", "items": {"type": "string"}},
                            "receipts": {"type": "array", "maxItems": 0},
                            "changed_files": {"type": "array", "items": {"type": "string"}},
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "additionalProperties": True,
        }
    if role == "replay":
        return {
            "type": "object",
            "required": [
                "schema_version",
                "interface_version",
                "run_id",
                "capsule_id",
                "steps",
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
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {"type": "string", "minLength": 1},
                            "expected_exit_code": {"type": "integer"},
                            "timeout_s": {"type": "integer", "minimum": 1},
                            "cwd": {"type": "string", "minLength": 1},
                        },
                        "additionalProperties": True,
                    },
                },
                "status": {"type": "string", "minLength": 1},
                "message": {"type": "string"},
                "failures": {"type": "array", "items": {"type": "string"}},
                "parity_results": {
                    "type": ["object", "array", "string", "number", "boolean", "null"],
                },
            },
            "additionalProperties": True,
        }
    raise WorkerAdapterError(f"unsupported worker role '{role}'")


def _build_worker_prompt(role: str, payload: dict[str, object]) -> str:
    payload_json = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    if role == "distill":
        return (
            "You are the OutcomeGraph distill worker adapter.\n"
            "Do not run shell commands.\n"
            "Return exactly one JSON object and nothing else.\n"
            "Use only the input payload below.\n"
            "Rules:\n"
            "- schema_version must be 2\n"
            "- interface_version must be 1\n"
            "- run_id must exactly match input.run_id\n"
            "- Emit one capsule_updates entry per input.target_capsules[].id\n"
            "- For each update set status='success', claims=[], decision_refs=[], errors=[], receipts=[]\n"
            "- Set changed_files to input.changed_paths\n"
            "\n"
            "Input payload JSON:\n"
            f"{payload_json}\n"
        )
    if role == "replay":
        return (
            "You are the OutcomeGraph replay worker adapter.\n"
            "Do not run shell commands.\n"
            "Return exactly one JSON object and nothing else.\n"
            "Use only the input payload below.\n"
            "Rules:\n"
            "- schema_version must be 2\n"
            "- interface_version must be 1\n"
            "- run_id must exactly match input.run_id\n"
            "- capsule_id must exactly match input.capsule_id\n"
            "- Return steps=[]\n"
            "- Return status='ok', message='replay plan generated', failures=[], parity_results=null\n"
            "\n"
            "Input payload JSON:\n"
            f"{payload_json}\n"
        )
    raise WorkerAdapterError(f"unsupported worker role '{role}'")


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
    return [
        [
            *normalized,
            "exec",
            "--json",
            "--output-schema",
            schema_path,
            "--output-last-message",
            last_message_path,
            "-",
        ],
        [*normalized, "exec", "--json", "-"],
        [*normalized, "exec", "-"],
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

    worker_prompt = _build_worker_prompt(role, payload)
    worker_schema = _build_worker_output_schema(role)
    last_error = "codex executable was not found"
    output = ""
    error_output = ""
    parsed: dict[str, object] | None = None
    selected_command: list[str] = []
    duration_ms = 0

    with tempfile.TemporaryDirectory(prefix="og-worker-") as temp_dir:
        schema_path = os.path.join(temp_dir, f"{role}-schema.json")
        last_message_path = os.path.join(temp_dir, f"{role}-last-message.json")
        _write_text_payload(schema_path, json.dumps(worker_schema, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
        command_variants = _build_worker_command_variants(
            str(entrypoint),
            schema_path,
            last_message_path,
        )

        for command in command_variants:
            if os.path.exists(last_message_path):
                try:
                    os.remove(last_message_path)
                except OSError:
                    pass
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    command,
                    input=worker_prompt,
                    text=True,
                    capture_output=True,
                    cwd=repo_root,
                    timeout=timeout_seconds,
                )
            except FileNotFoundError:
                last_error = "codex executable was not found"
                continue
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
                continue

            candidate_output = output
            if os.path.exists(last_message_path):
                try:
                    with open(last_message_path, "r", encoding="utf-8") as handle:
                        last_message = handle.read()
                except OSError:
                    last_message = ""
                if last_message.strip():
                    candidate_output = last_message

            try:
                parsed = _parse_worker_output(role, candidate_output)
            except WorkerAdapterError as exc:
                if candidate_output is not output:
                    try:
                        parsed = _parse_worker_output(role, output)
                    except WorkerAdapterError:
                        last_error = str(exc)
                        continue
                else:
                    last_error = str(exc)
                    continue

            selected_command = command
            break

    if parsed is None:
        raise WorkerAdapterError(last_error)

    trace_payload = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "status": "ok",
        "role": role,
        "adapter": manifest.get("name"),
        "input": payload,
        "command": selected_command,
        "duration_ms": duration_ms,
        "returncode": 0,
        "stdout": output,
        "stderr": error_output,
    }
    trace_text = json.dumps(trace_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    full_trace_path = os.path.join(repo_root, trace_path)
    _write_text_payload(full_trace_path, trace_text)
    trace_bytes = trace_text.encode("utf-8")
    return parsed, [
        _build_file_pointer(trace_path, trace_bytes, "application/json"),
        _store_put(repo_root, trace_bytes, "application/json"),
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


def _normalize_claim_payloads(raw: object, *, field: str) -> list[dict[str, object]]:
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
        capsule_id = _required_str(raw_claim.get("capsule_id"), f"{field}[{index}].capsule_id")
        claim_receipts = _normalize_receipt_pointers(
            raw_claim.get("receipt_pointers"),
            field=f"{field}[{index}].receipt_pointers",
            required=True,
        )
        claims.append(
            {
                "id": claim_id,
                "capsule_id": capsule_id,
                "category": str(raw_claim.get("category") or "behavior").strip() or "behavior",
                "text": str(raw_claim.get("text") or "Synthetic claim from codex adapter output.").strip(),
                "receipt_pointers": claim_receipts,
            }
        )
    return claims


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
        updates.append(
            {
                "id": _required_str(raw_update.get("id"), f"capsule_updates[{index}].id"),
                "status": str(raw_update.get("status") or "success"),
                "claims": _normalize_claim_payloads(
                    raw_update.get("claims"),
                    field=f"capsule_updates[{index}].claims",
                ),
                "decision_refs": _string_list(
                    raw_update.get("decision_refs"),
                    f"capsule_updates[{index}].decision_refs",
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


def _normalize_replay_plan(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise WorkerAdapterError("replay output must be an object")
    if raw.get("schema_version") != WORKER_SCHEMA_VERSION:
        raise WorkerAdapterError("replay output schema_version must be 2")
    if raw.get("interface_version") != WORKER_INTERFACE_VERSION:
        raise WorkerAdapterError("replay output interface_version mismatch")
    run_id = _required_str(raw.get("run_id"), "run_id")
    capsule_id = _required_str(raw.get("capsule_id"), "capsule_id")
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
        "steps": steps,
        "status": str(raw.get("status") or "ok"),
        "message": str(raw.get("message") or ""),
        "parity_results": parity_results,
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
    target_capsules: list[str],
    changed_paths: list[str],
    policy_ref: str = ".outcomegraph/policy.yaml",
) -> dict[str, object]:
    return {
        "interface_version": WORKER_INTERFACE_VERSION,
        "schema_version": WORKER_SCHEMA_VERSION,
        "adapter_profile": profile,
        "mode": mode,
        "target_capsules": [{"id": capsule} for capsule in target_capsules],
        "changed_paths": changed_paths,
        "policy_ref": policy_ref,
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
    claim_text = text or f"Synthetic claim for {capsule_id} from codex worker stage."
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
) -> dict[str, object]:
    now = _utc_timestamp()
    normalized_refs: list[str] = []
    for raw_ref in claim_refs:
        if isinstance(raw_ref, str) and raw_ref:
            normalized_refs.append(raw_ref)
    return {
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


def _canonical_export_snapshot(repo_root: str) -> dict[str, object]:
    canonical_roots = ("constitution", "capsules", "refs", "decisions", "claims", "certificates", "datasets")
    artifact_files: list[str] = []
    for root in canonical_roots:
        root_path = os.path.join(repo_root, OG_ROOT, root)
        if not os.path.isdir(root_path):
            continue
        for dirpath, _, filenames in os.walk(root_path):
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                if not filename.endswith((".yaml", ".yml", ".json")):
                    continue
                relative_path = os.path.relpath(os.path.join(dirpath, filename), repo_root).replace("\\", "/")
                artifact_files.append(relative_path)

    for filename in ("materials.lock", "policy.yaml", "config.yaml"):
        full_path = os.path.join(repo_root, OG_ROOT, filename)
        if os.path.exists(full_path):
            artifact_files.append(f"{OG_ROOT}/{filename}")

    artifact_files = sorted(set(artifact_files))

    records = [_read_artifact_record(repo_root, path) for path in artifact_files]
    by_scope: dict[str, int] = {}
    ids_by_scope: dict[str, list[str]] = {}
    for record in records:
        rel_path = record["path"]
        scope = rel_path.split("/", 2)[1] if rel_path.startswith(f"{OG_ROOT}/") else rel_path.split("/", 1)[0]
        by_scope[scope] = by_scope.get(scope, 0) + 1
        artifact_id = record.get("id")
        if isinstance(artifact_id, str) and artifact_id:
            ids_by_scope.setdefault(scope, []).append(artifact_id)
    return {
        "generated_at": _utc_timestamp(),
        "artifacts": records,
        "counts": {
            "total": len(records),
            "by_scope": by_scope,
        },
        "ids_by_scope": {scope: sorted(set(ids)) for scope, ids in ids_by_scope.items()},
    }


def _render_agents_export(snapshot: dict[str, object]) -> str:
    counts = snapshot["counts"]
    by_scope = counts["by_scope"]
    lines = [
        "# AGENTS",
        "",
        "This file is generated by OutcomeGraph export stage.",
        f"Generated at: {snapshot['generated_at']}",
        "",
        "## Command surface",
        "- og init",
        "- og sync",
        "- og verify --changed",
        "- og replay --changed",
        "- og status",
        "- og export",
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
        f"Generated at: {snapshot['generated_at']}",
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
        f"Generated at: {snapshot['generated_at']}",
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
        "generated_at": snapshot["generated_at"],
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
    return {
        "schema_version": 2,
        "command": "mcp-server",
        "options": options,
        "tools": sorted(MCP_CONTROL_TOOL_DEFS, key=lambda item: item["name"]),
        "resources": [
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
        ],
        "prompts": list(MCP_CONTROL_PROMPTS),
        "artifact_counts": {scope: artifact_counts.get(scope, 0) for scope in MCP_CONTROL_RESOURCES},
        "status": "ok",
        "generated_at": snapshot.get("generated_at"),
        "message": "MCP control surface available from canonical artifact projections.",
    }


def _run_mcp_server_stage(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    try:
        snapshot = _canonical_export_snapshot(repo_root)
        payload = _build_mcp_server_payload(snapshot, options)
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

    outputs = {
        EXPORT_PATHS["agents"]: _render_agents_export(snapshot),
        EXPORT_PATHS["outcomes"]: _render_readme_outcomes(snapshot),
        EXPORT_PATHS["skill"]: _render_skill_export(snapshot),
        EXPORT_PATHS["mcp_resources"]: _render_mcp_resource_export(snapshot),
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
mode: observe
profile: analyze
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
) -> dict:
    return {"schema_version": 2, "status": status, "created_at": created_at, "updated_at": created_at, "holder": holder}


def _build_lock_payload(created_at: str, status: str = LOCK_STATUS_UNLOCKED, holder: dict | None = None) -> str:
    return json.dumps(_build_lock_record(created_at, status, holder), indent=2, sort_keys=True) + "\n"

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
            payload = _build_lock_record(created_at, LOCK_STATUS_LOCKED, holder_payload)
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
    payload = _build_lock_record(_utc_timestamp(), LOCK_STATUS_UNLOCKED, None)
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
        f"{OG_ROOT}/constitution/default.yaml": _build_constitution_payload(created_at),
        f"{WORK_STATE_FILE}": _build_state_payload(created_at),
        f"{WORK_LOCK_FILE}": _build_lock_payload(created_at),
        f"{OG_ROOT}/policy.yaml": _build_policy_payload(created_at),
        f"{OG_ROOT}/config.yaml": _build_config_payload(created_at),
        OUTCOME_GITIGNORE: _build_outcome_gitignore_payload(),
    }

    for relative_path, content in baseline_files.items():
        full_path = os.path.join(repo_root, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
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
        f'PENDING_FILE="{os.path.join(repo_root, ".outcomegraph", "work", "pending")}"\n'
        f'WORK_FILE="{os.path.join(repo_root, ".outcomegraph", "work", "pending")}"\n'
        "mkdir -p \"$(dirname \"$WORK_FILE\")\"\n"
        f'printf \'%s\\n\' \"' + f'{{\"hook\":\"{hook_name}\",\"at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}' + '" > \"$WORK_FILE\"\\n'
        f"{original_invocation}"
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
                installed.append({"hook": hook_name, "path": target, "backup": None, "status": "already-managed"})
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


def _disable_autopilot() -> dict[str, object]:
    repo_root = _git_root()
    state_path = _autopilot_state_path(repo_root)
    state = _read_json_file(state_path)

    if not isinstance(state, dict):
        return {
            "status": "ok",
            "command": "autopilot",
            "subcommand": "disable",
            "options": {},
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

    return {
        "status": "ok",
        "command": "autopilot",
        "subcommand": "disable",
        "options": {},
        "installed_hooks": disabled_hooks,
        "state_present": True,
        "restored_core_hooks_path": hooks_path,
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


def _init_autopilot(force_hooks_path: bool) -> dict[str, object]:
    repo_root = _git_root()

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
        if force_hooks_path and not _confirm(f"core.hooksPath is already set to '{existing_path}'. Replace it with '{AUTOPILOT_MANAGED_HOOK_DIR}'?"):
            emit_error("aborted by user", "autopilot", EXIT_USAGE, False)
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
    }

    state_path = os.path.join(repo_root, AUTOPILOT_STATE_FILE)
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)

    return {
        "status": "ok",
        "command": "autopilot",
        "subcommand": "init",
        "options": {"force_hooks_path": force_hooks_path},
        "state": state,
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


def _daemon_build_script(repo_root: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "\n"
        f'REPO_ROOT="{repo_root}"\n'
        "\n"
        "cd \"$REPO_ROOT\"\n"
        'export OG_AUTOPILOT="1"\n'
        "if command -v og >/dev/null 2>&1; then\n"
        "  exec og daemon run \"$@\"\n"
        "fi\n"
        f'exec uvx --from "{DAEMON_UVX_SOURCE}" og daemon run "$@"\n'
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
        }
    )
    _daemon_write_state(repo_root, state)
    return {
        "status": "ok",
        "command": "daemon",
        "subcommand": "install",
        "options": {},
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
    runtime = {
        "installed": installed,
        "running": running,
        "pid": state.get("pid"),
        "script_path": _daemon_script_path(repo_root),
        "log_path": _daemon_log_path(repo_root),
        "watch_interval_seconds": DAEMON_WATCH_INTERVAL_SECONDS,
        "state": state,
    }
    message = "daemon not installed."
    if installed and running:
        message = f"daemon running (pid={runtime['pid']})."
    elif installed:
        message = "daemon installed but not running."
    status = "ok" if installed else "warn"
    return {
        "status": status,
        "command": "daemon",
        "subcommand": "status",
        "options": {},
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
    if shutil.which("og"):
        cmd = ["og", "sync", "--json"]
    else:
        cmd = ["uvx", "--from", DAEMON_UVX_SOURCE, "og", "sync", "--json"]
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
    if not parse_error_output and raw_stdout.strip():
        parse_error_output = raw_stdout.strip()

    if process.returncode != 0:
        if isinstance(parsed, dict):
            parsed["status"] = "error"
        if not parsed:
            parsed = {
                "status": "error",
                "command": "sync",
                "message": parse_error_output or "sync subprocess failed",
            }
    elif not parsed.get("status"):
        message = parse_error_output or "sync subprocess returned malformed JSON payload"
        parsed = {
            "status": "error",
            "command": "sync",
            "message": message,
            **parsed,
        }
    parsed["runtime"] = {
        "daemon_sync_exit_code": process.returncode,
        "duration_ms": duration_ms,
    }
    _daemon_write_run_log(repo_root, parsed)
    return parsed


def _daemon_start() -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
    if not _daemon_is_installed(repo_root):
        _daemon_install()
        running, state = _daemon_running_state(repo_root)
    if running:
        state["status"] = "running"
        state["running"] = True
        _daemon_write_state(repo_root, state)
        return _daemon_status_payload(repo_root, True, state)

    script_path = _daemon_script_path(repo_root)
    log_path = _daemon_log_path(repo_root)
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

    state.update(
        {
            "status": "running",
            "running": True,
            "pid": process.pid,
            "started_at": _utc_timestamp(),
            "last_started_at": _utc_timestamp(),
            "last_restart_at": _utc_timestamp(),
        }
    )
    _daemon_write_state(repo_root, state)
    return {
        "status": "ok",
        "command": "daemon",
        "subcommand": "start",
        "options": {},
        "runtime": {
            "installed": True,
            "running": True,
            "pid": process.pid,
            "script_path": script_path,
            "log_path": log_path,
        },
        "message": "daemon started.",
    }


def _daemon_stop() -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
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
        }
    )
    state.pop("pid", None)
    _daemon_write_state(repo_root, state)

    return {
        "status": "ok" if stopped else "error",
        "command": "daemon",
        "subcommand": "stop",
        "options": {},
        "runtime": {
            "installed": _daemon_is_installed(repo_root),
            "running": False,
            "pid": pid,
        },
        "message": "daemon stopped." if stopped else "failed to stop daemon process.",
    }


def _daemon_status() -> dict[str, object]:
    repo_root = _git_root()
    running, state = _daemon_running_state(repo_root)
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
    return _daemon_status_payload(repo_root, running, state)


def _daemon_run() -> int:
    repo_root = _git_root()
    last_signature = ""
    running, state = _daemon_running_state(repo_root)
    state_pid = state.get("pid")
    if running and state_pid != os.getpid():
        emit_error("daemon run cannot start while daemon process is already managed", "daemon", EXIT_RUNTIME, False)

    state.update(
        {
            "status": "running",
            "running": True,
            "last_started_at": _utc_timestamp(),
            "pid": os.getpid(),
            "last_poll_at": _utc_timestamp(),
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
            }
        )
        _daemon_write_state(repo_root, state)
        last_signature = signature

        if not _DAEMON_STOP_REQUESTED:
            time.sleep(DAEMON_WATCH_INTERVAL_SECONDS)

    state["status"] = "stopped"
    state["running"] = False
    state["last_stopped_at"] = _utc_timestamp()
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
) -> tuple[dict[str, object], list[str]]:
    changed = False
    profile = None
    mode = None
    force_hooks_path = False
    force_full_sync = False
    capsule_filters: list[str] = []
    ref_filters: list[str] = []
    certificate_filters: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help"}:
            emit_command_result({"message": emit_usage() + "\nUse --help with a specific command for details."}, output_json)
            sys.exit(EXIT_SUCCESS)
        if arg == "--json":
            output_json = True
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
            i += 1
            continue
        if arg == "--capsule":
            if not allow_capsule_filter:
                emit_error(f"{command} does not accept --capsule", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --capsule", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            capsule_filters.extend([item.strip() for item in value.split(",") if item.strip()])
            i += 2
            continue
        if arg.startswith("--capsule="):
            if not allow_capsule_filter:
                emit_error(f"{command} does not accept --capsule", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            capsule_filters.extend([item.strip() for item in value.split(",") if item.strip()])
            i += 1
            continue
        if arg == "--ref":
            if not allow_ref_filter:
                emit_error(f"{command} does not accept --ref", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --ref", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            ref_filters.extend([item.strip() for item in value.split(",") if item.strip()])
            i += 2
            continue
        if arg.startswith("--ref="):
            if not allow_ref_filter:
                emit_error(f"{command} does not accept --ref", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            ref_filters.extend([item.strip() for item in value.split(",") if item.strip()])
            i += 1
            continue
        if arg == "--certificate":
            if not allow_certificate_filter:
                emit_error(f"{command} does not accept --certificate", command, EXIT_USAGE, output_json)
            if i + 1 >= len(args):
                emit_error(f"{command} requires a value for --certificate", command, EXIT_USAGE, output_json)
            value = args[i + 1]
            certificate_filters.extend([item.strip() for item in value.split(",") if item.strip()])
            i += 2
            continue
        if arg.startswith("--certificate="):
            if not allow_certificate_filter:
                emit_error(f"{command} does not accept --certificate", command, EXIT_USAGE, output_json)
            value = arg.split("=", 1)[1]
            certificate_filters.extend([item.strip() for item in value.split(",") if item.strip()])
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

    options: dict[str, object] = {
        "changed": changed,
        "profile": profile,
        "mode": mode,
        "force_hooks_path": force_hooks_path,
        "force_full_sync": force_full_sync,
        "output_json": output_json,
    }
    if capsule_filters:
        options["capsule"] = capsule_filters
    if ref_filters:
        options["ref"] = ref_filters
    if certificate_filters:
        options["certificate"] = certificate_filters
    return options, []


def _parse_optimize_prompts_flags(
    args: list[str],
    output_json: bool,
) -> dict[str, object]:
    dataset_path: str | None = None
    candidate_prompt: str | None = None
    baseline_prompt: str | None = None
    metric = "contains"
    min_improvement = OPTIMIZATION_DEFAULT_MIN_IMPROVEMENT
    approve = False
    i = 0

    while i < len(args):
        arg = args[i]
        if arg in {"-h", "--help"}:
            emit_command_result({"message": emit_usage() + "\nUse --help with a specific command for details."}, output_json)
            sys.exit(EXIT_SUCCESS)
        if arg == "--json":
            output_json = True
            i += 1
            continue
        if arg == "--dataset":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --dataset", "optimize", EXIT_USAGE, output_json)
            dataset_path = args[i + 1].strip()
            i += 2
            continue
        if arg.startswith("--dataset="):
            dataset_path = arg.split("=", 1)[1].strip()
            i += 1
            continue
        if arg == "--candidate":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --candidate", "optimize", EXIT_USAGE, output_json)
            candidate_prompt = args[i + 1].strip()
            i += 2
            continue
        if arg.startswith("--candidate="):
            candidate_prompt = arg.split("=", 1)[1].strip()
            i += 1
            continue
        if arg == "--baseline":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --baseline", "optimize", EXIT_USAGE, output_json)
            baseline_prompt = args[i + 1].strip()
            i += 2
            continue
        if arg.startswith("--baseline="):
            baseline_prompt = arg.split("=", 1)[1].strip()
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
            metric = value
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
            metric = value
            i += 1
            continue
        if arg == "--min-improvement":
            if i + 1 >= len(args):
                emit_error("optimize prompts requires a value for --min-improvement", "optimize", EXIT_USAGE, output_json)
            try:
                value = parse_float_option(args[i + 1], "min-improvement")
            except ValueError as exc:
                emit_error(f"invalid --min-improvement value: {exc}", "optimize", EXIT_USAGE, output_json)
            min_improvement = value
            i += 2
            continue
        if arg.startswith("--min-improvement="):
            try:
                value = parse_float_option(arg.split("=", 1)[1], "min-improvement")
            except ValueError as exc:
                emit_error(f"invalid --min-improvement value: {exc}", "optimize", EXIT_USAGE, output_json)
            min_improvement = value
            i += 1
            continue
        if arg == "--approve":
            approve = True
            i += 1
            continue
        if arg.startswith("--approve="):
            try:
                approve = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --approve value: {exc}", "optimize", EXIT_USAGE, output_json)
            i += 1
            continue
        emit_error(f"unknown option '{arg}' for optimize prompts", "optimize", EXIT_USAGE, output_json)

    if not dataset_path:
        emit_error("optimize prompts requires --dataset", "optimize", EXIT_USAGE, output_json)
    if not candidate_prompt:
        emit_error("optimize prompts requires --candidate", "optimize", EXIT_USAGE, output_json)
    if not baseline_prompt:
        emit_error("optimize prompts requires --baseline", "optimize", EXIT_USAGE, output_json)
    if not isinstance(min_improvement, (int, float)) or min_improvement < 0:
        emit_error("--min-improvement must be >= 0", "optimize", EXIT_USAGE, output_json)
    if min_improvement > 1:
        min_improvement = min_improvement / 100.0

    return {
        "dataset": dataset_path.strip(),
        "candidate": candidate_prompt.strip(),
        "baseline": baseline_prompt.strip(),
        "metric": metric,
        "min_improvement": min_improvement,
        "approve": bool(approve),
        "output_json": output_json,
    }


def _normalize_path_list(raw: str) -> list[str]:
    return sorted({entry.strip() for entry in raw.splitlines() if entry.strip()})


def _normalize_dataset_path(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a path string")
    path = value.strip().replace("\\", "/")
    if not path:
        raise ValueError(f"{field} must be a non-empty path")
    return _normalize_repo_relative_path(path)


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
    raw = _normalize_path_list(tracked)
    normalized: list[str] = []
    for path in raw:
        candidate = _normalize_repo_relative_path(path)
        if any(candidate.startswith(prefix) for prefix in RUNTIME_IGNORE_PREFIXES):
            continue
        normalized.append(candidate)
    return normalized


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
    if baseline.get("strategy") == "empty_tree":
        changed_files = _collect_all_non_runtime_files(repo_root)
    else:
        changed_files = _collect_changed_paths(repo_root, baseline_ref)
    if not changed_files and force_full_sync and baseline.get("strategy") != "empty_tree":
        changed_files = _collect_all_non_runtime_files(repo_root)
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

    return {"name": name.strip(), "command": command_value, "scope": scope}


def _load_capsule_oracles(repo_root: str, capsule_id: str) -> list[dict[str, object]]:
    yaml_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.yaml")
    json_path = os.path.join(repo_root, OG_ROOT, "capsules", f"{_safe_slug(capsule_id)}.json")

    for candidate in (json_path, yaml_path):
        if not os.path.isfile(candidate):
            continue
        payload = _read_json_file(candidate)
        if not isinstance(payload, dict):
            continue
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
) -> dict[str, object]:
    oracle_name = str(oracle.get("name", "unknown-oracle"))
    command = oracle.get("command")
    command_text = command.strip() if isinstance(command, str) else None
    resolved_policy = policy or _default_policy()
    if command_text:
        denied = _ensure_policy_action_allowed(
            resolved_policy,
            command="verify",
            category="verify_commands",
            target=command_text,
            mode=mode,
        )
        if denied is not None:
            return {
                **denied,
                "schema_version": 2,
                "oracle_name": oracle_name,
                "capsule_id": capsule_id,
                "run_id": run_id,
                "mode": mode,
                "status": "error",
                "checked_at": _utc_timestamp(),
                "changed_paths": changed_paths,
                "command": command_text,
                "message": denied.get("message"),
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

    if not command_text:
        result_payload["status"] = "pass"
        result_payload["observed_code"] = 0
        result_payload["message"] = "No oracle command configured; marked pass."
        payload_bytes = (json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
    else:
        try:
            executed = subprocess.run(
                command_text,
                shell=True,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            result_payload["status"] = "error"
            result_payload["observed_code"] = 124
            result_payload["error"] = "oracle command timed out"
            payload_bytes = (
                json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
        except Exception as exc:
            result_payload["status"] = "error"
            result_payload["observed_code"] = 1
            result_payload["error"] = f"oracle command failed to execute: {exc}"
            payload_bytes = (
                json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
        else:
            result_payload["observed_code"] = executed.returncode
            if executed.returncode == 0:
                result_payload["status"] = "pass"
            else:
                result_payload["status"] = "fail"
            result_payload["stdout"] = (executed.stdout or "").splitlines()[-5:]
            result_payload["stderr"] = (executed.stderr or "").splitlines()[-5:]
            result_payload["message"] = "oracle command executed."
            payload_bytes = (
                json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")

    result_payload["duration_ms"] = int((time.perf_counter() - start) * 1000)
    trace_path = f"{OG_ROOT}/traces/{_safe_slug(capsule_id)}-{_safe_slug(run_id)}-{_safe_slug(oracle_name)}-verify.json"
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


def _collect_replay_equivalence_baseline(repo_root: str, capsule_id: str) -> str | None:
    certificates = _collect_certificate_records(repo_root)
    if not certificates:
        return None

    normalized_target = _safe_slug(capsule_id)
    latest_updated_at: datetime.datetime | None = None
    baseline_hash: str | None = None

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
        candidate_hash = equivalence.get("observed_hash")
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
        baseline_hash = candidate_hash

    return baseline_hash


def _collect_replay_sandbox_paths(repo_root: str, changed_materials: list[dict[str, object]]) -> list[str]:
    material_records, _ = _read_material_lock_records(repo_root)
    paths: set[str] = set()

    selected_changed_paths = [str(item.get("path") or "") for item in changed_materials if isinstance(item, dict)]

    for raw_path in list(material_records.keys()) + selected_changed_paths:
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


def _materialize_replay_sandbox(repo_root: str, sandbox_root: str, changed_materials: list[dict[str, object]]) -> list[str]:
    os.makedirs(os.path.join(repo_root, sandbox_root), exist_ok=True)
    selected_paths = _collect_replay_sandbox_paths(repo_root, changed_materials)
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


def _run_replay_step(
    repo_root: str,
    sandbox_root: str,
    run_id: str,
    capsule_id: str,
    step_index: int,
    step: dict[str, object],
) -> dict[str, object]:
    command = str(step.get("command") or "").strip()
    expected_exit_code = step.get("expected_exit_code")
    if not isinstance(expected_exit_code, int):
        expected_exit_code = 0
    timeout_s = step.get("timeout_s")
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
    step_cwd = os.path.normpath(os.path.join(sandbox_root_abs, normalized_cwd))
    if not step_cwd.startswith(sandbox_root_abs):
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
        "resolved_cwd": os.path.relpath(step_cwd, os.path.join(repo_root, sandbox_root)).replace("\\", "/"),
    }

    if not command:
        result_payload["status"] = "fail"
        result_payload["observed_exit_code"] = 1
        result_payload["message"] = "Replay step has no command."
        result_payload["failures"] = ["Replay step has no command."]
    else:
        try:
            executed = subprocess.run(
                command,
                shell=True,
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
        except subprocess.TimeoutExpired as exc:
            result_payload["status"] = "fail"
            result_payload["observed_exit_code"] = -1
            result_payload["message"] = f"Replay step timed out after {timeout_s}s"
            result_payload["failures"] = [f"Replay step {step_index} timed out after {timeout_s}s"]
            result_payload["timeout_error"] = str(exc)
        except Exception as exc:
            result_payload["status"] = "fail"
            result_payload["observed_exit_code"] = 1
            result_payload["message"] = "Replay step failed to execute"
            result_payload["failures"] = [f"Replay step {step_index} failed: {exc}"]

    result_payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
    trace_path = f"{OG_ROOT}/traces/{_safe_slug(run_id)}-{_safe_slug(capsule_id)}-replay-step-{step_index}.json"
    trace_payload_bytes = json.dumps(result_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    full_trace_path = os.path.join(repo_root, trace_path)
    _write_text_payload(full_trace_path, trace_payload_bytes.decode("utf-8"))
    result_payload["trace"] = trace_path
    result_payload["receipt_pointers"] = [
        _build_file_pointer(trace_path, trace_payload_bytes, "application/json"),
        _store_put(repo_root, trace_payload_bytes, "application/json"),
    ]
    return result_payload


def _collect_affected_capsules(changed_files: list[str]) -> list[str]:
    if not changed_files:
        return []
    capsules = set()
    for path in changed_files:
        normalized = _normalize_repo_relative_path(path)
        if normalized.startswith(f"{OG_ROOT}/"):
            normalized = normalized[len(OG_ROOT) + 1 :]
        if normalized.startswith("capsules/"):
            capsules.add(normalized.split("/", 1)[1].split(".")[0])
        elif normalized.startswith("decisions/"):
            capsules.add(normalized.split("/", 1)[1].split(".")[0])
        elif normalized.startswith("claims/"):
            capsules.add("default")
        elif normalized.startswith("certificates/"):
            capsules.add("default")
        elif normalized.startswith("refs/"):
            capsules.add(normalized.split("/", 1)[1].split(".")[0])
        elif normalized == "materials.lock":
            capsules.add("materials")
        else:
            capsules.add("default")
    return sorted(capsules)


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
    return [item for item in raw if isinstance(item, dict)]


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
    if isinstance(existing_created_at, str):
        created_at = existing_created_at
    elif isinstance(payload.get("captured_at"), str):
        created_at = payload.get("captured_at")

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
    status: str = "active",
) -> dict[str, object]:
    now = _utc_timestamp()
    existing = existing_payload or {}
    existing_scope = _safe_string_list(existing.get("scope")) if isinstance(existing, dict) else []
    scope = existing_scope if existing_scope else []
    if not scope:
        for item in _safe_string_list(changed_files):
            normalized = _normalize_repo_relative_path(item)
            if normalized.startswith(f"{OG_ROOT}/"):
                continue
            if not normalized:
                continue
            top = normalized.split("/", 1)[0]
            if top and top not in scope:
                scope.append(top)
    if not scope:
        scope = ["."]

    existing_oracles = _safe_object_list(existing.get("oracles"))
    oracles = existing_oracles if existing_oracles else [{"name": f"{_safe_slug(capsule_id)}-verify", "command": None, "scope": []}]
    if not isinstance(existing_oracles, list) or not existing_oracles:
        oracles = [{"name": f"{_safe_slug(capsule_id)}-verify", "command": None, "scope": []}]

    merged_decision_refs = _normalize_artifact_path_refs(existing.get("decision_refs"), "decisions") if isinstance(existing, dict) else []
    merged_decision_refs.extend(_safe_string_list(decision_refs))
    merged_decision_refs = sorted({item for item in merged_decision_refs if isinstance(item, str)})
    created_at = str(existing.get("created_at") or created_at_default)
    return {
        "schema_version": 2,
        "artifact_type": "capsule",
        "id": _safe_slug(capsule_id),
        "goal": str(existing.get("goal") or f"OutcomeGraph capsule for {capsule_id}"),
        "scope": scope,
        "oracles": oracles,
        "materials_lock_ref": f"{OG_ROOT}/materials.lock",
        "decision_refs": merged_decision_refs,
        "lineage": existing.get("lineage") or {},
        "status": str(existing.get("status") or status),
        "created_at": created_at,
        "updated_at": now,
    }


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
        "statement": str(existing.get("statement") or f"Decision for {capsule_id} derived from sync outcome."),
        "rationale": str(existing.get("rationale") or "Computed from distill/apply stage evidence."),
        "claim_refs": merged_claim_refs,
        "status": str(existing.get("status") or "accepted"),
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
    distill_input = _build_distill_input(
        run_id=run_id,
        profile=profile,
        mode=mode,
        target_capsules=changed_capsules,
        changed_paths=changed_files,
        policy_ref=f"{OG_ROOT}/policy.yaml",
    )
    trace_path = f"{OG_ROOT}/traces/{_safe_slug(run_id)}-distill.json"
    try:
        output, receipts = _run_codex_worker(
            "distill",
            distill_input,
            repo_root,
            trace_path,
            adapter=worker_adapter,
        )
        delta_payload = _normalize_distill_delta(output)
        deltas = []
        for update in delta_payload["capsule_updates"]:
            raw_delta = update if isinstance(update, dict) else {}
            deltas.append(
                {
                    "capsule_id": str(raw_delta.get("id")),
                    "status": str(raw_delta.get("status") or "success"),
                    "claims": raw_delta.get("claims"),
                    "decision_refs": raw_delta.get("decision_refs"),
                    "errors": raw_delta.get("errors"),
                    "receipts": raw_delta.get("receipts") if isinstance(raw_delta.get("receipts"), list) else [],
                    "changed_files": raw_delta.get("changed_files", changed_files),
                    "adapter_receipts": receipts,
                }
            )
        adapter_name = str(worker_adapter.get("name", WORKER_ADAPTER_NAME))
        for delta in deltas:
            delta["adapter_name"] = adapter_name
    except WorkerAdapterError as exc:
        error_message = str(exc)
        if _is_worker_unavailable_error(error_message):
            _set_pending_state(repo_root, f"worker runtime unavailable during distill: {error_message}")
        return {
            "name": "distill",
            "status": "pending" if _is_worker_unavailable_error(error_message) else "error",
            "message": error_message,
            "profile": profile,
            "mode": mode,
            "affected_capsules": changed_capsules,
            "generated_deltas": [],
            "errors": [error_message],
            "adapter_name": str(worker_adapter.get("name", WORKER_ADAPTER_NAME)),
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
    }


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
            "errors": [policy_error.get("message", "policy configuration is invalid")],
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
            "mode": mode,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "applied_capsules": [],
            "applied_refs": [],
            "applied_decisions": [],
            "errors": [str(deny_payload.get("message", "policy denied write"))],
            "message": str(deny_payload.get("message", "policy denied apply action")),
        }
        return deny_payload

    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        return {
            "name": "apply",
            "status": "error",
            "message": f"Canonical artifact validation failed: {exc}",
            "mode": mode,
            "applied_changes": 0,
            "applied_claims": [],
            "applied_certificates": [],
            "errors": [f"Canonical artifact validation failed: {exc}"],
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
        return {
            "name": "apply",
            "status": "error",
            "message": "Distill result contained malformed deltas.",
            "mode": mode,
            "applied_changes": 0,
            "errors": ["Invalid generated_deltas format"],
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

    for delta in deltas:
        if not isinstance(delta, dict):
            errors.append("Invalid delta entry")
            continue
        capsule_id = _normalize_capsule_id(delta.get("capsule_id"), "default")
        if str(delta.get("status") or "success") != "success":
            delta_errors = delta.get("errors")
            if isinstance(delta_errors, list):
                errors.extend([str(item) for item in delta_errors if str(item)])
            errors.append(f"distill reported non-success for capsule {capsule_id}")
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
        claims = delta.get("claims")
        if isinstance(claims, list):
            raw_claims = claims
        else:
            raw_claims = []

        decision_ref_candidates = _normalize_artifact_path_refs(delta.get("decision_refs"), "decisions")

        try:
            claim_refs = []
            if not raw_claims:
                claim_id = f"cl-{_safe_slug(capsule_id)}-{_short_hash(f'{run_id}:{capsule_id}:fallback')}"
                generated_claims = [
                    {
                        "id": claim_id,
                        "capsule_id": capsule_id,
                        "category": "behavior",
                        "text": f"Synthetic claim for {capsule_id} from distill stage.",
                        "receipt_pointers": receipt_paths,
                    }
                ]
            else:
                generated_claims = []
                for claim in raw_claims:
                    if not isinstance(claim, dict):
                        continue
                    claim_capsule = _safe_slug(str(claim.get("capsule_id") or capsule_id))
                    if claim.get("capsule_id") and claim_capsule != capsule_id:
                        continue
                    generated_claims.append(
                        {
                            "id": str(
                                claim.get("id")
                                or f"cl-{_safe_slug(capsule_id)}-{_short_hash(f'{run_id}:{capsule_id}:{len(generated_claims)}')}"
                            ),
                            "capsule_id": claim_capsule,
                            "category": str(claim.get("category") or "behavior"),
                            "text": str(claim.get("text") or f"Synthetic claim for {capsule_id} from distill stage."),
                            "receipt_pointers": claim.get("receipt_pointers")
                            if isinstance(claim.get("receipt_pointers"), list)
                            else [],
                        }
                    )
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
            decision_refs = list(dict.fromkeys([*decision_ref_candidates, decision_ref]))
            existing_payload = _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "capsules", f"{capsule_id}.json"))
            capsule_payload = _build_capsule_payload(
                capsule_id,
                normalized_changed_files,
                decision_refs,
                existing_payload,
                _utc_timestamp(),
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
                adapter_name=str(distill_result.get("adapter_name") or WORKER_ADAPTER_NAME),
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

    baseline_capsules = normalized_discovered_capsules or ["default"]
    if "default" not in baseline_capsules:
        baseline_capsules.append("default")
    for capsule_id in sorted(set(baseline_capsules)):
        if capsule_id in processed_capsules:
            continue
        try:
            existing_payload = _read_json_file_dict(os.path.join(repo_root, OG_ROOT, "capsules", f"{capsule_id}.json"))
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
        }

    return {
        "name": "apply",
        "status": "ok",
        "message": "Applied synthetic deltas to canonical artifacts.",
        "mode": mode,
        "applied_changes": len(applied_claims),
        "applied_claims": applied_claims,
        "applied_certificates": applied_certs,
        "applied_capsules": applied_capsules,
        "applied_refs": applied_refs,
        "applied_decisions": applied_decisions,
        "applied_deltas": deltas,
    }


def _run_replay_stage(
    repo_root: str,
    snapshot: dict[str, object],
    run_id: str,
    profile: str,
    mode: str,
    changed_only: bool = True,
    policy: dict[str, object] | None = None,
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
            "message": str(sandbox_check.get("message", "policy denied sandbox operation")),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(sandbox_check.get("message", "policy denied sandbox operation"))],
            **sandbox_check,
        }

    write_check = _evaluate_policy_writes(
        policy_payload,
        command="replay",
        mode=mode,
        targets=[f"{OG_ROOT}/claims", f"{OG_ROOT}/certificates"],
    )
    if write_check is not None:
        return {
            "name": "replay",
            "status": "error",
            "message": str(write_check.get("message", "policy denied write")),
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [str(write_check.get("message", "policy denied write"))],
            **write_check,
        }

    try:
        _validate_canonical_artifact_records(repo_root)
    except ValueError as exc:
        return {
            "name": "replay",
            "status": "error",
            "message": f"Canonical artifact validation failed: {exc}",
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": [f"Canonical artifact validation failed: {exc}"],
        }

    if not isinstance(snapshot, dict):
        return {
            "name": "replay",
            "status": "error",
            "message": "Invalid snapshot payload",
            "mode": mode,
            "replay_plans": [],
            "replay_results": [],
            "certificate_ids": [],
            "certificate_refs": _preserve_certificate_refs(),
            "errors": ["Invalid snapshot payload"],
        }
    changed_files = snapshot.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = []

    changed_files = [str(item) for item in changed_files]
    targets = _collect_affected_capsules(changed_files) if changed_only else _list_known_capsules(repo_root)
    if not targets:
        targets = ["default"]

    changed_materials = _collect_changed_materials(repo_root, changed_files if changed_only else [])
    plans: list[dict[str, object]] = []
    replay_results: list[dict[str, object]] = []
    certificate_ids: list[str] = []
    certificate_refs: list[str] = []
    failed_capsules: list[str] = []
    errors: list[str] = []
    overall_failed = False

    for capsule in targets:
        trace_path = f"{OG_ROOT}/traces/{_safe_slug(capsule)}-{_safe_slug(run_id)}-replay.json"
        try:
            input_payload = _build_replay_input(
                run_id=run_id,
                profile=profile,
                mode=mode,
                capsule_id=capsule,
                changed_materials=changed_materials,
            )
            output, receipts = _run_codex_worker(
                "replay",
                input_payload,
                repo_root,
                trace_path,
                adapter=worker_adapter,
            )
            plan = _normalize_replay_plan(output)
            plan["adapter_receipts"] = receipts
            plans.append(plan)
        except WorkerAdapterError as exc:
            error_message = str(exc)
            if _is_worker_unavailable_error(error_message):
                _set_pending_state(repo_root, f"worker runtime unavailable during replay: {error_message}")
            errors.append(error_message)
            overall_failed = True
            failed_capsules.append(capsule)
            replay_results.append(
                {
                    "capsule_id": capsule,
                    "status": "pending" if _is_worker_unavailable_error(error_message) else "error",
                    "plan_status": "error",
                    "certificate_id": None,
                    "trace": trace_path,
                    "failures": [error_message],
                    "parity_results": None,
                }
            )
            continue

        step_status = str(plan.get("status") or "ok")
        lower_status = step_status.lower()
        replay_status = "success"
        replay_failures = _safe_string_list(plan.get("failures"))
        replay_steps: list[dict[str, object]] = []
        replay_receipts: list[dict[str, object]] = _safe_object_list(plan.get("adapter_receipts"))
        materialized_paths = _collect_replay_sandbox_paths(repo_root, changed_materials)
        sandbox_root = f"{OG_ROOT}/work/replay/{_safe_slug(run_id)}/{_safe_slug(capsule)}"
        replay_result: dict[str, object] = {
            "capsule_id": capsule,
            "status": replay_status,
            "plan_status": step_status,
            "certificate_id": None,
            "trace": trace_path,
            "failures": replay_failures,
            "parity_results": plan.get("parity_results"),
            "replay_steps": replay_steps,
            "equivalence": None,
            "materialized_paths": materialized_paths,
        }

        if lower_status in {"error", "failed", "fail", "warn"}:
            replay_status = "failed"
            overall_failed = True
            replay_failures.append(f"Replay plan rejected with status '{step_status}'.")

        certificate_id = f"cert-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"
        claim_id = f"cl-{_safe_slug(capsule)}-{_short_hash(f'{run_id}:{capsule}:replay')}"

        if replay_status == "success":
            missing_paths = _materialize_replay_sandbox(repo_root, sandbox_root, changed_materials)
            if missing_paths:
                replay_status = "failed"
                overall_failed = True
                replay_failures.append(
                    "Replay sandbox materialization missing required paths: " + ", ".join(missing_paths)
                )
            else:
                sandbox_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
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
                    )
                    replay_steps.append(step_result)
                    replay_result["replay_steps"] = replay_steps
                    replay_receipts.extend(_safe_object_list(step_result.get("receipt_pointers")))
                    if str(step_result.get("status") or "") != "pass":
                        replay_status = "failed"
                        overall_failed = True
                        replay_failures.extend(_safe_string_list(step_result.get("failures")))
                        break

                baseline_hash = _collect_replay_equivalence_baseline(repo_root, capsule)
                observed_hash = _compute_replay_observed_hash(replay_steps)
                equivalence = {
                    "baseline_hash": baseline_hash,
                    "observed_hash": observed_hash,
                    "oracle_digest": observed_hash,
                    "match": baseline_hash is None or baseline_hash == observed_hash,
                    "materialized_path_count": len(materialized_paths),
                    "trace_count": len(replay_steps),
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
                changed_files if changed_only else [],
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
            errors.append(f"Failed to write replay claim for {capsule}: {exc}")
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
            )
            cert_payload["replay_context"] = {
                "run_id": run_id,
                "adapter_profile": profile,
                "source_ref": "HEAD",
                "sandbox_root": sandbox_root,
                "changed_materials": changed_materials,
                "materialized_paths": materialized_paths,
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
            errors.append(f"Failed to write replay certificate for {capsule}: {exc}")
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

    return {
        "name": "replay",
        "status": "error" if overall_failed else "ok",
        "message": "Replay adapter completed with failures." if overall_failed else "Replay adapter produced executable plans.",
        "mode": mode,
        "replay_plans": plans,
        "replay_results": replay_results,
        "certificate_ids": certificate_ids,
        "certificate_refs": sorted(final_certificate_refs),
        "failed_capsules": sorted(set(failed_capsules)),
        "errors": errors,
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

    start_at = time.perf_counter()
    verify = _run_verify_stage(
        repo_root=repo_root,
        changed_capsules=changed_capsules,
        changed_paths=changed_files if changed_only else [],
        run_id=run_id,
        mode=mode,
    )
    verify_status = str(verify.get("status") or "error").lower()

    failed_capsules: list[str] = []
    for capsule, checks in verify.get("oracle_results", {}).items():
        for raw_result in checks:
            status = str(raw_result.get("status", "skipped")).lower()
            if status in {"fail", "error"}:
                failed_capsules.append(capsule)
                break

    payload = {
        "status": "ok" if verify_status in {"ok", "skipped"} else "error",
        "command": "verify",
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
    }

    payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
    payload["summary_event"] = _record_verify_summary_event(
        repo_root,
        payload,
        payload["duration_ms"],
        snapshot,
    )
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
        normalized = value.strip().lower()
        if not normalized:
            return ""
        return os.path.splitext(os.path.basename(normalized))[0]

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
            if normalize_identifier(raw_ref.get("id")) in requested_refs or normalize_identifier(raw_ref.get("path")) in requested_refs:
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
            or normalize_identifier(cert.get("path")) in requested_certificates
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
            return {
                "name": "explain",
                "status": "error",
                "message": "No explain data found for requested filters.",
                "mode": mode,
                "profile": profile,
                "run_id": run_id,
                "claims": [],
                "certificates": [],
                "decisions": [],
                "deltas": [],
                "errors": ["No explain artifacts matched the requested filters."],
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

    write_check = _ensure_policy_action_allowed(
        policy_payload,
        command="verify",
        category="file_writes",
        target=f"{OG_ROOT}/claims",
        mode=mode,
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
    errors: list[str] = []

    for capsule in changed_capsules:
        capsule_oracles = _load_capsule_oracles(repo_root, capsule)
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
                )
            )

        receipt_records: list[dict[str, object]] = []
        for check in checks:
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
            errors.append(error_message)
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
                errors.append(error_message)
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

    status = "warn" if overall_failed else "ok"
    if policy_denied:
        status = "error"
    if policy_denied and not errors and policy_denied_messages:
        errors.extend(policy_denied_messages)

    return {
        "name": "verify",
        "status": status,
        "message": (
            "Oracle-driven verify loop blocked by policy."
            if policy_denied
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
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _record_replay_summary_event(repo_root: str, payload: dict[str, object], total_ms: int, snapshot: dict[str, object]) -> str:
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
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _record_verify_summary_event(repo_root: str, payload: dict[str, object], total_ms: int, snapshot: dict[str, object]) -> str:
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
    }
    path, event_payload = _append_ledger_event(repo_root, event_payload)
    return path


def _run_sync_job(repo_root: str, options: dict[str, object]) -> dict[str, object]:
    profile = str(options.get("profile") or "analyze")
    mode = str(options.get("mode") or "observe")
    force_full_sync = bool(options.get("force_full_sync", False))
    snapshot = _collect_sync_snapshot(repo_root, profile, mode, force_full_sync=force_full_sync)
    idempotency_key = _compute_idempotency_key(snapshot, profile, mode)
    run_id = f"sync-{_utc_timestamp().replace(':', '').replace('-', '')}-{idempotency_key[:10]}"
    sync_options: dict[str, object] = {
        "changed": options.get("changed", False),
        "profile": profile,
        "mode": mode,
        "force_full_sync": force_full_sync,
    }
    policy_payload, policy_error = _resolve_policy_for_repo(repo_root)
    if policy_error:
        payload = {
            "status": "error",
            "code": POLICY_CONFIG_ERROR_CODE,
            "command": "sync",
            "subcommand": None,
            "run_id": run_id,
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

    if current_state.get("last_idempotency_key") == idempotency_key:
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
        lambda: _run_distill_stage(repo_root, snapshot, run_id, profile=profile, mode=mode),
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
        ),
    )
    steps.append(verify)

    _build_work_payload(repo_root, status="export", last_message="starting export")
    export = _time_step(
        "export",
        lambda: _run_export_stage(repo_root, mode=mode, policy=policy_payload),
    )
    steps.append(export)

    run_status = "ok"
    if any(item.get("status") == "error" for item in steps):
        run_status = "error"
    elif any(item.get("status") == "warn" for item in steps):
        run_status = "warn"
    sync_message = "sync workflow completed"
    if run_status == "warn":
        sync_message = "sync workflow completed with warnings"
    elif run_status == "error":
        sync_message = "sync workflow failed"
    payload = {
        "status": run_status,
        "command": "sync",
        "subcommand": None,
        "run_id": run_id,
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
    }
    duration_ms = int((time.perf_counter() - start_at) * 1000)
    summary_path = _record_sync_summary_event(repo_root, payload, duration_ms)
    _build_work_payload(
        repo_root,
        status="idle" if run_status == "ok" else "degraded",
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
    steps = payload.get("steps")
    if isinstance(steps, list):
        for raw_step in steps:
            if isinstance(raw_step, dict) and str(raw_step.get("code") or "") == code:
                return True
    return False


def run_command(args: list[str], output_json: bool) -> int:
    if not args:
        emit_error("missing command\n\n" + emit_usage(), None, EXIT_USAGE, output_json)

    command = args[0]
    rest = args[1:]
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
        options, _ = parse_command_flags(rest, "init", False, False, False, output_json)
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
        )
        repo_root = _git_root()
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
                    "code": "INTEGRITY_CHECK_FAILED",
                    "options": options,
                    "integrity": integrity,
                    "repair": repair,
                    "message": f"integrity check failed: {integrity.get('message', 'ledger validation error')}",
                }
                emit_command_result(payload, output_json)
                return EXIT_RUNTIME
        holder = {"pid": os.getpid(), "host": socket.gethostname(), "command": "og sync"}
        lock_acquired, lock_payload = _acquire_work_lock(repo_root, holder)
        if not lock_acquired:
            _set_pending_state(repo_root, f"lock contented by {lock_payload.get('holder', {}).get('pid') if lock_payload else 'unknown'}")
            emit_command_result(
                {
                    "status": "ok",
                    "command": "sync",
                    "options": options,
                    "lock": {"status": "contended", "holder": lock_payload.get("holder") if isinstance(lock_payload, dict) else None},
                    "pending": True,
                    "message": "sync is already running; pending work recorded.",
                },
                output_json,
            )
            return EXIT_SUCCESS
        try:
            payload = _run_sync_job(repo_root, options)
            payload["lock"] = {"status": LOCK_STATUS_LOCKED, "payload": lock_payload}
            emit_command_result(payload, output_json)
            if _payload_has_code(payload, POLICY_CONFIG_ERROR_CODE):
                return EXIT_USAGE
            return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS
        finally:
            _release_work_lock(repo_root, holder)
        return EXIT_SUCCESS

    if command == "verify":
        options, _ = parse_command_flags(rest, "verify", True, True, True, output_json)
        repo_root = _git_root()
        payload = _run_verify_job(repo_root, options)
        if not output_json:
            payload["message"] = _render_verify(payload)
        emit_command_result(payload, output_json)
        if _payload_has_code(payload, POLICY_CONFIG_ERROR_CODE):
            return EXIT_USAGE
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "replay":
        options, _ = parse_command_flags(rest, "replay", True, True, True, output_json)
        repo_root = _git_root()
        profile = str(options.get("profile") or "analyze")
        mode = str(options.get("mode") or "observe")
        snapshot = _collect_sync_snapshot(repo_root, profile, mode)
        run_id = _build_run_id("replay", _short_hash(f"{profile}:{mode}:{snapshot.get('changed_count', 0)}", 8))
        start_at = time.perf_counter()
        replay = _run_replay_stage(
            repo_root=repo_root,
            snapshot=snapshot,
            run_id=run_id,
            profile=profile,
            mode=mode,
            changed_only=bool(options.get("changed")),
        )
        payload = {
            "status": "ok" if replay.get("status") == "ok" else "error",
            "command": "replay",
            "options": options,
            "run_id": run_id,
            "steps": [replay],
            "message": replay.get("message", "replay adapter completed"),
            "replay_plans": replay.get("replay_plans", []),
            "replay_results": replay.get("replay_results", []),
            "certificate_ids": replay.get("certificate_ids", []),
            "certificate_refs": replay.get("certificate_refs", []),
            "errors": replay.get("errors", []),
        }
        payload["duration_ms"] = int((time.perf_counter() - start_at) * 1000)
        payload["summary_event"] = _record_replay_summary_event(repo_root, payload, payload["duration_ms"], snapshot)
        emit_command_result(payload, output_json)
        if _payload_has_code(payload, POLICY_CONFIG_ERROR_CODE):
            return EXIT_USAGE
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "status":
        options, _ = parse_command_flags(rest, "status", False, False, False, output_json)
        repo_root = _git_root()
        payload = _build_status_payload(repo_root, options)
        if not output_json:
            payload["message"] = _render_status(payload)
        emit_command_result(payload, output_json)
        return EXIT_SUCCESS

    if command == "export":
        options, _ = parse_command_flags(rest, "export", False, False, False, output_json)
        repo_root = _git_root()
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
        if _payload_has_code(payload, POLICY_CONFIG_ERROR_CODE):
            return EXIT_USAGE
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "explain":
        options, _ = parse_command_flags(
            rest,
            "explain",
            False,
            True,
            True,
            output_json,
            allow_capsule_filter=True,
            allow_ref_filter=True,
            allow_certificate_filter=True,
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
        if not output_json:
            payload["message"] = _render_explain(payload)
        emit_command_result(payload, output_json)
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "drift":
        options, _ = parse_command_flags(rest, "drift", False, False, False, output_json)
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
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "mcp-server":
        options, _ = parse_command_flags(rest, "mcp-server", False, False, False, output_json)
        repo_root = _git_root()
        payload = _run_mcp_server_stage(repo_root, options)
        if not output_json and payload.get("status") == "ok":
            payload["message"] = _render_mcp_server(payload)
        emit_command_result(payload, output_json)
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "optimize":
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
        options = _parse_optimize_prompts_flags(rest[1:], output_json)
        repo_root = _git_root()
        payload = _run_optimize_prompts_stage(repo_root, options)
        if not output_json:
            payload["message"] = _render_optimize_prompts(payload) if payload.get("status") == "ok" else payload.get(
                "message", "optimize prompts execution failed"
            )
        emit_command_result(payload, output_json)
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    if command == "autopilot":
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
        )
        if sub == "init":
            state = _init_autopilot(bool(options.get("force_hooks_path", False)))
            state["message"] = "autopilot init command executed."
            emit_command_result(state, output_json)
            return EXIT_SUCCESS
        if sub == "disable":
            state = _disable_autopilot()
            emit_command_result(state, output_json)
            return EXIT_SUCCESS
        emit_command_result(build_payload("autopilot", sub, **options), output_json)
        return EXIT_SUCCESS

    if command == "daemon":
        if not rest:
            emit_error("missing daemon action\n\nAvailable: install, start, stop, status", "daemon", EXIT_USAGE, output_json)
        sub = rest[0]
        if sub not in {"install", "start", "stop", "status", "run"}:
            emit_error(
                f"unknown daemon action '{sub}'\n\nAvailable: install, start, stop, status",
                "daemon",
                EXIT_USAGE,
                output_json,
            )
        if sub == "run":
            parse_command_flags(rest[1:], "daemon run", False, False, False, output_json)
            return _daemon_run()
        if sub == "install":
            options, _ = parse_command_flags(rest[1:], "daemon install", False, False, False, output_json)
            payload = _daemon_install()
            payload["options"] = options
            emit_command_result(payload, output_json)
            return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS
        if sub == "start":
            options, _ = parse_command_flags(rest[1:], "daemon start", False, False, False, output_json)
            payload = _daemon_start()
            payload["options"] = options
            emit_command_result(payload, output_json)
            return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS
        if sub == "stop":
            options, _ = parse_command_flags(rest[1:], "daemon stop", False, False, False, output_json)
            payload = _daemon_stop()
            payload["options"] = options
            emit_command_result(payload, output_json)
            return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS
        options, _ = parse_command_flags(rest[1:], "daemon status", False, False, False, output_json)
        payload = _daemon_status()
        payload["options"] = options
        emit_command_result(payload, output_json)
        return EXIT_RUNTIME if str(payload.get("status") or "").lower() == "error" else EXIT_SUCCESS

    emit_error(f"unknown command '{command}'\n\n" + emit_usage(), None, EXIT_USAGE, output_json)
    return EXIT_USAGE


def main(argv: list[str]) -> int:
    output_json = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            output_json = True
            i += 1
            continue
        if arg.startswith("--json="):
            try:
                output_json = parse_bool_option(arg.split("=", 1)[1])
            except ValueError as exc:
                emit_error(f"invalid --json value: {exc}", None, EXIT_USAGE, output_json)
            i += 1
            continue
        if arg in {"-h", "--help"}:
            print(emit_usage())
            return EXIT_SUCCESS
        if arg in {"-v", "--version"}:
            if output_json:
                emit_json({"status": "ok", "command": "version", "version": VERSION})
            else:
                print(f"og {VERSION}")
            return EXIT_SUCCESS
        if arg.startswith("-"):
            emit_error(f"unknown global option '{arg}'", None, EXIT_USAGE, output_json)
        break

    command_args = argv[i:]
    return run_command(command_args, output_json)


def og_cli() -> None:
    raise SystemExit(main(sys.argv[1:]))


def ogd_cli() -> None:
    raise SystemExit(main(["daemon", *sys.argv[1:]]))


if __name__ == "__main__":
    try:
        og_cli()
    except Exception as exc:
        emit_error(f"internal error: {exc}", None, EXIT_RUNTIME, False)
