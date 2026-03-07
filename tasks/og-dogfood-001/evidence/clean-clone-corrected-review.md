# Clean Clone Corrected Dogfood Review

Subject:
- `/tmp/outcomegraph-dogfood-final-Nwve`

Setup:
- Clean local clone of the repo with task-local overlays for `og.py`, `tests/test_og_sync_verify_replay_hooks.py`, `skills/og-dogfood/scripts/run_dogfood.sh`, and the dogfood task artifacts.
- First corrected rerun used `OG_DOGFOOD_TIMEOUT_SECONDS=3600 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-final-Nwve`.
- Second corrected rerun refreshed the clone inputs, rebuilt `.venv`, and ran the same dogfood command again.

Result:
- The old `tasks` / `tests` / `to-do` distill stall is no longer the blocker after the size-aware batching change in `og.py`.
- The first corrected rerun advanced through distill and into verify, where generated oracles still invoked bare `uv run pytest ...`. In the clean-clone runtime that failed with `Failed to spawn: pytest` and `os error 2`, so the sync terminated with verify errors instead of producing acceptance artifacts.
- The second corrected rerun started from a refreshed clone and matching `og.py` hash, but external Codex throughput effectively serialized distill work. After roughly 25 minutes only batches `0` through `3` had written trace triplets, `.outcomegraph/events/dogfood-sync.json` was still `0` bytes, and there was still no terminal sync envelope to drive verify, replay, or drift.
- During that second rerun the workspace copy of `og.py` drifted to `398c2ad9a35a21d0c81dee0e60e6f304841d0259bc657713d2c1b4f9e73a9800` while the clean clone stayed at `46d14c45b8a9ff80f431633cae5aa5ff385c13950592f46aeda4a1d21fd0860f`. That made the staged dogfood baseline unstable before capsule review could be trusted.
- Cancelling the second rerun left worker process group `897885` behind, which was terminated manually.

Evidence:
- `clean-clone-corrected-trace-summary.json`
- `clean-clone-3600-review.md`
- `clean-clone-3600-trace-summary.json`

Capsule review gate:
- `og`: blocked until a stable clean-clone sync completes verify/replay/drift on a stable source baseline
- `tests`: blocked until the corrected clean-clone rerun finishes beyond distill with regenerated capsules
- `runbooks`: blocked until apply/verify/export complete in a successful clean-clone loop
- `spec-v2`: blocked until apply/verify/export complete in a successful clean-clone loop
- `uv`: blocked until apply/verify/export complete in a successful clean-clone loop
