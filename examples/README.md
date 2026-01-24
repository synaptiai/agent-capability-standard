# Examples

## 10-minute quickstart
Run the compiler-grade validator on the reference workflows:

```bash
cd reference/claude_world_modeling_skill_system
python3 tools/validate_workflows.py
```

Optional: emit suggested patch diffs for coercions:
```bash
python3 tools/validate_workflows.py --emit-patch
```

