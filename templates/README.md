# Templates

This directory contains templates and shared patterns for skill development.

## Available Templates

| Template | Purpose |
|----------|---------|
| `SKILL_TEMPLATE_ENHANCED.md` | Complete skill template with all sections |
| `capability_atoms.md` | Reference list of atomic capability names |
| `output_contracts.md` | Quick reference for output contract types |
| `output_contracts_full.md` | Comprehensive output contract documentation |
| `composition_patterns.md` | Patterns for composing skills into workflows |
| `verification_patterns.md` | Patterns for skill verification and testing |

## Creating a New Skill

1. Copy `SKILL_TEMPLATE_ENHANCED.md` to your skill directory:
   ```bash
   cp templates/SKILL_TEMPLATE_ENHANCED.md skills/<layer>/<skill-name>/SKILL.md
   ```

2. Fill in required sections:
   - **Frontmatter**: name, layer, capabilities, inputs, outputs
   - **Description**: What the skill does
   - **Workflow**: Steps and bindings

3. Reference `capability_atoms.md` for valid capability names

4. Use `output_contracts.md` for output type definitions

## Composition Patterns

See `composition_patterns.md` for:
- Sequential composition
- Parallel execution
- Conditional branching
- Recovery loops
- Gate patterns

## Validation

After creating a skill, validate it:
```bash
python tools/validate_workflows.py
```
