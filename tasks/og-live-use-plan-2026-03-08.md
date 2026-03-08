# OutcomeGraph Live Use Plan (End-User Walkthrough)

Date: 2026-03-08
Repo: /home/agent/outcomegraph
Goal: Exercise OutcomeGraph the same way an end user would, from clean slate to steady-state operation.

## Paths read to build this plan
- /home/agent/outcomegraph/README.md
- /home/agent/outcomegraph/QUICKSTART.md
- /home/agent/outcomegraph/RUNBOOKS.md
- Live command contract via `./og --help` and `./og clean --help`
- Current runtime baseline via `./og status --json`

## Paths this walkthrough writes
- /home/agent/outcomegraph/.outcomegraph/**
- /home/agent/outcomegraph/skills/outcome-steward/SKILL.md
- /home/agent/outcomegraph/.outcomegraph/events/dogfood-*.json
- /home/agent/outcomegraph/.outcomegraph/events/dogfood-drift.txt

## Phase 0: Environment sanity

```bash
cd /home/agent/outcomegraph
uv --version
uv run og --version
uv run og --help
```

Pass criteria:
- `uv run og` commands execute without command-not-found errors.

## Phase 1: Full clean bootstrap (true first-use simulation)

```bash
cd /home/agent/outcomegraph
uv run og clean --scope all --yes --json
uv run og init --json
uv run og status --json
```

Pass criteria:
- `clean` returns `status: "ok"`.
- `init` returns `status: "ok"`.
- `status` no longer reports uninitialized runtime.

## Phase 2: Core manual user loop (recommended default)

```bash
cd /home/agent/outcomegraph
uv run og sync --json
uv run og status --json
uv run og verify --changed --json
uv run og replay --changed --json
uv run og drift --json
```

Pass criteria:
- `sync` ends with `status: "ok"` and includes `distill`, `apply`, `verify`, `export` steps.
- `verify --changed` ends `status: "ok"` with non-empty `verified_capsules` when changes exist.
- `replay --changed` ends `status: "ok"` with non-empty `replay_results` when changes exist.
- `drift` reports clean/non-blocking state.

## Phase 3: Evidence capture (dogfood-quality run)

```bash
cd /home/agent/outcomegraph
uv run og status --json > .outcomegraph/events/dogfood-status-pre-sync.json
uv run og sync --json > .outcomegraph/events/dogfood-sync.json
uv run og verify --changed --json > .outcomegraph/events/dogfood-verify.json
uv run og replay --changed --json > .outcomegraph/events/dogfood-replay.json
uv run og drift > .outcomegraph/events/dogfood-drift.txt
uv run og status --json > .outcomegraph/events/dogfood-status-final.json
cp .outcomegraph/events/dogfood-status-final.json .outcomegraph/events/dogfood-status.json
```

Pass criteria:
- `.outcomegraph/events/dogfood-status.json` has top-level `status: "ok"`, runtime `idle`, and `issues: []`.
- `.outcomegraph/events/dogfood-sync.json` has top-level `status: "ok"`.
- `.outcomegraph/events/dogfood-verify.json` has top-level `status: "ok"`.
- `.outcomegraph/events/dogfood-replay.json` has top-level `status: "ok"`.
- `.outcomegraph/events/dogfood-drift.txt` does not contain `POLICY_DENIED`.

## Phase 4: Diagnostics and recovery drill (simulate real ops)

Run only if any phase above is not `ok`.

```bash
cd /home/agent/outcomegraph
uv run og doctor --json
uv run og sync --validate --json
uv run og verify --changed --validate --json
uv run og replay --changed --dry-run --json
```

Pass criteria:
- `doctor` provides actionable remediation and no unresolved hard blocker after fixes.

## Phase 5: Optional autonomous mode (end-user ops hardening)

```bash
cd /home/agent/outcomegraph
uv run og autopilot init --non-interactive --yes
uv run og daemon install
uv run og daemon start
uv run og daemon status --json
```

Pass criteria:
- daemon reports healthy/running state.
- subsequent `uv run og status --json` stays green while repo changes are processed.

## Suggested one-shot execution order for this repo today

Because the current baseline is warning after clean, run in this order:
1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4 only if needed
5. Phase 5 only if you want autonomous operation

## Notes for this repository state (2026-03-08)
- Current `status` shows warnings caused by missing certificates and out-of-sync exports after cleanup.
- First `uv run og sync --json` is expected to resolve those warnings by regenerating runtime artifacts and exports.
