# OutcomeGraph Runbooks (v2.1)

Status: Draft v2.1  
Date: 2026-03-04  
Source: [SPEC-v2.md](./SPEC-v2.md)

## 1) Operational runbook

### 1.1 New repo bootstrap

1. Run `og init`.
2. Confirm `.outcomegraph` directories and constitution are present.
3. Run `og sync`.
4. Run `og status` and verify:
   - freshness state is current,
   - lock is free,
   - no unknown verification status for tracked capsules.

### 1.2 Day-to-day human flow

1. Make code edits.
2. Run `og sync`.
3. Inspect summary output.
4. Run `og verify --changed` for uncertain surfaces.
5. Run `og explain` when traceability is needed.
6. If needed, run `og replay --changed` for stronger behavioral confirmation.

### 1.3 Autonomous flow

1. Run `og autopilot init` once.
2. Verify hooks/daemon install.
3. Use `ogd start` or keep CI-triggered hooks in place.
4. Run `og status` on cadence and on alert.

### 1.4 Safe-mode checks

- `.outcomegraph` and generated exports are writable in default flow.
- code writes, dependency mutators, or deployment actions require explicit autonomy mode and allowlist policy.

## 2) Failure runbook

### 2.1 Lock contention

Symptom: `og sync` exits without running job and reports pending state.

Recovery:

- Retry after active run finishes.
- Confirm `og status` no longer shows active sync.
- Pending work will be picked up on next run.

### 2.2 `POLICY_DENIED`

Symptom: structured error with `code: POLICY_DENIED`.

Recovery:

- Review target action against policy category.
- Add explicit allowlist entry in `.outcomegraph/policy.yaml` where safe.
- Re-run using required autonomy mode if policy requires it.

### 2.3 Autonomous writes blocked by degraded state

Symptom: command fails in `autonomous` mode with `code: AUTONOMOUS_WRITE_BLOCKED`.

Recovery:

- Inspect `og status --json` and resolve:
  - policy checks (`og status` drift/integrity entries)
  - integrity ledger health (`status.integrity`).
- Repair policy configuration or integrity index.
- Re-run the write command in `autonomous` mode after remediation.

### 2.4 Worker unavailable

Symptom: distill failures and no new claims/decisions.

Recovery:

- Check worker binary/runtime availability.
- Do not block local coding.
- Continue with `og status` and rerun sync on next loop.

### 2.5 Oracle unavailable or failing

Symptom: verification state becomes stale/unknown with failed certificates.

Recovery:

- Fix oracle command/runtime.
- Re-run `og verify --changed`.
- For persistent failures, run `og replay --changed` to confirm behavioral evidence separately.

### 2.6 Adapter/interface mismatch

Symptom: startup error with `ADAPTER_INTERFACE_MISMATCH`.

Recovery:

- Install matching adapter version matching required interface.
- Restart command entrypoint.
- Validate diagnostics with the plugin list output.

### 2.7 Storage/index corruption

Symptom: inability to read existing objects or manifests.

Recovery:

- Preserve canonical artifact files as source of truth.
- Rebuild derived index from canonical evidence path.
- Re-run `og sync` and `og status`.

## 3) Recovery runbook

### 3.1 Recover from pending/degraded state

1. Capture current status: `og status`.
2. Inspect pending marker and latest sync summary.
3. Fix underlying dependency (policy, runtime, oracle, adapter).
4. Re-run `og sync`.
5. Confirm status transitions to healthy/fresh and certificates are emitted again.

### 3.2 Re-run with narrowed scope

Use changed-scope commands to isolate regressions:

- `og verify --changed`
- `og replay --changed`
- `og sync` after baseline cleanup.

### 3.3 Escalation

If recovery remains blocked:

- collect latest event logs and status JSON output,
- include environment details (`OG_*`, mode, profile),
- capture last successful adapter and policy snapshots before escalation.

## 4) Release/readiness review workflow

Use this checklist for release candidates and handoff gates:

1. Run core freshness and validation commands:
   - `og sync --json`
   - `og status --json`
   - `og verify --changed --json`
2. Confirm conformance matrix readiness:
   - Open [`SPEC_IMPLEMENTATION_MATRIX.md`](./SPEC_IMPLEMENTATION_MATRIX.md)
   - Run `rg -n "\\b(partial|missing)\\b" SPEC_IMPLEMENTATION_MATRIX.md`
   - Release is not ready until all gating requirements are `implemented` or explicitly approved with follow-up tasks.
3. Run targeted verification tests:
   - `uv run pytest tests/test_og_sync_verify_replay_hooks.py`
4. Gate decisions:
   - If matrix has `missing` status items: set release to blocked.
   - If matrix has `partial` status items: capture compensating controls and owner tasks before proceeding.
   - If matrix is clear: proceed with release readiness approval.

`SPEC_IMPLEMENTATION_MATRIX.md` is now the canonical checklist for whether `SPEC-v2` conformance is acceptable before release.

## 4.1) Full-spec dogfood evidence runbook

Run these commands during pre-release rollout:

1. `og status --json > .outcomegraph/events/dogfood-status.json`
2. `og sync --json > .outcomegraph/events/dogfood-sync.json`
3. `og verify --changed --json > .outcomegraph/events/dogfood-verify.json`
4. `og drift > .outcomegraph/events/dogfood-drift.txt`

Acceptance criteria:

- `dogfood-status.json` has `status: ok`, runtime `status: idle`, and `issues: []`.
- `dogfood-sync.json` has `status: ok`, a non-empty `steps` array, and no schema validation errors.
- `dogfood-verify.json` has `status: ok` and a populated `verified_capsules` list.
- `dogfood-drift.txt` does not report `POLICY_DENIED` or drift-blocking recommendations.

Store evidence under `.outcomegraph/events` and include event IDs in release notes.

This repository currently has a dogfood migration blocker:

- Validation fails with `materials.lock` schema mismatch because `artifact_type` is missing.
- Fix the migration first, then rerun from step 1 before deciding rollout completion.
