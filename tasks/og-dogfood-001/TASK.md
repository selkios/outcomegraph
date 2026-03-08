# OG-DOGFOOD-001

Status: completed

Summary:
- Fixed replay failure mode in `og.py` by backfilling missing `replay plan.equivalence_inputs.baseline_hash` from known baseline equivalence during contract validation.
- Hardened dogfood JSON capture in `skills/og-dogfood/scripts/run_dogfood.sh` by capturing both stdout and stderr for JSON-mode commands.
- Added regression coverage in `tests/test_og_sync_verify_replay_hooks.py` for replay baseline backfill behavior.
- Re-ran clean-clone dogfood in `/tmp/outcomegraph-dogfood-20260308-nY1wfy` with `OG_DOGFOOD_TIMEOUT_SECONDS=1800`; end-to-end acceptance passed.

Acceptance evidence:
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-status-pre-sync.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-sync.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-verify.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-replay.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-drift.txt`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-status-final.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-dogfood-status.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-sync-summary.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-verify-summary.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-replay-summary.json`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-review.md`
- `tasks/og-dogfood-001/evidence/clean-clone-pass-1800-trace-summary.json`

Capsule review result (`og`, `tests`, `runbooks`, `spec-v2`, `uv`):
- `og`: success; executable oracle present.
- `tests`: success; executable oracle set present and passed during verify/replay.
- `runbooks`: success; advisory doc oracle set (non-executable by design).
- `spec-v2`: success; advisory doc oracle set (non-executable by design).
- `uv`: success; advisory lockfile oracle set (non-executable by design).

Verification:
- `uv run og replay --changed --json --timeout 1800` (clean clone) -> `status: ok`
- `OG_DOGFOOD_TIMEOUT_SECONDS=1800 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-20260308-nY1wfy` -> `PASS: dogfood evidence is healthy.`

Commit:
- No commit created.
