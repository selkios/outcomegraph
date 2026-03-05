---
name: og-quality-pass
description: Run a full local quality gate for OutcomeGraph using ruff, ty, and pytest in one pass. Use when asked to lint/type-check/test this repo, validate recent changes before commit/release, or collect a single quality status after edits.
---

# OG Quality Pass

## Overview
Run one deterministic quality pass for this repository in this order: `ruff` -> `ty` -> `pytest`.
Use the bundled script so all commands run even if an earlier step fails, then report a single pass/fail result.

## Workflow
1. Run the bundled script:
```bash
bash skills/og-quality-pass/scripts/run_quality_pass.sh
```
2. If needed, pass an explicit repo root:
```bash
bash skills/og-quality-pass/scripts/run_quality_pass.sh /home/agent/outcomegraph
```
3. Read the final summary from script output:
- `PASS: all quality checks succeeded.`
- `FAIL: one or more quality checks failed.`

## Command Contract
- Execute from repo root context.
- Use repo-local `.venv` tools only.
- Run checks in this exact order:
1. `ruff check og.py tests`
2. `ty check --output-format concise`
3. `pytest -q`
- Continue to later checks even if earlier checks fail.
- Return non-zero exit when any step fails.

## Reporting Contract
- For each failed step, report:
1. tool name
2. failing command
3. key errors (first actionable lines)
- Keep remediation focused on concrete failures; avoid speculative refactors.
