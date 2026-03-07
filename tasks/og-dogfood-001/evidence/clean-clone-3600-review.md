# Clean Clone 3600s Dogfood Review

Subject:
- `/tmp/outcomegraph-dogfood-ralf-i4rj`

Setup:
- Clean local clone of `HEAD`
- Overlaid task-local files from `/home/agent/outcomegraph`:
  - `og.py`
  - `prompts/workers/distill-v1.txt`
  - `prompts/workers/manifest.json`
  - `prompts/workers/replay-v1.txt`
  - `skills/og-dogfood/scripts/run_dogfood.sh`
  - `tests/test_og_sync_verify_replay_hooks.py`
  - `WORKER_CAPSULE_REFACTOR_PLAN.md`
- Ran:
  - `OG_DOGFOOD_TIMEOUT_SECONDS=3600 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-ralf-i4rj`

Result:
- `clean`, `init`, and pre-sync `status` completed as expected.
- Distill batches `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7`, and `9` wrote full trace triplets under `.outcomegraph/traces/`.
- Batch `8` never wrote a trace triplet or `distill-last-message.json`. Based on batch ordering, that missing batch is the `tasks` / `tests` / `to-do` group.
- `dogfood-sync.json` remained zero bytes, `.outcomegraph/work/state.json` stayed at `status: "distill"` with `last_sync_id: null`, and `.outcomegraph/work/lock` stayed pinned to the dead `og sync` holder.
- Cancelling the stuck sync left an orphaned `codex exec` process group for the missing batch, which had to be terminated manually.

Evidence:
- `clean-clone-3600-dogfood-status-pre-sync.json`
- `clean-clone-3600-dogfood-sync.json`
- `clean-clone-3600-work-state.json`
- `clean-clone-3600-work-lock.json`
- `clean-clone-3600-trace-summary.json`

Capsule review gate:
- `og`: blocked, distill completed for the `og` batch but no terminal sync ran apply/verify to regenerate canonical capsules
- `tests`: blocked, the final `tasks` / `tests` / `to-do` batch never returned
- `runbooks`: blocked, distill completed for the `runbooks` batch but no terminal sync ran apply/verify to regenerate canonical capsules
- `spec-v2`: blocked, distill completed for the `spec-v2` batch but no terminal sync ran apply/verify to regenerate canonical capsules
- `uv`: blocked, distill completed for the `uv` batch but no terminal sync ran apply/verify to regenerate canonical capsules

Blocking observation:
- This 3600-second clean-clone rerun cleared the earlier missing batches `0` and `9`, but batch `8` still exceeded the previous worst completed batch duration (`966165ms` in the earlier clean-clone 1800-second run) without producing any worker output or a terminal sync envelope.
