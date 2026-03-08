# OutcomeGraph Steward Skill

Scope: This skill documents canonical Steward workflows for bootstrap, sync, and control-surface updates.

## 1) Bootstrap
- Run `og init` to create required OutcomeGraph directories and baseline metadata.
- Ensure `.outcomegraph/` exists with `constitution`, `capsules`, `refs`, `decisions`, `certificates`, `datasets`, `events`, `objects`, and `work`.

## 2) Deterministic sync flow
1. Run `og sync` for the canonical refresh loop.
2. Distill changes into synthetic deltas.
3. Apply deltas and refresh exports.
4. Emit structured summary into `.outcomegraph/events`.

## 3) Verification and replay expectations
- Use `og verify --changed` after focused edits.
- Use `og replay --changed` when behavior parity validation is required.
- Handle verification failures by inspecting certificate and error signals before continuing.

## 4) Failure handling
- If lock contention occurs, treat command result as `pending` and rerun.
- Preserve existing canonical artifacts when worker or oracle stages are unavailable.
- Keep exporting control surfaces from available truth where possible.

## 5) Artifact health
- Track canonical artifacts under `.outcomegraph/` and treat export files as projections.
- Export refresh includes `export/AGENTS.md`, `export/README_OUTCOMES.md`, and `export/mcp-resources.json`.
