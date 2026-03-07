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
- Keep agent-facing instructions current (`CONTEXT.md`, exported `AGENTS.md`, skill docs, MCP resources).
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

The stable contract is command-focused, with explicit parsing behavior and return semantics.

```bash
og init
og sync [--profile analyze|propose|apply] [--mode observe|autonomous]
og verify [--changed] [--profile analyze|propose|apply] [--mode observe|autonomous]
og replay [--changed] [--profile analyze|propose|apply] [--mode observe|autonomous]
og status
og doctor
og export [--validate] [--dry-run]
og explain
og drift
og mcp-server
og optimize prompts
og autopilot init
og autopilot disable
og daemon install
og daemon start
og daemon stop
og daemon status
og schema
og describe <command>

ogd install
ogd start
ogd stop
ogd status
```

Core parsing rules:

- All command and flag validation is explicit and exits with command-appropriate error codes.
- `--strict` is supported globally and can be set per-run to enforce strictness (`--strict=true` or `--strict=false`).
- `--changed` is allowed only for commands that operate on incremental scope (`verify`, `replay`, and daemon subcommands when delegated).
- `--profile` and `--mode` are validated against finite enumerations.
- Runtime defaults use this precedence order:
  - explicit CLI flags (`--json`, `--output`, `--profile`, `--mode`)
  - environment variables (`OG_DEFAULT_OUTPUT`, `OG_DEFAULT_PROFILE`, `OG_DEFAULT_MODE`, `OG_CONFIG_PATH`, `OG_POLICY_PATH`, `OG_CODEX_HOME`)
  - repo config defaults from `.outcomegraph/config.yaml`
- `.outcomegraph/config.yaml` schema version `2` may define:
  - `defaults.output: human|json|jsonl`
  - `defaults.profile: analyze|propose|apply`
  - `defaults.mode: observe|autonomous`
  - `worker.codex_home: <relative-or-absolute-path>`
  - `safety.policy_file: <relative-or-absolute-path>`
- `OG_CONFIG_FILE` and `OG_POLICY_FILE` remain accepted legacy aliases for the preferred `*_PATH` variables.
- `CODEX_HOME` remains a fallback alias for `OG_CODEX_HOME`.
- Relative `OG_CONFIG_PATH` / `OG_POLICY_PATH` values resolve from the repository root.
- `safety.policy_file` resolves relative to the config file that declares it.
- `sync`, `verify`, `replay`, and `export` accept explicit no-write recovery modes:
  - `--validate` performs contract/policy/integrity preflight without mutating artifacts.
  - `--dry-run` returns a no-write execution plan (targets, write intent, and staged work) without mutating artifacts.
- `sync`, `verify`, and `replay` accept bounded recovery controls for subprocess-heavy paths:
  - `--max-retries <n>` retries transient worker/oracle/replay-step failures up to a bounded ceiling.
  - `--timeout <seconds>` overrides subprocess timeouts for worker/oracle/replay-step execution.
- `verify`, `replay`, `explain`, and `mcp-server` support output shaping flags:
  - `--output json|jsonl|human` (human-readable default, explicit JSON envelope, or JSONL stream mode).
  - `--fields <field>[,<field>...]` for top-level payload projection.
  - `--limit <n>` and `--offset <n>` for deterministic pagination of list-like fields.
- `autopilot disable` and `daemon start|stop|status` accept `--session-id <id>` to resume or assert a known resumable session.
- Agent-provided identifiers and optimization inputs are normalized and validated: `--capsule`, `--ref`, and `--certificate` use strict identifier allowlists (`[a-z0-9._-]`, max 128 chars), while `--dataset`, `--candidate`, and `--baseline` are validated as repository-relative paths and rejected when absolute, traversal-laden, control-character-bearing, or percent-encoded.
- Unknown options or subcommands are treated as usage errors.

Machine introspection is supported:

- `og schema` emits all supported command signatures, request fields, response envelope shape, and known error codes in machine-readable form.
- `og describe <command>` emits the signature for one command, including nested command names like `daemon status`.
- The same command-signature registry drives `og --help`, `og schema`, `og describe`, and MCP `tools[]` descriptors so CLI and MCP surfaces cannot drift independently.
- `og doctor` emits structured diagnostics and remediation hints for runtime, integrity, drift, export control surfaces, and daemon state.

`og optimize prompts` accepts:

- `--dataset <path>` path to an `eval_dataset` artifact (`schema_version: 2`).
- `--candidate <path>` path to candidate prompt artifact text.
- `--baseline <path>` path to baseline prompt artifact text.
- `--params <json-file|->` payload submitter for full request body (path or stdin via `-`).
- `--metric {contains|exact}` scoring metric (`contains` default).
- `--min-improvement <number>` score delta threshold, interpreted as percentage when > 1.
- `--approve` to persist an active prompt pack.
- `--json` for machine-readable output.
- `--strict` to reject unknown payload keys, implicit defaults, and lossy coercions when payload keys are used.

Payload precedence in strict mode:

- Explicit command flags override payload keys when both are provided.
- In strict mode, optional payload fields are required if absent from command flags (`--metric`, `--min-improvement`, `--approve`).
- In non-strict mode, unknown payload fields are ignored and best-effort coercion applies where safe.

Exit codes:

- `0` success
- `1` runtime / implementation failure
- `64` usage, validation, or contract violation

Structured output:

- `--json` prints a single top-level envelope for every command and error path.
- `--output jsonl` prints envelope + item stream lines for each projected list field.
  - Envelope and stream lines are single-line JSON.
  - List fields are replaced by `"_streamed": true` payload markers and accompanied by `data.list_window` metadata.
  - Each stream line is shaped as `{"event":"item","command":...,"field":"...","index":...,"item":...}`.
- Envelope fields are:
  - `schema_version` (`1`)
  - `command`
  - `status`
  - `run_id` (optional, `null` when unavailable)
  - `session_id` (optional, `null` when unavailable)
  - `data`
  - `errors` (typed list of error objects with `error_class`, `error_code`, `message`, `retryable`, `hint`)
  - `warnings`
  - `metrics`
- `data` contains command-specific payload for backward-readable migration from the pre-envelope contract.
- `data.options.configuration` records resolved config/policy paths plus the source for `output_mode`, `profile`, and `mode`.
- `data.session` is present for lock, daemon, and autopilot lifecycles and includes `session_id`, `lifecycle`, `state`, `expires_at`, and resume metadata.
- Session lifecycle failures are mirrored into top-level `errors` even when the full session payload remains under `data`.
- Command IDs are stable across help/usage, success, and failure envelopes.

Example:

```json
{
  "schema_version": 1,
  "command": "sync",
  "status": "ok",
  "run_id": "sync-20260305T000000Z-abcdef1234",
  "session_id": "sync-20260305t000000z-abcdef1234",
  "data": {
    "status": "ok",
    "command": "sync",
    "run_id": "sync-20260305T000000Z-abcdef1234",
    "session_id": "sync-20260305t000000z-abcdef1234",
    "steps": []
  },
  "errors": [],
  "warnings": [],
  "metrics": {
    "duration_ms": 1234
  }
}
```

Migration note:

- Old command payloads that previously emitted command-specific JSON shapes now always appear under `data`.
- Clients should treat top-level fields as the stable contract and preserve `data` as the legacy payload body.

## 6) Repository layout and tracking policy

Recommended layout:

```text
CONTEXT.md
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
  claims/
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
- `claims/**`
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

All canonical ArtifactGraph payloads are schema-versioned records with `schema_version: 2`.

- Canonical locations:
  - `capsules/<id>.yaml`
  - `refs/<name>.yaml`
  - `decisions/<id>.yaml`
  - `certificates/<id>.yaml`
  - `materials.lock`
  - `claims/<id>.yaml`
- Receipt pointers are embedded objects used by claims and certificates.

Every canonical artifact must include:

- `schema_version: 2`
- `artifact_type`: one of `capsule`, `ref`, `decision`, `certificate`, `materials_lock`, `claim`, `prompt_pack`, `eval_dataset`, `optimization_eval_result`
- `id` (namespace-unique)
- `created_at` and `updated_at` (ISO-8601 UTC when applicable)

### 7.1 `capsules/<id>.yaml`

Required fields:

- `id`
- `goal`
- `scope`
- `oracles`
- `materials_lock_ref`
- `status`

Suggested schema:

```yaml
schema_version: 2
artifact_type: capsule
id: cap-frontend
kind: code
goal: "Reduce startup latency on cold boot."
scope:
  - "src/**/*.ts"
constraints:
  - "no dependency updates"
oracles:
  - name: "unit_startup"
    command: "npm test -- startup"
materials_lock_ref: ".outcomegraph/materials.lock"
decision_refs:
  - decisions/dec-001.yaml
lineage:
  parent_capsule_ids:
    - cap-legacy
status: active
created_at: "2026-03-04T10:00:00Z"
updated_at: "2026-03-04T10:00:00Z"
```

Kind policy:

- Capsules written by current distill/apply flows persist a `kind` field.
- `kind` is one of `code`, `test`, `doc`, `config`, or `runtime`.
- `code` and `test` capsules require at least one executable oracle command before `status: success` is considered strong enough to persist.
- `doc`, `config`, and `runtime` capsules may remain `success` with advisory or `command: null` oracles when that is the strongest honest evidence.

### 7.2 `refs/<name>.yaml`

Required fields:

- `id`
- `capsule_id`
- `updated_at`

```yaml
schema_version: 2
artifact_type: ref
id: main
capsule_id: cap-frontend
updated_at: "2026-03-04T10:00:00Z"
```

### 7.3 `decisions/<id>.yaml`

Required fields:

- `id`
- `capsule_id`
- `statement`
- `rationale`
- `claim_refs`
- `status`
- `evidence_refs`
- `created_at`

```yaml
schema_version: 2
artifact_type: decision
id: dec-001
capsule_id: cap-frontend
statement: "Increase startup timeout from 5s to 8s."
rationale: "Observed CI startup spikes in integration profile."
claim_refs:
  - claims/cl-001.yaml
status: accepted
evidence_refs:
  - "#/materials.lock?entry=src/main.ts"
created_at: "2026-03-04T10:00:00Z"
```

### 7.4 `materials.lock`

Required fields:

- `id`
- `captured_at`
- `entries`

Each entry requires `path` and `digest`.

```yaml
schema_version: 2
artifact_type: materials_lock
id: materials-lock
captured_at: "2026-03-04T10:00:00Z"
entries:
  - path: "src/main.ts"
    digest: "sha256:6b..."
    kind: file
    size: 1024
  - path: "package.json"
    digest: "sha256:1a..."
    kind: file
    size: 320
```

### 7.5 `certificates/<id>.yaml`

Required fields:

- `id`
- `capsule_id`
- `run_id`
- `status`
- `adapter`
- `claim_refs`
- `receipt_pointers`
- `replay_context` (if produced by replay loop)

```yaml
schema_version: 2
artifact_type: certificate
id: cert-8899
capsule_id: cap-frontend
run_id: run-001
status: success
adapter:
  name: codex
  version: "v1"
claim_refs:
  - claims/cl-001.yaml
receipt_pointers:
  - { "schema_version": 2, "type": "cas", "target": "sha256:..." }
replay_context:
  run_id: run-001
  adapter_profile: analyze
  sandbox_root: ".outcomegraph/work/replay/run-001/cap-frontend"
  source_ref: "HEAD"
  materialized_paths:
    - "src/frontend/main.ts"
  equivalence:
    baseline_hash: "sha256:..."
    observed_hash: "sha256:..."
    oracle_digest: "sha256:..."
created_at: "2026-03-04T10:00:00Z"
updated_at: "2026-03-04T10:00:00Z"
```

### 7.6 `claims/<id>.yaml`

Required fields:

- `id`
- `capsule_id`
- `text`
- `category`
- `receipt_pointers`
- `created_at`

```yaml
schema_version: 2
artifact_type: claim
id: cl-001
capsule_id: cap-frontend
text: "Startup timeout was increased to reduce CI flake risk."
category: behavior
receipt_pointers:
  - { "schema_version": 2, "type": "file", "target": ".outcomegraph/traces/claim-001.ndjson", "hash": "sha256:9c..." }
created_at: "2026-03-04T10:00:00Z"
```

### 7.7 Receipt pointer object

Receipt pointers are small records embedded in claims/certificates.

Required fields:

- `schema_version: 2`
- `type`: `file` or `cas`
- `target`

```yaml
schema_version: 2
type: file
target: ".outcomegraph/traces/run-001.ndjson"
hash: "sha256:9c..."
media_type: "application/json"
size: 17320
```

`type: file` targets git-stored or gitignored files by relative path.
`type: cas` targets content-addressed blob stores by hash.

Rule:

- Every claim must resolve to at least one receipt pointer.

### 7.8 Schema version checks and migration guardrails

- All mutation commands must validate `schema_version` before writing:
  - Missing `schema_version`
  - `schema_version < 2`
  - `schema_version > 2` not currently supported
  - Any unexpected `artifact_type` for its path
- On violation, the artifact is rejected with:
  - file path
  - detected version/type
  - short remediation: migrate to v2 and rerun.
- Legacy (`1`) artifacts are unsupported by default; no silent auto-upgrade.
- Repository-level checks are strict:
  - Mixed versions inside `.outcomegraph` are a hard error.
  - Migration must be explicit and validated by rerunning schema checks.

Detailed migration playbooks (including v1 -> v2 transitions and mixed-version remediation) are in [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md).

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
3. Resolve change baseline:

- Prefer `HEAD~1` when available.
- Else, if `ORIG_HEAD` exists, use `git merge-base ORIG_HEAD HEAD`.
- Else, fallback to empty-tree/full-sync semantics (all tracked, non-runtime paths are treated as changed).
4. Compute changed paths against the resolved baseline.
5. Filter out runtime directories from changed paths:

- `.outcomegraph/work/**`
- `.outcomegraph/cache/**`
- `.outcomegraph/events/**`
- `.outcomegraph/objects/**`

6. Map filtered paths to target capsules.
7. Build idempotency key.
8. Run `distill` (if needed).
9. Apply structured deltas.
10. Run fast verify loop (policy-driven).
11. Refresh exports.
12. Record run summary.
13. Release lock.

Edge cases:

- If `HEAD` exists but `HEAD~1` does not (initial commit), sync uses empty-tree comparison.
- If `ORIG_HEAD` exists but `merge-base` fails, sync escalates to full scope diff mode.
- If all detected paths are runtime-tracked-only (filtered out), `Changes detected` is false unless `--force-full-sync` is set.

## 9) Concurrency and trigger model

Locking:

- Exclusive lock file at `.outcomegraph/work/lock`.
- One active `sync` per repo.

Contention:

- New trigger marks `pending=true` in runtime state and exits.
- Sync contention emits `SESSION_CONTENDED` plus the active lock `session_id`.
- Next loop consumes pending state.

Session policy:

- Session ids use the lowercase shape `<kind>-<yyyymmdd>t<hhmmss>z-<hash>`.
- `sync` lock sessions are `ephemeral`.
  - emitted in command envelopes and sync summary events as `session_id`
  - never resumable
  - expire on lock release or when the lock exceeds `WORK_LOCK_STALE_SECONDS`
- `daemon` sessions are `resumable`.
  - persisted in `.outcomegraph/work/daemon/state.json`
  - `install`, `start`, `status`, and `stop` emit the same `session_id` until the session expires or is replaced
  - `--session-id <id>` asserts or resumes the known daemon session
  - expiry returns `SESSION_EXPIRED`; mismatched resume attempts return `SESSION_RESUME_INVALID`
- `autopilot` sessions are `resumable`.
  - persisted in `.outcomegraph/autopilot/state.json`
  - `autopilot init` emits the install `session_id`
  - `autopilot disable --session-id <id>` asserts the expected installed session before teardown
  - missing or mismatched resumes return `SESSION_RESUME_INVALID`

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
- Managed `pre-commit` runs the local quality pass and blocks the commit on failure.
- Other hook failures warn and defer work by default (do not block developer flow).

## 11) Plugin architecture contracts

Adapters expose one typed contract per interface family. All plugin entrypoints are registered once at startup and must pass version negotiation.

### 11.1 Versioned manifest

See [PLUGIN_API.md](./PLUGIN_API.md) for the complete manifest schema, adapter interface signatures, and typed payload reference.

Every plugin exports a `manifest` object:

```yaml
schema_version: 2
type: worker|oracle|sandbox|store|exporter
name: codex
implementation_version: "1.0.0"
interface_version: 1
capabilities:
  - "distill"
  - "replay"
  - "explain"
entrypoint: "codex://v1"
```

Core compatibility map is fixed per type:

- `worker`: `interface_version == 1`
- `oracle`: `interface_version == 1`
- `sandbox`: `interface_version == 1`
- `store`: `interface_version == 1`
- `exporter`: `interface_version == 1`

Incompatible plugin contract:

- Missing `interface_version`
- Non-integer `interface_version`
- Mismatch with required interface
- `schema_version != 2` on manifest

Failure output must include:

- `status: error`
- `code: ADAPTER_INTERFACE_MISMATCH`
- `type`
- `name`
- `required_interface_version`
- `detected_interface_version`
- `remediation` with upgrade/rebuild guidance

### 11.2 Adapter interface contracts

`WorkerAdapter`:

- `distill(input: DistillInput) -> DistillDelta`
- `replay(input: ReplayInput) -> ReplayPlan`
- `explain(input: ExplainInput) -> ClaimSet`

`OracleAdapter`:

- `run(input: OracleInput) -> OracleResult`

`SandboxAdapter`:

- `create(input: EnvSpec) -> SandboxRef`
- `exec(input: ExecInput) -> ExecResult`
- `destroy(input: SandboxRef) -> DestroyResult`

`StoreAdapter`:

- `put(input: StorePutInput) -> StorePutResult`
- `get(input: StoreGetInput) -> StoreGetResult`
- `exists(input: StoreExistsInput) -> StoreExistsResult`

`ExporterAdapter`:

- `render(input: ExportInput) -> ExportResult`

### 11.3 Typed payloads

```yaml
# DistillInput
interface_version: 1
schema_version: 2
adapter_profile: analyze|propose|apply
mode: observe|autonomous
target_capsules:
  - id: cap-frontend
    kind: code
changed_paths:
  - "src/main.ts"
policy_ref: ".outcomegraph/policy.yaml"
run_id: "run-2026-03-04T10:00:00Z"
```

```yaml
# DistillDelta
interface_version: 1
schema_version: 2
run_id: "run-001"
capsule_updates:
  - id: cap-frontend
    status: success
    claims:
      - id: cl-001
    decision_refs:
      - decisions/dec-001.yaml
    errors: []
    receipts:
      - schema_version: 2
        type: file|cas
        target: ".outcomegraph/traces/distill-001.ndjson"
        hash: "sha256:..."
```

```yaml
# ReplayPlan
interface_version: 1
schema_version: 2
run_id: "run-001"
capsule_id: cap-frontend
capsule_scope:
  - "src/frontend/**"
material_inputs:
  - path: "src/frontend/main.ts"
    digest: "sha256:..."
    kind: "file"
    size: 4821
steps:
  - command: "npm test"
    expected_exit_code: 0
    cwd: ".outcomegraph/work/replay/cap-frontend"
  - command: "pytest -q"
    expected_exit_code: 0
    timeout_s: 120
acceptance_checks:
  - name: "frontend-unit"
    oracle_name: "frontend-unit"
    command: "npm test -- frontend"
    expected_signal: "exit_code=0"
    reason: null
equivalence_inputs:
  baseline_hash: "sha256:..."
  oracle_names:
    - "frontend-unit"
  material_paths:
    - "src/frontend/main.ts"
  notes:
    - "Compare replay oracle output against the latest successful replay certificate when available."
```

```yaml
# ReplayInput
interface_version: 1
schema_version: 2
run_id: "run-001"
mode: observe|autonomous
adapter_profile: analyze|propose|apply
capsule_id: cap-frontend
source_ref: "HEAD"
materials_lock_ref: ".outcomegraph/materials.lock"
changed_materials:
  - path: "src/frontend/main.ts"
    digest: "sha256:..."
scope_materials:
  - path: "src/frontend/main.ts"
    digest: "sha256:..."
capsule:
  id: cap-frontend
  scope:
    - "src/frontend/**"
  oracles:
    - name: "frontend-unit"
      command: "npm test -- frontend"
      scope:
        - "src/frontend/**"
baseline_equivalence:
  baseline_hash: "sha256:..."
  oracle_digest: "sha256:..."
```

```yaml
# ClaimSet
interface_version: 1
schema_version: 2
claims:
  - id: cl-001
    capsule_id: cap-frontend
    category: behavior
    text: "Startup timeout increased from 5s to 8s."
    receipt_pointers:
      - schema_version: 2
        type: file
        target: ".outcomegraph/traces/claim-001.ndjson"
```

```yaml
# OracleInput
interface_version: 1
schema_version: 2
oracle:
  name: unit_startup
  command: "npm test -- startup"
scope:
  - "src/**/*.ts"
budget_ms: 120000
```

```yaml
# OracleResult
interface_version: 1
schema_version: 2
oracle_name: unit_startup
status: pass|fail|error|skipped
observed_code: 0
duration_ms: 1205
receipt_pointers:
  - schema_version: 2
    type: cas
    target: "sha256:..."
```

```yaml
# EnvSpec / SandboxRef / ExecInput / ExecResult / DestroyResult
interface_version: 1
schema_version: 2
rootfs: ".outcomegraph/work/sandboxes/cap-frontend"
network: restricted
timeout_s: 120
sandbox_id: sbx-001
status: success
exit_code: 0
stdout_ref: ".outcomegraph/traces/sandbox-stdout.ndjson"
stderr_ref: ".outcomegraph/traces/sandbox-stderr.ndjson"
```

```yaml
# Store contracts
interface_version: 1
schema_version: 2
content_hash: "sha256:..."
stored: true
blob_exists: true
bytes: 1234
```

```yaml
# Export contracts
interface_version: 1
schema_version: 2
targets:
  - "CONTEXT.md"
  - "skills/outcome-steward/SKILL.md"
files_written:
  - ".outcomegraph/export/AGENTS.md"
errors: []
```

### 11.4 Plugin loader and registration API

Core performs startup discovery from:

1. Built-in adapters (for tests and bootstrap)
2. `.outcomegraph/adapters/<type>/*.json`
3. Optional `$OG_ADAPTER_PATH` override

Registration flow:

1. instantiate adapter entrypoint
2. fetch manifest
3. validate schema and interface versions
4. register under type and name
5. set default adapter for each interface family (`worker=codex`, `store=filesystem`, etc.)
6. make all registrations available through command-time resolution API

Recommended API:

- `adapter_register(type, name, implementation, manifest)`
- `adapter_get(type, name = default)`
- `adapter_list(type)`
- `adapter_set_default(type, name)`

No successful registration occurs when compatibility checks fail.

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
- seed `CONTEXT.md` during bootstrap and update generated export control-surface files
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

### 13.1 Policy versioning and file format

Default policy file: `.outcomegraph/policy.yaml` (optional).

If no file exists, OutcomeGraph uses the built-in observe-default:

```yaml
schema_version: 2
mode: observe
policy_id: observe-default-v1
allow:
  file_writes:
    - ".outcomegraph/**"
    - "export/**"
    - "skills/outcome-steward/**"
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
    - npm install
    - pip install
    - cargo add
    - go mod tidy
  deployment:
    - push
    - git commit --amend
    - github pr create
    - gha workflow_dispatch
```

### 13.2 Safe-by-default enforcement rules

`og sync` and downstream autonomous jobs must perform this check before any non-observation action:

1. Resolve effective mode (`observe` or `autonomous`) from parsed CLI mode and environment override.
2. Load `.outcomegraph/policy.yaml` if present; otherwise use built-in defaults.
3. Merge in repository-level policy extensions (if present) and validate schema version 2.
4. Evaluate candidate actions against allow/deny lists in this order:
   - Explicit deny always wins.
   - Explicit allow in active mode enables action.
   - Missing allow entry disables action with `POLICY_DENIED`.

Observed mode supports only safe actions from section 13.1 and read-only oracle/sandbox operations.
Broader write/deploy actions require `--mode autonomous` and explicit allowlisting.

### 13.3 Policy violations and remediation output

Violations are first-class `og` errors with action and remediations:

```json
{
  "status": "error",
  "error_class": "policy",
  "error_code": "POLICY_DENIED",
  "retryable": false,
  "hint": "Review policy allowlist and rerun in an allowed mode with explicit policy configuration.",
  "command": "sync",
  "mode": "observe",
  "category": "file_writes",
  "target": "src/app/main.ts",
  "message": "Observe mode forbids application code writes without explicit allowlist.",
  "remediation": [
    "Run with --mode autonomous only for this explicit action.",
    "Add the path to allowlist.file_writes in .outcomegraph/policy.yaml."
  ]
}
```

Automated actions must exit with usage-like status `64` for policy misconfiguration and runtime-like status `1` for enforcement denials.

See [SECURITY_POLICY.md](./SECURITY_POLICY.md) for a canonical policy file example, allow/deny semantics, and remediation playbooks.

## 14) Verification and replay loops

Three loops:

Fast loop:

- Runs on meaningful change.
- Executes affected oracles only.

Replay loop (changed capsules only):

- Runs on selected commits or idle windows.
- Rebuilds changed capsules only.
- For each replay unit:
  - Creates an isolated clean sandbox/worktree at `.outcomegraph/work/replay/<run_id>/<capsule_id>/`.
  - Materializes the capsule-scoped files from `.outcomegraph/materials.lock` and scope-discovered repo files, plus runtime toolchain metadata.
  - Requires the replay plan to declare capsule scope, scoped material inputs, executable acceptance checks, and explicit equivalence inputs before execution.
  - Executes the capsule’s replay plan in the fresh environment.
  - Compares acceptance-oracle outputs against last-good evidence hash (`equivalence_hash`) for behavior equivalence.
  - Writes replay certificates only when execution and oracle behavior are stable enough to certify.
- Writes failure diagnostics when equivalence diverges, scoped regeneration inputs are missing, or a sandbox/runtime error occurs.

Resilience loop:

- Runs nightly/CI sampling older capsules.
- Detects drift across tool and model changes.

Budget controls are required:

- max sync frequency
- max replay jobs per hour
- per-repo concurrency cap
- timeout and retry policies
- CLI recovery overrides (`--max-retries`, `--timeout`) must remain bounded and surface recovery outcomes in command payloads and summary events.

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
- In `autonomous` mode, all evidence-writing commands (`sync`, `verify`, `replay`, `apply`, `export`) are hard-blocked when policy checks or integrity are degraded, returning clear remediation suggestions.

## 16) Degraded mode and failure behavior

If worker runtime is unavailable:

- Mark pending distill in runtime state.
- Continue status/export updates from existing artifacts.
- Never block normal coding workflow.

If oracle runtime fails:

- Record failed attempt and reason.
- Preserve previous valid certificates and continue to expose the last successful evidence set.
- Surface stale/unknown verification state in `og status`.

If storage/index is corrupted:

- Keep canonical artifacts immutable.
- rebuild derived index from canonical ledger.
- If integrity mode is degraded, autonomous write loops pause and require repair before further writes.

## 17) Standards triad contract

`CONTEXT.md`:

- canonical top-level startup contract for any agent.
- versioned with the CLI and schema contract.
- documents required automation patterns (`--fields`, `--dry-run`, explicit confirmation flags, and `--strict` expectations).

`.outcomegraph/export/AGENTS.md`:

- generated projection of `CONTEXT.md` plus current artifact snapshot metadata.
- consumed by agent surfaces that expect an `AGENTS.md` export.

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

Experimental schemas:

- `eval_dataset`:

```json
{
  "schema_version": 2,
  "artifact_type": "eval_dataset",
  "id": "llm-routing-bugfix",
  "name": "LLM routing bugfix dataset",
  "cases": [
    {
      "id": "q-001",
      "input": "When should I file a ticket?",
      "expected_contains": ["create a ticket", "ticketing"],
      "must_not_contain": ["panic"],
      "weight": 1.0
    }
  ]
}
```

- `optimization_eval_result`:

```json
{
  "schema_version": 2,
  "artifact_type": "optimization_eval_result",
  "id": "opt-llm-routing-bugfix-abc123",
  "dataset_id": "llm-routing-bugfix",
  "metric": "contains",
  "min_improvement": 0.02,
  "baseline_score": 0.35,
  "candidate_score": 0.52,
  "score_delta": 0.17,
  "status": "pass"
}
```

- `prompt_pack`:

```json
{
  "schema_version": 2,
  "artifact_type": "prompt_pack",
  "id": "llm-routing-bugfix-active-pack",
  "dataset_id": "llm-routing-bugfix",
  "status": "active",
  "baseline_prompt": ".outcomegraph/datasets/baseline.txt",
  "candidate_prompt": ".outcomegraph/datasets/candidate.txt",
  "result_ref": ".outcomegraph/datasets/opt-llm-routing-bugfix-abc123.json"
}
```

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

For this implementation, the published in-repo documentation set is:

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [PLUGIN_API.md](./PLUGIN_API.md)
- [RUNBOOKS.md](./RUNBOOKS.md)
- [SECURITY_POLICY.md](./SECURITY_POLICY.md)
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md)

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
