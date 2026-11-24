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
            # other command that may name the file or another file of .claude/audit
            # (in any quoting, $'...' and $"..." and line continuations included,
            # from a directory under .claude, by a glob or a brace that may match it
            # or a directory on its way, or by a redirection to a name the shell
            # builds) is read word by word, as the shell passes the words (escapes
            # and line continuations read as bash reads them), and may not write a
            # file, run a program that could (an interpreter, an in-place editor, cp,
            # tee, dd, ...), or build its text when it runs; mv only moves the
            # project's records file aside in its own directory. So a file named with
            # quotes, a glob or a brace, or a record rewritten in two steps, is
            # refused. In every command, a program that writes the files its input
            # names (an archive or patch tool, git apply or a git alias, gunzip -N, a
            # download a server or a configuration file names, find -exec or xargs
            # running another) is refused, read again with no quoting at all where a
            # command substitution's quotes may hide it. A name built only when a
            # command runs, code inside a word (sh -c, an interpreter's, a script)
            # and a link planted under another name are not read here; the plugin's
            # pre-tool-use hook gates such a write as a mutate.
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
              # command that may write the records file is read: one that names records,
              # jsonl, audit or .claude in any quoting (quotes, backslashes and line
              # breaks removed, so a name split by a line continuation is read whole),
              # that holds $'...' or $"..." (which can spell any name: $'\x2ecla\x75de'),
              # that runs in a directory under .claude, that holds a glob character or a
              # brace (read below: a pattern that may match the records file or a
              # directory on its way), that redirects output and expands text, or that
              # names a program that writes files its input names (read below), as
              # written or with its line continuations joined (pat\<newline>ch)
              RUNS_IN="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)" || RUNS_IN=""
              [ -n "$RUNS_IN" ] || RUNS_IN="$(pwd)"
              JOINED="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // "" | split("\\\n") | add // ""' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
              NAMED=false
              INAUDIT=false
              case "$CMD$JOINED" in *"\$'"* | *'$"'*) NAMED=true ;; esac
              printf '%s\n' "$CMD" | tr -d "\"'\\\\\n" | grep -qiE 'records|jsonl|audit|\.claude' && NAMED=true
              printf '%s\n' "$RUNS_IN" | grep -qi '\.claude' && INAUDIT=true
              if [ "$NAMED" = false ] && [ "$INAUDIT" = false ]; then
                READ=false
                case "$CMD" in *'*'* | *'?'* | *'['* | *'{'*) READ=true ;; esac
                case "$CMD" in *'>'*'$'* | *'$'*'>'* | *'>'*'`'* | *'`'*'>'*) READ=true ;; esac
                printf '%s\n%s\n' "$CMD" "$JOINED" | tr -d "\"'\\\\" | grep -qE '(^|[^A-Za-z0-9_.-])(g?tar|bsdtar|pax|cpio|ar|unzip|7zr?a?|unar|unrar|rar|jar|cabextract|lha|unsquashfs|dpkg(-deb)?|rpm|patch|rsync|busybox|toybox|xargs|find|apply|am|update-index|read-tree|checkout-index|mktree|fast-import|alias|config-env|git|g?zip|gunzip|unpigz|pigz|GZIP|curl|wget|aria2c|https?|httpie|zipfile|tarfile|ditto|xar|aa|aunpack|atool|dtrx|patool)($|[^A-Za-z0-9_-])' && READ=true
                [ "$READ" = true ] || exit 0
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
            # quotes and escapes removed. Each word: raw (as written), d (dequoted), m
            # (dequoted, an unquoted glob character *, ?, [ or ] as \u0001), braces (an
            # unquoted brace outside ${...}), ansi (it holds $'...' or $"...", kept as
            # written: bash decodes or translates them), subst (it holds a backtick, or
            # $( or ${ in double quotes, whose own quotes bash pairs apart from the text
            # around them, so this reading may not follow it), assign (NAME=value), target
            # (a redirection's target) and writes (the redirection writes). Quotes pair as
            # bash pairs them: a backslash escapes the next character (inside double
            # quotes or $'...' too, so an escaped quote never closes one), and a line
            # continuation (a backslash and a newline) is removed, inside an operator and
            # before a comment as well. commands gives {why, cmds}: why names what this
            # reading cannot follow (an unclosed quote, a here-document, a process
            # substitution), else is null. jq's global match costs the text times its
            # matches, so the caller bounds the command's length.
            def unquoted_globs: [explode[] | if . == 42 or . == 63 or . == 91 or . == 93 then 1 else . end] | implode;
            # Text inside double quotes as bash passes it: \ before $, `, ", \ or a
            # newline is removed (a line continuation with its newline), any other stays.
            def dq_text: [scan("\\\\[\\s\\S]|[^\\\\]+")]
              | map(if . == "\\\n" then "" elif test("^\\\\[$`\"\\\\]$") then .[1:] else . end) | add // "";
            def segments: [scan("\\$'(?:[^'\\\\]|\\\\[\\s\\S])*'|\\$\"(?:[^\"\\\\]|\\\\[\\s\\S])*\"|'[^']*'|\"(?:[^\"\\\\]|\\\\[\\s\\S])*\"|\\\\[\\s\\S]|(?:[^'\"\\\\$]|\\$(?!['\"]))+")]
              | map(if startswith("$'") then {q: true, sq: true, ansi: true, t: .[2:-1]}
                    elif startswith("$\"") then {q: true, sq: false, ansi: true, t: (.[2:-1] | dq_text)}
                    elif startswith("'") then {q: true, sq: true, t: .[1:-1]}
                    elif startswith("\"") then {q: true, sq: false, t: (.[1:-1] | dq_text)}
                    elif startswith("\\") then {q: true, sq: false, esc: true, t: (if . == "\\\n" then "" else .[1:] end)}
                    else {q: false, sq: false, t: .} end);
            def word($raw): ($raw | segments) as $s
              | {raw: $raw,
                 d: ($s | map(.t) | add // ""),
                 m: ($s | map(if .q then .t else (.t | unquoted_globs) end) | add // ""),
                 braces: ($s | any((.q | not) and (.t | gsub("\\$\\{[^}]*\\}"; "") | test("[{}]")))),
                 ansi: ($s | any(.ansi)),
                 subst: ($s | any(if .sq or .esc then false elif .q then .t | test("`|\\$[({]") else .t | test("`") end)),
                 assign: ($raw | test("^[A-Za-z_][A-Za-z0-9_]*\\+?="))};
            # Operators (a line continuation may stand between their characters: <\
            # < is <<), comments (a # where a word may start, after any continuation), a
            # lone continuation, words, and a quote or a backslash that nothing closes.
            def tokens: [match("(?<op>\n|&(?:\\\\\n)*&|\\|(?:\\\\\n)*\\||;(?:\\\\\n)*;|[0-9]*(?:\\\\\n)*(?:(?:>(?:\\\\\n)*&|<(?:\\\\\n)*&)(?:(?:\\\\\n)*[0-9]+(?:(?:\\\\\n)*-)?|(?:\\\\\n)*-)?|<(?:\\\\\n)*<(?:\\\\\n)*<|<(?:\\\\\n)*<(?:(?:\\\\\n)*-)?|<(?:\\\\\n)*>|>(?:\\\\\n)*>|>(?:\\\\\n)*\\||&(?:\\\\\n)*>(?:(?:\\\\\n)*>)?|[<>])|[;&|()])|(?<comment>(?:\\\\\n)*#[^\n]*)|(?<cont>(?:\\\\\n)+)|(?<word>(?:\\$'(?:[^'\\\\]|\\\\[\\s\\S])*'|\\\\[\\s\\S]|\\$(?!')|[^\\s'\"\\\\$|&;()<>]|'[^']*'|\"(?:[^\"\\\\]|\\\\[\\s\\S])*\")+)|(?<bad>\\$'|['\"\\\\])"; "g")
              | .captures | map(select(.string != null)) | .[0]
              | {(.name): (if .name == "op" then .string | split("\\\n") | add else .string end)}]
              | map(select(has("comment") or has("cont") | not));
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
            # Whether a word with a glob character (marked \u0001), or a word a brace
            # expansion gives, may name the records file or another file of
            # .claude/audit (the records moved aside, records.<time>.jsonl), or a
            # directory on its way (.claude, .claude/audit: cd .cl*/au*t, then the
            # file by its last name), from the directory the command runs in: each of
            # its last components may match the path's, and the directories it leaves
            # out are the last ones of that directory. A glob character matches any run
            # here (more than the shell's), but not a name's leading dot; a sequence of
            # numbers gives a run of digits (\u0006).
            # (A pattern with more characters than the name, glob characters
            # aside, cannot match it: so no regex is built from a long word.)
            def glob_part($pattern): . as $name | ($pattern | ascii_downcase) as $p
              | ($p | explode | map(select(. != 1 and . != 6)) | length) <= ($name | length)
              and (($name | startswith(".")) and ($p | startswith("\u0001")) | not)
                and ($name | test("^" + ($p | gsub("(?<c>[.+*?()^$|{}\\[\\]\\\\])"; "\\\(.c)") | gsub("\u0001"; ".*") | gsub("\u0006"; "[0-9-]*")) + "$"));
            def may_name_path($cwd; $file): . as $parts
              | ($file | length) as $n
              | ([$parts | length, $n] | min) as $k
              | (all(range(0; $k); . as $i | $parts[($parts | length) - 1 - $i] as $p | ($file[$n - 1 - $i] | . == null or glob_part($p))))
                and ($k == $n or ($cwd | ascii_downcase | rtrimstr("/") | endswith("/" + ($file[:$n - $k] | join("/")))));
            # (null: any name of the directory)
            def may_name_records($cwd): split("/") | map(select(. != "" and . != ".")) as $parts
              | any($parts[]; . == "..")
                or any([".claude"], [".claude", "audit"], [".claude", "audit", null]; . as $file | $parts | may_name_path($cwd; $file));
            # A path as the shell reaches it from the call's directory, its //, . and
            # trailing / read, ${CLAUDE_PROJECT_DIR:-.} at its start as the project's
            # directory, in lower case; null when it holds .., a ~ or an expansion.
            def resolved($cwd; $project):
              (if startswith("${CLAUDE_PROJECT_DIR:-.}") then $project + "/" + ltrimstr("${CLAUDE_PROJECT_DIR:-.}") else . end) as $p
              | if ($p | test("[$`~]")) then null
                else (if $p | startswith("/") then $p else $cwd + "/" + $p end)
                | split("/") | map(select(. != "" and . != "."))
                | if any(.[]; . == "..") then null else "/" + join("/") | ascii_downcase end
                end;
            def parent_of: sub("/[^/]*$"; "");
            # Brace expansion, as bash makes it of a word: a group holding a comma, or a
            # sequence x..y, gives its words (.cl{a,}ude is .claude and .clude), the
            # innermost group first. A sequence of numbers gives digits (\u0006); a
            # group bash leaves as it is stays, as a character no name holds (\u0007).
            # At most 256 words, from at most 32 groups: null for more.
            def brace_group: "\\{[^{}]*(,|\\.\\.)[^{}]*\\}";
            def expand_first: match(brace_group) as $g
              | .[:$g.offset] as $pre | .[$g.offset + $g.length:] as $post | $g.string[1:-1] as $body
              | if $body | test(",") then $body | split(",")[]
                elif $body | test("^-?[0-9]+\\.\\.-?[0-9]+(\\.\\.-?[0-9]+)?$") then "\u0006"
                elif $body | test("^[A-Za-z]\\.\\.[A-Za-z](\\.\\.-?[0-9]+)?$") then
                  ($body | explode) as $c | range([$c[0], $c[3]] | min; ([$c[0], $c[3]] | max) + 1) | [.] | implode
                else "\u0007" end
              | $pre + . + $post;
            def brace_words: {n: 0, ws: [.]}
              | until(all(.ws[]; test(brace_group) | not) or (.ws | length) > 256 or .n > 32;
                      {n: (.n + 1), ws: [.ws[] | if test(brace_group) then expand_first else . end]})
              | if (.ws | length) > 256 or .n > 32 then null else .ws end;
            def names_records($cwd): may_name_records($cwd) or (sub("^[^=]*="; "") | may_name_records($cwd));
            def may_name($cwd):
              if .braces then (.m | brace_words) as $ws | $ws == null or any($ws[]; names_records($cwd))
              else .m | test("\u0001") and names_records($cwd) end;
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
                  # mv moves the project's records file aside in its own directory,
                  # <project>/.claude/audit: a file from elsewhere never takes a
                  # records name there, and the records never leave it
                  elif $prog == "mv" then
                    [$args[1:][] | select(.d | startswith("-") | not)] as $ops
                    | ($ops | map(.d | resolved($cwd; $project))) as $at
                    | ([$project] | map(resolved($cwd; $cwd)) | .[0]) as $root
                    | if any($args[1:][]; .d | startswith("-") and (test("^-[fniv]+$") | not))
                         or ($ops | length) != 2
                         or any($ops[]; (.m | test("\u0001")) or .ansi or .braces)
                         or any($at[]; . == null)
                         or $root == null
                         or any($at[]; parent_of != $root + "/.claude/audit")
                         or ($at[0] | basename_ci) != "records.jsonl"
                         or ($at[1] | basename_ci | test("^records\\.[^/]+\\.jsonl$") | not)
                      then {kind: "mv", word: ($args | map(.d) | join(" "))}
                      else null end
                  else null end
                end;
            # The simple commands of any command, read even where the shared reader
            # stops: a here-document's body is read as commands too (more than bash
            # runs), a lone quote is left out, and heredoc says whether it holds one.
            def loose: tokens as $t | ($t | length) as $n
              | [range(0; $n) as $i | $t[$i]
                 | if .word then
                     ($t[$i - 1].op // "") as $op
                     | word(.word) + {target: ($i > 0 and ($op | takes_target)),
                                      writes: ($i > 0 and ($op | takes_target) and ($op | test(">")))}
                   else . end] as $w
              | ([-1] + [range(0; $n) | select($t[.].op and ($t[.].op | test("[<>]") | not))] + [$n]) as $b
              | {heredoc: any($t[]; .op and (.op | test("<<")) and (.op | test("<<<") | not)),
                 cmds: [range(0; ($b | length) - 1) as $k | $w[$b[$k] + 1:$b[$k + 1]] | map(select(.d != null)) | select(length > 0)],
                 # whether these words are the ones bash reads: no quote is left
                 # unclosed and no word holds a command substitution
                 follows: ((any($t[]; .bad) | not) and (any($w[]; .subst) | not))};
            # The command with no quoting at all, read where the reader cannot follow
            # it (a quote inside a command substitution, a backtick's command, an
            # unclosed quote): each line continuation removed (a backslash and a
            # newline after an even run of backslashes, as bash removes it), a
            # backtick read as ;, a # as a letter (no comment), and every quote and
            # backslash removed. It reads more commands than bash runs, and every one
            # bash runs.
            def unquoted_text: gsub("(?<!\\\\)(?<k>(?:\\\\\\\\)*)\\\\\n"; .k) | gsub("`"; " ; ") | gsub("#"; "_") | gsub("[\"'\\\\]"; "");
            def name_of: sub("^.*/"; "");
            # Programs that run the program their words name (timeout 5 tar ...).
            def wrappers: ["env", "nice", "nohup", "timeout", "time", "command", "builtin", "exec", "sudo", "doas", "stdbuf", "ionice", "chrt", "taskset", "setsid", "unbuffer", "xargs", "watch", "flock", "chroot", "strace", "ltrace", "faketime", "firejail", "nsenter", "unshare", "prlimit", "numactl", "systemd-run", "script", "parallel", "busybox", "toybox"];
            # Programs that write the files their input names (an archive's members, a
            # patch's targets, a download's name or directory a server or a
            # configuration file gives), and git's commands that write files or the
            # index from a patch or from data (git checkout then writes what the index
            # holds).
            def writers: ["gtar", "bsdtar", "pax", "cpio", "ar", "7z", "7za", "7zr", "unar", "unrar", "rar", "jar", "cabextract", "lha", "unsquashfs", "dpkg-deb", "patch", "rsync", "busybox", "toybox", "aria2c", "http", "https", "httpie", "ditto", "xar", "aa", "aunpack", "atool", "dtrx", "patool"];
            def git_writers: ["apply", "am", "update-index", "read-tree", "checkout-index", "mktree", "fast-import"];
            # git's own commands: any other is an alias, which a configuration file or
            # variable may define (git x then runs git apply), or another program.
            def git_own: ["add", "am", "annotate", "apply", "archimport", "archive", "backfill", "bisect", "blame", "branch", "bugreport", "bundle", "cat-file", "check-attr", "check-ignore", "check-mailmap", "check-ref-format", "checkout", "checkout-index", "cherry", "cherry-pick", "citool", "clean", "clone", "column", "commit", "commit-graph", "commit-tree", "config", "count-objects", "credential", "credential-cache", "credential-store", "cvsexportcommit", "cvsimport", "cvsserver", "daemon", "describe", "diagnose", "diff", "diff-files", "diff-index", "diff-tree", "difftool", "fast-export", "fast-import", "fetch", "fetch-pack", "filter-branch", "fmt-merge-msg", "for-each-ref", "for-each-repo", "format-patch", "fsck", "fsck-objects", "gc", "get-tar-commit-id", "grep", "gui", "hash-object", "help", "hook", "http-backend", "http-fetch", "http-push", "imap-send", "index-pack", "init", "init-db", "instaweb", "interpret-trailers", "last-modified", "log", "ls-files", "ls-remote", "ls-tree", "mailinfo", "mailsplit", "maintenance", "merge", "merge-base", "merge-file", "merge-index", "merge-octopus", "merge-one-file", "merge-ours", "merge-recursive", "merge-recursive-ours", "merge-recursive-theirs", "merge-resolve", "merge-subtree", "merge-tree", "mergetool", "mktag", "mktree", "multi-pack-index", "mv", "name-rev", "notes", "p4", "pack-objects", "pack-redundant", "pack-refs", "patch-id", "pickaxe", "prune", "prune-packed", "pull", "push", "quiltimport", "range-diff", "read-tree", "rebase", "receive-pack", "reflog", "refs", "remote", "remote-ext", "remote-fd", "remote-ftp", "remote-ftps", "remote-http", "remote-https", "repack", "replace", "replay", "request-pull", "rerere", "reset", "restore", "rev-list", "rev-parse", "revert", "rm", "send-email", "send-pack", "shell", "shortlog", "show", "show-branch", "show-index", "show-ref", "sparse-checkout", "stage", "stash", "status", "stripspace", "submodule", "subtree", "svn", "switch", "symbolic-ref", "tag", "unpack-file", "unpack-objects", "update-index", "update-ref", "update-server-info", "upload-archive", "upload-pack", "var", "verify-commit", "verify-pack", "verify-tag", "version", "whatchanged", "worktree", "write-tree"];
            # Whether a word sets an option: a short option's cluster holds one of
            # $flags up to the first letter that takes a value ($values: the rest of
            # the word is its value), or a long one is one of $long, as written or
            # abbreviated to at least $min characters (curl, wget and gzip read
            # an unambiguous prefix as the option).
            def sets($flags; $values; $long; $min):
              .d as $d
              | if $d | startswith("--") then ($d | sub("=.*$"; "")) as $name
                  | any($long[]; . as $l | $name == $l or (($name | length) >= $min and ($l | startswith($name))))
                elif $d | test("^-[^-]") then ($d[1:] | explode | map([.] | implode)) as $ls
                  | (first(range(0; $ls | length) as $i | select($values | contains($ls[$i])) | $i) // ($ls | length)) as $at
                  | any($ls[:$at + 1][]; . as $c | $flags | contains($c))
                else false end;
            # gzip and its kin restore the name stored in the file with -N (or GZIP=-N).
            def gzip_refusal($prog; $rest; $text):
              if $text | test("GZIP") then "\($prog) where the command names GZIP"
              else (first($rest[] | select(sets("N"; "bpSI"; ["--name"]; 4))) // null) as $w
              | if $w != null then "\($prog) \($w.d)" else null end end;
            # curl names a file from the server with -J, reads its options from a file
            # with -K, builds them from files or variables with --variable, and reads
            # ~/.curlrc (which may set remote-header-name or output-dir) unless -q is
            # its first word.
            def curl_refusal($rest):
              if (($rest[0].d // "") | IN("-q", "--disable")) | not then "curl without -q first (its configuration file may name the files it writes)"
              else (first($rest[] | select(sets("JK"; "ECbcdDFPHhmoUQreXYytzTuAwxK"; ["--remote-header-name", "--config", "--variable"]; 5) or (.d | startswith("--expand-")))) // null) as $w
              | if $w != null then "curl \($w.d)" else null end end;
            # wget names files from the server (--content-disposition,
            # --trust-server-names), from the pages it follows (-r, -m, -p) or the URLs
            # it reads (-i, -x), runs wgetrc commands (-e), and reads ~/.wgetrc and
            # /etc/wgetrc (which may set any of these) unless given --no-config.
            def wget_refusal($rest):
              if any($rest[]; .d == "--no-config") | not then "wget without --no-config (its configuration file may name the files it writes)"
              else (first($rest[] | select(sets("rmpxieBF"; "oaBtOTwQPUlARDIXnei"; ["--content-disposition", "--trust-server-names", "--recursive", "--mirror", "--page-requisites", "--force-directories", "--force-html", "--input-file", "--input-metalink", "--metalink-over-http", "--execute", "--config", "--base"]; 4))) // null) as $w
              | if $w != null then "wget \($w.d)" else null end end;
            # dpkg and rpm extract or install the files a package names.
            def package_refusal($prog; $rest):
              (if $prog == "dpkg" then [$rest[] | select(sets("xXiR"; ""; ["--extract", "--vextract", "--install", "--unpack", "--recursive"]; 5))]
               else [$rest[] | select(sets("iUF"; ""; ["--install", "--upgrade", "--freshen", "--reinstall", "--restore"]; 5))] end) as $w
              | if ($w | length) > 0 then "\($prog) \($w[0].d)" else null end;
            # python -m zipfile or tarfile extracts an archive.
            def python_refusal($prog; $rest):
              if any(range(0; $rest | length) as $i | ($rest[$i].d | IN("-mzipfile", "-mtarfile")) or ($rest[$i].d == "-m" and (($rest[$i + 1].d // "") | IN("zipfile", "tarfile"))); .)
              then "\($prog) -m zipfile or tarfile" else null end;
            # The programs find -exec and xargs may run on the names they find or read.
            def fed_readers: [readers[] | select(. != "mv" and . != "openssl" and . != "cd")];
            def letters: ltrimstr("-") | explode | map([.] | implode);
            # tar creating or listing an archive, with short options only.
            def tar_reads($rest): ($rest | map(.d)) as $r
              | (any($r[]; startswith("--")) | not)
                and ([($r[] | select(startswith("-"))), (if ($r | length) > 0 and ($r[0] | startswith("-") | not) then $r[0] else empty end) | letters[]] as $ls
                     | ($ls | length) > 0 and all($ls[]; IN("c", "t", "v", "f", "z", "j", "J", "C", "T", "h", "p", "P", "S")) and any($ls[]; . == "c" or . == "t"));
            # unzip listing or testing an archive.
            def unzip_reads($rest): ($rest | map(.d)) as $r
              | ($r | length) > 0 and ($r[0] | startswith("-"))
                and ([$r[] | select(startswith("-")) | letters[]] as $ls
                     | all($ls[]; IN("l", "t", "v", "Z", "q", "z")) and any($ls[]; IN("l", "t", "v", "Z")));
            def git_refusal($rest):
              (reduce $rest[] as $w ({skip: false, sub: null, alias: false};
                 if .sub != null then .
                 elif .skip then .skip = false | .alias = (.alias or ($w.d | ascii_downcase | startswith("alias.")))
                 elif $w.d | startswith("-") then
                   .skip = ($w.d | test("^(-C|-c|--git-dir|--work-tree|--namespace|--super-prefix|--config-env|--exec-path|--attr-source)$"))
                   | .alias = (.alias or ($w.d | test("^-c.*alias\\.|^--config-env"; "i")))
                 else .sub = $w.d end)) as $g
              | if $g.alias then "git -c alias.*"
                elif $g.sub == null then null
                elif any(git_writers[]; . == $g.sub) then "git \($g.sub)"
                elif $g.sub == "config" and any($rest[]; .d | ascii_downcase | startswith("alias.")) then "git config alias.*"
                elif ($g.sub | IN(git_own[])) | not then "git \($g.sub) (not one of git's own commands: an alias or another program)"
                else null end;
            def find_refusal($rest):
              first(range(0; $rest | length) as $i | $rest[$i].d as $d
                | select(($d | IN("-fprint", "-fprint0", "-fprintf", "-fls"))
                         or (($d | IN("-exec", "-execdir", "-ok", "-okdir")) and (($rest[$i + 1].d // "") as $q | any(fed_readers[]; . == $q) | not)))
                | "find \($d) \($rest[$i + 1].d // "")") // null;
            def xargs_refusal($rest):
              (reduce $rest[] as $w ({skip: false, prog: null};
                 if .prog != null then .
                 elif .skip then .skip = false
                 elif $w.d | startswith("-") then .skip = ($w.d | test("^(-[aIdEnLPs]|--(arg-file|delimiter|eof|max-args|max-lines|max-procs|max-chars|process-slot-var))$"))
                 else .prog = $w.d end)) as $x
              | if $x.prog == null or any(fed_readers[]; . == $x.prog) then null else "xargs \($x.prog)" end;
            # A program of a simple command that writes files its input names: its
            # program, and any word after a program that runs another. Each is read
            # over its next 64 words (no list grows with the command); a longer one is
            # refused.
            def writer_refusal($words; $text):
              ($words | map(select(.target | not))) as $a
              | ($a | length) as $n
              | (first(range(0; $n) | select($a[.].assign | not)) // $n) as $p
              | (first(range($p; $n) | select($a[.].d | name_of | IN(wrappers[]))) // $n) as $wrap
              | first(range($p; $n) as $i | select($i == $p or $i > $wrap)
                      | ($a[$i].d | name_of) as $prog | $a[$i + 1:$i + 65] as $rest
                      | if ($prog | IN(writers[])) then $prog
                        elif ($prog | IN("tar", "unzip", "git", "find", "xargs", "gzip", "gunzip", "pigz", "unpigz", "curl", "wget", "dpkg", "rpm") or test("^python[0-9.]*$") | not) then empty
                        elif $n - $i > 65 then "\($prog) with more than 64 words"
                        elif $prog == "tar" then (if tar_reads($rest) then empty else "tar" end)
                        elif $prog == "unzip" then (if unzip_reads($rest) then empty else "unzip" end)
                        elif $prog == "git" then (git_refusal($rest) // empty)
                        elif $prog == "find" then (find_refusal($rest) // empty)
                        elif $prog == "xargs" then (xargs_refusal($rest) // empty)
                        elif $prog | IN("gzip", "gunzip", "pigz", "unpigz") then (gzip_refusal($prog; $rest; $text) // empty)
                        elif $prog == "curl" then (curl_refusal($rest) // empty)
                        elif $prog == "wget" then (wget_refusal($rest) // empty)
                        elif $prog | IN("dpkg", "rpm") then (package_refusal($prog; $rest) // empty)
                        else (python_refusal($prog; $rest) // empty) end
                      | {kind: "writer", word: .}) // null;
            .tool_input.command // ""
            | . as $text
            | if utf8bytelength > 16384 then "long "
              else loose as $l
              # Where the reader cannot follow the command, it is read again with no
              # quoting at all, which reads more than bash runs
              | (if $l.follows then [] else (unquoted_text | loose | .cmds) end) as $u
              # A command that may name the records file, or a directory on its way, or
              # that redirects output to a name the shell builds, is read as a whole
              | if $named or $inaudit or any($l.cmds[][], $u[][]; may_name($cwd))
                   or any($l.cmds[][]; .writes and ((.raw | test("[$`]")) or .braces)) then
                  # $'...' and $"..." are decoded or translated by bash, unread here
                  if test("\\$['\"]") then "subst "
                  elif [scan("'[^']*'|\"[^\"]*\"|[^'\"]+")] | map(select(startswith("'") | not)) | add // "" | test("\\$\\(|`|\\\\") then "subst "
                  else commands as $c
                  | if $c.why == "process substitution" then "subst "
                    elif $c.why != null then "expands \($c.why)"
                    elif any($c.cmds[][]; .braces) then "expands an unquoted brace"
                    else (first($c.cmds[][] | select(.writes and (.d as $t | any(sinks[]; . == $t) | not))) // null) as $w
                    | if $w != null then "writes \($w.d | .[:200])"
                      else (first($c.cmds[] | check_command(.) | select(. != null)) // null) as $r
                      | if $r == null then "ok" else "\($r.kind) \($r.word | .[:200])" end
                      end
                    end
                  end
                # A here-document whose text a quote carries past a line's end: where
                # its body ends, and what runs after it, are not read
                elif $l.heredoc and any($l.cmds[][]; .raw | test("\n")) then "expands a here-document"
                else (first($l.cmds[], $u[] | writer_refusal(.; $text) | select(. != null)) // null) as $r
                | if $r == null then "ok" else "\($r.kind) \($r.word | .[:200])" end
                end
              end
            JQ
            )"
              VERDICT="$(printf '%s' "$INPUT" | jq -r --arg cwd "$RUNS_IN" --arg project "${CLAUDE_PROJECT_DIR:-$RUNS_IN}" --argjson named "$NAMED" --argjson inaudit "$INAUDIT" "$READER" 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: the audit skill's check could not read the command" >&2; exit 2; }
              KIND="${VERDICT%% *}"
              WORD="${VERDICT#* }"
              ONE_FORM="append a record only as printf '%s\n' '<json>' >> \"\${CLAUDE_PROJECT_DIR:-.}/.claude/audit/records.jsonl\", with the record literal (STANDARD 1.2.0 §6.7)"
              case "$KIND" in
                ok) ;;
                writes) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command writes a file only in the one append form, whose record this check reads; it does not redirect output to '$WORD' (a name quoted, globbed, braced, linked or built when the command runs may be the records file): $ONE_FORM" >&2; exit 2 ;;
                writer) echo "F504 CONSTRAINT_VIOLATED: in the audit skill no command runs a program that writes files its input names, which could write the records file unread: '$WORD' (an archive or patch tool, git apply, am, update-index, read-tree, checkout-index, mktree or fast-import, a git alias or another command than git's own, find -exec or xargs running a program other than a reader, gunzip -N, curl but as curl -q without -J, -K or --variable, wget but with --no-config and without -r, -m, -p, -x, -i or --content-disposition, HTTPie, aria2c, dpkg -x or -i, rpm -i; tar only creates or lists, with short options, and unzip only lists): $ONE_FORM" >&2; exit 2 ;;
                program) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command runs only programs that write no file but by a redirection and run no other code (cat, echo, printf, jq, ls, head, tail, wc, grep, cut, tr, base64, sha256sum, shasum, md5sum, date, hostname, sleep, test, true, false, pwd, cd, stat, basename, dirname, mkdir, mv to move the records file aside, openssl dgst), each by its name; it does not run '$WORD', which could write the records file unread: $ONE_FORM" >&2; exit 2 ;;
                mv) echo "F504 CONSTRAINT_VIOLATED: in the audit skill mv only moves the records file aside, in the project's audit directory, as mv <project>/.claude/audit/records.jsonl <project>/.claude/audit/records.<UTC time>.jsonl with literal paths (no .., ~ or expansion); it does not run '$WORD', which could put another file in its place or take the records out: $ONE_FORM" >&2; exit 2 ;;
                assign) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command does not set a variable for one command (NAME=value cmd), nor PATH, IFS, ENV, BASH_ENV, CDPATH, LD_*, DYLD_* or OPENSSL_*, which change what a program runs or writes: '$WORD'" >&2; exit 2 ;;
                subst) echo "F504 CONSTRAINT_VIOLATED: in the audit skill a command may not substitute a command or a process, or escape text (\$(, a backtick, <(, >(, \\ outside single quotes, \$'...' or \$\"...\"), since what runs is not what this check reads; run each command on its own, with literal values: $ONE_FORM" >&2; exit 2 ;;
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
            SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
            # A quote, or an escaped one (\" in JSON text inside a JSON string)
            SECRET_Q="\\\\*[\"']"
            # A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password; a user of at most 256 characters, so no run is read again from each of its positions)
            SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
            SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
            SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]{0,256}:"
            secret_in() {
              printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
              # A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
              printf '%s' "$1" | grep -Eiq -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']" && return 0
              # The password of a URL's userinfo, unless it is a placeholder (its scheme read from the start of its run, once)
              printf '%s' "$1" | grep -Eo -- '(^|[^A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]*:[^[:space:]/@]+@' |
                sed -E 's#^.*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
              # An Authorization header's value, 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
                sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
                sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # A user option's password (curl -u user:password), 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eo -- "$SECRET_USER[^[:space:]\"'\\\\]{8,}" |
                sed -E 's/^[^:]*://' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              # An unquoted value of 12 or more characters with letters and digits, assigned or given to a credential option
              printf '%s' "$1" | grep -Eio -- "$SECRET_OPT[[:space:]]+[^-[:space:]\"'][^[:space:]\"']{11,}" |
                sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]' && return 0
              printf '%s' "$1" | grep -Eio -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
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

**The line step 6 appends** (with `AUDIT_HMAC_KEY=example-key`; `python tools/verify_audit_log.py --log-file .claude/audit/records.jsonl --no-head` checks the chain, which no head anchors):

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
