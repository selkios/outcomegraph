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

## Worker prompt assets and capsule quality

- Worker prompt bodies live under `prompts/workers/`, and `prompts/workers/manifest.json`
  binds each supported role to a stable prompt `id`, `version`, `path`, and required
  template variables.
- Worker startup fails fast when the manifest is missing, a role/version binding drifts,
  an asset is unreadable, or a template references undeclared variables.
- Prompt assets are repo-owned implementation inputs. Keep them reviewed and versioned in
  the main codebase, not under `.outcomegraph/`.
- `.outcomegraph/` remains the canonical replayable truth. Worker runs only persist prompt
  provenance (`id`, `version`, `source_path`) into traces, stage payloads, certificates,
  and sync/verify/replay summary events so a run can be tied back to the exact prompt asset.
- When prompt behavior changes, update the asset and bump its declared version in the
  manifest/binding so provenance remains meaningful across runs.
- Strong capsules are compact recreation briefs, not file-by-file summaries. They should
  carry a bounded goal/scope plus behavior claims, invariants, dependencies, unknowns, and
  an acceptance oracle or explicit oracle-gap reason.
- `code` and `test` capsules need executable oracle evidence to stay `success`.
  `doc`, `config`, and `runtime` capsules may still be `success` with advisory or
  `command: null` oracles only when the gap is explained explicitly and the capsule remains
  materially reusable.

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

Use the bundled dogfood flow so the evidence layout stays deterministic:

```bash
bash skills/og-dogfood/scripts/run_dogfood.sh /home/agent/outcomegraph
```

Review the generated artifacts under `.outcomegraph/events/`:

1. `dogfood-status.json` should end with top-level `status: "ok"`, `data.issues: []`, and `data.runtime.status: "idle"`.
2. `dogfood-sync.json` should end with top-level `status: "ok"` and include `distill`, `apply`, `verify`, and `export`.
3. `dogfood-verify.json` should end with top-level `status: "ok"` and a non-empty `data.verified_capsules`.
4. `dogfood-replay.json` should end with top-level `status: "ok"` and a non-empty `data.replay_results`.
5. `dogfood-drift.txt` should include `drift: ok` and should not include `POLICY_DENIED`.
6. `dogfood-sync.json`, `dogfood-verify.json`, `dogfood-replay.json`, and resulting certificates should expose prompt provenance that points back to `prompts/workers/*.txt`.
7. Review `og`, `tests`, `runbooks`, `spec-v2`, and `uv` under `.outcomegraph/capsules/` for bounded scope, recreation-brief fields, and any stale-doc contradictions.
8. `code` and `test` capsules should show executable oracle commands. `doc`, `config`, and `runtime` capsules may use advisory oracle gaps only with an explicit reason.

If the bundled run fails, inspect the written `dogfood-*.json` artifacts before trying ad hoc reruns.

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
og doctor --json            # collect machine-readable diagnostics + remediation
og sync --json              # performs deterministic reconciliation
og verify --changed --json  # checks changed capsules only and refreshes exports
og replay --changed --json  # optional stronger confirmation; also refreshes exports
og drift --json             # should stay clean after the standalone flows above
```

Headless defaults for CI/agents:

```bash
export OG_DEFAULT_OUTPUT=json
export OG_DEFAULT_PROFILE=analyze
export OG_DEFAULT_MODE=observe
export OG_CONFIG_PATH=.outcomegraph/config.yaml   # optional, legacy: OG_CONFIG_FILE
export OG_POLICY_PATH=.outcomegraph/policy.yaml   # optional, legacy: OG_POLICY_FILE
export OG_CODEX_HOME="$HOME/.codex"               # optional, legacy fallback: CODEX_HOME
```

Precedence is `CLI flags > env vars > .outcomegraph/config.yaml`.
Resolved sources and config/policy paths are echoed back in command `options.configuration`.

## Agent guidance contract

`og init` seeds a root [`CONTEXT.md`](./CONTEXT.md). This is the canonical, versioned
startup contract for automation. [`.outcomegraph/export/AGENTS.md`](./.outcomegraph/export/AGENTS.md)
is the generated projection kept in sync with it during export refresh.

Machine callers should follow these rules:

- discover command shapes with `og schema` and `og describe <command>`
- narrow large payloads with `--fields`, `--limit`, `--offset`, or `--output jsonl`
- run `--validate` or `--dry-run` before mutating commands when you need a no-write preview
- require explicit `--yes` for destructive actions and treat `--strict` failures as hard contract violations

## Core command contract

`og` supports these top-level commands:

- `init`
- `sync`
- `verify [--changed]`
- `replay [--changed]`
- `status`
- `doctor`
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
- `--validate` / `--validate=true|false` (preflight mutating commands without writing)
- `--dry-run` / `--dry-run=true|false` (render no-write plans for `sync`, `verify`, `replay`, and `export`)
- `--max-retries <n>` (bounded retry budget for transient worker/oracle/replay-step failures)
- `--timeout <seconds>` (override subprocess timeouts for `sync`, `verify`, and `replay`)
- `--session-id <id>` (resume or assert a known `daemon` or `autopilot disable` session using the emitted lowercase `<kind>-<timestamp>-<hash>` id)

Environment defaults:

- `OG_DEFAULT_OUTPUT={human|json|jsonl}` sets the default output mode before command parsing.
- `OG_DEFAULT_PROFILE={analyze|propose|apply}` sets the default worker profile for commands that accept `--profile`.
- `OG_DEFAULT_MODE={observe|autonomous}` sets the default operating mode for commands that accept `--mode`.
- `OG_CONFIG_PATH=<path>` overrides the config defaults file location (YAML or JSON). `OG_CONFIG_FILE` is accepted as a legacy alias.
- `OG_POLICY_PATH=<path>` overrides the policy file location (YAML or JSON). `OG_POLICY_FILE` is accepted as a legacy alias.
- `OG_CODEX_HOME=<path>` overrides the Codex home/config directory for worker execution. `CODEX_HOME` remains a fallback alias.
- Relative config/policy paths resolve from the repository root; `safety.policy_file` inside the config file resolves relative to that config file.
- CLI flags still win: `--json`, `--output`, `--profile`, and `--mode` override env and config defaults.

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
  "session_id": "<session identifier or null>",
  "data": { "...": "..." },
  "errors": [],
  "warnings": [],
  "metrics": {}
}
```

- `command` is the command identifier (`init`, `sync`, `verify`, ...).
- `status` is the command status.
- `run_id` carries command correlation ids when available (e.g. sync/replay/verify/explain).
- `session_id` carries lifecycle ids for explicit runtime sessions (`sync` lock sessions and resumable `daemon` / `autopilot` flows).
- `data` contains command payload (canonical payload fields and step details).
- `data.session` is present when the command owns an explicit session lifecycle and includes state, expiry, and resume metadata.
- `errors` are typed records with:
  - `error_class`: stable machine class (`usage`, `session`, `policy`, `integrity`, `adapter`, `runtime`)
  - `error_code`: stable code identifier
  - `message`: human-readable summary
  - `retryable`: boolean retryability hint
  - `hint`: bounded short remediation hint
- Session resume/expiry/conflict failures are surfaced both in `data` and in the top-level `errors` list.
- `warnings` are strings and remain informational.
- `metrics` holds command-level timing/counters plus `agent_reliability` (`observation` + rolling `snapshot`).
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
- `--validate` / `--dry-run`: inspect affected capsules, oracle selection, and write targets without mutating artifacts.
- `--max-retries` / `--timeout`: bound retry and timeout behavior for oracle subprocesses.

### `og replay`

Builds reproducible replay plans and writes replay claims/certificates, including
execution parity records where applicable.

- `--changed`: replay only impacted capsules based on working-tree deltas.
- `--validate` / `--dry-run`: inspect replay targets and write intent without mutating artifacts.
- `--max-retries` / `--timeout`: bound retry and timeout behavior for worker, replay-step, and replay-oracle subprocesses.

### `og doctor`

Runs machine-readable diagnostics for runtime health, drift, integrity, daemon state,
and remediation hints. Use it before escalation or when `status`/`sync` failures need
structured operator guidance. `doctor` now includes an `agent_reliability` check and
echoes the current rolling metric snapshot under `data.agent_reliability`.

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
- rolling `agent_reliability` metrics for commands-per-successful-task, schema-valid output rate, retry auto-recovery rate, and resumable session churn

`status --json` publishes the same rolling snapshot under `data.agent_reliability`.

### `og mcp-server`

Generates a control-plane resource payload for MCP clients (`tools`, `resources`,
`prompts`, counts, and errors when available).
Each `tools[]` entry now embeds the same command signature object exposed by
`og schema` and `og describe`, so CLI help/introspection and MCP tool metadata
are generated from one registry.

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
- `autopilot init` emits a resumable `session_id` persisted in `.outcomegraph/autopilot/state.json`.
- managed `pre-commit` runs the local quality pass and blocks the commit if it fails.
- `autopilot disable` restores core hook state and removes managed scripts.
- `autopilot disable --session-id <id>` asserts the installed autopilot session before teardown.

### `og daemon`

Long-running watcher process for autonomous execution:

- `install`: writes wrapper script under `.outcomegraph/work/daemon/run-ogd.sh` and emits a resumable `session_id`
- `start`: starts the daemon process and keeps the same `session_id` unless the prior session expired
- `stop`: stops daemon gracefully, escalates if needed, and accepts `--session-id <id>`
- `status`: prints managed state, current sync trigger state, and accepts `--session-id <id>`
- `run`: internal loop entrypoint (invoked by script)

The daemon watches file changes and pending work; when triggered it invokes
`og sync --json` as a child process and persists run results to a structured log.

### Session model

- Session ids use the lowercase shape `<kind>-<yyyymmdd>t<hhmmss>z-<hash>`.
- `sync` emits an ephemeral lock `session_id`; it is never resumable and expires on release or stale-lock timeout.
- `sync` carries the active lock `session_id` in command envelopes and sync summary events.
- Lock contention returns `status: "warn"` with `error_code: "SESSION_CONTENDED"` and the active sync `session_id`.
- `autopilot` is resumable only across `autopilot init` and `autopilot disable`; `disable --session-id <id>` asserts the currently installed session before teardown.
- `daemon` is resumable across `install`, `start`, `status`, and `stop`; active daemon sessions expire when the watcher state goes stale.
- `daemon` and `autopilot` emit resumable session records with `data.session.state`, `data.session.expires_at`, and `data.session.resume_command`.
- Explicit resume/assert failures return typed session errors: `SESSION_EXPIRED` and `SESSION_RESUME_INVALID`.

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
  - `session_id`
  - `errors`
  - `message`
  - stage-level `steps` for `sync`
  - daemon `last_sync_status`
- check lock state with `og status --json`.
- run `og doctor --json` to collect consolidated diagnostics and remediation hints.
- use `og sync --validate --json`, `og verify --validate --json`, or `og replay --dry-run --json` before re-running mutating commands after a failure.
- repair ledger state intentionally via sync repair flow if integrity is degraded (the CLI emits repair artifacts when possible).
- If you receive `SESSION_CONTENDED`, wait for the active session or reuse the emitted `session_id` on resumable `daemon` / `autopilot disable` commands.

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
