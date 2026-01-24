# Composed skills

These are workflow-level skills that orchestrate atomic capabilities.

They assume the atomic skill library exists (e.g. `claude_capability_skill_library/`).
You can either:
- copy these into your skills directory, or
- treat them as reference playbooks.

- `digital-twin-sync-workflow/` — digital twin sync loop (ingest → update → drift → act → verify → audit)
