# Fix-Everything Plan (2026-03-08)

## Completed in this pass
1. Hardened distill stage snapshot handling and unexpected exception normalization in `og.py`.
2. Added sync lock heartbeat refresh (`_refresh_work_lock` + background heartbeat thread) in `og.py`.
3. Added regression tests for lock refresh and distill guardrails in `tests/test_og_sync_verify_replay_hooks.py`.
4. Corrected README `--changed` contract wording.
5. Hardened dogfood JSON capture flow to emit structured failure envelopes in `skills/og-dogfood/scripts/run_dogfood.sh`.
6. Verified with full quality gate: `ruff`, `ty`, and full `pytest` all pass.

## Remaining work to truly close “everything”
1. Replace placeholder dogfood sync evidence files with real outputs from a successful clean-clone run.
2. Unblock `tasks/og-dogfood-001` by completing sync/verify/replay/drift acceptance with stable runtime baseline.
3. Decide whether to remove generated `outcomegraph.egg-info/*` from source tracking.
4. Add a CI check that cross-validates documented CLI flags against schema/parser output.

## Execution order
1. Dogfood evidence rerun and replacement.
2. Task status transition from `blocked` to `done` once evidence validates.
3. Generated metadata cleanup policy.
4. Docs/contract CI guard.
