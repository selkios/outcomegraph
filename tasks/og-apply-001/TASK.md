# OG-APPLY-001

Status: done

Summary:
- Removed apply-stage heuristics that inferred `pytest -q` or upgraded `warn` capsules to `success` without stronger distill evidence.
- Tightened capsule payload building so weak apply inputs overwrite previously strong brief fields instead of silently backfilling behavior claims, dependencies, invariants, unknowns, or stronger oracles.
- Added regression coverage proving thin Python capsules stay transparently weak until distill or replay provides stronger evidence.

Read:
- `/home/agent/outcomegraph/to-do.json`
- `/home/agent/outcomegraph/to-do.schema.json`
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/ARCHITECTURE.md`
- `/home/agent/outcomegraph/QUICKSTART.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/WORKER_CAPSULE_REFACTOR_PLAN.md`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-distill-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-002/task-plan.json`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-apply-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-apply-001/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
