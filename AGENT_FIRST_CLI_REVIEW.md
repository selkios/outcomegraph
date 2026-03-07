# Agent-First CLI Review (OutcomeGraph `og`)

Date: 2026-03-05  
Scope: `/home/agent/outcomegraph`

## Review Team

1. Contract Agent: command/flag/help stability.
2. Output Agent: machine-readable output envelope/streaming.
3. Error Agent: typed errors and exit-code semantics.
4. Input + Introspection Agent: payload inputs, strictness, schema discovery.
5. Ops + Safety Agent: non-interactive usage, recovery, state/session, security, guidance, metrics.

## Top Findings (Priority Order)

1. `--help` contract is command-complete for top-level and nested commands.
2. JSON output uses a single, versioned, command-level envelope for all command results and failures.
3. Error payloads are now typed with `error_class`, `error_code`, and bounded `retryable`/`hint` metadata.
4. Runtime introspection is now first-class via `schema` and `describe`, with request/response metadata discoverable for each command.
5. Path inputs for `optimize prompts` are constrained to repository-safe paths.

## Checklist Results

| Checklist Area | Status | Evidence | Notes |
|---|---|---|---|
| 1) CLI surface contract | Done | `og.py` and tests in `tests/test_og_sync_verify_replay_hooks.py` | `og <command> --help` now dispatches per-command usage contracts, and nested dispatches (`optimize`, `autopilot`, `daemon`) include `help` coverage including `daemon run`. |
| 2) Structured output + unambiguous success | Done | [`og.py`](./og.py) | `--json` now emits a single contract envelope with `schema_version`, `command`, `status`, `run_id`, `data`, `errors`, `warnings`, and `metrics` for command/help/error paths across all commands. |
| 3) Error model + exit codes | Done | [`og.py:1169`](./og.py#L1169), [`README.md:135`](./README.md#L135), [`SPEC-v2.md:198`](./SPEC-v2.md#L198), [`tests/test_og_sync_verify_replay_hooks.py:670`](./tests/test_og_sync_verify_replay_hooks.py#L670) | Error payload now includes stable typed metadata (`error_class`, `error_code`, `retryable`, `hint`), envelope rendering normalizes `errors` to object records, and exit mapping uses `error_class` semantics. |
| 4) Agent-oriented input design | Done | [`og.py:6312`](./og.py#L6312), [`og.py:6729`](./og.py#L6729), [`tests/test_og_sync_verify_replay_hooks.py:48`](./tests/test_og_sync_verify_replay_hooks.py#L48), [`tests/test_og_sync_verify_replay_hooks.py:531`](./tests/test_og_sync_verify_replay_hooks.py#L531), [`README.md:132`](./README.md#L132), [`SPEC-v2.md:173`](./SPEC-v2.md#L173) | Added `--params` payload mode for `optimize prompts`, global/command strict mode support, and schema/help coverage for strict+payload controls. |
| 5) Runtime introspection | Done | [`og.py:899`](./og.py#L899), [`og.py:10643`](./og.py#L10643), [`og.py:10716`](./og.py#L10716), [`og.py:11270`](./og.py#L11270) | `schema` and `describe` now provide machine-readable command signatures for discovery and per-command introspection. |
| 6) Context/window + payload controls | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Added `--fields`, `--limit`, `--offset`, and `--output jsonl` for verify/replay/explain/mcp-server, plus deterministic pagination and streaming metadata tests. |
| 7) Interaction traps | Done | [`og.py:5984`](./og.py#L5984), [`og.py:5999`](./og.py#L5999) | `autopilot init --force-hooks-path` now requires explicit `--yes`, and global `--non-interactive` is available. No command paths now depend on interactive confirmation. |
| 8) Recovery tooling | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`RUNBOOKS.md`](./RUNBOOKS.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | `sync`, `verify`, `replay`, and `export` now expose explicit `--validate` / `--dry-run` preflight contracts; `og doctor` ships machine-readable diagnostics; and retry/timeout controls plus recovery summaries are available for worker/oracle/replay execution paths. |
| 9) Explicit state/session | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Lock, daemon, and autopilot flows now declare explicit session lifecycles, emit `session_id`, and return typed session errors for contention, expiry, and invalid resume attempts. |
| 10) Security + safety for agent failure modes | Done | [`og.py:3684`](./og.py#L3684), [`og.py:3708`](./og.py#L3708), [`og.py:3738`](./og.py#L3738), [`og.py:6262`](./og.py#L6262), [`og.py:6665`](./og.py#L6665) | Hardened agent-supplied identifiers and dataset/candidate/baseline paths. IDs are strict allowlisted, and user-supplied optimization paths now enforce repository-relative, traversal-free, control-char-free, and percent-decoding-free validation. |
| 11) Agent guidance shipped with binary | Partial | [`.outcomegraph/export/AGENTS.md`](./.outcomegraph/export/AGENTS.md), [`skills/outcome-steward/SKILL.md`](./skills/outcome-steward/SKILL.md) | Guidance exists, but it is export-generated and not a stable top-level, versioned agent contract file like `CONTEXT.md`. |
| 12) Optional multi-surface support | Partial | [`og.py:165`](./og.py#L165), [`og.py:4036`](./og.py#L4036) | Has env-var hooks (`OG_ADAPTER_PATH`, signer env) and MCP control-surface payload command, but no env default for output mode and not a full typed stdio MCP server contract. |
| 13) AI-native outcome metrics | Fail | [`og.py:9231`](./og.py#L9231) | Per-run timing exists, but no tracked agent-centric metrics (schema-valid rate, command-per-task, recovery rate, session churn). |

## Quick Runtime Checks Performed

1. `./og --help`: top-level usage shown.
2. `./og <core-command> --help`: command-specific usage contracts with accepted options/output/exit sections.
3. `./og daemon --help`, `./og autopilot --help`, and `./og daemon run --help`: render dedicated help contracts.
4. `./og status --output json --json`: `--output` is rejected (exit `64`).
5. `./og status --json`, `./og mcp-server --json`, `./og clean --scope runtime --dry-run --json`, `./og daemon status --json`: machine-readable payloads emitted.
6. `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`: 109 tests passed.
