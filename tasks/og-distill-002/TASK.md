# OG-DISTILL-002

Status: done

Summary:
- Rewrote the distill worker contract to ask for compact recreation briefs instead of broad summaries.
- Expanded the distill output schema and normalizers so strong capsule updates must carry behavior claims, invariants, dependencies, unknowns, and an acceptance oracle or explicit oracle-gap reason.
- Tightened apply-stage success policy and added regression coverage showing stronger `og` and `tests` capsule outputs.

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
- `/home/agent/outcomegraph/tasks/og-distill-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-001/task-plan.json`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-distill-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-002/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
