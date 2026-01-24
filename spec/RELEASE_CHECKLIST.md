# Release checklist (world-class)

This is the minimum bar for *credible publication*.

## 0) Decide publication mode
- **Open Standard + reference implementation** (recommended)
- Whitepaper only (weak for adoption)
- Academic paper (strong credibility but slower)

## 1) IP + licensing
- Choose license (Apache-2.0 recommended for standard + tooling)
- Ensure third-party assets are compatible
- Add `LICENSE`, `NOTICE`, `COPYRIGHT`

## 2) Specification completeness
- `STANDARD-v1.0.0.md` must define:
  - Terms, core concepts, invariants
  - Canonical schemas
  - Workflow semantics
  - Conformance requirements
  - Error model
  - Versioning and compatibility policy

## 3) Reference implementation
- Validator CLI
- Example workflows
- Example schema set
- Deterministic transform registry + mapping stubs

## 4) Conformance test suite
- Positive/negative fixtures
- Automated CI run
- Badge + reproducibility

## 5) Security posture
- Threat model
- Safe-by-construction invariants
- Disclosure process

## 6) Documentation UX
- 10-minute quickstart
- 30-minute tutorial
- Reference docs
- Glossary

## 7) Distribution
- GitHub repo + Releases
- Version tags
- Release notes
- Optional: PyPI / npm packages for validator

## 8) Comms
- Whitepaper
- Announcement post
- 5-slide deck
- FAQ

## Done criteria
- A new user can validate a sample workflow in <10 minutes.
- The standard is coherent without reading the code.
- Conformance tests cover the main failure modes.

