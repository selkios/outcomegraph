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

## Quick start (recommended)

Run from your project repository root (no install required):

```bash
uvx --from git+https://github.com/selkios/outcomegraph og init
uvx --from git+https://github.com/selkios/outcomegraph og sync --json
uvx --from git+https://github.com/selkios/outcomegraph og status --json
```

Install once and run as `og` everywhere:

```bash
uv tool install --from git+https://github.com/selkios/outcomegraph outcomegraph
og init
og sync --json
og status --json
```

Optional: enable daemon mode with `uvx` (no install):

```bash
uvx --from git+https://github.com/selkios/outcomegraph og daemon install
uvx --from git+https://github.com/selkios/outcomegraph og daemon start
uvx --from git+https://github.com/selkios/outcomegraph og daemon status
```

Optional: enable daemon mode with installed `og`:

```bash
og daemon install
og daemon start
og daemon status
```

`og daemon install` now writes a launcher pinned to the current interpreter/module context.
Daemon runtime does not fetch remote repository `HEAD` implicitly after install.

## Development (from source)

```bash
git clone https://github.com/selkios/outcomegraph.git
cd outcomegraph
uv run og <command>
```

## Full-spec rollout and dogfood checklist

Use this repository as rollout validation:

1. `uv run og status --json` and confirm top-level `status: "ok"` and `state: "ok"`.
2. `uv run og sync --json` and confirm:
   - `status: "ok"`
   - `steps` include `distill`, `apply`, `verify`, and `export`
3. `uv run og verify --changed --json` and confirm:
   - `status: "ok"`
   - `steps` include `verify` and `export`
   - `verified_capsules` is non-empty
4. Run `uv run og drift` to confirm policy/certificate checks are healthy.

Canonical evidence artifacts captured in this repo:

- `.outcomegraph/events/sync-20260305T082953Z-8485041f63.json` (successful sync summary)
- `.outcomegraph/events/sync-20260305T092058Z-9008c47e88.json` (migration validation failure)
- `.outcomegraph/events/verify-20260305T092059Z-a1789787d4.json` (migration validation failure)

If sync or verify fails with schema checks, apply `MIGRATION_GUIDE.md` and rerun from step 1.

### Dogfood Example In This Repository

Use this repository itself as a reference project:

```bash
uv run og init
uv run og sync --json
uv run og status --json
```

Then inspect generated artifacts under `.outcomegraph/` and exported skill output under
`skills/outcome-steward/SKILL.md`.

Typical CI/automation loop:

```bash
og status --json            # guard: if status != ok -> fail fast
og sync --json              # performs deterministic reconciliation
og verify --changed --json  # checks changed capsules only and refreshes exports
og replay --changed --json  # optional stronger confirmation; also refreshes exports
og drift --json             # should stay clean after the standalone flows above
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
- `schema`
- `describe <command>`

Every top-level command supports `--help` as a stable contract surface:

- `og <command> --help` prints command-specific usage and accepted options.
- `og daemon --help` and `og daemon run --help` are valid contract entrypoints.

Machine bootstrap for agents:

```bash
og schema
og describe sync
og describe daemon status
```

Common flags:

- `--json` / `--json=true|false`
- `--output json|jsonl|human` (jsonl streams list-like fields in order)
- `--non-interactive` disable interactive prompts and require explicit confirmation flags for privileged operations
- `--fields <field>[,<field>...]` (top-level payload projection)
- `--limit <n>` / `--offset <n>` (pagination for list-like fields)
- `--strict` / `--strict=true|false`
- `--profile {analyze|propose|apply}`
- `--mode {observe|autonomous}`
- `--changed` (for focused sync/verify/replay behavior)

Command help contracts also list output modes and exit semantics:

- `default`: human-readable output
- `--json`: machine-readable output
- exit `0`: success
- exit `1`: runtime failure
- exit `64`: usage/validation failure

If you are running from source, prefer:

```bash
uv run og <command>
```

`og --version` uses the local `pyproject.toml` version in a source checkout and packaged metadata
when installed elsewhere, so release metadata and runtime version output stay aligned.

Return contract:

- Every command emits this top-level JSON envelope when `--json` is set:

```json
{
  "schema_version": 1,
  "command": "<top-level command id>",
  "status": "ok|error|warn",
  "run_id": "<operation identifier or null>",
  "data": { "...": "..." },
  "errors": [],
  "warnings": [],
  "metrics": {}
}
```

- `command` is the command identifier (`init`, `sync`, `verify`, ...).
- `status` is the command status.
- `run_id` carries command correlation ids when available (e.g. sync/replay/verify/explain).
- `data` contains command payload (canonical payload fields and step details).
- `errors` are typed records with:
  - `error_class`: stable machine class (`usage`, `policy`, `integrity`, `adapter`, `runtime`)
  - `error_code`: stable code identifier
  - `message`: human-readable summary
  - `retryable`: boolean retryability hint
  - `hint`: bounded short remediation hint
- `warnings` are strings and remain informational.
- `metrics` holds command-level timing and counters.
- `data.list_window` advertises list pagination metadata when `--fields`, `--limit`, or `--offset` are used.
- `--output jsonl` emits one envelope line plus one `event: "item"` line per streamed list entry.
- In non-JSON mode, command output remains human-readable (`message` is still shown).
- Exit codes:
  - `0` success
  - `1` runtime failure
  - `64` usage/validation failure

For long lists, stream with `--output jsonl`:

```bash
og verify --output jsonl --fields verified_capsules --limit 50 --offset 100
og explain --output jsonl --fields claims,decisions --limit 25
og mcp-server --output jsonl --fields tools,resources --limit 100
```

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

### `og optimize prompts`

`--params` submits the full request payload as JSON, either from a file path or
from stdin with `-`.

- `og optimize prompts --params payload.json`
- `cat payload.json | og optimize prompts --params -`

Either flag-based input or payload input is supported:

- `--dataset`, `--candidate`, and `--baseline` are required in strict mode even if
  defaults exist, and `--metric`, `--min-improvement`, and `--approve` are
  optional.
- Payload keys `dataset`, `candidate`, `baseline`, `metric`, `min_improvement`, and
  `approve` may replace the matching flags.
- `--params` payload values can be overridden by explicit flags.
- In `--strict` mode, unknown payload keys, missing optional defaults, and lossy
  type coercions are rejected.

### `og autopilot`

- `autopilot init` wires lifecycle hooks and tracks managed hook state.
- managed `pre-commit` runs the local quality pass and blocks the commit if it fails.
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
- [SPEC_IMPLEMENTATION_MATRIX.md](./SPEC_IMPLEMENTATION_MATRIX.md)
- [QUICKSTART.md](./QUICKSTART.md)

## Cleanup OutcomeGraph artifacts

Use `og clean` to remove OutcomeGraph state safely.

```bash
# Preview runtime cleanup only (non-destructive)
og clean --scope runtime --dry-run --json

# Preview generated canonical/export cleanup (non-destructive)
og clean --scope generated --dry-run --json

# Remove runtime artifacts
og clean --scope runtime --yes

# Remove generated artifacts
og clean --scope generated --yes

# Remove all OutcomeGraph artifacts and managed skill/symlink outputs
# (also attempts daemon stop + autopilot disable first)
og clean --scope all --yes
```

Scopes:
- `runtime`: `.outcomegraph/work`, `cache`, `events`, `objects`, `traces`
- `generated`: `.outcomegraph/capsules`, `refs`, `decisions`, `claims`, `certificates`, `export`, `materials.lock`
- `all`: `.outcomegraph`, `skills/outcome-steward`, `.agents/skills/og`, `.claude/skills/og`
