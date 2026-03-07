# Clean Clone Dogfood Review

Subject:
- `/tmp/outcomegraph-dogfood-clean2`

Setup:
- Clean local clone of `HEAD`
- Overlaid refactor workstream files from `/home/agent/outcomegraph`:
  - `og.py`
  - `prompts/workers/distill-v1.txt`
  - `prompts/workers/manifest.json`
  - `prompts/workers/replay-v1.txt`
  - `skills/og-dogfood/scripts/run_dogfood.sh`
  - `tests/test_og_sync_verify_replay_hooks.py`
  - `tests/test_capsule_quality_eval.py`
  - `README.md`
  - `RUNBOOKS.md`
  - `SPEC-v2.md`
  - `WORKER_CAPSULE_REFACTOR_PLAN.md`

Result:
- `clean` and `init` succeeded.
- Pre-sync `status` was the expected fresh-bootstrap `warn`.
- `sync` failed deterministically after `1412496ms` with `codex exec timed out after 900s (distill)`.
- `apply`, `verify`, and the sync-stage `verify` step were skipped, so the acceptance loop stopped before replay/drift/final-status.

Evidence:
- `clean-clone-dogfood-status-pre-sync.json`
- `clean-clone-dogfood-sync.json`
- `clean-clone-sync-summary.json`
- `clean-clone-distill-batch-9-input.json`
- `clean-clone-distill-batch-9-result.json`

Capsule review gate:
- `og`: blocked, no regenerated capsule from this run
- `tests`: blocked, no regenerated capsule from this run
- `runbooks`: blocked, no regenerated capsule from this run
- `spec-v2`: blocked, no regenerated capsule from this run
- `uv`: blocked, no regenerated capsule from this run

Blocking observation:
- The late `to-do` capsule batch alone consumed `841421ms`, which leaves too little headroom for the rest of the full-repo distill pass under the current 900s worker budget.
