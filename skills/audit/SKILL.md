---
name: audit
description: Produce a comprehensive audit trail of actions, tools used, changes made, and decision rationale. Use when recording compliance evidence, tracking changes, or documenting decision lineage.
argument-hint: "[event] [context] [retention]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # Code-decided check (STANDARD 1.2.0 §5.18.10): an audit record appended
            # to .claude/audit/records.jsonl holds no credential (§6.7). The records
            # file is written in one form only, whose record this hook reads; any
            # other command is read word by word, as the shell passes the words, and
            # may not write a file, run a program that could (an interpreter, an
            # in-place editor, cp, tee, dd, ...), or build its text when it runs. So a
            # file named with quotes or a glob, a record rewritten in two steps, or one
            # a program writes, is refused, whether or not its text names the file.
            # Claude Code passes the tool call as JSON on stdin, read once here; exit 2
            # blocks the call and the reason on stderr is shown to Claude. A call that
            # cannot be read is blocked.
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # A record is appended in one form only, whose text is the record:
            #   printf '%s\n' '<json>' >> "${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl"
            # (or >> .claude/audit/records.jsonl), on one line, <json> one JSON
            # object with no single quote. Any other command that names the file
            # may not build or redirect text: a $ (but in ${CLAUDE_PROJECT_DIR:-.}),
            # a backtick, a backslash, < or > would let the record's text be
            # computed when the command runs, where no scan of the command sees it.
            # The form is read with a case pattern and the removal of a literal
            # prefix and suffix, whose cost grows with the line alone: a pattern
            # removal such as ${REST#*\'} costs the line times itself when no
            # quote follows, so a long line would hold the hook past its time.
            FORM="printf '%s\n' '"
            RECORD=""
            for TO in "' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\"" "' >> .claude/audit/records.jsonl"; do
              case "$CMD" in
                "$FORM"*"$TO")
                  RECORD="${CMD#"$FORM"}"
                  RECORD="${RECORD%"$TO"}"
                  break
                  ;;
              esac
            done
            NL='
            '
            case "$RECORD" in *\'* | *"$NL"*) RECORD="" ;; esac
            if [ -n "$RECORD" ]; then
              # The record as a reader decodes it: its JSON text with escapes
              # resolved (g is g) and each of its strings
              DECODED="$(printf '%s' "$RECORD" | jq -rs 'if length == 1 and (.[0] | type) == "object" then .[0] | (tojson, (.. | strings)) else error("not one object") end' 2>/dev/null)" || {
                echo "F504 CONSTRAINT_VIOLATED: the audit record is not one JSON object; append it as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\"" >&2
                exit 2
              }
              # A member name given twice: jq keeps the last value, so the earlier
              # ones are never scanned, though the file holds them (I-JSON names are
              # unique). The values the text holds, as jq's stream reads them, against
              # those of the object jq keeps.
              STREAMED="$(printf '%s' "$RECORD" | jq -n --stream '[inputs | select(length == 2)] | length' 2>/dev/null)" || STREAMED="unread"
              KEPT="$(printf '%s' "$RECORD" | jq '[tostream | select(length == 2)] | length' 2>/dev/null)" || KEPT="unkept"
              if [ "$STREAMED" != "$KEPT" ]; then
                echo "F504 CONSTRAINT_VIOLATED: the audit record is not one JSON object with unique member names (I-JSON): a name given twice hides a value from this check; append it as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\"" >&2
                exit 2
              fi
            else
              # Skill hooks stay registered for the rest of the session, so only a
              # command that may name the records file is read: one that names records,
              # jsonl, audit or .claude in any quoting (quotes and backslashes removed),
              # that runs in a directory under .claude, or that holds a glob character
              # (read below: a glob that may match the records file)
              RUNS_IN="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)" || RUNS_IN=""
              [ -n "$RUNS_IN" ] || RUNS_IN="$(pwd)"
              NAMED=false
              INAUDIT=false
              printf '%s\n' "$CMD" | tr -d "\"'\\\\" | grep -qiE 'records|jsonl|audit|\.claude' && NAMED=true
              printf '%s\n' "$RUNS_IN" | grep -qi '\.claude' && INAUDIT=true
              if [ "$NAMED" = false ] && [ "$INAUDIT" = false ]; then
                case "$CMD" in
                  *'*'* | *'?'* | *'['*) ;;
                  *) exit 0 ;;
                esac
              fi
              case "$CMD" in
                *records.jsonl*)
                  LITERAL="$(printf '%s' "$CMD" | sed 's/[$]{CLAUDE_PROJECT_DIR:-[.]}//g')"
                  case "$LITERAL" in
                    *'$'* | *'`'* | *'\'* | *'<'* | *'>'*)
                      echo "F504 CONSTRAINT_VIOLATED: a command that names the audit records file may not expand, escape or redirect text, so a record built when it runs is never written unchecked; append a record only as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\", with the record literal (STANDARD 1.2.0 §6.7)" >&2
                      exit 2
                      ;;
                  esac
                  ;;
              esac
              DECODED=""
              # Any other command, read word by word (jq reads one of up to 16384
              # bytes in well under a second)
              READER="$(cat <<'JQ'
            # BEGIN shell-words (source: hooks/shell_words.jq; tests/test_skill_hooks.py keeps every copy equal)
            # A Bash command's simple commands and their words as the shell passes them,
            # quotes removed. Each word: raw (as written), d (dequoted), m (dequoted, an
            # unquoted glob character *, ?, [ or ] as \u0001), braces (an unquoted brace
            # outside ${...}), assign (NAME=value), target (a redirection's target) and
            # writes (the redirection writes). commands gives {why, cmds}: why names
            # what this reading cannot follow (an unclosed quote, a here-document, a
            # process substitution), else is null. jq's global match costs the text
            # times its matches, so the caller bounds the command's length.
            def unquoted_globs: [explode[] | if . == 42 or . == 63 or . == 91 or . == 93 then 1 else . end] | implode;
            def segments: [scan("'[^']*'|\"[^\"]*\"|[^'\"]+")]
              | map(if startswith("'") then {q: true, sq: true, t: .[1:-1]}
                    elif startswith("\"") then {q: true, sq: false, t: .[1:-1]}
                    else {q: false, sq: false, t: .} end);
            def word($raw): ($raw | segments) as $s
              | {raw: $raw,
                 d: ($s | map(.t) | add // ""),
                 m: ($s | map(if .q then .t else (.t | unquoted_globs) end) | add // ""),
                 braces: ($s | any((.q | not) and (.t | gsub("\\$\\{[^}]*\\}"; "") | test("[{}]")))),
                 assign: ($raw | test("^[A-Za-z_][A-Za-z0-9_]*\\+?="))};
            def tokens: [match("(?<op>\n|&&|\\|\\||;;|[0-9]*(?:<<<|<<-?|<>|>>|>\\||>&|<&|&>>?|[<>])(?:[0-9]+-?|-)?|[;&|()])|(?<comment>#[^\n]*)|(?<word>(?:[^\\s'\"|&;()<>]|'[^']*'|\"[^\"]*\")+)|(?<bad>['\"])"; "g")
              | .captures | map(select(.string != null)) | .[0] | {(.name): .string}] | map(select(.comment | not));
            # A redirection whose target is the next word (2>&1 and >&- name none).
            def takes_target: test("[<>]") and (test("&([0-9]+-?|-)$") | not);
            # Each step is linear in the command: no list grows by copying.
            def commands: tokens as $t | ($t | length) as $n
              | if any($t[]; .bad) then {why: "quote"}
                elif any($t[]; .op and (.op | test("<<")) and (.op | test("<<<") | not)) then {why: "heredoc"}
                elif any(range(1; $n); ($t[. - 1].op // "" | test("[<>]$")) and $t[.].op == "(") then {why: "process substitution"}
                else [range(0; $n) as $i | $t[$i]
                      | if .word then
                          ($t[$i - 1].op // "") as $op
                          | word(.word) + {target: ($i > 0 and ($op | takes_target)),
                                           writes: ($i > 0 and ($op | takes_target) and ($op | test(">")))}
                        else . end] as $w
                | ([-1] + [range(0; $n) | select($t[.].op and ($t[.].op | test("[<>]") | not))] + [$n]) as $b
                | {why: null, cmds: [range(0; ($b | length) - 1) as $k | $w[$b[$k] + 1:$b[$k + 1]] | map(select(.d != null)) | select(length > 0)]}
                end;
            # END shell-words
            # The programs a command may run here: none writes a file but by a
            # redirection, which is refused below, and none runs other code.
            def readers: ["cat", "echo", "printf", "jq", "ls", "head", "tail", "wc", "grep", "cut", "tr", "base64", "sha256sum", "shasum", "md5sum", "date", "hostname", "sleep", "test", "true", "false", "pwd", "cd", "stat", "basename", "dirname", "mkdir", "mv", "openssl"];
            def sinks: ["/dev/null", "/dev/stdout", "/dev/stderr"];
            def basename_ci: ascii_downcase | sub("/+$"; "") | sub("^.*/"; "");
            def literal_path: gsub("\\$\\{CLAUDE_PROJECT_DIR:-\\.\\}"; ".");
            def sensitive: test("^(PATH|ENV|BASH_ENV|IFS|CDPATH|LD_[A-Z0-9_]*|DYLD_[A-Z0-9_]*|OPENSSL_[A-Z0-9_]*)$");
            def openssl_writes: test("^-(out|engine|provider|config|writerand|rand)");
            # Whether a word with a glob character (marked \u0001) may name the
            # records file, .claude/audit/records.jsonl, from the directory the command
            # runs in: each of its last components may match the file's, and the
            # directories it leaves out are the last ones of that directory. A glob
            # character matches any run here (more than the shell's), but not a name's
            # leading dot.
            def glob_part($pattern): . as $name | ($pattern | ascii_downcase) as $p
              | (($name | startswith(".")) and ($p | startswith("\u0001")) | not)
                and ($name | test("^" + ($p | gsub("(?<c>[.+*?()^$|{}\\[\\]\\\\])"; "\\\(.c)") | gsub("\u0001"; ".*")) + "$"));
            def may_name_records($cwd): split("/") | map(select(. != "" and . != ".")) as $parts
              | [".claude", "audit", "records.jsonl"] as $file
              | ([$parts | length, 3] | min) as $k
              | any($parts[]; . == "..")
                or (all(range(0; $k); . as $i | $parts[($parts | length) - 1 - $i] as $p | ($file[2 - $i] | glob_part($p))))
                    and ($k == 3 or ($cwd | ascii_downcase | rtrimstr("/") | endswith("/" + ($file[:3 - $k] | join("/")))));
            # The first refusal of a simple command, or null.
            def check_command($words):
              ($words | map(select(.target | not))) as $args
              | (first(range(0; $args | length) | select($args[.].assign | not)) // ($args | length)) as $p
              | if $p == ($args | length) then
                  (first($args[] | select(.raw | sub("\\+?=.*$"; "") | sensitive)) // null) as $bad
                  | if $bad != null then {kind: "assign", word: $bad.raw} else null end
                elif $p > 0 then {kind: "assign", word: $args[0].raw}
                else $args[0].d as $prog
                | if ($prog | test("[/$]")) or (any(readers[]; . == $prog) | not) then {kind: "program", word: $prog}
                  elif $prog == "openssl" then
                    (first($args[1:][] | select(.d | startswith("-") | not)) // {d: ""}) as $sub
                    | if $sub.d != "dgst" then {kind: "program", word: "openssl \($sub.d)"}
                      else (first($args[1:][] | select(.d | openssl_writes)) // null) as $w
                      | if $w != null then {kind: "program", word: "openssl dgst \($w.d)"} else null end
                      end
                  elif $prog == "mv" then
                    [$args[1:][] | select(.d | startswith("-") | not)] as $ops
                    | if any($args[1:][]; .d | startswith("-") and (test("^-[fniv]+$") | not))
                         or ($ops | length) != 2
                         or any($ops[]; (.m | test("\u0001")) or (.d | literal_path | test("[$`]")))
                         or ($ops[0].d | literal_path | basename_ci) != "records.jsonl"
                         or ($ops[1].d | literal_path | basename_ci | test("^records\\.[^/]+\\.jsonl$") | not)
                      then {kind: "mv", word: ($args | map(.d) | join(" "))}
                      else null end
                  else null end
                end;
            .tool_input.command // ""
            | if utf8bytelength > 16384 then "long "
              elif [scan("'[^']*'|\"[^\"]*\"|[^'\"]+")] | map(select(startswith("'") | not)) | add // "" | test("\\$\\(|`|\\\\") then "subst "
              else commands as $c
              | if ($named | not) and ($inaudit | not) and ($c.why == null)
                   and (any($c.cmds[][]; .m | test("\u0001") and (may_name_records($cwd) or (sub("^[^=]*="; "") | may_name_records($cwd)))) | not) then "ok"
                elif $c.why == "process substitution" then "subst "
                elif $c.why != null then "expands \($c.why)"
                elif any($c.cmds[][]; .braces) then "expands an unquoted brace"
                else (first($c.cmds[][] | select(.writes and (.d as $t | any(sinks[]; . == $t) | not))) // null) as $w
                | if $w != null then "writes \($w.d | .[:200])"
                  else (first($c.cmds[] | check_command(.) | select(. != null)) // null) as $r
                  | if $r == null then "ok" else "\($r.kind) \($r.word | .[:200])" end
                  end
                end
              end
            JQ
            )"
              VERDICT="$(printf '%s' "$INPUT" | jq -r --arg cwd "$RUNS_IN" --argjson named "$NAMED" --argjson inaudit "$INAUDIT" "$READER" 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: the audit skill's check could not read the command" >&2; exit 2; }
              KIND="${VERDICT%% *}"
              WORD="${VERDICT#* }"
              ONE_FORM="append a record only as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\", with the record literal (STANDARD 1.2.0 §6.7)"
              case "$KIND" in
                ok) ;;
                writes) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command writes a file only in the one append form, whose record this check reads; it does not redirect output to '$WORD' (a name quoted, globbed or linked may be the records file): $ONE_FORM" >&2; exit 2 ;;
                program) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command runs only programs that write no file but by a redirection and run no other code (cat, echo, printf, jq, ls, head, tail, wc, grep, cut, tr, base64, sha256sum, shasum, md5sum, date, hostname, sleep, test, true, false, pwd, cd, stat, basename, dirname, mkdir, mv to move the records file aside, openssl dgst), each by its name; it does not run '$WORD', which could write the records file unread: $ONE_FORM" >&2; exit 2 ;;
                mv) echo "F504 CONSTRAINT_VIOLATED: in the audit skill mv only moves the records file aside, as mv <dir>/records.jsonl <dir>/records.<UTC time>.jsonl with literal paths; it does not run '$WORD', which could put another file in its place: $ONE_FORM" >&2; exit 2 ;;
                assign) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command does not set a variable for one command (NAME=value cmd), nor PATH, IFS, ENV, BASH_ENV, CDPATH, LD_*, DYLD_* or OPENSSL_*, which change what a program runs or writes: '$WORD'" >&2; exit 2 ;;
                subst) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command may not substitute a command or a process, or escape text (\$(, a backtick, <(, >( or \\ outside single quotes), since what runs is not what this check reads; run each command on its own, with literal values: $ONE_FORM" >&2; exit 2 ;;
                expands) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command may not hold text whose words this check cannot read ($WORD); $ONE_FORM" >&2; exit 2 ;;
                long) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command other than the append form is read up to 16384 bytes, and this one is longer; $ONE_FORM" >&2; exit 2 ;;
                *) echo "R407 SAFETY_CHECK_FAILED: the audit skill's check could not read the command" >&2; exit 2 ;;
              esac
              # A command that does not name the records file is read; its other
              # text is other hooks' business.
              case "$CMD" in
                *records.jsonl*) ;;
                *) exit 0 ;;
              esac
            fi
            # BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
            # secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7).
            SECRET_ERE='-----BEGIN [A-Z ]*PRIVATE KEY-----|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
            SECRET_KEY='(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
            secret_in() {
              printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
              # A quoted value with no whitespace, 8 or more characters
              printf '%s' "$1" | grep -Eiq -- "$SECRET_KEY[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^[:space:]\"']{8,}[\"']" && return 0
              # The password of a URL's userinfo, unless it is a placeholder
              printf '%s' "$1" | grep -Eo -- '[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]+:[^[:space:]/@]+@' |
                sed -E 's#^[^/]*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
              # An Authorization header's value, 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization[\"']?[[:space:]]*[:=][[:space:]]*[\"']?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
                sed -E "s/^[^:=]*[:=][[:space:]]*[\"']?//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)[\"'][[:space:]]*,[[:space:]]*[\"']?value[\"']?[[:space:]]*[:=][[:space:]]*[\"']((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)[\"'][[:space:]]*,[[:space:]]*[\"']((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}[\"'][[:space:]]*[])]" |
                sed -E "s/[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*[\"']//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # An unquoted value of 12 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "$SECRET_KEY[\"']?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
                sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]'
            }
            # END secret-scan
            if secret_in "$CMD" || secret_in "$DECODED"; then
              echo "F504 CONSTRAINT_VIOLATED: the audit record holds what looks like a credential; cite it by reference or digest (STANDARD 1.2.0 §6.7)" >&2
              exit 2
            fi
            exit 0
    - matcher: "Edit|Write|MultiEdit|NotebookEdit"
      hooks:
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # Code-decided check (STANDARD 1.2.0 §5.18.10, §6.7): the records file is
            # written only in the Bash append form, whose record the Bash hook reads,
            # so an Edit, Write, MultiEdit or NotebookEdit of it, or of another file of
            # .claude/audit/ (the records moved aside), is refused: the path as
            # written and the file it reaches (links followed; a link that cannot be
            # followed is refused), and another name of the records file (a hard
            # link). Claude Code passes the tool call as JSON on stdin; exit 2 blocks
            # the call and the reason on stderr is shown to Claude. A call that cannot
            # be read is blocked.
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            TARGET="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            [ -n "$TARGET" ] || exit 0
            REFUSE="F504 CONSTRAINT_VIOLATED: in the audit skill the records file is written only by appending a record with Bash, as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\", whose record is checked for credentials; an edit or a write of '$TARGET' could change it unread (STANDARD 1.2.0 §6.7)"
            REACHED="$TARGET"
            if [ -L "$TARGET" ]; then
              REACHED="$(readlink -f -- "$TARGET" 2>/dev/null)" || { echo "$REFUSE" >&2; exit 2; }
            elif [ -e "$TARGET" ] || [ -d "$(dirname -- "$TARGET")" ]; then
              REACHED="$(readlink -f -- "$TARGET" 2>/dev/null)" || REACHED="$TARGET"
            fi
            for P in "$TARGET" "$REACHED"; do
              # In lower case (a file system may ignore case), repeated slashes and ./
              # segments removed
              SEEN="$(printf '%s\n' "$P" | tr 'A-Z' 'a-z' | sed -e 's#//*#/#g' -e 's#/\./#/#g' -e 's#^\./##')"
              case "$SEEN" in
                .claude/audit/* | */.claude/audit/* | records.jsonl | */records.jsonl | records.*.jsonl | */records.*.jsonl | *..*.claude* | *.claude*..*)
                  echo "$REFUSE" >&2
                  exit 2
                  ;;
              esac
            done
            # Another name of the records file (a hard link)
            RECORDS="${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl"
            if [ -e "$TARGET" ] && [ -e "$RECORDS" ] && [ "$TARGET" -ef "$RECORDS" ]; then
              echo "$REFUSE" >&2
              exit 2
            fi
            exit 0
---

## Live Context

Current audit context:

- Recent git commits: !`git log --oneline -10 2>/dev/null || echo "No git history"`
- Git authors today: !`git log --since="midnight" --format="%an" 2>/dev/null | sort | uniq -c || echo "None"`
- Uncommitted changes: !`git status --short 2>/dev/null || echo "Not a git repo"`
- Recent file modifications: !`find . -type f -mtime -1 -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' '` files in last 24h
- Tool-call log exists: !`wc -l "${CLAUDE_PROJECT_DIR:-.}/.claude/audit.log" 2>/dev/null || echo "No .claude/audit.log"`
- Audit records exist: !`wc -l "${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl" 2>/dev/null || echo "No .claude/audit/records.jsonl"`
- Checkpoint log exists: !`ls -la .checkpoints/ 2>/dev/null | head -5 || echo "No .checkpoints/ directory"`

## Intent

Execute **audit** to create a structured record of actions taken, tools invoked, changes made, and the reasoning behind decisions. This provides accountability, enables investigation of issues, and supports compliance requirements.

**Success criteria:**
- Complete chronological record of relevant actions
- Every action linked to actor, timestamp, and rationale
- Changes documented with before/after state
- Provenance chain for all outputs

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `event` | Yes | object | Event to record |
| `context` | No | object | Event context |
| `retention` | No | string | How long the record is to be kept in the store it is written to: a duration (STANDARD v1.2 §5.10.1, e.g. `2555d` or `P30D`); absent, the store's own policy applies (§6.3). A literal outside the grammar is W614 |
| `require_record` | No | boolean | The step fails (R402, reason `not_recorded`) unless the record was written, in a workflow that targets 1.2 or later (STANDARD v1.2 §6.4) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Define audit scope**: Determine what to include in the audit
   - Record the `event` itself: what happened, by whom, when
   - Read the report scope from `context.scope` to identify targets
   - Apply the time window in `context.time_window` if provided
   - Identify relevant log sources (git log, tool invocations, file changes)

2) **Collect action records**: Gather all actions within scope
   - Read git log for commits and their messages
   - Review tool invocation history if available
   - Identify file changes (created, modified, deleted)
   - Record timestamps for each action

3) **Extract decision rationale**: Document the "why" for each action
   - Link actions to plans or goals that motivated them
   - Capture assumptions stated before action
   - Record any constraints that influenced decisions

4) **Build provenance chain**: Track inputs to outputs
   - For each output, identify its source inputs
   - Document transformations applied
   - List dependencies between artifacts

5) **Ground claims**: Attach evidence anchors to all audit entries (STANDARD v1.2 §6.5)
   - `{ref: "file:src/app.py:45", kind: file}`, `{ref: "tool:git:<commit>", kind: tool}`; the output's own is the record written, `{ref: "audit:<audit_id>", kind: record}` (§3.1)
   - Cite command outputs by reference or digest, never by copying them (§6.7)

6) **Write the record (append-only)**: Persist the audit record before returning
   - Build one compact JSON line, the output's `record` (Field Definitions): an action record of this skill's own (STANDARD v1.2 §6.4). Redact credentials and PII first, and never copy a member of `event` to the line's top level: an event shaped as a record stays under `details.event`
   - Append it with Bash as a literal, exactly `printf '%s\n' '<json>' >> "${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl"` on one line (no intermediate file: the skill's hook reads it there), after `mkdir -p` of its directory, the project's `.claude/`; refuse a symlink, and never rewrite, truncate or reorder lines. Any other Bash command that names the records file, `.claude` or the audit directory (or runs there, or holds a glob that may match the file) only reads: the skill's hook refuses one that redirects output to a file, runs a program but `cat`, `echo`, `printf`, `jq`, `ls`, `head`, `tail`, `wc`, `grep`, `cut`, `tr`, `base64`, `sha256sum`, `shasum`, `md5sum`, `date`, `hostname`, `sleep`, `test`, `true`, `false`, `pwd`, `cd`, `stat`, `basename`, `dirname`, `mkdir`, `openssl dgst` and the `mv` that moves the file aside, or substitutes a command (`$(...)`); so compute the HMAC and run `hostname -s` in commands of their own, and write values literally. An Edit or a Write of the file is refused too
   - Do not write to `.claude/audit.log`: the plugin's PostToolUse and PostToolUseFailure hooks keep it as an HMAC-chained log of every tool call (checked by `tools/verify_audit_log.py`), and a foreign line would break the chain. The hook appends a call's line only after the call finishes, so there is no line yet for this skill's invocation or for the append itself: cite earlier lines (the calls being audited) as evidence, not these
   - The plugin's PreToolUse hook treats this append as a `mutate` call, since a `>>` redirect writes a file: it is blocked without a valid checkpoint (F501), uses that checkpoint up, and asks for approval (F502). If the append is blocked or fails, set `recorded: false`, return the record in the output anyway, and say why in `assumptions`

7) **Format output**: Structure per audit contract; `recorded` is true only when step 6 appended the line, `record` is that line, and `store` is where it went (Field Definitions)

## Output Contract

Return a structured object:

```yaml
recorded: boolean  # Whether the record was appended to .claude/audit/records.jsonl
record: object  # The action record written (STANDARD v1.2 §6.4)
store:  # Where the record was written (STANDARD v1.2 §6.3, §6.6)
  name: string  # e.g. .claude/audit/records.jsonl
  durability: memory | session | durable  # never durable for a store that does not outlive the session
  retention: string | null  # the duration the store applies (§5.10.1); absent when it keeps records until removed by hand
audit_id: string  # Unique audit record ID
timestamp: string  # ISO 8601 date-time the audit record was generated
audit_record:
  actor: string  # Who/what performed audited actions
  action_type: string  # Category of actions
  targets: array[string]  # What was affected
  outcome: success | failure | partial
changes:
  - type: string  # create, modify, delete, execute
    before: string | null  # Previous state/value
    after: string | null  # New state/value
    location: string  # File path or identifier
    timestamp: string  # When change occurred
tool_usage:
  - tool: string  # Tool name
    invocation_count: integer
    success_rate: number  # 0.0-1.0
    commands: array[string]  # Actual commands if verbose
decision_rationale: string  # Why these actions were taken
provenance:
  inputs: array[string]  # Source data/files
  outputs: array[string]  # Produced artifacts
  dependencies: array[string]  # External dependencies used
confidence: number  # probability that the record was appended as reported (§4.1.1)
evidence_anchors: [{ref: "audit:<audit_id>", kind: record}, {ref: "tool:git:...", kind: tool}, {ref: "file:...", kind: file}]  # the record written grounds the output (STANDARD v1.2 §3.1)
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `recorded` | boolean | Whether the record was appended to `.claude/audit/records.jsonl` (false when the write was blocked or failed) |
| `record` | object | The action record of step 6: `action_id` (the `audit_id`), `timestamp`, `actor: agent`, `intent` (the event's `intent`, else its `event_type`, when a string; else `audit`), `status: executed`, `capability: audit`, `details` (`event`, `context` and `retention` when given, and the collected `audit_record`, `changes` and `provenance`), `recorded_by: {"name": "audit skill"}`, then `prev_hmac` (the `hmac` of the file's last line, empty for the first) and `hmac` (HMAC-SHA-256, as lowercase hex, of the line without `hmac` as `jq -c` prints it, with `openssl dgst -sha256 -hmac` under `AUDIT_HMAC_KEY`, else the default key the plugin's hook and `tools/verify_audit_log.py` use: `grounded-agency-audit-` then the short host name, `hostname -s`, or `default` when there is none). When the last line has no readable `hmac` (a line written before Standard 1.2, which does not verify), do not chain onto it: move the file aside (`records.<UTC time>.jsonl`, same directory) and start a new one, whose first line has `prev_hmac` empty. Each member of `event` stays under `details.event`: it is what the step reported, and cannot claim another writer, an actor, an approval or a place in the chain |
| `store` | object | Where the record was written: the store's `name`, its `durability` (`memory`, `session` or `durable`; a store that does not outlive the session is never reported `durable`) and the `retention` it applies, so a workflow can stop on `${a.store.durability} != 'durable'` (STANDARD v1.2 §6.3, §6.6). This skill's is `{name: ".claude/audit/records.jsonl", durability: durable}`, a file in the project kept until removed by hand, with no `retention` |
| `audit_id` | string | Unique identifier for this audit record |
| `timestamp` | string | ISO 8601 date-time the audit record was generated |
| `audit_record.actor` | string | Who performed the actions |
| `audit_record.outcome` | enum | Overall result of audited actions |
| `changes` | array | List of all changes with before/after |
| `tool_usage` | array | Summary of tools invoked |
| `decision_rationale` | string | Explanation of why actions were taken |
| `provenance` | object | Input/output/dependency lineage |
| `confidence` | number | Probability, 0.0-1.0, that the record was appended as reported (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | References to source evidence |
| `assumptions` | array | What was assumed during audit collection |

## Examples

### Example 1: Audit Code Change Session

**Input:**
```yaml
event:
  type: session_completed
  actor: "claude-agent"
  timestamp: "2024-01-15T16:00:00Z"
context:
  scope: "session"
  time_window:
    start: "2024-01-15T14:00:00Z"
    end: "2024-01-15T16:00:00Z"
  detail_level: standard
  include_diffs: false
```

**Output:**
```yaml
recorded: true
audit_id: "audit_20240115_160000_session"
timestamp: "2024-01-15T16:00:00Z"
audit_record:
  actor: "claude-agent"
  action_type: "code_modification"
  targets:
    - "src/api/handlers/user.py"
    - "src/api/handlers/auth.py"
    - "tests/test_handlers.py"
  outcome: success
changes:
  - type: modify
    before: "get_user() with inline SQL"
    after: "get_user() with parameterized query"
    location: "src/api/handlers/user.py:45-62"
    timestamp: "2024-01-15T14:45:00Z"
  - type: modify
    before: "5 test cases"
    after: "7 test cases (added SQL injection tests)"
    location: "tests/test_handlers.py"
    timestamp: "2024-01-15T15:15:00Z"
tool_usage:
  - tool: Read
    invocation_count: 12
    success_rate: 1.0
  - tool: Edit
    invocation_count: 4
    success_rate: 1.0
  - tool: Bash
    invocation_count: 3
    success_rate: 1.0
    commands: ["pytest tests/", "git diff", "git commit"]
decision_rationale: "Refactored to prevent SQL injection vulnerability identified in security audit. Added parameterized queries and corresponding test coverage."
provenance:
  inputs:
    - "security_audit_report.md"
    - "src/api/handlers/user.py (original)"
  outputs:
    - "src/api/handlers/user.py (modified)"
    - "tests/test_handlers.py (modified)"
  dependencies:
    - "pytest>=7.0"
    - "psycopg2"
confidence: 0.95
evidence_anchors:
  - {ref: "audit:audit_20240115_160000_session", kind: record}
  - {ref: "file:.claude/audit/records.jsonl", kind: file}
  - {ref: "tool:git:abc123def456", kind: tool}
  - {ref: "tool:bash:pytest tests/ - 7 passed", kind: tool}
  - {ref: "file:src/api/handlers/user.py:45", kind: file}
assumptions:
  - "Git log accurately reflects all changes"
  - "No manual edits outside of tracked session"
```

**The line step 6 appends** (with `AUDIT_HMAC_KEY=example-key`; `python tools/verify_audit_log.py --log-file .claude/audit/records.jsonl` checks the chain):

```json
{"action_id":"audit_20240115_160000_session","timestamp":"2024-01-15T16:00:00Z","actor":"agent","intent":"audit","status":"executed","capability":"audit","details":{"event":{"type":"session_completed","actor":"claude-agent","timestamp":"2024-01-15T16:00:00Z"},"context":{"scope":"session"},"audit_record":{"actor":"claude-agent","action_type":"code_modification","targets":["src/api/handlers/user.py"],"outcome":"success"},"changes":[{"type":"modify","location":"src/api/handlers/user.py:45-62","timestamp":"2024-01-15T14:45:00Z"}],"provenance":{"inputs":["security_audit_report.md"],"outputs":["src/api/handlers/user.py"],"dependencies":[]}},"recorded_by":{"name":"audit skill"},"prev_hmac":"","hmac":"67bcae7663853fd55f9d77492b9612e9a2ee77b91331995e964eefb17db4d90a"}
```

**Evidence pattern:** Git commit history, tool invocation logs, file diffs.

---

### Example 2: Audit Specific File Changes

**Input:**
```yaml
event:
  type: configuration_changed
  actor: "claude-agent"
  target: "config/production.yaml"
context:
  scope: "config/production.yaml"
  detail_level: verbose
  include_diffs: true
```

**Output:**
```yaml
recorded: true
audit_id: "audit_20240115_config"
timestamp: "2024-01-15T17:00:00Z"
audit_record:
  actor: "claude-agent"
  action_type: "configuration_change"
  targets:
    - "config/production.yaml"
  outcome: failure
changes:
  - type: modify
    before: |
      database:
        host: db.internal
        port: 5432
    after: |
      database:
        host: db.external
        port: 5433
    location: "config/production.yaml:12-15"
    timestamp: "2024-01-15T15:30:00Z"
  - type: rollback
    before: "(modified config)"
    after: "(original config)"
    location: "config/production.yaml"
    timestamp: "2024-01-15T16:00:00Z"
tool_usage:
  - tool: Edit
    invocation_count: 2
    success_rate: 0.5
decision_rationale: "Attempted database migration to external host. Rollback triggered after connection test failed."
provenance:
  inputs:
    - "migration_plan.md"
    - "config/production.yaml (original)"
  outputs:
    - "config/production.yaml (restored to original)"
  dependencies: []
confidence: 1.0
evidence_anchors:
  - {ref: "audit:audit_20240115_config", kind: record}
  - {ref: "file:.claude/audit/records.jsonl", kind: file}
  - {ref: "file:.checkpoints/chk_20240115_150000_config/manifest.json", kind: file}
  - {ref: "tool:bash:rollback command output", kind: tool}
assumptions: []
```

## Verification

Apply the following verification patterns:

- [ ] **Evidence Grounding**: All changes linked to evidence_anchors
- [ ] **Contract Validation**: Output has `recorded`, `audit_id` and `evidence_anchors` per the output schema
- [ ] **Completeness Check**: No gaps in timeline for the specified time window
- [ ] **Provenance Valid**: All inputs and outputs are verifiable

**Verification tools:** Read (for log files and the appended record), Grep (for searching history), Bash (to append the record)

## Safety Constraints

- `mutation`: true (it writes an audit record); `mutation_overridable`, so a step that only reads may declare `mutation: false`
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- Never modify audited artifacts during audit
- Preserve original timestamps (do not alter history)
- Include failed actions, not just successes
- Redact sensitive information (credentials, PII) from audit output
- Store audit records append-only: only ever append to `"${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl"`; never edit or delete earlier lines, and never write to the hook-maintained `.claude/audit.log`
- No credential in a record (STANDARD v1.2 §6.7): the skill's PreToolUse command hook blocks an append whose line holds what looks like one, read with its JSON escapes resolved (`F504 CONSTRAINT_VIOLATED:`, §5.18.10); rewrite the line to cite the value by reference or digest, then append again
- A literal record (§5.18.10): the hook reads the record only in step 6's form, one JSON object on one line with no single quote, and refuses (F504) any other command naming the records file that holds `$` (but in `${CLAUDE_PROJECT_DIR:-.}`), a backtick, `\`, `<` or `>`, which could build its text when the command runs. Compute the HMAC, and a moved-aside file's time, in commands of their own, then write them literally

## Composition Patterns

**Commonly follows:**
- `verify` - After verify passes (`passed: true`), audit the successful changes (CAVR pattern)
- `execute` / `mutate` - Audit what was executed
- `rollback` - Audit the rollback event itself

**Commonly precedes:**
- `explain` - Summarize audit for stakeholder reporting
- `persist` - Store audit record for compliance

**Anti-patterns:**
- Never skip audit after `execute` or `mutate` (breaks accountability)
- Never modify artifacts during audit (breaks integrity)
- Never omit failed actions from audit trail

**Workflow references:**
- See `reference/composition_patterns.md#debug-code-change` for audit-after-verify
- See `reference/composition_patterns.md#digital-twin-sync-loop` for audit in loops
