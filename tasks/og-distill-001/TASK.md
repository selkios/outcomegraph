# OG-DISTILL-001

Status: done

Summary:
- Enriched distill target payloads with bounded changed-region context, supporting scope discovery, existing capsule summaries, related test/oracle hints, and materials scope context.
- Updated distill-stage assembly so per-capsule materials are computed once and passed into the worker input.
- Added focused regression tests for diff-hunk region context, discovered supporting test files, and existing capsule/material/oracle enrichment.

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
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-distill-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-001/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
