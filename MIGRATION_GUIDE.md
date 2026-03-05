# Migration Guide (v2.1)

Status: Draft v2.1  
Date: 2026-03-04  
Source: [SPEC-v2.md](./SPEC-v2.md)

## 1) Scope

This guide covers repository migration into OutcomeGraph artifact schema v2 and adapter policy requirements.

OutcomeGraph v2 requires:

- canonical artifacts at schema version `2`
- explicit `artifact_type` and required core fields
- adapter manifests with `schema_version: 2`
- strict mixed-version rejection

## 2) Preflight audit

1. Record current repository `.outcomegraph` inventory.
2. Identify files with missing/unsupported schema version.
3. Record `og --version` and adapter manifest versions.
4. Capture baseline with:
   - `og status`
   - last successful sync summary
   - last successful verification event

## 3) Migration path v1 -> v2

OutcomeGraph does not perform silent auto-upgrade for canonical artifacts.
Recommended approach:

1. Back up repository branch.
2. Export or snapshot legacy artifacts as-is.
3. Recreate each canonical artifact with v2 keys:
   - `schema_version: 2`
   - `artifact_type`
   - required identifiers and timestamps
4. Validate canonical fields against section 7 of [SPEC-v2.md](./SPEC-v2.md).
5. Update policy manifest(s) and adapter manifests where required.

After migration, run:

- `og sync`
- `og verify --changed`

and confirm no mixed-version or schema violations remain.

## 4) Mixed-version and unsupported artifact handling

- Missing `schema_version` or `schema_version < 2`: fail fast and block writes.
- Mixed `.outcomegraph` schema versions: fail fast with hard error.
- `schema_version > 2`: refuse until runtime supports higher interface.

In all cases, migration must be explicit and rerun schema checks after fix.

## 5) Adapter migration

For each adapter:

- verify manifest has `schema_version: 2`
- verify `interface_version` for `worker`, `oracle`, `sandbox`, `store`, `exporter` equals `1`
- replace incompatible adapters before first post-migration runtime run

If an adapter is optional, keep degraded feature mode and unblock when safe.

### 3a) Dogfood migration blocker: `materials.lock` artifact_type

This repository surfaced a rollout-blocking schema mismatch:

- `.outcomegraph/materials.lock` had `schema_version: 2` but lacked `artifact_type`.
- Validation failed with `expected 'materials_lock' for this path and schema_version 2`.

Expected canonical shape:

```json
{
  "schema_version": 2,
  "artifact_type": "materials_lock",
  "material_paths": [],
  "notes": "bootstrap-generated materials lock",
  "created_at": "..."
}
```

Repair command:

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path('.outcomegraph/materials.lock')
data = json.loads(path.read_text(encoding='utf-8'))
data['artifact_type'] = 'materials_lock'
path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
PY
```

## 6) Post-migration validation

Expected clean state:

- `og status` healthy and fresh
- no `POLICY_DENIED` for canonical safe writes
- no adapter mismatch errors
- `og sync` can complete end-to-end with generated exports updated
- `og verify --changed` and `og replay --changed` complete on scoped candidates

For this rollout, archive evidence by ensuring:

- `RUNBOOKS`-captured `dogfood-*.json` files are status `ok`
- migration failure events are gone from current run IDs
