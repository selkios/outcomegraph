# Worker And Capsule Refactor Plan

## Purpose

Refactor the OutcomeGraph Codex worker integration so `.outcomegraph` artifacts become compact, reusable recreation records instead of mostly snapshot summaries. The immediate trigger is that the current graph is structurally healthy but still weak as a feature-regeneration prompt set.

This plan is the controlling document for the backlog tasks added in `to-do.json`. Every task in this workstream should reference this file explicitly.

## Current Findings

1. Worker prompts are hardcoded in `og.py`.
   - The `distill` and `replay` prompts live inline in `_build_worker_prompt()`.
   - This makes prompt review, versioning, and iteration harder than it should be.

2. Distill is still payload-bound in a way that favors summaries over recreation briefs.
   - Codex only sees `changed_file_snapshots`, a few `supporting_file_snapshots`, and limited existing capsule context.
   - That is enough to summarize visible state, but often not enough to produce strong feature-level reconstruction guidance.

3. Capsule quality policy is too uniform.
   - `doc`, `config`, `runtime`, `code`, and `test` capsules are effectively judged with the same success bar.
   - This lets code-heavy capsules reach `success` even when they mainly describe observations instead of regeneration contracts.

4. Apply still improves weak outputs heuristically.
   - Policy normalization is useful.
   - Synthetic strengthening or status promotion can make a capsule look stronger than the distill evidence really is.

5. Replay is not yet a strong enough downstream contract.
   - Replay plans and capsule oracles are not consistently treated as the executable proof of recreation.
   - Many capsules still stop at “advisory only” evidence.

6. The graph is useful but still incomplete for the expected end state.
   - The current `.outcomegraph` contains a good artifact graph with claims, decisions, certificates, and traces.
   - The remaining gap is quality of capsule meaning, not absence of files.

## Desired End State

OutcomeGraph should produce capsules that another agent can use to recreate a capability or feature without needing the original chat transcript or a full code dump in Git.

Each strong capsule should communicate:

- what capability exists
- where its boundary is
- what invariants must hold
- what dependencies or supporting files matter
- what the acceptance oracle is
- what is still unknown

The resulting `.outcomegraph` should remain compact and evidence-backed:

- no full chat transcripts as canonical truth
- no source-code mirroring into canonical artifacts
- no pretending that documentation examples are executable proof

## Non-Goals

- Do not store complete source files or raw code snapshots as canonical truth in Git.
- Do not replace the canonical artifact model with prompt text.
- Do not make doc capsules disappear; documentation capsules remain useful, but they should not dominate code reconstruction quality.
- Do not rely on Codex browsing the full repo interactively during distill. Inputs should remain bounded and deterministic.

## Design Principles

1. Prompt assets must be readable and versioned in the repo.
2. Prompt bodies and output schemas must be auditable independently of `og.py`.
3. Code capsules need a stricter success bar than doc capsules.
4. Distill should expose unknowns instead of manufacturing certainty.
5. Replay and executable oracles are the proof path for recreation.
6. Dogfood in this repo is the primary acceptance benchmark.

## Workstreams

### Phase 0: Plan Capture

Task: `OG-PLAN-001`

Deliverables:

- this plan file at `WORKER_CAPSULE_REFACTOR_PLAN.md`
- backlog tasks that reference this file directly

Acceptance:

- the plan is committed in the repo
- every task in this workstream references this plan file

### Phase 1: Prompt Asset System

Tasks: `OG-PROMPT-001`, `OG-PROMPT-002`

Goal:

Move worker prompt bodies out of `og.py` and into human-readable repo files, then record prompt provenance in traces and downstream artifacts.

Deliverables:

- a top-level prompt asset directory in the codebase
- a manifest describing prompt ids, versions, roles, and variables
- prompt loader/validator code
- prompt identity/version embedded in trace inputs and relevant certificates

Acceptance:

- no inline worker prompt bodies remain in `og.py`
- prompt loading fails fast when assets are missing or invalid
- traces identify the exact prompt version used for a worker run

### Phase 2: Capsule Kind Classification

Task: `OG-CAPSULE-001`

Goal:

Introduce explicit capsule kinds so success rules can differ for `code`, `test`, `doc`, `config`, and `runtime` capsules.

Deliverables:

- internal capsule-kind classifier
- kind-aware validation/status policy
- tests proving code/test capsules are held to a stricter standard

Acceptance:

- code and test capsules cannot silently qualify as strong artifacts with only doc-like evidence
- doc/config/runtime capsules can remain useful without being held to the same oracle bar

### Phase 3: Distill Input Enrichment

Task: `OG-DISTILL-001`

Goal:

Give Codex better feature context without giving it the whole repo.

Deliverables:

- richer changed-region snapshots
- supporting unchanged scope context
- explicit existing capsule summary
- related test and oracle hints where discoverable
- tighter materials/scope context for replayability

Acceptance:

- large-file changes are represented by the changed region, not just file prefixes
- capsules can see enough context to talk about features instead of only files

### Phase 4: Distill Contract Rewrite

Task: `OG-DISTILL-002`

Goal:

Rewrite the distill prompt and output expectations so the worker produces a recreation brief instead of a general-purpose summary.

Required capsule fields for strong outputs:

- feature/capability statement
- boundary
- behavior claims
- invariants
- dependencies
- acceptance oracle or explicit reason none exists
- unknowns

Acceptance:

- code capsules describe recreatable behavior, not just observed files
- doc examples no longer become accidental live oracles
- `success` means the capsule is materially reusable

### Phase 5: Apply Behavior Tightening

Task: `OG-APPLY-001`

Goal:

Reduce apply-stage strengthening that masks weak distill output.

Deliverables:

- retain policy normalization
- reduce synthetic success promotion
- preserve unknowns and evidence gaps in the canonical artifacts

Acceptance:

- apply no longer turns thin capsules into misleadingly strong ones
- artifact status more honestly reflects distill quality

### Phase 6: Replay Contract Tightening

Task: `OG-REPLAY-003`

Goal:

Make replay a real regeneration proof path for capsules instead of a weak adjunct.

Deliverables:

- replay prompt externalized with the same prompt asset system
- stronger replay-plan requirements
- tighter relationship between capsule scope, materials, and equivalence checks

Acceptance:

- replay plans are concrete and capsule-scoped
- replay evidence is useful for certifying recreation, not just re-execution bookkeeping

### Phase 7: Evaluation Harness

Task: `OG-EVAL-001`

Goal:

Create automated quality checks for the artifact graph itself.

Metrics to track:

- percentage of `code`/`test` capsules with executable oracles
- percentage of `code` capsules with explicit invariants
- percentage of `success` code capsules that still rely only on advisory evidence
- known stale-doc contradictions captured as accepted truth

Acceptance:

- quality regressions fail tests or the local quality pass
- prompt tuning is guided by measurable artifact quality signals

### Phase 8: Dogfood And Documentation

Tasks: `OG-DOGFOOD-001`, `OG-DOC-003`

Goal:

Validate the refactor end-to-end on this repo, then update docs to reflect the new prompt asset system and capsule quality rules.

Acceptance:

- clean bootstrap and full sync produce materially stronger capsules
- target capsules are manually reviewed against this plan:
  - `og`
  - `tests`
  - `runbooks`
  - `spec-v2`
  - `uv`
- docs describe where prompt assets live and what “good capsule quality” means

## Acceptance Criteria For The Whole Refactor

The refactor is complete when all of the following are true:

1. Worker prompt bodies live in human-readable repo files, not hardcoded strings in `og.py`.
2. Prompt provenance is recorded in traces and can be tied to generated artifacts.
3. Code and test capsules use stricter success standards than doc capsules.
4. Distill outputs are feature-oriented recreation briefs rather than mostly snapshot summaries.
5. Apply preserves evidence gaps instead of hiding them.
6. Replay meaningfully supports regeneration and equivalence.
7. A fresh dogfood run in this repo produces a graph where `success` implies reusable value.

## Recommended Sequence

1. `OG-PROMPT-001`
2. `OG-PROMPT-002`
3. `OG-CAPSULE-001`
4. `OG-DISTILL-001`
5. `OG-DISTILL-002`
6. `OG-APPLY-001`
7. `OG-REPLAY-003`
8. `OG-EVAL-001`
9. `OG-DOGFOOD-001`
10. `OG-DOC-003`

## Repo Files Expected To Change

- `og.py`
- `tests/test_og_sync_verify_replay_hooks.py`
- new top-level prompt assets directory
- `README.md`
- `RUNBOOKS.md`
- `SPEC-v2.md`
- `to-do.json`

## Notes

- This plan intentionally keeps prompt assets in the main codebase, not inside `.outcomegraph`.
- `.outcomegraph` remains the canonical artifact store for compact replayable truth.
- Prompt assets are implementation inputs, not canonical truth.
