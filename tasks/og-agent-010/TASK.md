# OG-AGENT-010

Status: done

Summary:
- Normalized command envelopes so `status: "error"` payloads with empty `errors` still emit typed top-level error records, which makes session expiry and invalid-resume failures machine-actionable without losing the detailed `data.session` payload.
- Kept session continuity explicit across `sync`, `autopilot`, and `daemon` flows, including emitted `session_id` values, runtime exit-code mapping for resume failures, and sync/event propagation.
- Updated help/examples and repo docs to define the session policy clearly: `sync` sessions are ephemeral, `autopilot` and `daemon` sessions are resumable, and emitted session ids use the lowercase `<kind>-<timestamp>-<hash>` format.

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
- `/home/agent/outcomegraph/tasks/og-distill-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-001/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-prompt-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-prompt-002/task-plan.json`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`
- `/home/agent/outcomegraph/skills/og-quality-pass/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/AGENT_FIRST_CLI_REVIEW.md`
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-agent-010/TASK.md`
- `/home/agent/outcomegraph/tasks/og-agent-010/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `uv run pytest tests/test_og_sync_verify_replay_hooks.py -q`
- `bash skills/og-quality-pass/scripts/run_quality_pass.sh`
