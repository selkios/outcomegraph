# OG-REPLAY-003

Status: done

Summary:
- Tightened replay plans so successful plans must declare capsule scope, scoped material inputs, executable acceptance checks, and explicit equivalence inputs.
- Replay now fails clearly when a capsule lacks enough regeneration proof data instead of treating advisory-only oracles as success, and replay certificates record the proof contract.
- Bumped the replay prompt asset version and updated the spec/runbook coverage to match the stricter regeneration path.

Read:
- `/home/agent/outcomegraph/to-do.json`
- `/home/agent/outcomegraph/to-do.schema.json`
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/ARCHITECTURE.md`
- `/home/agent/outcomegraph/QUICKSTART.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/WORKER_CAPSULE_REFACTOR_PLAN.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/prompts/workers/manifest.json`
- `/home/agent/outcomegraph/prompts/workers/replay-v1.txt`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-prompt-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-prompt-002/task-plan.json`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/prompts/workers/manifest.json`
- `/home/agent/outcomegraph/prompts/workers/replay-v1.txt`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/tasks/og-replay-003/TASK.md`
- `/home/agent/outcomegraph/tasks/og-replay-003/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
