# SPEC-v2 Conformance Matrix

Generated for task `OG-SPEC-001` from `SPEC-v2.md`.

Last updated: 2026-03-07

Legend:
- `implemented`: Requirement is enforced and/or tested in the current implementation.
- `partial`: Requirement intent exists but automation or enforcement is not fully covered.
- `missing`: No implementation evidence found for the stated requirement.

## 7) Canonical artifact model

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §7: "Every canonical artifact must include `schema_version: 2`, `artifact_type`, `id`, and timestamps." | implemented | `SPEC-v2.md` (design), `og.py` (canonical artifact validation), `tests/test_og_sync_verify_replay_hooks.py` | Enforced by `_validate_canonical_artifact_records` and covered by `TestSpecComplianceGates` metadata regression tests. |
| §7: "Every claim must resolve to at least one receipt pointer." | implemented | `SPEC-v2.md` (requirement), `og.py` (canonical artifact validation + claim builders), `tests/test_og_sync_verify_replay_hooks.py` | Enforced by canonical validation and covered by `test_validate_canonical_artifacts_rejects_claim_without_receipt_pointer`. |
| §7.8: "All mutation commands must validate `schema_version` before writing" (including unsupported/missing, mixed-version hard errors, and explicit migration path) | implemented | `og.py` (apply/verify/replay canonical pre-write checks), `tests/test_og_sync_verify_replay_hooks.py` | Covered by no-partial-write regressions for apply/verify/replay legacy-canonical inputs in `TestSpecComplianceGates`. |
| §7.8: "Legacy (`1`) artifacts unsupported by default; no silent auto-upgrade." | implemented | `SPEC-v2.md`, `og.py` (canonical validation), `tests/test_og_sync_verify_replay_hooks.py` | Covered by `test_validate_canonical_artifacts_rejects_non_version_two_schema` and stage-level legacy rejection tests before artifact writes. |

## 8) Runtime and lock behavior

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §8 + §9: `og sync` enforces lock-based sync and idempotent pipeline stages with baseline resolution and filtered changed paths behavior. | partial | `og.py` (`_acquire_work_lock`, `_collect_sync_snapshot`, sync stage handlers), `tests/test_og_sync_verify_replay_hooks.py` | Add/extend command tests for lock contention, baseline fallback, and runtime-dir filtering. Pass: lock contention sets pending state; fallback modes are deterministic; changed paths are respected by scope filter. |

## 10) Hook lifecycle

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §10: "`og autopilot init` must never silently clobber existing hooks." | implemented | `og.py` (autopilot/install path handling), `README.md` (autopilot contract) | Add automated hook migration test that covers both `core.hooksPath` unset and pre-existing paths. Pass: existing scripts remain bridged/restored unless explicitly forced. |

## 11) Plugin contracts and compatibility

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §11.1: "Adapters expose one typed contract per interface family" and must pass version negotiation. | implemented | `og.py` (plugin registration + validation), `tests/test_og_sync_verify_replay_hooks.py` | Keep contract validation in CI at bootstrap and on plugin load. Pass: valid interface/version combination loads; incompatible interface is rejected. |
| §11.1 core compatibility map (`interface_version == 1`) is enforced. | implemented | `og.py` (`WORKER_SCHEMA_VERSION`, `WORKER_INTERFACE_VERSION`, adapter validators) | Add regression test for every adapter type. Pass: each required adapter rejects mismatched interface versions. |
| §11.2 / §11.3: Incompatible plugin contracts produce `ADAPTER_INTERFACE_MISMATCH` diagnostics with required fields. | partial | `SPEC-v2.md`, `og.py` (schema/contract validation), test coverage pending around mismatch payload fields | Add assertion tests for error payload schema (`status`, `code`, `type`, `name`, required/existing interface versions). Pass: payload includes remediation and both required/existing versions. |

## 13) Policy enforcement

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §13.2: "`og sync` and downstream autonomous jobs must perform policy check before any non-observation action" including deny-first logic. | partial | `SPEC-v2.md`, `og.py` (`_collect_policy_checks` + runtime policy wiring) | Add/extend policy integration tests around observe/autonomous branching and `forbidden_actions`. Pass: deny-list rules block unsafe actions before execution, and allowlist permits only in autonomous mode. |
| §13.3: "Automated actions must exit with usage-like status `64` for policy misconfiguration and `1` for enforcement denials." | partial | `og.py` (exit-code constants, command dispatch), release verification pending on enforcement paths | Add tests for both categories: bad policy schema and runtime policy denial. Pass: bad schema returns `64`, enforcement denial returns `1`, both produce machine-readable payload. |

## 19) Documentation requirements

| Requirement | Status | Owners | Acceptance check (for release/readiness) |
| --- | --- | --- | --- |
| §19: "OutcomeGraph must ship with architecture overview, domain context docs, schema reference, plugin API reference, operational runbook, recovery runbook, security policy doc, migration guide." | implemented | `ARCHITECTURE.md`, `README.md`, `SPEC-v2.md`, `PLUGIN_API.md`, `RUNBOOKS.md`, `SECURITY_POLICY.md`, `MIGRATION_GUIDE.md` | Verify all listed docs exist and are versioned with the current spec release. Pass: required document files exist in repository root and are referenced in docs index. |

## Release/readiness wiring

The matrix is enforced through the following workflow checkpoints:

1. Run `og sync`, `og status`, and `og verify --changed`.
2. Review `SPEC_IMPLEMENTATION_MATRIX.md` and validate no `missing` status remains for release gates.
3. Validate `partial` entries are paired with explicit blocking tasks and accepted mitigations before release.
4. Confirm policy and adapter contract tests pass.

Recommended commands:

- `rg -n "\b(partial|missing)\b" SPEC_IMPLEMENTATION_MATRIX.md`
- `uv run pytest tests/test_og_sync_verify_replay_hooks.py`
- `uv run og sync --json`
- `uv run og verify --changed --json`
- `uv run og status --json`
