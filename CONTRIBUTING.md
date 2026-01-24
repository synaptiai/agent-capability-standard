# Contributing to Agent Capability Standard

Thank you for your interest in contributing to the Agent Capability Standard.

## Governance

This project follows a formal RFC process for changes. See [`spec/GOVERNANCE.md`](./spec/GOVERNANCE.md) for:
- Versioning policy (SemVer)
- Compatibility rules
- Decision-making process
- How to propose changes via RFC

## How to Contribute

### Reporting Issues

- Use GitHub Issues for bug reports and feature requests
- Include clear reproduction steps for bugs
- Reference specific skills or schemas when applicable

### Proposing Changes

1. Open an RFC issue describing:
   - Motivation for the change
   - Alternative approaches considered
   - Backward compatibility analysis
   - Required conformance test updates

2. Draft implementation in a feature branch
3. Ensure all conformance tests pass:
   ```bash
   python scripts/run_conformance.py
   ```
4. Validate workflows:
   ```bash
   python tools/validate_workflows.py
   ```
5. Submit a pull request

### Adding Skills

New skills must:
- Follow the template in `templates/SKILL_TEMPLATE_ENHANCED.md`
- Include valid capability references from `schemas/capability_ontology.json`
- Define clear input/output contracts
- Include workflow references where applicable

### Code Style

- YAML files: 2-space indentation
- Markdown files: CommonMark compatible
- Shell scripts: `shellcheck` compliant

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
