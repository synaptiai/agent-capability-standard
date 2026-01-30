# PVC Review Reports

This folder stores **Perspective Validation Checklist (PVC)** reports used for socio-technical and governance review of changes to core artifacts (e.g., `schemas/`, `skills/`, `hooks/`, `grounded_agency/`, `tools/`, `spec/`).

## Naming

Use a predictable filename:

`YYYY-MM-DD_<short-slug>.pvc.yaml`

Example:

`2026-01-29_operationalize-pvc.pvc.yaml`

## How to write a report

1. Start from `skills/perspective-validation/pvc_report_template.yaml`
2. Fill scores (PASS / PARTIAL / FAIL / N/A) with evidence references
3. Add remediation actions for any FAIL/PARTIAL

## Validation

Run:

```bash
python skills/perspective-validation/scripts/validate_pvc.py
```

Reports can be validated locally. Including a PVC report for changes to critical paths is recommended but not enforced by CI.

