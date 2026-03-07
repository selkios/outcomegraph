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
4. Runtime introspection is now first-class via `schema` and `describe`, with the same command signatures also embedded into MCP tool descriptors.
5. Path inputs for `optimize prompts` are constrained to repository-safe paths.

## Checklist Results

| Checklist Area | Status | Evidence | Notes |
|---|---|---|---|
| 1) CLI surface contract | Done | `og.py` and tests in `tests/test_og_sync_verify_replay_hooks.py` | `og <command> --help` now dispatches per-command usage contracts, and nested dispatches (`optimize`, `autopilot`, `daemon`) include `help` coverage including `daemon run`. |
| 2) Structured output + unambiguous success | Done | [`og.py`](./og.py) | `--json` now emits a single contract envelope with `schema_version`, `command`, `status`, `run_id`, `session_id`, `data`, `errors`, `warnings`, and `metrics` for command/help/error paths across all commands. |
| 3) Error model + exit codes | Done | [`og.py:1169`](./og.py#L1169), [`README.md:135`](./README.md#L135), [`SPEC-v2.md:198`](./SPEC-v2.md#L198), [`tests/test_og_sync_verify_replay_hooks.py:670`](./tests/test_og_sync_verify_replay_hooks.py#L670) | Error payload now includes stable typed metadata (`error_class`, `error_code`, `retryable`, `hint`), envelope rendering normalizes `errors` to object records, and exit mapping uses `error_class` semantics. |
| 4) Agent-oriented input design | Done | [`og.py:6312`](./og.py#L6312), [`og.py:6729`](./og.py#L6729), [`tests/test_og_sync_verify_replay_hooks.py:48`](./tests/test_og_sync_verify_replay_hooks.py#L48), [`tests/test_og_sync_verify_replay_hooks.py:531`](./tests/test_og_sync_verify_replay_hooks.py#L531), [`README.md:132`](./README.md#L132), [`SPEC-v2.md:173`](./SPEC-v2.md#L173) | Added `--params` payload mode for `optimize prompts`, global/command strict mode support, and schema/help coverage for strict+payload controls. |
| 5) Runtime introspection | Done | [`og.py:899`](./og.py#L899), [`og.py:10643`](./og.py#L10643), [`og.py:10716`](./og.py#L10716), [`og.py:11270`](./og.py#L11270) | `schema` and `describe` now provide machine-readable command signatures for discovery and per-command introspection. |
| 6) Context/window + payload controls | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Added `--fields`, `--limit`, `--offset`, and `--output jsonl` for verify/replay/explain/mcp-server, plus deterministic pagination and streaming metadata tests. |
| 7) Interaction traps | Done | [`og.py:5984`](./og.py#L5984), [`og.py:5999`](./og.py#L5999) | `autopilot init --force-hooks-path` now requires explicit `--yes`, and global `--non-interactive` is available. No command paths now depend on interactive confirmation. |
| 8) Recovery tooling | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`RUNBOOKS.md`](./RUNBOOKS.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | `sync`, `verify`, `replay`, and `export` now expose explicit `--validate` / `--dry-run` preflight contracts; `og doctor` ships machine-readable diagnostics; and retry/timeout controls plus recovery summaries are available for worker/oracle/replay execution paths. |
| 9) Explicit state/session | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Lock, daemon, and autopilot flows now declare explicit session lifecycles, emit `session_id`, and surface typed session errors for contention, expiry, and invalid resume attempts in both `data` and top-level `errors`. |
| 10) Security + safety for agent failure modes | Done | [`og.py:3684`](./og.py#L3684), [`og.py:3708`](./og.py#L3708), [`og.py:3738`](./og.py#L3738), [`og.py:6262`](./og.py#L6262), [`og.py:6665`](./og.py#L6665) | Hardened agent-supplied identifiers and dataset/candidate/baseline paths. IDs are strict allowlisted, and user-supplied optimization paths now enforce repository-relative, traversal-free, control-char-free, and percent-decoding-free validation. |
| 11) Agent guidance shipped with binary | Done | [`CONTEXT.md`](./CONTEXT.md), [`.outcomegraph/export/AGENTS.md`](./.outcomegraph/export/AGENTS.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | A canonical top-level `CONTEXT.md` now ships with the repo, pins contract and schema versions, documents safe automation patterns, and the generated `AGENTS.md` export is projection-tested against it. |
| 12) Optional multi-surface support | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`QUICKSTART.md`](./QUICKSTART.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Added headless defaults via `OG_DEFAULT_OUTPUT`, `OG_DEFAULT_PROFILE`, `OG_DEFAULT_MODE`, preferred path vars `OG_CONFIG_PATH` / `OG_POLICY_PATH` (with legacy `*_FILE` aliases), and `OG_CODEX_HOME`, with deterministic precedence (`CLI > env > config`) and source metadata echoed in command options. CLI signatures now also drive the exported MCP tool surface so `schema`/`describe` and `mcp-server` stay in lockstep. |
| 13) AI-native outcome metrics | Done | [`og.py`](./og.py), [`README.md`](./README.md), [`RUNBOOKS.md`](./RUNBOOKS.md), [`SPEC-v2.md`](./SPEC-v2.md), [`tests/test_og_sync_verify_replay_hooks.py`](./tests/test_og_sync_verify_replay_hooks.py) | Command envelopes now emit `metrics.agent_reliability` with the current observation plus rolling snapshot; sync/verify/replay/drift/optimize summary events capture the same snapshot; and `status` / `doctor` surface the tracked commands-per-successful-task, schema-valid output rate, retry auto-recovery rate, and resumable session churn contract. |

## Quick Runtime Checks Performed

1. `./og --help`: top-level usage shown.
2. `./og <core-command> --help`: command-specific usage contracts with accepted options/output/exit sections.
3. `./og daemon --help`, `./og autopilot --help`, and `./og daemon run --help`: render dedicated help contracts.
4. `./og status --output json --json`: `--output` is rejected (exit `64`).
5. `./og status --json`, `./og mcp-server --json`, `./og clean --scope runtime --dry-run --json`, `./og daemon status --json`: machine-readable payloads emitted.
6. `python3 -m unittest -q tests.test_og_sync_verify_replay_hooks`: 109 tests passed.
