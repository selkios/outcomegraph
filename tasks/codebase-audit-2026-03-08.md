# Codebase Audit Report (2026-03-08)

## 1. Executive Summary
- Health score: 8/10
- Runtime/test quality is strong (`ruff`, `ty`, and full `pytest` passed), and core concurrency/distill robustness gaps were fixed in this pass. Remaining risk is primarily release-readiness evidence quality (blocked dogfood artifacts and generated metadata tracked in source).

## 2. Critical Issues (ranked)
- [High] og.py:8946-9004, 18090-18110: Lock could go stale during long sync runs (>300s) causing false contention and duplicate/stale session behavior. Fixed by heartbeat refresh.
- [High] og.py:14629-14707, 14864-14885: `_run_distill_stage` could raise `KeyError`/unexpected exceptions and abort the run without structured payloads. Fixed with snapshot validation and broad exception normalization.
- [Medium] skills/og-dogfood/scripts/run_dogfood.sh:20-82: Dogfood JSON steps previously wrote raw/empty output directly, leaving non-JSON or zero-byte artifacts. Fixed with structured failure envelope + raw output retention.
- [Medium] README.md:198: CLI contract docs claimed `--changed` applied to sync, but parser contract allows it for verify/replay only. Fixed.
- [Medium] tasks/og-dogfood-001/evidence/clean-clone-1800-dogfood-sync.json:5 and .../clean-clone-3600-dogfood-sync.json:5: Evidence files are placeholders, not real sync outputs. Still unresolved and should be replaced by fresh dogfood run artifacts.

## 3. File-by-File Findings
Only files with actionable findings are listed below with exact locations and fixes.

- `og.py`
  - Lines 14629-14707, 14864-14885
  - Type: Bug / error-handling
  - Description: Distill could fail on missing `changed_files` or unexpected worker exceptions without normalized error payloads.
  - Recommended fix: Guard snapshot shape and normalize all unexpected distill exceptions into runtime error payloads.
  - Status: Fixed in this pass.
- `og.py`
  - Lines 8946-9004, 9006-9034, 18090-18110
  - Type: Concurrency / stale-lock risk
  - Description: Long sync runs could exceed lock stale timeout with no heartbeat refresh.
  - Recommended fix: Add `_refresh_work_lock` and background heartbeat during `sync` command execution.
  - Status: Fixed in this pass.
- `tests/test_og_sync_verify_replay_hooks.py`
  - Lines 1385, 1403, 1798, 2897
  - Type: Test coverage gap
  - Description: Missing regressions for lock refresh ownership/timestamp and distill guardrails.
  - Recommended fix: Add focused tests for lock refresh + distill malformed/exception paths.
  - Status: Fixed in this pass.
- `skills/og-dogfood/scripts/run_dogfood.sh`
  - Lines 20-82
  - Type: Reliability / incomplete artifact risk
  - Description: JSON dogfood steps previously allowed invalid/empty artifacts on failure.
  - Recommended fix: Emit structured JSON failure envelopes and persist raw output refs.
  - Status: Fixed in this pass.
- `README.md`
  - Line 198
  - Type: Documentation contract mismatch
  - Description: `--changed` described as sync/verify/replay, but sync parser rejects it.
  - Recommended fix: Document `--changed` for verify/replay only.
  - Status: Fixed in this pass.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-dogfood-sync.json`
  - Line 5
  - Type: Incomplete work artifact
  - Description: Placeholder evidence (`run_id` ends with `-placeholder`) instead of real sync output.
  - Recommended fix: Re-run dogfood clean-clone flow and replace placeholder with real envelope.
  - Status: Open.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-dogfood-sync.json`
  - Line 5
  - Type: Incomplete work artifact
  - Description: Placeholder evidence (`run_id` ends with `-placeholder`) instead of real sync output.
  - Recommended fix: Re-run dogfood clean-clone flow and replace placeholder with real envelope.
  - Status: Open.
- `tasks/og-dogfood-001/TASK.md`
  - Line 3
  - Type: Structural / release-readiness risk
  - Description: Task remains `Status: blocked`; dogfood acceptance not complete.
  - Recommended fix: Execute stabilized dogfood rerun with fixed runtime baseline and replace blocked evidence set.
  - Status: Open.

## 4. Dead Code Map
- `outcomegraph.egg-info/PKG-INFO`
- `outcomegraph.egg-info/SOURCES.txt`
- `outcomegraph.egg-info/dependency_links.txt`
- `outcomegraph.egg-info/entry_points.txt`
- `outcomegraph.egg-info/requires.txt`
- `outcomegraph.egg-info/top_level.txt`
Recommendation: treat these as generated build artifacts and remove from source tracking after confirming release workflow regenerates them.

## 5. Recommendations (Top 5)
1. Re-run `OG-DOGFOOD-001` on a stable clean clone and replace placeholder sync evidence artifacts.
2. Keep lock heartbeat in place and add an integration test that simulates sync durations > stale timeout.
3. Keep distill defensive guards and add one more regression for non-dict snapshot input at command boundary.
4. Remove `outcomegraph.egg-info/*` from source control (or document why it must be tracked) to reduce generated-file drift.
5. Add CI gating for docs/CLI contract consistency checks so option docs cannot drift from parser contract.

## Full Coverage Matrix
- `og.py`: Resolved in this pass: lock heartbeat refresh for long sync runs; distill snapshot/input hardening; catch unexpected distill worker exceptions; removed redundant cast warning.
- `RUNBOOKS.md`: No actionable finding in this audit pass.
- `QUICKSTART.md`: No actionable finding in this audit pass.
- `ARCHITECTURE.md`: No actionable finding in this audit pass.
- `WORKER_CAPSULE_REFACTOR_PLAN.md`: No actionable finding in this audit pass.
- `skills/og-dogfood/SKILL.md`: No actionable finding in this audit pass.
- `skills/og-dogfood/scripts/run_dogfood.sh`: Resolved in this pass: JSON-producing steps now write structured error envelopes plus raw output refs when commands fail or emit invalid JSON.
- `skills/og-dogfood/agents/openai.yaml`: No actionable finding in this audit pass.
- `skills/outcome-steward/SKILL.md`: No actionable finding in this audit pass.
- `skills/og-quality-pass/SKILL.md`: No actionable finding in this audit pass.
- `skills/og-quality-pass/scripts/run_quality_pass.sh`: No actionable finding in this audit pass.
- `skills/og-quality-pass/agents/openai.yaml`: No actionable finding in this audit pass.
- `skills/og/SKILL.md`: No actionable finding in this audit pass.
- `pyproject.toml`: No actionable finding in this audit pass.
- `README.md`: Resolved in this pass: corrected `--changed` flag contract text (verify/replay only, not sync).
- `outcomegraph.egg-info/entry_points.txt`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `outcomegraph.egg-info/top_level.txt`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `outcomegraph.egg-info/dependency_links.txt`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `outcomegraph.egg-info/requires.txt`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `outcomegraph.egg-info/SOURCES.txt`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `outcomegraph.egg-info/PKG-INFO`: Candidate dead/generated artifact; prefer build-time generation over source tracking.
- `tasks/og-agent-010/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-agent-010/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-apply-001/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-apply-001/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-doc-003/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-doc-003/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-distill-002/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-distill-002/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-agent-014/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-agent-014/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-replay-003/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-replay-003/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-agent-012/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-agent-012/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-distill-001/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-distill-001/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-prompt-002/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-prompt-002/TASK.md`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/task-plan.json`: Open/blocker evidence mirrors TASK.md blocked state.
- `tasks/og-dogfood-001/TASK.md`: Open/blocker evidence: dogfood acceptance remains blocked by environment/runtime constraints; not executable code but indicates release-readiness risk.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-work-state.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-dogfood-status-pre-sync.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-distill-batch-9-input.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-dogfood-status-pre-sync.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-dogfood-sync.json`: Open/incomplete artifact: placeholder sync evidence (`run_id` includes `-placeholder`).
- `tasks/og-dogfood-001/evidence/clean-clone-1800-distill-batch-9-result.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-work-lock.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-sync-summary.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-review.md`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-work-lock.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-corrected-review.md`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-review.md`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-distill-batch-9-input.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-distill-batch-9-result.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-dogfood-status-pre-sync.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-trace-summary.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-3600-work-state.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-dogfood-sync.json`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-1800-dogfood-sync.json`: Open/incomplete artifact: placeholder sync evidence (`run_id` includes `-placeholder`).
- `tasks/og-dogfood-001/evidence/clean-clone-1800-review.md`: No actionable finding in this audit pass.
- `tasks/og-dogfood-001/evidence/clean-clone-corrected-trace-summary.json`: No actionable finding in this audit pass.
- `tasks/og-eval-001/task-plan.json`: No actionable finding in this audit pass.
- `tasks/og-eval-001/TASK.md`: No actionable finding in this audit pass.
- `PLUGIN_API.md`: No actionable finding in this audit pass.
- `to-do.json`: No actionable finding in this audit pass.
- `to-do.schema.json`: No actionable finding in this audit pass.
- `uv.lock`: No actionable finding in this audit pass.
- `ogd`: No actionable finding in this audit pass.
- `prompts/workers/manifest.json`: No actionable finding in this audit pass.
- `prompts/workers/distill-v1.txt`: No actionable finding in this audit pass.
- `prompts/workers/replay-v1.txt`: No actionable finding in this audit pass.
- `CONTEXT.md`: No actionable finding in this audit pass.
- `SPEC-v2.md`: No actionable finding in this audit pass.
- `tests/test_og_sync_verify_replay_hooks.py`: Resolved in this pass: added regressions for lock refresh ownership/timestamp and distill guardrails.
- `tests/test_capsule_quality_eval.py`: No actionable finding in this audit pass.
- `tests/conftest.py`: No actionable finding in this audit pass.
- `tests/test_cli_mcp_contracts.py`: No actionable finding in this audit pass.
- `AGENT_FIRST_CLI_REVIEW.md`: No actionable finding in this audit pass.
- `og`: No actionable finding in this audit pass.
- `SPEC_IMPLEMENTATION_MATRIX.md`: No actionable finding in this audit pass.
- `SECURITY_POLICY.md`: No actionable finding in this audit pass.
- `MIGRATION_GUIDE.md`: No actionable finding in this audit pass.
