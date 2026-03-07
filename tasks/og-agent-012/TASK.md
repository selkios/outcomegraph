# OG-AGENT-012

Status: done

Summary:
- Added runtime defaults for headless usage in `og.py`, loading `.outcomegraph/config.yaml` plus env overrides for output mode, profile, mode, config/policy paths, and the Codex home/config directory.
- Enforced deterministic precedence as `CLI flags > env vars > config defaults`, and echoed the resolved sources back in command metadata under `options.configuration`.
- Updated docs and review artifacts to document the new defaults contract, and added focused regression tests for precedence, env parity, and policy/config path resolution.

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
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/QUICKSTART.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tasks/og-agent-012/TASK.md`
- `/home/agent/outcomegraph/tasks/og-agent-012/task-plan.json`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m py_compile /home/agent/outcomegraph/og.py /home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `uv run pytest /home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py -q`
