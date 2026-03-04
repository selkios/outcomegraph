# Plugin API Reference (v2.1)

Status: Draft v2.1  
Date: 2026-03-04  
Source: [SPEC-v2.md](./SPEC-v2.md)

## 1) Scope

This document defines the versioned adapter contracts required by OutcomeGraph Steward for v2.1.  
All adapters are discovered at startup and validated before runtime operations begin.

## 2) Adapter discovery

Runtime loads adapter definitions from:

- built-in adapters
- `.outcomegraph/adapters/<type>/*.json`
- directories from `$OG_ADAPTER_PATH` (override)

Each definition must provide a manifest object and must pass schema and interface checks.

## 3) Manifest contract

All manifests are schema-versioned records:

- `schema_version: 2`
- `type`: `worker`, `oracle`, `sandbox`, `store`, `exporter`
- `name`: adapter key used for selection
- `implementation_version`: string
- `interface_version`: integer
- `capabilities`: string array
- `entrypoint`: adapter-specific launch string

## 4) Interface version matrix

Required versions:

- worker: `interface_version == 1`
- oracle: `interface_version == 1`
- sandbox: `interface_version == 1`
- store: `interface_version == 1`
- exporter: `interface_version == 1`

Any mismatch is hard-failed for required adapters with `ADAPTER_INTERFACE_MISMATCH`.

## 5) Required methods by adapter type

### 5.1 WorkerAdapter (`interface_version == 1`)

- `distill(input: DistillInput) -> DistillDelta`
- `replay(input: ReplayInput) -> ReplayPlan`
- `explain(input: ExplainInput) -> ClaimSet`

### 5.2 OracleAdapter

- `run(input: OracleInput) -> OracleResult`

### 5.3 SandboxAdapter

- `create(input: EnvSpec) -> SandboxRef`
- `exec(input: ExecInput) -> ExecResult`
- `destroy(input: SandboxRef) -> DestroyResult`

### 5.4 StoreAdapter

- `put(input: StorePutInput) -> StorePutResult`
- `get(input: StoreGetInput) -> StoreGetResult`
- `exists(input: StoreExistsInput) -> StoreExistsResult`

### 5.5 ExporterAdapter

- `render(input: ExportInput) -> ExportResult`

## 6) Typed payload references

The following payloads are used as input/output across the above methods:

- `DistillInput`
- `DistillDelta`
- `ReplayInput`
- `ReplayPlan`
- `ReplayResult`
- `ClaimSet`
- `OracleInput`
- `OracleResult`
- `EnvSpec`
- `SandboxRef`
- `ExecInput`
- `ExecResult`
- `DestroyResult`
- `StorePutInput`
- `StoreGetInput`
- `StoreExistsInput`
- `ExportInput`

Canonical examples are provided in [SPEC-v2.md](./SPEC-v2.md) sections 11 and 12.

## 7) Runtime registration API

Steward exposes the following registration and resolution operations:

- `register(type, name, impl, manifest)`  
  validates and stores an adapter implementation.
- `set_default(type, name)`  
  marks a default adapter for orchestration calls.
- `resolve(type, name?)`  
  returns selected adapter for calls; with no `name`, uses default.
- `list(type)`  
  returns all registered adapters for diagnostics.

## 8) Failure behavior

If manifest validation fails, startup behavior is:

- `status: error`
- `code: ADAPTER_INTERFACE_MISMATCH`
- include: `type`, `name`, `required_interface_version`, `detected_interface_version`, `remediation`
- fail startup when adapter is required
- continue in degraded mode when optional and safe to do so

Required adapters are documented in implementation defaults and include worker and store interfaces.

## 9) Built-in adapters

Implemented defaults for v2.1:

- worker: `codex` (v1)
- store: `filesystem` (v1)
- oracle: `null-impl` fallback in recovery mode where applicable
- sandbox: local worktree sandbox
- exporter: `canonical` deterministic renderer

For architecture-level integration, see [ARCHITECTURE.md](./ARCHITECTURE.md).
