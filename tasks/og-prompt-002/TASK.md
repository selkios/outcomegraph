# OG-PROMPT-002

Status: done

Summary:
- Recorded worker prompt provenance (`id`, `version`, `source_path`) in trace input and trace result records while keeping the raw stdout trace intact.
- Propagated prompt provenance through distill/replay stage payloads, worker-driven certificates, and sync/replay/verify summary events.
- Added regression tests covering trace provenance, distill/apply propagation, replay certificates, and sync summary-event capture.

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
- `/home/agent/outcomegraph/prompts/workers/manifest.json`
- `/home/agent/outcomegraph/prompts/workers/distill-v1.txt`
- `/home/agent/outcomegraph/prompts/workers/replay-v1.txt`
- `/home/agent/outcomegraph/tasks/og-distill-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-001/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-distill-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-002/task-plan.json`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-prompt-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-prompt-002/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`
