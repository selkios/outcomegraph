# OutcomeGraph

OutcomeGraph is a Git-native workflow layer for teams that use AI builders. It turns every meaningful change into a small, replayable record so the next person or agent can continue with less guesswork.

Instead of only tracking raw files, OutcomeGraph tracks:
- what changed,
- why it changed,
- how it was verified,
- and where to find the evidence.

If you work with coding agents, this is the difference between "what worked last time" and "what we can prove and recreate reliably."

## Why this is useful

As a developer:
- reduce context churn when you switch tasks or return after a break,
- get machine-readable evidence of what happened (`--json`),
- and replay risky changes in clean environments before they break CI.

As a team:
- align humans and agents on one command contract (`og`),
- keep docs/runbooks/tests/artifacts synchronized through the same pipeline as code changes,
- and surface regressions with actionable, typed errors instead of free-form logs.

As an AI explorer:
- version control where AI behavior is derived from (`prompts/workers/*` + manifest),
- compare prompt variants with evidence,
- and keep prompt-driven logic traceable by run IDs and provenance.

## In plain English: what you get after setup

- A canonical, repo-local truth plane in `.outcomegraph/` (tracked artifacts).
- A reproducible change log (`work/`, `events/`, `objects/`, `traces/`) for replay and audit.
- Structured command output and stable exit behavior for CI and bots.
- A built-in workflow to keep `.outcomegraph/export/AGENTS.md` aligned for future agent sessions.

## Install and run quickly

Run from a checked-out project root:

```bash
# one-off, no install
uvx --from git+https://github.com/selkios/outcomegraph og init
uvx --from git+https://github.com/selkios/outcomegraph og sync --json
uvx --from git+https://github.com/selkios/outcomegraph og status --json
```

Then the same flow with a local install:

```bash
uv tool install --from git+https://github.com/selkios/outcomegraph outcomegraph
og init
og sync --json
og status --json
```

From source:

```bash
git clone https://github.com/selkios/outcomegraph.git
cd outcomegraph
uv run og <command>
```

## The first useful loop (recommended)

After you make changes:

```bash
og sync --recover-stale-lock --json        # reconcile project changes into OutcomeGraph
og status --verbose --json                  # check freshness and drift in one shot
og verify --changed --json                   # run targeted validation
og replay --changed --json                   # optional stronger confidence check
```

Use this pattern:
- `--validate` or `--dry-run` before destructive changes,
- `--changed` for focused loops during local development,
- `--json` whenever you need automation-friendly output.

## What this solves (team language)

- **Less tribal knowledge**: every capsule has purpose, scope, and rationale.
- **Less "mystery fixes"**: verification/replay evidence is explicit.
- **Less drift between humans and agents**: exports are deterministic and machine-discoverable.
- **Less rollout uncertainty**: you can validate with `status -> sync -> verify -> replay -> drift`.

## Why not just keep git history?

Git tracks file snapshots. OutcomeGraph tracks:
- behavior intent,
- validation evidence,
- and machine-consumable links between decisions, claims, and certificates.

That makes handoffs and recovery much cheaper when multiple agents or frequent context switches are involved.

## Core command shape

`og` is the stable contract for both people and agents. All commands support `--help` and have explicit output modes:
- `human` (default)
- `--json` (single machine-readable envelope)
- `--output jsonl|human|json`

Top-level commands:
- `init`
- `sync`
- `verify [--changed]`
- `replay [--changed]`
- `status`
- `doctor`
- `export`
- `explain [--capsule --ref --certificate]`
- `drift`
- `clean`
- `mcp-server`
- `optimize prompts`
- `autopilot init|disable`
- `daemon install|start|stop|status|run`
- `schema`
- `describe <command>`

Machine-first usage that most teams adopt:

```bash
og schema                      # discover command signatures
og describe sync               # inspect one command in machine-readable form
og status --json               # CI gate, quick health check
og sync --json                 # standard reconciliation
og verify --changed --json      # focused validation
og drift --json                # policy/cert drift check
```

## The sync cycle, in one line

`og sync` runs: **distill → apply → verify → export**.

That means:
- distill: convert changes to structured capsule deltas,
- apply: update canonical artifacts,
- verify: attach execution evidence,
- export: refresh generated docs/agent guidance.

## Artifact map (what matters)

Tracked in git by default:
- `.outcomegraph/constitution/**`
- `.outcomegraph/config.yaml`
- `.outcomegraph/policy.yaml`
- `.outcomegraph/export/AGENTS.md`
- `.outcomegraph/.gitignore`

Ignored as runtime/generated churn by default:
- `.outcomegraph/work/`, `.outcomegraph/cache/`, `.outcomegraph/events/`, `.outcomegraph/objects/`, `.outcomegraph/traces/`
- regenerated canon: `.outcomegraph/capsules/`, `.outcomegraph/refs/`, `.outcomegraph/decisions/`, `.outcomegraph/claims/`, `.outcomegraph/certificates/`, `.outcomegraph/materials.lock`, `.outcomegraph/export/*` (except `export/AGENTS.md`)

## Added-value workflow for AI teams

1. Keep prompt assets in version control:
   - `prompts/workers/manifest.json`
   - `prompts/workers/*.txt`
2. Run `og optimize prompts ...` on a dataset to compare baselines against candidates.
3. `--approve` only when results pass your confidence bar.
4. Re-run `og sync` so the rest of the system knows the new active prompt provenance.

## CI / automation defaults (optional)

```bash
export OG_DEFAULT_OUTPUT=json
export OG_DEFAULT_PROFILE=analyze
export OG_DEFAULT_MODE=observe
export OG_CONFIG_PATH=.outcomegraph/config.yaml   # optional
export OG_POLICY_PATH=.outcomegraph/policy.yaml   # optional
export OG_CODEX_HOME="$HOME/.codex"             # optional
```

Precedence is always: CLI flags > environment > `.outcomegraph/config.yaml`.

## Troubleshooting at a glance

- Use `--json` first: inspect `status`, `session_id`, `errors`, and `data.steps`.
- For lock issues, try `og sync --recover-stale-lock --json`.
- For diagnostics, run `og doctor --json`.
- Before re-run: `og sync --validate --json`, `og verify --validate --json`, or `og replay --dry-run --json`.
- For stale daemon/autopilot state, prefer explicit session IDs where supported.

## Optional environment modes and safety defaults

`og` is safe-by-default (`observe` mode): it can update `.outcomegraph/**` and generated exports but does not edit product code unless you explicitly allow broader modes.

- `--non-interactive` disables prompts and requires explicit flags for sensitive steps.
- `--strict` enforces stricter input/output validation.

## Full Spec and deep reference

Use these files when you need exact contracts, schemas, or architecture details:

- [SPEC-v2.md](./SPEC-v2.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [QUICKSTART.md](./QUICKSTART.md)
- [PLUGIN_API.md](./PLUGIN_API.md)
- [RUNBOOKS.md](./RUNBOOKS.md)
- [SECURITY_POLICY.md](./SECURITY_POLICY.md)
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md)
- [SPEC_IMPLEMENTATION_MATRIX.md](./SPEC_IMPLEMENTATION_MATRIX.md)

## Advanced details (for operators)

### Worker prompts and capsule quality

- Prompt bodies live in `prompts/workers/`.
- `prompts/workers/manifest.json` binds role/version/path/variables.
- Worker startup fails fast if manifest, binding, or template contracts are invalid.
- Code/runtime changes are tracked as compact recreation capsules (goal/scope/claims/invariants/dependencies/unknowns/oracle evidence).
- `code` and `test` capsules require executable proof for strong `success`; advisory proof is allowed only where gaps are explicit.

### Command output contract (quick reminder)

When `--json` is used, commands emit a stable envelope (`schema_version`, `command`, `status`, `run_id`, `session_id`, `data`, `errors`, `warnings`, `metrics`).

Exit semantics:
- `0`: success
- `1`: runtime failure
- `64`: usage/validation failure

Session model (important for daemon/autopilot):
- IDs are resumable where documented,
- expired/invalid resume attempts produce typed session errors,
- `sync` lock sessions are ephemeral and scoped to the active run.

### Cleanup

Use `og clean` with `--scope` only when you want to reclaim local state:

```bash
og clean --scope runtime --dry-run --json
og clean --scope generated --dry-run --json
og clean --scope all --yes
```

Scope meanings:
- `runtime`: work/cache/events/objects/traces
- `generated`: capsules/refs/decisions/claims/certificates/export/materials.lock
- `all`: `.outcomegraph`, `skills/outcome-steward`, `.agents/skills/og`, `.claude/skills/og`
