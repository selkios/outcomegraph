# Architecture - OutcomeGraph and Steward

Canonical spec: [SPEC-v2.md](./SPEC-v2.md)

This document explains how OutcomeGraph works as a Git-native artifact graph, and how Steward keeps it synchronized in the background.

## 1) System overview

OutcomeGraph is the canonical artifact model in the repo.
Steward is the sidecar runtime that continuously updates and verifies that model.
`og` is the stable CLI contract used by humans, agents, CI, and MCP clients.

```mermaid
flowchart LR
  A[Developer or Main Agent] --> B[Git working tree and commits]
  B --> C[Steward sidecar via og sync]
  C --> D[Worker Adapter - Codex v1]
  D --> E[OutcomeGraph artifacts]
  C --> F[Verification and Replay]
  F --> E
  E --> G[Exports: AGENTS.md, SKILL.md, MCP resources]
  G --> H[Next agent session starts with current truth]
```

## 2) Bounded contexts (DDD)

The system is split into clear contexts so components can evolve independently.

```mermaid
flowchart TB
  subgraph AG[ArtifactGraph]
    C1[Capsules]
    C2[Refs]
    C3[Decisions]
    C4[Certificates]
    C5[Materials Locks]
  end

  subgraph SR[StewardRuntime]
    R1[SyncRun]
    R2[Scheduler]
    R3[Budget Policy]
    R4[Pending State]
  end

  subgraph VF[Verification]
    V1[Oracle Runs]
    V2[Replay Runs]
    V3[Replay Certificates]
  end

  subgraph AD[Adapters]
    A1[WorkerAdapter]
    A2[OracleAdapter]
    A3[SandboxAdapter]
    A4[StoreAdapter]
    A5[ExporterAdapter]
  end

  subgraph EX[ExportSurface]
    E1[AGENTS export]
    E2[Skill export]
    E3[MCP resources]
  end

  SR --> AG
  SR --> VF
  SR --> AD
  AG --> EX
  VF --> AG
```

## 3) Core runtime loop (`og sync`)

All autonomous entrypoints (hooks, daemon, CI) compile to one command: `og sync`.
This keeps locking, dedupe, policy, and safety in one place.

```mermaid
flowchart TD
  S[og sync] --> L{Acquire lock}
  L -- no --> Q[Set pending=true and exit]
  L -- yes --> D{Changes detected}
  D -- no --> VS{Verify stale or scheduled}
  D -- yes --> M[Map changes to capsules]
  M --> W[Run distill via WorkerAdapter]
  W --> A[Apply structured deltas]
  A --> VS
  VS -- yes --> V[Run fast verify loop]
  VS -- no --> X[Skip verify]
  V --> E[Refresh exports]
  X --> E
  E --> R[Record sync summary event]
  R --> U[Release lock]
```

## 4) Distillation flow (Codex v1 adapter)

Codex is the first worker runtime, but it is behind the `WorkerAdapter` interface.

```mermaid
sequenceDiagram
  participant T as Trigger (hook/daemon/CI/manual)
  participant OG as og sync
  participant G as Git + mappings
  participant C as Codex distiller
  participant S as Artifact store

  T->>OG: start sync
  OG->>OG: acquire lock + idempotency check
  OG->>G: inspect diffs and affected capsules
  OG->>C: codex exec with output schema
  C-->>OG: structured deltas + claims + evidence pointers
  OG->>OG: validate schema and policy
  OG->>S: write capsule/ref/decision updates
  OG->>S: store receipts and summary events
  OG-->>T: sync result
```

## 5) Verification and replay loops

Verification is continuous, not a final ceremony.

```mermaid
flowchart LR
  A[Meaningful change] --> B[Fast loop]
  B --> C[Affected tests or contracts]
  C --> D[Oracle receipts]

  E[Commit or idle window] --> F[Replay loop]
  F --> G[Fresh worktree regeneration]
  G --> H[Behavior equivalence checks]
  H --> I[Replay certificate]

  J[Nightly or CI schedule] --> K[Resilience loop]
  K --> L[Sample older capsules]
  L --> M[Detect drift early]
```

## 6) Plugin architecture and portability

Adapters make the system future-proof across workers, oracle engines, and sandbox providers.

```mermaid
flowchart TB
  Core[Steward core orchestration]
  Core --> WA[WorkerAdapter]
  Core --> OA[OracleAdapter]
  Core --> SA[SandboxAdapter]
  Core --> STA[StoreAdapter]
  Core --> EA[ExporterAdapter]

  WA --> W1[Codex adapter v1]
  WA --> W2[Future worker adapters]

  SA --> S1[Local worktree sandbox]
  SA --> S2[Remote sandbox provider]

  STA --> ST1[Local CAS]
  STA --> ST2[Remote CAS]
```

## 7) Data boundaries (tracked vs not tracked)

The repo tracks compact replayable truth. Bulky runtime exhaust is kept out of Git by default.

```mermaid
flowchart LR
  subgraph GT[Git tracked]
    T1[constitution]
    T2[capsules]
    T3[refs]
    T4[decisions]
    T5[certificate manifests]
    T6[generated guidance exports]
  end

  subgraph NG[Not tracked by default]
    N1[raw JSONL traces]
    N2[full stdout or stderr blobs]
    N3[screenshots and temp reports]
    N4[local cache blobs]
  end

  GT --> O[Canonical replayable truth]
  NG --> P[Operational evidence in CAS]
```

## 8) Safety and degraded operation

Default mode is safe-by-default (`observe`):

- automatic writes are limited to OutcomeGraph artifacts and configured exports
- product code edits require explicit broader mode
- failures in worker runtime degrade to pending state, not workflow blockage

```mermaid
flowchart TD
  A[Autonomous job starts] --> B{Worker available}
  B -- yes --> C[Distill or verify proceeds]
  B -- no --> D[Mark pending work]
  D --> E[Keep status and exports current]
  E --> F[Retry on next sync]
  C --> G{Policy violation}
  G -- yes --> H[Abort write and report]
  G -- no --> I[Commit artifact updates]
```

## 9) Operational touchpoints

- Human path: `og init`, optional `og autopilot init`, then `og sync`.
- Agent path: use steward skill, run the same CLI contract.
- CI path: trigger `og sync`, `og verify --changed`, `og replay --changed` per policy.

This keeps one architecture across local development, automation, and multi-agent environments.
