# OG-AGENT-014

Status: done

Summary:
- Added a first-class agent reliability tracker in `og.py` that persists rolling metrics for commands-per-successful-task, schema-valid output rate, retry auto-recovery rate, and resumable session churn under `.outcomegraph/work/agent_reliability.json`.
- Wired the metric snapshot into command envelopes (`metrics.agent_reliability`), sync/verify/replay/drift/optimize summary events, and the `status` / `doctor` payload surfaces so agents can inspect one machine-readable contract end-to-end.
- Updated docs and regression coverage to define the metric contract, interpretation guidance, and the status/doctor/schema surfaces that expose it.

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
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-agent-010/TASK.md`
- `/home/agent/outcomegraph/tasks/og-agent-010/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-agent-012/TASK.md`
- `/home/agent/outcomegraph/tasks/og-agent-012/task-plan.json`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`
- `/home/agent/outcomegraph/skills/og-quality-pass/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tasks/og-agent-014/TASK.md`
- `/home/agent/outcomegraph/tasks/og-agent-014/task-plan.json`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `python3 -m py_compile /home/agent/outcomegraph/og.py /home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `uv run pytest /home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py -q`
- `bash /home/agent/outcomegraph/skills/og-quality-pass/scripts/run_quality_pass.sh /home/agent/outcomegraph`
