#!/usr/bin/env bash
# Example hook: block access to common secret paths.
# You would wire this via Claude Code hooks config (PreToolUse).
# This script should print a message and exit non-zero to block.

payload="$1"
echo "$payload" | grep -E -i "(\.env|id_rsa|ssh/|aws_?credentials|gcp|azure|secrets?)" >/dev/null
if [ $? -eq 0 ]; then
  echo "Blocked: potential secret path detected."
  exit 1
fi
exit 0
