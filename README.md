# Agent Capability Standard (v1.0.0)

A comprehensive capability ontology and skill library for AI agents, providing 103 composable skills across 8 layers with workflow composition, world modeling, and safety primitives.

**Status:** Candidate Standard v1.0.0
**Release date:** 2026-01-24

## Installation (Claude Code Plugin)

```bash
# Install as a Claude Code plugin
claude plugin install https://github.com/danielbentes/agent-capability-standard

# Or clone and install locally
git clone https://github.com/danielbentes/agent-capability-standard.git
claude plugin install ./agent-capability-standard
```

## What's Included

### 103 Skills Across 8 Layers

| Layer | Count | Purpose |
|-------|-------|---------|
| PERCEPTION | 4 | Observe the world (inspect, search, retrieve, receive) |
| MODELING | 45 | Build understanding (detect, identify, estimate, forecast, world-state) |
| REASONING | 20 | Think and decide (compare, plan, decide, critique, explain) |
| ACTION | 12 | Change things (act, generate, transform, send) |
| SAFETY | 8 | Protect and verify (verify, checkpoint, rollback, audit, constrain) |
| META | 6 | Self-reflection (discover, discover-relationship) |
| MEMORY | 1 | Persistence (recall) |
| COORDINATION | 3 | Multi-agent (delegate, synchronize, invoke-workflow) |
| + WORKFLOWS | 4 | Composed multi-step skills |

See [skills/README.md](./skills/README.md) for the complete skill index.

### Schemas & Ontology

- **Capability Ontology** - 99 atomic capabilities with input/output schemas, layer assignments, and prerequisites
- **Workflow Catalog** - Composable workflows with bindings, gates, and recovery loops
- **World State Schema** - Grounded observations with provenance and uncertainty
- **Trust & Identity Policies** - Authority ranking, alias scoring, merge/split

### Safety Hooks

Hooks implementing SAFETY layer capabilities from the spec:
- `pretooluse_require_checkpoint.sh` - Enforce checkpoint before mutations (implements `checkpoint` capability)
- `posttooluse_log_tool.sh` - Audit trail logging (implements `audit` capability)

### Validation Tools

```bash
# Validate workflow definitions
python tools/validate_workflows.py

# Generate patch suggestions
python tools/validate_workflows.py --emit-patch

# Run conformance tests
python scripts/run_conformance.py
```

## Directory Structure

```
agent-capability-standard/
├── plugin.json              # Plugin manifest
├── settings.json            # Plugin settings
├── skills/                  # 103 skills by layer
│   ├── perception/          # 4 skills
│   ├── modeling/            # 45 skills
│   ├── reasoning/           # 20 skills
│   ├── action/              # 12 skills
│   ├── safety/              # 8 skills
│   ├── meta/                # 6 skills
│   ├── memory/              # 1 skill
│   ├── coordination/        # 3 skills
│   └── workflows/           # 4 composed workflows
├── hooks/                   # 2 spec-aligned safety hooks
├── schemas/                 # Ontology + workflow + world state schemas
│   └── transforms/          # Type coercion mappings
├── tools/                   # Workflow validator
├── templates/               # Shared skill templates
├── spec/                    # Standard documentation
├── examples/                # Usage examples
└── tests/                   # Conformance fixtures
```

## Documentation

- **Standard Specification:** `spec/STANDARD-v1.0.0.md`
- **RFC Motivation:** `spec/RFC-0001-agent-capability-ontology-and-workflow-dsl.md`
- **Whitepaper:** `spec/WHITEPAPER.md`
- **Conformance Tests:** `spec/CONFORMANCE.md`
- **Governance:** `spec/GOVERNANCE.md`
- **Security Model:** `spec/SECURITY.md`

## Quick Start

```python
# Example: Invoke a skill programmatically
from pathlib import Path
import yaml

skill_path = Path("skills/modeling/detect/SKILL.md")
content = skill_path.read_text()
# Parse YAML frontmatter and execute workflow
```

```bash
# Example: Use via Claude Code
claude> /agent-capability-standard:detect-anomaly input.json
```

## Contributing

See `spec/GOVERNANCE.md` for contribution guidelines.

## License

See [LICENSE](./LICENSE) for details.
