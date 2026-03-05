#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
REPO_ROOT="${1:-$DEFAULT_REPO_ROOT}"
VENV_BIN="${REPO_ROOT}/.venv/bin"

if [[ ! -x "${VENV_BIN}/ruff" || ! -x "${VENV_BIN}/ty" || ! -x "${VENV_BIN}/pytest" ]]; then
  echo "Missing required tools in ${VENV_BIN}."
  echo "Install with:"
  echo "  ${REPO_ROOT}/.venv/bin/pip install ruff ty pytest"
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

run_step "ruff" "${VENV_BIN}/ruff" check og.py tests
run_step "ty" "${VENV_BIN}/ty" check --output-format concise
run_step "pytest" "${VENV_BIN}/pytest" -q

if [[ "${FAILURES}" -eq 0 ]]; then
  echo "PASS: all quality checks succeeded."
  exit 0
fi

echo "FAIL: one or more quality checks failed."
exit 1
