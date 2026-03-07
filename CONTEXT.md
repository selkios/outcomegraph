# CONTEXT

OutcomeGraph canonical agent guidance contract.

- Contract version: 1
- CLI version: 0.1.0
- JSON envelope schema_version: 1
- Canonical artifact schema_version: 2
- Generated projection: `.outcomegraph/export/AGENTS.md`

## Automation boundary
- Use `og` as the stable interface for status, sync, verify, replay, export, and daemon flows.
- Treat `.outcomegraph/**` as canonical truth and `.outcomegraph/export/**` as derived control surfaces.
- Default automation mode is `observe`; do not edit product code unless command mode and policy explicitly allow it.
- Discover machine contracts with `og schema` and `og describe <command>` before constructing unattended calls.

## Required request patterns
- Use `--json` for machine callers and branch on top-level `status`, `errors`, and `data`.
- Narrow large payloads with `--fields`, `--limit`, `--offset`, or `--output jsonl` before requesting list-heavy data.
- For mutating commands, run `--validate` or `--dry-run` when you need a no-write preview or recovery check.
- Destructive or privileged actions require explicit confirmation flags such as `--yes`; never infer confirmation from context.
- In `--strict` mode, unknown payload keys, lossy coercions, and missing required values are contract violations; fix the request instead of retrying loosely.
- Use `--non-interactive` for unattended runs so commands fail instead of waiting for prompts.

## Safe command sequence
1. `og status --json`
2. `og schema` or `og describe <command>`
3. `og <command> --validate --json` or `og <command> --dry-run --json` before writes
4. `og <command> --json`
5. `og verify --changed --json` and `og replay --changed --json` for stronger confirmation when needed

## Write boundaries
- Safe by default: update `.outcomegraph/**`, refresh generated control surfaces, and run configured verification commands.
- Require explicit policy or confirmation: hook changes, cleanup operations, daemon lifecycle actions, dependency changes, and application-code edits.
- Never treat generated exports or skill files as canonical data sources.
