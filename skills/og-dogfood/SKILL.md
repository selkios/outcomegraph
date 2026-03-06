---
name: og-dogfood
description: "Run OutcomeGraph live end-to-end dogfood validation in this repository or another source checkout, starting from a full OutcomeGraph cleanup and bootstrap, capturing canonical evidence artifacts, and validating final `status`, `sync`, `verify`, `replay`, and `drift` results. Use when Codex needs to smoke-test `og` like an end user, collect rollout evidence, or troubleshoot live dogfood failures."
---

# OG Dogfood

## Overview

Run the live `og` workflow from a source checkout and keep the evidence layout deterministic.
Prefer the bundled script so cleanup, bootstrap, evidence capture, and acceptance checks stay aligned.

## Workflow

1. Run the bundled script from the repository root:
```bash
bash skills/og-dogfood/scripts/run_dogfood.sh
```

2. If needed, pass an explicit checkout path:
```bash
bash skills/og-dogfood/scripts/run_dogfood.sh /home/agent/outcomegraph
```

3. The script runs this exact sequence:
1. `uv run og clean --scope all --yes --json`
2. `uv run og init --json`
3. pre-sync `uv run og status --json` -> `.outcomegraph/events/dogfood-status-pre-sync.json`
4. `uv run og sync --json` -> `.outcomegraph/events/dogfood-sync.json`
5. `uv run og verify --changed --json` -> `.outcomegraph/events/dogfood-verify.json`
6. `uv run og replay --changed --json` -> `.outcomegraph/events/dogfood-replay.json`
7. `uv run og drift` -> `.outcomegraph/events/dogfood-drift.txt`
8. final `uv run og status --json` -> `.outcomegraph/events/dogfood-status-final.json`
9. copy final status to `.outcomegraph/events/dogfood-status.json`

## Important Behavior

- Use `uv run og <command>` for source checkouts.
- Do not use `og clean all`; the supported destructive form is `og clean --scope all --yes`.
- Expect the pre-sync status snapshot to be `warn` on a fresh bootstrap because certificates, sync summaries, and exports do not exist yet.
- Treat `.outcomegraph/events/dogfood-status.json` as the canonical acceptance artifact. The pre-sync baseline is preserved separately as `dogfood-status-pre-sync.json`.
- Expect the run to leave generated output under `.outcomegraph/` and `skills/outcome-steward/`.

## Acceptance Contract

- `dogfood-status.json` must have top-level `status: "ok"`, `data.issues: []`, and `data.runtime.status: "idle"`.
- `dogfood-sync.json` must have top-level `status: "ok"` and stage names `distill`, `apply`, `verify`, and `export`.
- `dogfood-verify.json` must have top-level `status: "ok"` and a non-empty `data.verified_capsules`.
- `dogfood-replay.json` must have top-level `status: "ok"` and non-empty `data.replay_results`.
- `dogfood-drift.txt` must include `drift: ok` and must not include `POLICY_DENIED`.

## Reporting Contract

- If the script fails, report the failing command, the evidence file it was writing, and the first actionable error lines.
- Keep conclusions tied to the captured evidence files rather than re-running ad hoc variants unless the first run is clearly invalid.
- If a failure mentions schema or artifact validation, inspect `.outcomegraph/events/dogfood-*.json` first and only then branch into migration or repair work.

## Local References

- Read [README.md](/home/agent/outcomegraph/README.md) for the source-checkout dogfood example and rollout checklist.
- Read [RUNBOOKS.md](/home/agent/outcomegraph/RUNBOOKS.md) for the documented evidence contract.
- Read [MIGRATION_GUIDE.md](/home/agent/outcomegraph/MIGRATION_GUIDE.md) if the live run hits schema migration failures.

## Script

Use [run_dogfood.sh](/home/agent/outcomegraph/skills/og-dogfood/scripts/run_dogfood.sh) for the deterministic live test.
