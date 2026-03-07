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

Standalone `verify` and `replay` now refresh exported summaries automatically, so `og drift`
should remain clean after either command when policy and verification both pass.

Use `og explain` to inspect what changed, why, and evidence pointers.

You can also discover per-command contracts at any time:

```bash
og --help
og sync --help
og daemon --help
og daemon run --help
og schema
og describe sync
```

Headless defaults for CI/agents:

```bash
export OG_DEFAULT_OUTPUT=json
export OG_DEFAULT_PROFILE=analyze
export OG_DEFAULT_MODE=observe
```

Optional path overrides:

```bash
export OG_CONFIG_PATH=.outcomegraph/config.yaml
export OG_POLICY_PATH=.outcomegraph/policy.yaml
export OG_CODEX_HOME="$HOME/.codex"
```

Precedence is `CLI flags > env vars > .outcomegraph/config.yaml`.

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
      "expected_contains": ["checks and retries"]
    }
  ]
}
```

## 3) Autonomous flow

When autopilot is enabled, Steward runs the local quality pass from `pre-commit`
and `og sync` from hooks/daemon/CI.
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

## 6) Full-spec rollout validation (dogfood)

Run this sequence as a release-readiness gate:

```bash
uv run og status --json
uv run og sync --json
uv run og verify --changed --json
uv run og drift
```

Expected outputs before rollout:

```text
status: ok
sync:  status: ok with steps [distill, apply, verify, export]
verify: status: ok with steps [verify, export] and verified_capsules present
drift:  no blocking policy or certificate regressions
```

Observed rollout evidence in this repository:

- `.outcomegraph/events/sync-20260305T082953Z-8485041f63.json`
- `.outcomegraph/events/sync-20260305T092058Z-9008c47e88.json`
- `.outcomegraph/events/verify-20260305T092059Z-a1789787d4.json`

Known migration blocker discovered during dogfood:

- `.outcomegraph/materials.lock` missing `artifact_type` caused validation errors.
- Fix per `MIGRATION_GUIDE.md` and rerun the full sequence.
