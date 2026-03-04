# Quickstart - OutcomeGraph

Canonical specification: [SPEC-v2.md](./SPEC-v2.md)

OutcomeGraph is the Git-native artifact truth for replayable software.
Steward is the sidecar loop that keeps artifacts current.

## 1) Bootstrap

From repo root:

```bash
og init
```

Optional always-on setup:

```bash
og autopilot init
```

## 2) Manual-first flow (recommended)

After meaningful code changes:

```bash
og sync
og status
og verify --changed
og replay --changed
```

Use `og explain` to inspect what changed, why, and evidence pointers.

## 2b) Experimental prompt optimization

`og optimize prompts` compares two prompt files using an evaluation dataset and writes an optimization result under `.outcomegraph/datasets/`.

Example:

```bash
og optimize prompts \
  --dataset .outcomegraph/datasets/bugfix-llm-eval.json \
  --baseline .outcomegraph/datasets/baseline.txt \
  --candidate .outcomegraph/datasets/candidate.txt \
  --metric contains \
  --min-improvement 2
```

Append `--approve` to write an active prompt pack at:

```text
.outcomegraph/datasets/<dataset-id>-prompt-pack.json
```

`--approve` is required for activation.

The dataset format is:

```json
{
  "schema_version": 2,
  "artifact_type": "eval_dataset",
  "id": "bugfix-llm-eval",
  "cases": [
    {
      "id": "q-001",
      "input": "What is the failure mode here?",
      "expected_contains": "checks and retries"
    }
  ]
}
```

## 3) Autonomous flow

When autopilot is enabled, Steward runs `og sync` from hooks/daemon/CI.
`og status` is the primary check for freshness, pending work, and verification state.

## 4) Safety defaults

Default mode is safe-by-default (`observe`):

- updates `.outcomegraph/**`
- updates generated agent-facing exports
- does not edit product code unless explicitly opted into broader modes

## 5) What is canonical

Tracked in Git (compact truth):

- constitutions
- capsules
- refs
- decisions
- certificates
- generated guidance exports

Not tracked by default:

- raw traces
- bulky logs
- local caches

For details, contracts, schemas, and architecture, use [SPEC-v2.md](./SPEC-v2.md).
