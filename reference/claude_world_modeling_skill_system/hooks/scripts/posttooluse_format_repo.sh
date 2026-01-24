#!/usr/bin/env bash
# Post-edit formatter: run formatters if present.
# Safe best-effort: never fail the pipeline.
set +e
if [ -f "package.json" ]; then
  if command -v npm >/dev/null 2>&1; then
    npm run -s format >/dev/null 2>&1
  fi
fi
if [ -f "pyproject.toml" ]; then
  if command -v ruff >/dev/null 2>&1; then
    ruff format . >/dev/null 2>&1
  fi
fi
exit 0
