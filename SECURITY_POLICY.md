# Security Policy (v2.1)

Status: Draft v2.1  
Date: 2026-03-04  
Source: [SPEC-v2.md](./SPEC-v2.md), [README.md](./README.md)

## 1) Default model

Default execution mode is safe-by-default (`observe`).
Only bounded-safe actions are allowed without explicit mode expansion.

Default safe model:

- allow `mode: observe` artifact updates and generated exports
- allow read-only verification and sandbox execution where configured
- deny application code writes, dependency mutation, deployment actions, and unrestricted network by default

## 2) Policy file

Default policy file (if present): `.outcomegraph/policy.yaml`

Expected shape:

```yaml
schema_version: 2
mode: observe
policy_id: observe-default-v1
allow:
  file_writes:
    - ".outcomegraph/**"
    - "export/**"
    - "skills/outcome-steward/**"
  verify_commands:
    - "npm test --listTests"
    - "npm test"
    - "npm test*"
    - "go test ./..."
    - "go test ./...*"
    - "pytest -q"
    - "pytest -q*"
    - "uv run --with pytest --no-project pytest -q*"
    - "uv run --with pytest pytest -q*"
    - "uv run pytest -q*"
    - "python -m unittest -q*"
    - "python3 -m unittest -q*"
  sandbox_operations:
    - create_isolated_worktree
    - read_repo_state
    - read_artifacts
deny:
  file_writes:
    - "src/**"
    - "lib/**"
    - "app/**"
    - "packages/**"
  network:
    - unrestricted
  dependencies:
    - npm install
    - pip install
    - cargo add
    - go mod tidy
  deployment:
    - push
    - git commit --amend
    - github pr create
```

## 3) Enforcement order

- explicit deny always wins
- explicit allow enables action in active mode
- missing allow entries block by default with `POLICY_DENIED`
- `AUTONOMOUS_WRITE_BLOCKED` is returned when writes are requested in `autonomous` mode while policy is degraded or integrity cannot be validated.

## 3b) CLI input safety

- `og` treats agent-supplied IDs (`--capsule`, `--ref`, `--certificate`) as untrusted input and rejects values with:
  - unsupported characters outside `[a-z0-9._-]`,
  - control characters,
  - malformed percent-encoding,
  - empty values, or values that exceed policy limits.
- `og` treats prompt optimization paths (`--dataset`, `--candidate`, `--baseline`) as untrusted input and rejects values that are absolute, traverse outside the repository, include control characters, or include percent-encoding.
- On input violations, commands fail closed with usage-level exit and explicit error messaging.

## 4) Error and remediation

When denied, `og` must emit error payload with:

- `status: error`
- `code: POLICY_DENIED`
- `command`, `mode`, and `category`
- `target` and remediation suggestions

For policy schema violations or unreadable policy files, use usage-like exit code `64`.

Autonomous writes are also suspended when the integrity ledger is not in `ok` health until a repair action restores trust.

## 5) Policy extension and updates

- keep policy documents in `.outcomegraph/policy.yaml`
- validate `schema_version: 2`
- prefer repository allowlist extension over global defaults
- commit intentional policy changes to preserve auditability

## 6) Operational checks

Before running write actions in `observe` mode, `og` resolves effective mode and evaluates policy.
Unsafe actions must not silently succeed.
