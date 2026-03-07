# OG-APPLY-001

Status: done

Summary:
- Tightened apply-stage artifact writing so weak capsules no longer receive misleading success certificates.
- Stopped apply from synthesizing placeholder claim text/category when distill claim payloads are incomplete.
- Added regressions proving weak code capsules stay weak and malformed claims are rejected instead of normalized into stronger artifacts.

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
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-apply-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-apply-001/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
