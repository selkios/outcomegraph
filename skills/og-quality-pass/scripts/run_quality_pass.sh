#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
REPO_ROOT="${1:-$DEFAULT_REPO_ROOT}"
VENV_BIN="${REPO_ROOT}/.venv/bin"

resolve_tool() {
  local tool_name="$1"
  local candidates=(
    "${VENV_BIN}/${tool_name}"
    "/usr/bin/${tool_name}"
    "/usr/local/bin/${tool_name}"
    "${tool_name}"
  )
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  echo ""
  return 1
}

RUFF_BIN="$(resolve_tool ruff || true)"
TY_BIN="$(resolve_tool ty || true)"
PYTEST_BIN="$(resolve_tool pytest || true)"

if [[ -z "$RUFF_BIN" || -z "$TY_BIN" || -z "$PYTEST_BIN" ]]; then
  echo "Missing required tools: ruff, ty, or pytest."
  echo "Hint: install in venv with '${REPO_ROOT}/.venv/bin/pip install ruff ty pytest' or use a Python environment containing them."
  exit 2
fi

if [[ ! -f "${REPO_ROOT}/og.py" || ! -d "${REPO_ROOT}/tests" ]]; then
  echo "Repository layout check failed at ${REPO_ROOT}."
  echo "Expected og.py and tests/ directory."
  exit 2
fi

FAILURES=0

run_step() {
  local label="$1"
  shift
  echo "==> ${label}"
  echo "CMD: $*"
  if (cd "${REPO_ROOT}" && "$@"); then
    echo "OK: ${label}"
  else
    local rc=$?
    echo "FAIL(${rc}): ${label}"
    FAILURES=1
  fi
  echo
}

run_step "ruff" "$RUFF_BIN" check og.py tests
run_step "ty" "$TY_BIN" check --output-format concise
run_step "pytest" "$PYTEST_BIN" -q

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "PASS: all quality checks succeeded."
  exit 0
fi

echo "FAIL: one or more quality checks failed."
exit 1
