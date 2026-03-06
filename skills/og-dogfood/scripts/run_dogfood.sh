#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(pwd)}"
repo_root="$(cd "$repo_root" && pwd)"

if [[ ! -f "$repo_root/pyproject.toml" || ! -f "$repo_root/og" ]]; then
  echo "error: expected an OutcomeGraph source checkout at $repo_root" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required to run the dogfood flow" >&2
  exit 1
fi

run_json() {
  local label="$1"
  local outfile="$2"
  shift 2
  echo "==> $label"
  (
    cd "$repo_root"
    "$@" | tee "$outfile"
  )
}

run_stdout() {
  local label="$1"
  shift
  echo "==> $label"
  (
    cd "$repo_root"
    "$@"
  )
}

run_text() {
  local label="$1"
  local outfile="$2"
  shift 2
  echo "==> $label"
  (
    cd "$repo_root"
    "$@" | tee "$outfile"
  )
}

echo "Repo: $repo_root"

run_stdout "clean" uv run og clean --scope all --yes --json
run_stdout "init" uv run og init --json

events_dir="$repo_root/.outcomegraph/events"
mkdir -p "$events_dir"

run_json "status (pre-sync)" "$events_dir/dogfood-status-pre-sync.json" uv run og status --json
run_json "sync" "$events_dir/dogfood-sync.json" uv run og sync --json
run_json "verify" "$events_dir/dogfood-verify.json" uv run og verify --changed --json
run_json "replay" "$events_dir/dogfood-replay.json" uv run og replay --changed --json
run_text "drift" "$events_dir/dogfood-drift.txt" uv run og drift
run_json "status (final)" "$events_dir/dogfood-status-final.json" uv run og status --json
cp "$events_dir/dogfood-status-final.json" "$events_dir/dogfood-status.json"

echo "==> validate"
(
  cd "$repo_root"
  uv run python - <<'PY'
import json
from pathlib import Path

root = Path(".outcomegraph/events")
status_path = root / "dogfood-status.json"
sync_path = root / "dogfood-sync.json"
verify_path = root / "dogfood-verify.json"
replay_path = root / "dogfood-replay.json"
drift_path = root / "dogfood-drift.txt"

status = json.loads(status_path.read_text(encoding="utf-8"))
sync = json.loads(sync_path.read_text(encoding="utf-8"))
verify = json.loads(verify_path.read_text(encoding="utf-8"))
replay = json.loads(replay_path.read_text(encoding="utf-8"))
drift = drift_path.read_text(encoding="utf-8")

errors = []

if status.get("status") != "ok":
    errors.append("dogfood-status.json: top-level status is not ok")
if status.get("data", {}).get("issues") != []:
    errors.append("dogfood-status.json: issues is not empty")
if status.get("data", {}).get("runtime", {}).get("status") != "idle":
    errors.append("dogfood-status.json: runtime.status is not idle")

sync_steps = [step.get("name") for step in sync.get("data", {}).get("steps", [])]
required_sync_steps = {"distill", "apply", "verify", "export"}
if sync.get("status") != "ok":
    errors.append("dogfood-sync.json: top-level status is not ok")
if not required_sync_steps.issubset(sync_steps):
    errors.append(
        "dogfood-sync.json: missing required sync steps "
        + ", ".join(sorted(required_sync_steps - set(sync_steps)))
    )

verified_capsules = verify.get("data", {}).get("verified_capsules", [])
if verify.get("status") != "ok":
    errors.append("dogfood-verify.json: top-level status is not ok")
if not isinstance(verified_capsules, list) or not verified_capsules:
    errors.append("dogfood-verify.json: verified_capsules is empty")

replay_results = replay.get("data", {}).get("replay_results", [])
if replay.get("status") != "ok":
    errors.append("dogfood-replay.json: top-level status is not ok")
if not isinstance(replay_results, list) or not replay_results:
    errors.append("dogfood-replay.json: replay_results is empty")

if "drift: ok" not in drift:
    errors.append("dogfood-drift.txt: missing 'drift: ok'")
if "POLICY_DENIED" in drift:
    errors.append("dogfood-drift.txt: contains POLICY_DENIED")

if errors:
    print("FAIL: dogfood evidence failed validation.")
    for item in errors:
        print(f"- {item}")
    raise SystemExit(1)

print("PASS: dogfood evidence is healthy.")
print(f"status: {status_path}")
print(f"sync: {sync_path}")
print(f"verify: {verify_path}")
print(f"replay: {replay_path}")
print(f"drift: {drift_path}")
PY
)
