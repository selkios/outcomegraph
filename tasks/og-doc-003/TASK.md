# OG-DOC-003

Status: done

Summary:
- Documented the repo-managed worker prompt asset system in the public docs, including where prompt templates live, how the manifest versions and binds prompt roles, and how prompt provenance is recorded downstream without turning prompt files into canonical artifacts.
- Tightened the capsule-quality contract in the docs so `success` now clearly means a materially reusable recreation brief, with kind-specific oracle expectations for `code`, `test`, `doc`, `config`, and `runtime` capsules.
- Updated the dogfood documentation to use the bundled deterministic script, include replay evidence in the acceptance contract, and require prompt-provenance plus manual capsule review of the target capsules.

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
- `/home/agent/outcomegraph/prompts/workers/distill-v1.txt`
- `/home/agent/outcomegraph/prompts/workers/replay-v1.txt`
- `/home/agent/outcomegraph/tests/test_capsule_quality_eval.py`
- `/home/agent/outcomegraph/tests/test_og_sync_verify_replay_hooks.py`
- `/home/agent/outcomegraph/tasks/og-prompt-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-prompt-002/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-replay-003/TASK.md`
- `/home/agent/outcomegraph/tasks/og-eval-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/task-plan.json`
- `/home/agent/outcomegraph/skills/og-dogfood/SKILL.md`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/README.md`
- `/home/agent/outcomegraph/ARCHITECTURE.md`
- `/home/agent/outcomegraph/SPEC-v2.md`
- `/home/agent/outcomegraph/RUNBOOKS.md`
- `/home/agent/outcomegraph/tasks/og-doc-003/TASK.md`
- `/home/agent/outcomegraph/tasks/og-doc-003/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `git diff --check -- README.md ARCHITECTURE.md SPEC-v2.md RUNBOOKS.md tasks/og-doc-003/TASK.md`
- `jq empty to-do.json`
- `jq empty tasks/og-doc-003/task-plan.json`
