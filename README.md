# OutcomeGraph

OutcomeGraph is a Git-native workflow layer for keeping a project’s artifact graph
canonicalized and replayable. The `og` command line interface is the stable
boundary for humans, agents, CI, and MCP clients.

## What this repository is

- Source-of-truth artifacts live under `.outcomegraph/`.
- `og sync` is the reconciliation pipeline:
  distill → apply → verify → export.
- `work`, `events`, and `objects` are written as immutable evidence for replay and audit.
- Runtime errors are surfaced with structured status payloads so callers can branch safely.

## Quick start

```bash
git init .
uv run og init
uv run og status --json
uv run og sync --json
```

Typical CI/automation loop:

```bash
uv run og status --json           # guard: if status != ok -> fail fast
uv run og sync --json             # performs deterministic reconciliation
uv run og verify --changed --json  # checks changed capsules only
```

## Core command contract

`og` supports these top-level commands:

- `init`
- `sync`
- `verify [--changed]`
- `replay [--changed]`
- `status`
- `export`
- `explain [--capsule --ref --certificate]`
- `drift`
- `mcp-server`
- `optimize prompts`
- `autopilot init|disable`
- `daemon install|start|stop|status|run`

Common flags:

- `--json` / `--json=true|false`
- `--profile {analyze|propose|apply}`
- `--mode {observe|autonomous}`
- `--changed` (for focused sync/verify/replay behavior)

If you are running from source, prefer:

```bash
uv run og <command>
```

Return contract:

- Every command emits a status object with at least `status`, `command`, and `message`.
- In non-JSON mode, `message` is a human-readable summary.
- In `--json` mode, payloads remain machine-parseable and deterministic.
- Exit codes:
  - `0` success
  - `1` runtime failure
  - `64` usage/validation failure

## Pipeline overview

### `og sync`

Runs the production reconciliation pipeline:

1. `distill`
   - Launches the worker adapter contract to produce delta-style capsule updates.
2. `apply`
   - Persists new claims/certificates into `.outcomegraph/`.
3. `verify`
   - Executes scoped oracle checks and writes verification claims/certificates.
4. `export`
   - Regenerates exported summary snapshots under `.outcomegraph/export/`.

Sync uses a work lock and idempotency key:

- if no material changes are detected, sync may short-circuit to `ok`.
- duplicate runs are prevented by lock/pending state.
- failed stages are captured as `status: error` with explicit `message` and `errors`.

### `og verify`

Validates impacted capsules and writes structured verify artifacts for drift and evidence tracing.

- `--changed`: verify only capsules impacted by current working-tree changes.
- Without `--changed`: verify known capsules (falls back to safe defaults).

### `og replay`

Builds reproducible replay plans and writes replay claims/certificates, including
execution parity records where applicable.

- `--changed`: replay only impacted capsules based on working-tree deltas.

### `og explain`

Assembles explainability material (claims, certificates, decisions, deltas) by
capsule/filter set for troubleshooting and review.

### `og drift`

Runs policy/certificate drift checks and writes a drift report artifact in the
current event stream.

### `og status`

Builds a runtime/freshness dashboard used by operators and daemons:

- work state (`pending` / `degraded` / `running` / etc.)
- lock health
- sync freshness
- verification freshness
- certificate freshness
- drift and integrity status

### `og mcp-server`

Generates a control-plane resource payload for MCP clients (`tools`, `resources`,
`prompts`, counts, and errors when available).

### `og autopilot`

- `autopilot init` wires lifecycle hooks and tracks managed hook state.
- `autopilot disable` restores core hook state and removes managed scripts.

### `og daemon`

Long-running watcher process for autonomous execution:

- `install`: writes wrapper script under `.outcomegraph/work/daemon/run-ogd.sh`
- `start`: starts the daemon process
- `stop`: stops daemon gracefully, escalates if needed
- `status`: prints managed state and current sync trigger state
- `run`: internal loop entrypoint (invoked by script)

The daemon watches file changes and pending work; when triggered it invokes
`og sync --json` as a child process and persists run results to a structured log.

## Artifact model (short reference)

Canonical artifact root:

- `.outcomegraph/constitution`
- `.outcomegraph/capsules`
- `.outcomegraph/refs`
- `.outcomegraph/decisions`
- `.outcomegraph/certificates`
- `.outcomegraph/claims`
- `.outcomegraph/datasets`
- `.outcomegraph/events`
- `.outcomegraph/objects`
- `.outcomegraph/export`
- `.outcomegraph/work`

Most artifacts are JSON with:

- `schema_version`
- `artifact_type`
- versioned command/phase context and trace pointers where available

## Integrity and determinism

- Sync and verify transitions are appended as ledger events to `.outcomegraph/events`.
- Integrity checkpoints help detect chain issues.
- `_read` operations normalize malformed or missing state where practical and emit
  explicit degraded/error state when assumptions fail.
- `run_id`, receipts, hashes, and deterministic payload ordering support replay.

## Troubleshooting

If you see unexpected status or stale diagnostics:

- re-run with `--json` and inspect:
  - `status`
  - `errors`
  - `message`
  - stage-level `steps` for `sync`
  - daemon `last_sync_status`
- check lock state with `og status --json`.
- repair ledger state intentionally via sync repair flow if integrity is degraded (the CLI emits repair artifacts when possible).

## Documentation index

- [SPEC-v2.md](./SPEC-v2.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [PLUGIN_API.md](./PLUGIN_API.md)
- [RUNBOOKS.md](./RUNBOOKS.md)
- [SECURITY_POLICY.md](./SECURITY_POLICY.md)
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md)
- [QUICKSTART.md](./QUICKSTART.md)
