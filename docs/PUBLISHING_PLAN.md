# Publishing plan (v1.0.0)

## Target
Ship an open standard + reference implementation with CI-backed conformance.

## Contents
- `spec/` — standard + RFC + whitepaper + governance + security + conformance
- `reference/` — v10 reference implementation (validator + schemas + workflows)
- `conformance_fixtures/` — negative/positive fixtures for validator
- `scripts/run_conformance.py` — CI test runner
- `.github/workflows/conformance.yml` — GitHub Actions pipeline

## Release steps
1) Create GitHub repo (public)
2) Push this repo
3) Confirm Actions passes
4) Tag `v1.0.0`
5) Create GitHub Release:
   - attach `reference/` bundle zip (optional)
   - link spec docs
6) Announce using `docs/PRESS_KIT.md`

