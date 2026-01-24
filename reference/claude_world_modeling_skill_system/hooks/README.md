# Claude Code hooks: production templates

Below are **rigorous** hooks intended to enforce safety, provenance, and quality.

> Note: Hook configuration keys/events vary by Claude Code version.
> Treat this as a *reference implementation* and adapt to your local config schema.

## Hook goals

1) **Block secret access** (prevents leaks)
2) **Require checkpoints** before destructive tool use
3) **Auto-format** after edits
4) **Log tool usage** for audit trails
5) **Detect prompt injection patterns** before tool execution

## Recommended lifecycle coverage

- PreToolUse: block secrets, injection detection, checkpoint requirement
- PostToolUse: logging, formatting
- PermissionRequest: enforce allow/deny logic
- Stop/SubagentStop: finalize audit log

## Scripts included

- `scripts/pretooluse_block_secrets.sh`
- `scripts/pretooluse_detect_injection.sh`
- `scripts/pretooluse_require_checkpoint.sh`
- `scripts/posttooluse_format_repo.sh`
- `scripts/posttooluse_log_tool.sh`

## Policy philosophy (non-negotiable)

- **Least privilege**: allow the smallest toolset possible
- **Evidence-first**: require provenance logging for changes
- **Rollback ready**: checkpoints before mutation
