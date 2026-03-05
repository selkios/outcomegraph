---
name: og
description: "Operate and maintain OutcomeGraph (`og`) workflows, including sync/verify/replay execution, daemon/autopilot lifecycle, artifact integrity, and troubleshooting. Trigger when a task needs stable OutcomeGraph command semantics or repo maintenance."
---

# OutcomeGraph (`og`) Skill

Use this skill when working in the OutcomeGraph repository and you need to:

- run or reason about `og` CLI flows (`sync`, `verify`, `replay`, `status`, etc.)
- manage daemon/autopilot behavior
- inspect or repair artifact/state integrity paths
- produce deterministic, machine-safe outputs for automation

## Core execution model

OutcomeGraph’s operational contract is:

1. `og sync` runs the ordered pipeline: distill → apply → verify → export.
2. Each stage emits status artifacts and run summaries under `.outcomegraph/`.
3. `status`, `verify`, and `replay` consume canonical artifacts and write traceable outputs.

## Standard command policy

- Prefer `--json` for scripts/CI.
- Treat `status: error` as non-zero exit path in automation.
- Keep status and run summaries persisted by updating:
  - `.outcomegraph/work/` state + lock files
  - `.outcomegraph/events/` ledger events
  - `.outcomegraph/claims/` / `.outcomegraph/certificates/`

## Command quick map

Use this matrix to choose the correct command set:

- `init`: bootstrap `.outcomegraph` structure.
- `sync`: run full reconcile loop.
- `verify --changed`: validate impacted capsules.
- `replay --changed`: generate replay plans and persistence artifacts.
- `status`: runtime freshness + lock/degraded diagnostics.
- `export`: refresh canonical export snapshots.
- `explain`: collect explainability payload by capsule/ref/filter.
- `drift`: calculate policy/certificate drift report.
- `mcp-server`: emit MCP control surface payload.
- `autopilot init|disable`: install/remove managed Git hooks.
- `daemon install|start|stop|status|run`: run/watch/autonomy hooks.

## Safety checks to run before concluding success

1. Verify status payloads are explicit and parseable (`status` present and valid).
2. Ensure command outputs include deterministic runtime fields (`runtime`, `status`, `message`).
3. For daemon sync paths, do not treat malformed/non-JSON `og sync --json` output as success.
4. Confirm lock/pending semantics before repeated sync runs.

## Repo-specific paths to anchor changes

- Source entrypoint: `og`
- Wrapper/importable entrypoint: `og.py`
- Daemon script/runtime state under `.outcomegraph/work/daemon/`
- Event ledger: `.outcomegraph/events/`
- Work state/lock: `.outcomegraph/work/`

## Output style requirements

- Keep edits minimal and production-safe.
- Prioritize concrete failure handling over placeholders.
- Preserve existing status conventions (`ok`, `warn`, `error`, etc.).
- Avoid speculative refactors.
