## Summary

<What does this change do?>

## PVC (Perspective Validation Checklist)

- PVC report (recommended for changes to `schemas/`, `hooks/`, `skills/`, `grounded_agency/`, `tools/`, or `spec/`):
  - `docs/reviews/pvc/<YYYY-MM-DD>_<slug>.pvc.yaml`

## Validation

- [ ] `python tools/validate_workflows.py` (if workflows changed)
- [ ] `python scripts/run_conformance.py` (optional)
- [ ] `python skills/perspective-validation/scripts/validate_pvc.py` (optional)

## Notes / Risks

<Any migrations, rollouts, backwards compat, or known limitations?>

