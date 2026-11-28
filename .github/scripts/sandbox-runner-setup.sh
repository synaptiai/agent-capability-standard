#!/usr/bin/env bash
# Prepares a hosted runner for sandboxed commands and checks that srt can
# start a sandbox there as the runner's user. The boundary jobs run it
# after srt is installed.
#
# On Linux, srt runs a command in bubblewrap, and its seccomp helper makes
# a second user namespace inside the first one. On ubuntu-latest on
# 2026-11-27, with kernel.apparmor_restrict_unprivileged_userns set to 0,
# bubblewrap started but the helper failed: "apply-seccomp: write
# /proc/self/setgroups (nested userns is capability-restricted; caller must
# provide CAP_SYS_ADMIN): Permission denied". Which AppArmor setting causes
# that on the runner has not been confirmed. This script lifts the
# candidates where they are in force:
# - kernel.apparmor_restrict_unprivileged_userns and
#   kernel.apparmor_restrict_unprivileged_unconfined;
# - an AppArmor profile for bwrap (such as bwrap-userns-restrict), which
#   can move the commands bubblewrap starts to a profile with no
#   capabilities.
# It prints what it found, then runs a probe like the suite's runtime
# fixture: a write inside allowWrite must succeed and a write outside it
# must be refused.
set -euo pipefail

if [ "$(uname -s)" = Linux ]; then
  for k in apparmor_restrict_unprivileged_userns apparmor_restrict_unprivileged_unconfined; do
    f="/proc/sys/kernel/$k"
    if [ -r "$f" ]; then
      echo "kernel.$k=$(cat "$f")"
      if [ "$(cat "$f")" != 0 ]; then
        sudo sysctl -w "kernel.$k=0"
      fi
    else
      echo "$f is absent"
    fi
  done
  echo "AppArmor profiles for bubblewrap or user namespaces in /etc/apparmor.d:"
  found=0
  for p in /etc/apparmor.d/*bwrap* /etc/apparmor.d/*userns*; do
    [ -e "$p" ] || continue
    echo "$p"
    found=1
  done
  [ "$found" = 1 ] || echo "(none)"
  for p in /etc/apparmor.d/bwrap-userns-restrict /etc/apparmor.d/bwrap; do
    if [ -f "$p" ]; then
      echo "Unloading $p"
      sudo apparmor_parser -R "$p" || echo "::warning::$p could not be unloaded (it may not be loaded)"
    fi
  done
  echo "Loaded AppArmor profiles that name bwrap or userns:"
  sudo aa-status 2> /dev/null | grep -i -E 'bwrap|userns' || echo "(none)"
  bwrap --version
fi

srt=${ACS_SRT:-srt}
base=$(mktemp -d "${RUNNER_TEMP:-/tmp}/srt-probe.XXXXXX")
base=$(cd "$base" && pwd -P)
mkdir "$base/inside" "$base/outside"
printf '{"network":{"allowedDomains":[],"deniedDomains":[]},"filesystem":{"denyRead":[],"allowWrite":["%s"],"denyWrite":[]}}\n' \
  "$base/inside" > "$base/c.json"
status=0
(cd "$base/inside" && "$srt" --settings "$base/c.json" -c "echo ok > '$base/inside/a'; echo x > '$base/outside/b'") \
  > "$base/out.txt" 2>&1 || status=$?
if [ -e "$base/outside/b" ]; then
  echo "::error::srt ran the probe but did not confine it: a write outside allowWrite succeeded"
  exit 1
fi
if [ ! -f "$base/inside/a" ]; then
  echo "::error::srt cannot start a sandbox as $(id -un) on this runner (exit $status)"
  cat "$base/out.txt"
  if [ "$(uname -s)" = Linux ]; then
    sudo aa-status 2> /dev/null || true
    sudo dmesg 2> /dev/null | grep -i apparmor | tail -20 || true
  fi
  exit 1
fi
echo "srt starts a sandbox as $(id -un)"
