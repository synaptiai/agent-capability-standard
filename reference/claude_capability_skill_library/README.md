# Claude capability skill library

This is a generated **Claude Code skills** library: one folder per capability.

## Structure
- `_shared/` contains reusable templates, references, hooks, and scripts.
- `dis_level4/` contains the 8 top-level verbs.
- `dis_level3/` contains the 44 action+inference “atoms”.
- `missing_atoms/` contains the expanded agentic + world-modeling atoms.

## Conventions
- Each folder is a Claude Code skill folder containing `SKILL.md`.
- Skill names are kebab-case and match folder names.
- Most skills run in `context: fork` for isolation.
- High-risk skills (act/rollback) are `agent: general-purpose` and allow more tools.

## Next step
1) Pick a subset to harden.
2) Add examples, reference docs, and deterministic scripts.
3) Add hooks in your Claude Code settings to enforce safety and formatting.
