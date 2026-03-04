# SPEC-v2.md - OutcomeGraph and Steward

Status: Draft v2.1
Date: 2026-03-04
Supersedes: `SPEC.md`, `MORE-SPECS.md`, `QUICKSTART-draft.md`

## 0) Product statement

OutcomeGraph is a Git-native artifact graph for replayable software.
Steward is an always-on sidecar that keeps that graph current while work happens.

One-line freeze:

Code is a materialization. Artifacts are durable truth. Steward keeps truth in sync.

## 1) Terms and component identities

- `OutcomeGraph`: the canonical artifact model and storage layout tracked with Git.
- `Steward`: the autonomous runtime loop that observes, distills, verifies, replays, and exports.
- `og`: stable CLI contract for humans, agents, CI, and MCP callers.
- `Worker adapter`: pluggable runtime for distillation and regeneration. First implementation is Codex.

## 2) Design principles

- CLI-first: all behavior is reachable via shell commands and scriptable in CI.
- Git-native: only compact replayable truth is tracked in Git.
- DDD boundaries: each domain context has clear entities and interfaces.
- Plugin architecture: workers, oracles, sandboxes, stores, and exporters are replaceable.
- Safe autonomy: default mode never edits product code.
- Degraded operation: normal development continues when worker/runtime dependencies are down.
- Extensive docs: all contracts, schemas, and operational runbooks are versioned in-repo.

## 3) Goals and non-goals

### 3.1 Goals

- Distill code changes into compact capsules and evidence-backed claims.
- Verify behavior through oracle receipts.
- Replay changed capabilities in clean environments.
- Keep agent-facing instructions current (`AGENTS.md`, skill docs, MCP resources).
- Support future workers/oracles/sandboxes without schema breakage.

### 3.2 Non-goals

- Replacing Git as a VCS.
- Storing full agent chat transcripts as canonical truth.
- Silent background modification of product code in default mode.

## 4) DDD bounded contexts

### 4.1 `ArtifactGraph` context

Entities:

- `Capsule`
- `Ref`
- `Decision`
- `MaterialsLock`
- `Certificate`
- `Claim`
- `ReceiptPointer`

Responsibilities:

- Canonical schemas.
- Referential integrity.
- Artifact evolution and migration.

### 4.2 `StewardRuntime` context

Entities:

- `SyncRun`
- `Job`
- `SchedulerPolicy`
- `BudgetPolicy`
- `PendingState`

Responsibilities:

- Trigger intake.
- Locking and idempotency.
- Job orchestration and retries.

### 4.3 `Verification` context

Entities:

- `Oracle`
- `OracleRun`
- `ReplayRun`
- `ReplayCertificate`

Responsibilities:

- Fast verify loop.
- Replay and equivalence checks.
- Resilience sampling.

### 4.4 `Adapters` context

Entities:

- `WorkerAdapter`
- `OracleAdapter`
- `SandboxAdapter`
- `StoreAdapter`
- `ExporterAdapter`

Responsibilities:

- Stable plugin interfaces.
- Capability discovery.
- Adapter lifecycle and version compatibility.

### 4.5 `ExportSurface` context

Entities:

- `AgentsExport`
- `SkillExport`
- `McpResourceExport`

Responsibilities:

- Generate control surfaces from canonical artifacts.
- Keep generated files deterministic.

### 4.6 `Optimization` context

Entities:

- `PromptPack`
- `EvalDataset`
- `EvalResult`
- `PromotionGate`

Responsibilities:

- Optimize prompts/routing offline.
- Enforce eval-gated promotion.

## 5) CLI contract

The stable command contract is:

```bash
og init
og sync
og verify --changed
og replay --changed
og status
og export
og explain
og drift
og mcp-server
og optimize prompts
```

Autopilot management:

```bash
og autopilot init
og autopilot disable
```

Optional daemon management:

```bash
ogd install
ogd start
ogd stop
ogd status
```

Convenience wrappers may exist, but are non-normative:

- `og init --autonomous --codex` is an alias that composes `og init` + `og autopilot init`.

## 6) Repository layout and tracking policy

Recommended layout:

```text
AGENTS.md
skills/
  outcome-steward/
    SKILL.md
.codex/
  config.toml
  rules/
  agents/
.outcomegraph/
  constitution/
  capsules/
  refs/
  decisions/
  certificates/
  datasets/
  events/
  objects/
  export/
  work/
  cache/           # gitignored
  traces/          # gitignored by default
```

Git-tracked by default:

- `constitution/**`
- `capsules/**`
- `refs/**`
- `decisions/**`
- `certificates/**` (compact manifests)
- `export/AGENTS.md`
- `export/README_OUTCOMES.md`

Not Git-tracked by default:

- raw JSONL traces
- full stdout/stderr blobs
- screenshots and temporary reports
- local cache blobs

Bulky evidence is stored in CAS (local or remote). Git tracks pointers and hashes.

## 7) Canonical artifact model

All top-level docs include `schema_version: 2`.

Canonical artifacts:

- `capsule.yaml`: goal, scope, constraints, oracles, materials lock ref, lineage.
- `refs/<name>.yaml`: mutable pointer to current capsule version.
- `decisions/<id>.md|yaml`: decision records with artifact links.
- `materials.lock`: canonical material digest set.
- `certificate.yaml`: replay/verify summary with evidence pointers and hashes.

Rule:

- Every claim must resolve to a receipt pointer or a file pointer.

## 8) Steward runtime contract

Steward runs typed, short-lived jobs:

- `observe`
- `distill`
- `verify`
- `replay`
- `compact`
- `export`
- `optimize` (experimental)

All autonomous entrypoints compile to:

```bash
og sync
```

`og sync` algorithm:

1. Acquire repo lock.
2. Snapshot working tree and commit state.
3. Compute affected capsules.
4. Build idempotency key.
5. Run `distill` (if needed).
6. Apply structured deltas.
7. Run fast verify loop (policy-driven).
8. Refresh exports.
9. Record run summary.
10. Release lock.

## 9) Concurrency and trigger model

Locking:

- Exclusive lock file at `.outcomegraph/work/lock`.
- One active `sync` per repo.

Contention:

- New trigger marks `pending=true` in runtime state and exits.
- Next loop consumes pending state.

Trigger sources:

- Git hooks.
- `ogd` daemon watchers.
- CI jobs.
- Manual invocation.

Loop prevention:

- Internal runs set `OG_AUTOPILOT=1`.
- Managed hooks no-op when `OG_AUTOPILOT=1`.
- Watchers ignore `.outcomegraph/work/**`, `.outcomegraph/cache/**`, `.outcomegraph/events/**`, `.outcomegraph/objects/**`.

## 10) Hook installation and migration

`og autopilot init` must never silently clobber existing hooks.

Behavior:

- If `core.hooksPath` unset, configure `.outcomegraph/hooks`.
- If `core.hooksPath` already set, install bridge scripts into existing path by default.
- `--force-hooks-path` allows takeover with explicit consent.
- Previous hook configuration is persisted and restored by `og autopilot disable`.

Hook edge cases:

- Missing `HEAD~1`: use empty tree baseline.
- Missing `ORIG_HEAD`: fallback to merge-base or full sync.
- Hook failures warn and defer work by default (do not block developer flow).

## 11) Plugin architecture contracts

Interfaces are versioned independently.

`WorkerAdapter`:

- `distill(input) -> DistillDelta`
- `replay(input) -> ReplayPlan`
- `explain(input) -> ClaimSet`

`OracleAdapter`:

- `run(oracle, scope) -> OracleResult`

`SandboxAdapter`:

- `create(envSpec) -> SandboxRef`
- `exec(sandboxRef, command) -> ExecResult`
- `destroy(sandboxRef)`

`StoreAdapter`:

- `put(bytes) -> contentHash`
- `get(contentHash) -> bytes`
- `exists(contentHash) -> bool`

`ExporterAdapter`:

- `render(context) -> files`

Compatibility rule:

- Plugins declare `interface_version`.
- Core rejects incompatible plugins with actionable error output.

## 12) Codex adapter v1

Codex is the first `WorkerAdapter` implementation.

Execution:

- Use `codex exec` in non-interactive mode.
- Use JSONL event capture where configured.
- Use output schema validation for structured deltas.

Roles:

- `distiller`
- `verifier`
- `replayer`
- `optimizer`
- `monitor`

Profiles:

- `analyze` (default, read-only)
- `propose` (writes only in isolated worktree)
- `apply` (explicit opt-in, restricted environments)

Codex-specific configs live in `.codex/`, but canonical truth remains in `.outcomegraph/`.

## 13) Safety policy

Default autopilot mode is `observe`.

Allowed automatically:

- update `.outcomegraph/**`
- update generated `AGENTS.md` block/files per config
- update vendored skill artifacts
- read-only repo inspection
- safe configured verify commands
- create isolated worktrees/sandboxes

Prompt/forbid by default:

- modify application code
- add or update dependencies
- unrestricted network access
- deployment actions
- secrets access and secret writes
- push branches or open PRs

Policy is declarative and versioned in config.

## 14) Verification and replay loops

Three loops:

Fast loop:

- Runs on meaningful change.
- Executes affected oracles only.

Replay loop:

- Runs on selected commits or idle windows.
- Rebuilds changed capsules in fresh worktrees and validates equivalence by oracles.

Resilience loop:

- Runs nightly/CI sampling older capsules.
- Detects drift across tool and model changes.

Budget controls are required:

- max sync frequency
- max replay jobs per hour
- per-repo concurrency cap
- timeout and retry policies

## 15) Integrity and provenance

Canonical integrity:

- Content-addressed objects (`sha256`).
- Append-only event ledger.
- Event hash chaining.
- Periodic checkpoints.
- Optional signatures on checkpoints/certificates.

Provenance fields in certificates:

- adapter identity and version
- sandbox profile
- toolchain fingerprint
- oracle set and results
- artifact hashes used during run

Integrity failure places repo in `degraded` state and blocks autonomous writes until repaired.

## 16) Degraded mode and failure behavior

If worker runtime is unavailable:

- Mark pending distill in runtime state.
- Continue status/export updates from existing artifacts.
- Never block normal coding workflow.

If oracle runtime fails:

- Record failed attempt and reason.
- Preserve previous valid certificates.
- Surface stale/unknown verification state in `og status`.

If storage/index is corrupted:

- Keep canonical artifacts immutable.
- rebuild derived index from canonical ledger.

## 17) Standards triad contract

`AGENTS.md`:

- short startup contract for any agent.
- points to OutcomeGraph commands and generated guidance.

`skills/outcome-steward/SKILL.md`:

- long procedural SOP for bootstrap, sync, verify, replay, and failure handling.

`og mcp-server`:

- tools: `sync`, `verify`, `replay`, `explain`, `status`
- resources: capsules, refs, constitutions, certificates
- prompts: bootstrap, replay, repair

Rule:

- these are control surfaces and projections, not canonical data stores.

## 18) Optimization subsystem

`og optimize prompts` is experimental.

Scope:

- optimize Steward prompt packs and routing policies.
- never mutate canonical artifact schema.

Promotion gate:

- require eval dataset results against baseline.
- require manual review/approval before activation.
- no automatic production promotion.

## 19) Documentation requirements

OutcomeGraph must ship with:

- architecture overview
- domain context docs
- schema reference
- plugin API reference
- operational runbook
- failure and recovery runbook
- security policy doc
- migration guide

Docs are versioned with the CLI and schema.

## 20) Roadmap

v2.1:

- core artifact model
- Steward runtime with `og sync`
- Codex adapter v1
- safety policies and locking
- AGENTS/skill/MCP exports

v2.2:

- remote sandbox adapter for parallel verify/replay
- remote CAS adapter
- certificate signing backends

v2.3:

- additional worker adapters
- richer oracle plugins
- optimization subsystem maturation

## 21) Non-negotiable invariants

1. Canonical truth is the OutcomeGraph artifact model, not chat transcripts.
2. Autonomous writes are safe-by-default and bounded by policy.
3. `og sync` is the only autonomous entrypoint.
4. Every claim has evidence pointers.
5. Verification and replay are continuous loops, not one-off ceremonies.
6. Adapters are replaceable without changing canonical artifact semantics.

