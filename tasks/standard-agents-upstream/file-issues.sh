#!/usr/bin/env bash
# File the issue texts in this folder in standardagents/spec.
#
#   ./file-issues.sh            list what would be filed (nothing is created)
#   ./file-issues.sh --file     create the issues, in the order below
#   ./file-issues.sh --file 06  create only issue 06
#
# Needs the GitHub CLI (gh), signed in as the account the issues should come
# from. Each file is one issue: its first line is the title, the rest is the
# body. An issue whose title already exists in the repository is skipped, so
# the script can be run again after a failure.
set -euo pipefail

REPO="standardagents/spec"
# 06 first: it is small and asks for nothing. Then 01, which matters most.
ORDER=(06 01 07 09 02 03 04 05 08 10 11 12)

cd "$(dirname "$0")"
mode="list"
only=""
for arg in "$@"; do
  case "$arg" in
    --file) mode="file" ;;
    [0-9][0-9]) only="$arg" ;;
    *) echo "usage: $0 [--file] [NN]" >&2; exit 2 ;;
  esac
done

for number in "${ORDER[@]}"; do
  if [[ -n "$only" && "$only" != "$number" ]]; then continue; fi
  file=$(ls "$number"-*.md)
  title=$(head -n 1 "$file" | sed 's/^# //')
  if [[ "$mode" == "list" ]]; then
    printf '%s  %s\n' "$file" "$title"
    continue
  fi
  existing=""
  while IFS=$'\t' read -r found_title found_url; do
    if [[ "$found_title" == "$title" ]]; then existing="$found_url"; break; fi
  done < <(gh issue list --repo "$REPO" --state all --limit 200 \
    --json title,url --jq '.[] | [.title, .url] | @tsv')
  if [[ -n "$existing" ]]; then
    printf 'exists   %s  %s\n' "$number" "$existing"
    continue
  fi
  # The body is read in full before gh runs, so a failed read files nothing.
  # BSD sed (macOS) needs the ';' before '}'.
  body=$(tail -n +2 "$file" | sed '1{/^$/d;}')
  if [[ -z "$body" ]]; then
    echo "empty body: $file; nothing filed" >&2
    exit 1
  fi
  url=$(printf '%s\n' "$body" | gh issue create --repo "$REPO" --title "$title" --body-file -)
  printf 'filed    %s  %s\n' "$number" "$url"
done

if [[ "$mode" == "list" ]]; then
  echo
  # The texts link this repository at one commit; set it to main's head on
  # the day of filing (see README.md, Filing).
  # grep exits 1 when no text has a pinned link; that is not an error here.
  pinned=$( { grep -ho 'synaptiai/agent-capability-standard/\(tree\|blob\)/[0-9a-f]\{40\}' \
    [0-9][0-9]-*.md || true; } | sed 's#.*/##' | sort -u | tr '\n' ' ')
  echo "Links into this repository are pinned to: ${pinned:-none}"
  echo "Nothing was created. Run with --file to create these issues in $REPO."
fi
