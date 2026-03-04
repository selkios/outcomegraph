# OutcomeGraph

OutcomeGraph is a Git-native artifact graph for replayable software, with Steward as the always-on sidecar that keeps artifacts current.

## Start here

- Main specification: [SPEC-v2.md](./SPEC-v2.md)

## Core idea

- Code is a materialization.
- Artifacts are durable truth.
- Steward keeps truth in sync.

## Documentation index (v2.1)

- [SPEC-v2.md](./SPEC-v2.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [PLUGIN_API.md](./PLUGIN_API.md)
- [RUNBOOKS.md](./RUNBOOKS.md)
- [SECURITY_POLICY.md](./SECURITY_POLICY.md)
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md)
- [QUICKSTART.md](./QUICKSTART.md)

## CLI contract

`og` is the stable execution boundary for humans, agents, CI, and MCP clients.

```bash
og init
og sync
og verify --changed
og replay --changed
og status
og export
og explain
og drift
og mcp-server
og optimize prompts
og autopilot init
og autopilot disable
og daemon install|start|stop|status   # command aliases for ogd

ogd install|start|stop|status        # dedicated daemon wrappers
```

Common options:

- `--profile {analyze|propose|apply}`
- `--mode {observe|autonomous}`
- `--changed` (for changed-scope operations)
- `--json` for machine-readable results and errors

Optimization workflow:

- `og optimize prompts` evaluates `candidate` and `baseline` prompt files against an evaluation dataset.
- Output artifacts are stored under `.outcomegraph/datasets/`:
  - `opt-<dataset-id>-<hash>.json` (evaluation result)
  - `<dataset-id>-prompt-pack.json` (active pack, only when `--approve` passes threshold)
- Promotion is intentionally manual-first for this experimental path; threshold success alone does not activate the pack unless `--approve` is used.

Schema versioning:

- Canonical `.outcomegraph` artifacts are v2:
  `schema_version: 2` plus `artifact_type` and required core fields.
- Commands validate on read/write that artifact versions are supported.
- Legacy versions (for example v1) and mixed-version directories are rejected with a clear migration hint.

## Exit codes

- `0` success
- `1` runtime/implementation failure
- `64` usage/validation failure

Use `--json` with CI callers to get parseable success/error payloads.
