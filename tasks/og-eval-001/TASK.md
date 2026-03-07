# OG-EVAL-001

Status: done

Summary:
- Added a focused artifact-quality evaluator in `og.py` that scores capsule usefulness on the Phase 7 acceptance signals: executable oracle coverage, code invariant coverage, receipt-backed behavior-claim coverage, advisory-only success code capsules, and accepted stale-doc contradiction capture.
- Added a repo-shaped regression harness in `tests/test_capsule_quality_eval.py` that builds a minimal OutcomeGraph artifact graph and fails each metric independently when capsule usefulness regresses.
- Wired the harness into the existing local quality pass implicitly through `pytest`, then verified the full bundled gate succeeds.

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
- `/home/agent/outcomegraph/skills/og-quality-pass/SKILL.md`
- `/home/agent/outcomegraph/skills/og-quality-pass/scripts/run_quality_pass.sh`
- `/home/agent/outcomegraph/tasks/og-apply-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-apply-001/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-distill-002/TASK.md`
- `/home/agent/outcomegraph/tasks/og-distill-002/task-plan.json`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-dogfood-001/task-plan.json`
- `/home/agent/.codex/skills/todo-json-manager/SKILL.md`
- `/home/agent/.codex/skills/git-conventional-commit/SKILL.md`
- `/home/agent/selkios/selkios-os/skills/selkios-task-implement/SKILL.md`

Wrote:
- `/home/agent/outcomegraph/og.py`
- `/home/agent/outcomegraph/tests/test_capsule_quality_eval.py`
- `/home/agent/outcomegraph/tasks/og-eval-001/TASK.md`
- `/home/agent/outcomegraph/tasks/og-eval-001/task-plan.json`
- `/home/agent/outcomegraph/to-do.json`

Verification:
- `./.venv/bin/pytest -q tests/test_capsule_quality_eval.py`
- `bash skills/og-quality-pass/scripts/run_quality_pass.sh /home/agent/outcomegraph`
