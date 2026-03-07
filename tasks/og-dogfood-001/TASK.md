# OG-DOGFOOD-001

Status: blocked

Summary:
- Added size-aware bootstrap distill batching in `og.py` and regression coverage in `tests/test_og_sync_verify_replay_hooks.py`. The focused distill/replay hook suite passed, and the repo quality pass completed successfully.
- The earlier clean-clone stall on the `tasks` / `tests` / `to-do` distill batch is no longer the active failure. A corrected clean-clone rerun at `/tmp/outcomegraph-dogfood-final-Nwve` advanced into verify, then failed because clone-generated oracles still invoked bare `uv run pytest ...`, and that clean-clone runtime could not spawn `pytest`.
- After refreshing the clone and rebuilding `.venv`, a second rerun from `/tmp/outcomegraph-dogfood-final-Nwve` no longer reproduced the old batch stall, but distill progressed only through batches `0` to `3` over roughly 25 minutes and never produced a terminal sync envelope. `.outcomegraph/events/dogfood-sync.json` stayed at `0` bytes, and the orphaned worker process group `897885` had to be terminated after cancellation.
- The workspace source baseline drifted during the second rerun. `/home/agent/outcomegraph/og.py` moved to `398c2ad9a35a21d0c81dee0e60e6f304841d0259bc657713d2c1b4f9e73a9800` while the clean clone stayed at `46d14c45b8a9ff80f431633cae5aa5ff385c13950592f46aeda4a1d21fd0860f`, so the repo snapshot used to stage the dogfood run was no longer stable enough for an acceptance-quality capsule review.

Current blockers:
- Direct repo reruns remain externally rate-limited. `/home/agent/outcomegraph/.outcomegraph/events/sync-20260307T151022Z-df8698e4e8.json` records a Codex usage-limit failure before distill starts.
- The first corrected clean-clone rerun from `/tmp/outcomegraph-dogfood-final-Nwve` failed verify because clone-generated oracles still used bare `uv run pytest ...`, and the clean-clone runtime could not spawn `pytest`.
- The second corrected clean-clone rerun from `/tmp/outcomegraph-dogfood-final-Nwve` advanced only through distill batches `0` to `3` in about 25 minutes, leaving `dogfood-sync.json` at `0` bytes with no terminal sync, verify, replay, or drift artifacts.
- `/home/agent/outcomegraph/og.py` drifted again during the second rerun, so the clean-clone source baseline was no longer stable enough to review regenerated capsules for `og`, `tests`, `runbooks`, `spec-v2`, and `uv`.

Read:
- `/home/agent/outcomegraph/to-do.json`
- `/home/agent/outcomegraph/to-do.schema.json`
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/ARCHITECTURE.md`
- `/home/agent/outcomegraph/QUICKSTART.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/WORKER_CAPSULE_REFACTOR_PLAN.md`
- `/home/agent/outcomegraph/skills/outcome-steward/SKILL.md`
- `/home/agent/outcomegraph/skills/og-quality-pass/SKILL.md`
- `/home/agent/outcomegraph/skills/og-dogfood/SKILL.md`
- `/home/agent/outcomegraph/skills/og-dogfood/scripts/run_dogfood.sh`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/.outcomegraph/events/sync-20260307T151022Z-df8698e4e8.json`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/evidence/clean-clone-3600-review.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/evidence/clean-clone-3600-trace-summary.json`
- `/tmp/outcomegraph-dogfood-final-Nwve/.outcomegraph/events/dogfood-sync.json`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/evidence/clean-clone-corrected-review.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/evidence/clean-clone-corrected-trace-summary.json`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `uv run pytest -q tests/test_og_sync_verify_replay_hooks.py -k "run_distill_stage_batches_complex_snapshot_capsules or run_distill_stage_splits_oversized_bootstrap_prompt_batches or run_distill_stage_uses_bootstrap_timeout_for_full_snapshot or run_distill_stage_uses_bootstrap_timeout_for_source_heavy_snapshot or run_codex_worker_kills_process_group_on_timeout or run_codex_worker_uses_configured_codex_home"`
- `bash skills/og-quality-pass/scripts/run_quality_pass.sh /home/agent/outcomegraph`
- `OG_DOGFOOD_TIMEOUT_SECONDS=3600 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-final-Nwve`
- `OG_DOGFOOD_TIMEOUT_SECONDS=3600 bash skills/og-dogfood/scripts/run_dogfood.sh /tmp/outcomegraph-dogfood-final-Nwve`

Commit:
- No commit created. Task remains blocked.
