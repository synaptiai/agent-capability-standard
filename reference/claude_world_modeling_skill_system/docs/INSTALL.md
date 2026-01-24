# Install & use (Claude Code)

## 1) Skill libraries

You now have:
- `claude_capability_skill_library/` (atomic skills)
- `claude_world_modeling_skill_system/` (ontology + workflows + composed skills + hooks)

### Recommended layout in your repo

```
.claude/
  skills/
    <atomic skills copied here>
    <composed skills copied here>
  refs/
  hooks/
```

## 2) Enable hooks

Copy scripts from:
- `hooks/scripts/` → your `.claude/hooks/scripts/`

Then configure Claude Code to run:
- PreToolUse: block_secrets, detect_injection, require_checkpoint
- PostToolUse: log_tool, format_repo

## 3) Use the ontology

The ontology is your planning backbone:
- Pick a workflow goal
- Traverse required edges
- Run capability skills in sequence
- Enforce verification and rollback for high-risk steps

## 4) Start with these commands

- `/world-model-workflow` to model a domain/system
- `/debug-workflow` to fix code safely
- `/gap-analysis-workflow` to identify missing skills
