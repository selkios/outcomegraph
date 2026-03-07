# Clean Clone 1800s Dogfood Review

Subject:
- `/tmp/outcomegraph-dogfood-clean3-ayih`

Setup:
- Clean local clone of `HEAD`
- Overlaid task-local files from `/home/agent/outcomegraph`:
  - `og.py`
  - `prompts/workers/distill-v1.txt`
  - `skills/og-dogfood/scripts/run_dogfood.sh`
  - `tests/test_og_sync_verify_replay_hooks.py`
  - `WORKER_CAPSULE_REFACTOR_PLAN.md`
- Ran:
  - `OG_DOGFOOD_TIMEOUT_SECONDS=1800 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-clean3-ayih`

Result:
- `clean`, `init`, and pre-sync `status` all completed as expected.
- Distill batches `1`, `2`, `3`, `4`, `5`, `6`, `7`, and `9` produced full trace triplets under `.outcomegraph/traces/`, so the longer timeout clearly advanced beyond the earlier 900-second ceiling.
- The run never emitted a terminal sync envelope or summary event. `.outcomegraph/events/dogfood-sync.json` remained zero bytes, `.outcomegraph/work/state.json` stayed at `status: "distill"` with `last_sync_id: null`, and `.outcomegraph/work/lock` still pointed at the dead `og sync` holder.
- Missing trace triplets for batches `0` and `8` leave the failure unresolved. The dogfood loop never reached `verify`, `replay`, `drift`, or final `status`.

Evidence:
- `clean-clone-1800-dogfood-status-pre-sync.json`
- `clean-clone-1800-dogfood-sync.json`
- `clean-clone-1800-distill-batch-9-input.json`
- `clean-clone-1800-distill-batch-9-result.json`
- `clean-clone-1800-work-state.json`
- `clean-clone-1800-work-lock.json`

Capsule review gate:
- `og`: blocked, no regenerated capsule from a terminal sync
- `tests`: blocked, no regenerated capsule from a terminal sync
- `runbooks`: blocked, no regenerated capsule from a terminal sync
- `spec-v2`: blocked, no regenerated capsule from a terminal sync
- `uv`: blocked, no regenerated capsule from a terminal sync

Blocking observation:
- This 1800-second clean-clone attempt proved that later batches can complete, but the run still terminated abnormally before `og` could publish a terminal sync result for the whole queue.
