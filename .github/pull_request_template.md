## Summary

<What does this change do?>

## PVC (Perspective Validation Checklist)

- PVC report (required when changing `schemas/`, `hooks/`, `skills/`, `grounded_agency/`, `tools/`, or `spec/`):
  - `docs/reviews/pvc/<YYYY-MM-DD>_<slug>.pvc.yaml`

## Validation

- [ ] `python scripts/run_conformance.py`
- [ ] `python tools/validate_workflows.py` (if workflows changed)
- [ ] `python tools/validate_pvc.py`

## Notes / Risks

<Any migrations, rollouts, backwards compat, or known limitations?>

