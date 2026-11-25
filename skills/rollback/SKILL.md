---
name: rollback
description: Safely undo changes by restoring to a checkpoint. Use when verify fails, errors occur, or explicit undo is requested. Essential for the CAVR pattern recovery.
argument-hint: "[checkpoint_id] [scope]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Bash, Git
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            ROLLBACK SAFETY VALIDATION

            The tool call follows this prompt as JSON; the rollback command is tool_input.command.

            The safety layer checks the restore command: `git stash apply <sha>`,
            with the full id of the commit a checkpoint recorded, is a
            `rollback` call (a checkpoint taken earlier, F503); applying any
            other commit, and the skill's own restore, a `git restore
            --source=<sha> ...` line, is a `mutate` call (a fresh checkpoint,
            F501, and approval, F502). An expired or used checkpoint can still
            be restored (STANDARD 1.2.0 §5.2.2).

            Before executing rollback, verify:
            1. Current state has been captured (for audit)
            2. Rollback scope matches intended restore scope
            3. No ongoing operations that would conflict

            CRITICAL CHECKS:
            - Is checkpoint integrity verified (hash match)?
            - Will any data be irreversibly lost?
            - Are there uncommitted changes that would be overwritten?

            Return ok: true if rollback is safe to execute.
            Return ok: false, with the reason, if:
            - Checkpoint is missing or corrupted
            - Rollback would cause data loss beyond intended scope
            - Current state needs to be preserved first
          once: false
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # A restore in this skill restores a checkpoint taken in the project
            # (STANDARD 1.2.0 §5.18.6, F503): a command that restores a stash (git
            # stash pop, apply or branch) is allowed only as `git stash pop|apply
            # <id>`, a simple command whose words, as the shell passes them (quotes
            # removed), are those four, with <id> the full id of a commit a checkpoint
            # recorded, entered in the project's git directory
            # (<git dir>/acs/checkpoints/commits/, one lookup; outside the work
            # tree, so no clone, checkout or applied stash can ship an entry),
            # holding the HMAC of the commit under the project's checkpoint key
            # (<git dir>/acs/checkpoints/key), so a file a command made there is
            # no entry, in a git directory git made for a work tree (a
            # repository can ship one of its own), and run in the project's
            # repository (the call's cwd), as the plugin's pre-tool-use hook
            # reads it; valid or not, used or not; beside other commands on its line
            # only where each of them only reads (a variable set or named, printf -v,
            # alias, hash, a function, source, cd or a file written may make the
            # restore's git another program, or run it elsewhere). Any other
            # spelling is refused:
            # git's options before stash (-C, -c, an alias), a program that runs git
            # (env, xargs), a restore in a word (sh -c '...', code piped to a shell),
            # a word the shell expands or escapes ($, a backtick, \, a glob, a
            # brace), and a command these words cannot be read from (an unclosed
            # quote, an extglob pattern, a here-document, a process substitution,
            # over 16384 bytes). Skill hooks stay registered for the rest of the
            # session, so only a command that names stash (quotes, backslashes, $
            # and line breaks removed), holds $'...' or $"...", or holds a glob, a
            # brace or an extglob opener (touch stash; git st?sh apply <id>, or
            # git st@(a)sh once shopt -s extglob has run) is read; a glob counts as
            # stash, pop, apply or branch where its pattern matches the name, in any
            # letter case, each bracket expression read as bash reads one
            # (glob_marks: git st[[:alpha:]]sh). A name built only when a command runs, or one
            # git's configuration gives, is not, and the plugin's pre-tool-use hook
            # gates such a command as a mutate. git runs with core.fsmonitor and
            # hooks turned off.
            # Claude Code passes the tool call as JSON on stdin; exit 2 blocks the
            # call and the reason on stderr is shown to Claude. A call that cannot
            # be read is blocked (R407).
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // "" | strings' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # (with its line continuations joined too: sta\<newline>sh, $\<newline>'...')
            JOINED="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // "" | strings | split("\\\n") | add // ""' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            case "$CMD$JOINED" in
              *"\$'"* | *'$"'* | *'*'* | *'?'* | *'['* | *'{'* | *'@('* | *'!('* | *'+('*) ;;
              *) printf '%s\n' "$CMD" | tr -d "\"'\\\\\$\n" | grep -q stash || exit 0 ;;
            esac
            # The cwd exactly as given: a command substitution strips the line
            # breaks that end its output, and a directory's name may end in one,
            # so an x is printed after it and taken off.
            CWD="$(printf '%s' "$INPUT" | jq -j '(.cwd // "" | strings), "x"' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            CWD="${CWD%x}"
            # The restores of the command: "restore <id>" for each `git stash
            # pop|apply <id>`, "refuse <words>" for any other spelling of one.
            reader_program() {
              cat <<'JQ'
            # BEGIN shell-words (source: hooks/shell_words.jq; tests/test_skill_hooks.py keeps every copy equal)
            # A Bash command's simple commands and their words as the shell passes them,
            # quotes and escapes removed. Each word: raw (as written), d (dequoted), m
            # (dequoted, an unquoted glob character *, ?, [ or ] as \u0001), g (dequoted,
            # the unquoted *, ?, [ and ] as \u0001 to \u0004: glob_text), braces (an
            # unquoted brace outside ${...}), ansi (it holds $'...' or $"...", kept as
            # written: bash decodes or translates them), subst (it holds a backtick, or
            # $( or ${ in double quotes, whose own quotes bash pairs apart from the text
            # around them, so this reading may not follow it), assign (NAME=value), target
            # (a redirection's target) and writes (the redirection writes). Quotes pair as
            # bash pairs them: a backslash escapes the next character (inside double
            # quotes or $'...' too, so an escaped quote never closes one), and a line
            # continuation (a backslash and a newline) is removed, inside an operator and
            # before a comment as well. An unquoted extglob opener (@(, !(, +(, *( or
            # ?(, a line continuation allowed before its parenthesis) is a token of its
            # own, ext: once a command has run shopt -s extglob, bash reads the group as
            # part of a word (blanks, ; and | included) and expands it as a pattern, and
            # otherwise refuses the line. commands gives {why, cmds}: why names what this
            # reading cannot follow (an unclosed quote, an extglob pattern, a
            # here-document, a process substitution), else is null. jq's global match
            # costs the text times its matches, so the caller bounds the command's
            # length.
            def unquoted_globs: [explode[] | if . == 42 or . == 63 or . == 91 or . == 93 then 1 else . end] | implode;
            # A word's text as a glob: with $unquoted, *, ?, [ and ] as \u0001 to
            # \u0004; a character from \u0001 to \u0005 typed in it as U+FFFD, which
            # matches no name, as bash matches the character.
            def glob_text($unquoted): [explode[] | if . >= 1 and . <= 5 then 65533
              elif ($unquoted | not) then .
              elif . == 42 then 1 elif . == 63 then 2 elif . == 91 then 3 elif . == 93 then 4 else . end] | implode;
            # A glob (glob_text) with each bracket expression read as bash reads one, in
            # time linear in the glob. A [, then ! or ^ and a character, or a character
            # other than ! and ^, then characters, up to the ] that closes it, is one
            # character (\u0002) where no character before that ] is a [ followed by :,
            # = or . (a class such as [:alpha:], [=c=] or [.c.]) and the first is no ]
            # (bash reads a ] first in the set as one of it). Where a [ that a ] follows
            # opens any other bracket expression, the run from it to the last ] is any
            # run (\u0001): more than bash matches there, never less. With $lossy (the
            # quotes were removed before, so a ] in a set cannot be told from one after
            # it), a ] after a bracket expression makes that run any run too. A [ or ]
            # left is a character (bash reads a [ that no ] closes as one). A run of
            # \u0001 and \u0006 (a brace expansion's digits) is one, \u0001 where either
            # is.
            def glob_marks($lossy): explode as $c | ($c | length) as $n
              # $stop[k]: the first j >= k where a set ends or cannot go on (a ], or a
              # [ followed by :, = or .), null if none
              | (reduce range($n - 1; -1; -1) as $j ([null];
                   .[$j] = (if $c[$j] == 4 or ($c[$j] == 3 and ($c[$j + 1] == 58 or $c[$j + 1] == 61 or $c[$j + 1] == 46))
                            then $j else .[$j + 1] end))) as $stop
              | (reduce range(0; $n) as $i ({skip: 0, out: []};
                   if $i < .skip then .
                   elif $c[$i] == 3 then
                     ($i + 1 + (if $c[$i + 1] == 33 or $c[$i + 1] == 94 then 1 else 0 end)) as $f
                     | if $f < $n and $stop[$f] != $f and $stop[$f] != null and $c[$stop[$f]] == 4
                       then .out += [5] | .skip = $stop[$f] + 1
                       else .out += [3] end
                   else .out += [$c[$i]] end) | .out) as $o
              | ($o | length) as $m
              | (first(range(0; $m) as $i | select($o[$i] == 3 or ($lossy and $o[$i] == 5)) | $i) // null) as $open
              | (if $open == null then null else first(range($m - 1; $open; -1) as $i | select($o[$i] == 4) | $i) // null end) as $close
              | (if $close != null then $o[:$open] + [1] + $o[$close + 1:] else $o end)
              | reduce .[] as $x ([];
                  if ($x == 1 or $x == 6) and (.[-1] == 1 or .[-1] == 6) then .[-1] = (if $x == 1 then 1 else .[-1] end)
                  else . + [if $x == 5 then 2 else $x end] end)
              | implode;
            # The fewest characters a glob_marks glob matches.
            def glob_min: explode | map(select(. != 1 and . != 6)) | length;
            # A glob_marks glob as an anchored regular expression.
            def marks_regex: "^" + (gsub("(?<c>[.+*?()^$|{}\\[\\]\\\\])"; "\\\(.c)") | gsub("\u0001"; ".*") | gsub("\u0002"; ".")
              | gsub("\u0003"; "\\[") | gsub("\u0004"; "\\]") | gsub("\u0006"; "[0-9-]*")) + "$";
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
                 g: ($s | map(.q as $q | .t | glob_text($q | not)) | add // ""),
                 braces: ($s | any((.q | not) and (.t | gsub("\\$\\{[^}]*\\}"; "") | test("[{}]")))),
                 ansi: ($s | any(.ansi)),
                 subst: ($s | any(if .sq or .esc then false elif .q then .t | test("`|\\$[({]") else .t | test("`") end)),
                 assign: ($raw | test("^[A-Za-z_][A-Za-z0-9_]*\\+?="))};
            # Operators (a line continuation may stand between their characters: <\
            # < is <<), comments (a # where a word may start, after any continuation), a
            # lone continuation, words, an extglob opener, and a quote or a backslash
            # that nothing closes.
            def tokens: [match("(?<op>\n|&(?:\\\\\n)*&|\\|(?:\\\\\n)*\\||;(?:\\\\\n)*;|[0-9]*(?:\\\\\n)*(?:(?:>(?:\\\\\n)*&|<(?:\\\\\n)*&)(?:(?:\\\\\n)*[0-9]+(?:(?:\\\\\n)*-)?|(?:\\\\\n)*-)?|<(?:\\\\\n)*<(?:\\\\\n)*<|<(?:\\\\\n)*<(?:(?:\\\\\n)*-)?|<(?:\\\\\n)*>|>(?:\\\\\n)*>|>(?:\\\\\n)*\\||&(?:\\\\\n)*>(?:(?:\\\\\n)*>)?|[<>])|[;&|()])|(?<comment>(?:\\\\\n)*#[^\n]*)|(?<cont>(?:\\\\\n)+)|(?<word>(?:\\$'(?:[^'\\\\]|\\\\[\\s\\S])*'|\\\\[\\s\\S]|\\$(?!')|[^\\s'\"\\\\$|&;()<>@!+*?]|[@!+*?](?!(?:\\\\\n)*\\()|'[^']*'|\"(?:[^\"\\\\]|\\\\[\\s\\S])*\")+)|(?<ext>[@!+*?](?:\\\\\n)*\\()|(?<bad>\\$'|['\"\\\\])"; "g")
              | .captures | map(select(.string != null)) | .[0]
              | {(.name): (if .name == "op" then .string | split("\\\n") | add else .string end)}]
              | map(select(has("comment") or has("cont") | not));
            # A redirection whose target is the next word (2>&1 and >&- name none).
            def takes_target: test("[<>]") and (test("&([0-9]+-?|-)$") | not);
            # Each step is linear in the command: no list grows by copying.
            def commands: tokens as $t | ($t | length) as $n
              | if any($t[]; .bad) then {why: "quote"}
                elif any($t[]; .ext) then {why: "extglob"}
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

            # A word the shell expands or escapes: any word at all after expansion.
            def expands: (.raw | test("[$`\\\\]")) or (.m | test("\u0001")) or .braces;
            # Whether a word the shell expands may give one of $names: a glob whose
            # pattern matches one (in any letter case, as with nocaseglob; each
            # bracket expression read as bash reads one, glob_marks: git st[[:alpha:]]sh,
            # git stash [[:alpha:]]pply), and any other expansion. (No regex is built
            # from a glob that matches more characters than the longest name has.)
            def may_be($names): if (.raw | test("[$`\\\\]")) or .braces then true
              elif .m | test("\u0001") then
                (.g | ascii_downcase | glob_marks(false)) as $g
                | ($names | split("|")) as $ns
                | if ($g | glob_min) > ($ns | map(length) | max) then false
                  else ($g | marks_regex) as $re | any($ns[]; test($re)) end
              else false end;
            # The word with its backslashes removed, as bash removes them.
            def plain: .d | gsub("\\\\"; "");
            def token($names): plain | test("(^|[^A-Za-z0-9_.-])(\($names))($|[^A-Za-z0-9_.-])");
            def names_git: (plain | sub("^.*/"; "") == "git") or token("git");
            # An unquoted $ expansion or a backtick: the shell splits what it
            # gives into words (S="git stash"; $S apply ...). $'...' does not.
            def splits: [.raw | scan("'[^']*'|\"[^\"]*\"|[^'\"]+")] as $s
              | any(range(0; $s | length) as $i | $s[$i]
                    | select((startswith("'") or startswith("\"")) | not)
                    | test("\\$[^'\"]|`") or (endswith("$") and $i == ($s | length) - 1); .);
            def restore($words):
              ($words | map(select(.target | not))) as $a
              # the program's word: the first that sets no variable
              | (first(range(0; $a | length) as $i | select($a[$i].assign | not) | $i) // 0) as $p
              | if any($words[]; (plain | test("\\s")) and token("stash") and token("pop|apply|branch")) then
                  {refuse: first($words[] | select((plain | test("\\s")) and token("stash") and token("pop|apply|branch")) | .d)}
                elif ([range(0; $a | length) as $i | ($a[$i] | names_git or splits) or ($i == $p and ($a[$i] | expands))] | any)
                     and any($a[]; token("stash") or may_be("stash")) and any($a[]; token("pop|apply|branch") or may_be("pop|apply|branch")) then
                  if ($a | length) == 4 and $a[0].d == "git" and $a[1].d == "stash" and ($a[2].d == "pop" or $a[2].d == "apply")
                     and ($a[3].d | test("^([0-9a-f]{40}|[0-9a-f]{64})$")) and (any($a[]; expands) | not)
                  then {restore: "\($a[2].d) \($a[3].d)"}
                  else {refuse: ($a | map(.d) | join(" "))} end
                else null end;

            # The commands a line that restores a checkpoint may hold beside the
            # restore: ones that only read. Any other may make the restore's git
            # another program, or run it elsewhere, unread here: a variable set or
            # named (PATH=..., printf -v PATH, BASH_CMDS[git]=..., GIT_DIR, an
            # export), another name for git (alias, hash, enable, git() { ...; }),
            # code run (source, eval), a directory change (cd), a file written (a
            # hook, git's configuration).
            def beside: ["git", "echo", "printf", "cat", "ls", "head", "tail", "wc", "grep", "pwd", "true", "false", "test", "date", "sleep", "stat"];
            def names_variable: test("^(-[A-Za-z]*)?(PATH|ENV|BASH_ENV|IFS|CDPATH|BASH_CMDS|BASH_ALIASES|GIT_[A-Za-z0-9_]*|LD_[A-Za-z0-9_]*|DYLD_[A-Za-z0-9_]*)(\\[.*\\])?(\\+?=.*)?$");
            def reads_only: . as $words
              | ($words | map(select(.target | not))) as $a
              | ($a | length) > 0
                and (any($words[]; .writes and (.d | IN("/dev/null", "/dev/stdout", "/dev/stderr") | not)) | not)
                and (any($a[]; .assign or expands or (.d | names_variable)) | not)
                and ($a[0].d | IN(beside[]))
                and ($a[0].d != "printf" or (($a[1].d // "") | startswith("-") | not))
                and ($a[0].d != "git" or (($a[1].d // "") | IN("status", "log", "diff", "show", "rev-parse")));

            .tool_input.command // ""
            | if utf8bytelength > 16384 then "unread over 16384 bytes"
              else commands as $c
              | if $c.why != null then "unread \(if $c.why == "quote" then "an unclosed quote" elif $c.why == "heredoc" then "a here-document" elif $c.why == "extglob" then "an extglob pattern" else "a process substitution" end)"
                else ($c.cmds | map(restore(.))) as $r
                | (if any($r[]; . != null and has("restore"))
                   then first(range(0; $r | length) as $i | select($r[$i] == null and ($c.cmds[$i] | reads_only | not)) | $c.cmds[$i]) // null
                   else null end) as $other
                # (each restore first: one of no recorded checkpoint is refused as that)
                | ($r[] | select(. != null)
                   | if .restore then "restore \(.restore)" else "refuse \(.refuse | gsub("[\n\r]"; " ") | .[:200])" end),
                  (if $other != null then "beside \($other | map(.d) | join(" ") | gsub("[\n\r]"; " ") | .[:200])" else empty end)
                end
              end
            JQ
            }
            READER="$(reader_program)"
            LINES="$(printf '%s' "$INPUT" | jq -r "$READER" 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: the rollback skill's check could not read the command" >&2; exit 2; }
            [ -n "$LINES" ] || exit 0
            if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then P="$CLAUDE_PROJECT_DIR"
            elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then P="$CLAUDE_PLUGIN_ROOT"
            else P="$(pwd)"; fi
            G="git -c core.fsmonitor=false -c core.hooksPath=/dev/null"
            GD="$($G -C "$P" rev-parse --absolute-git-dir 2>/dev/null || true)"
            case "$GD" in */.git|*/.git/worktrees/*|*/.git/modules/*) ;; *) GD="" ;; esac
            if [ -n "$GD" ] && [ -n "$CWD" ] && [ "$($G -C "$CWD" rev-parse --absolute-git-dir 2>/dev/null || true)" != "$GD" ]; then GD=""; fi
            KEY=""
            if [ -n "$GD" ] && [ -f "$GD/acs/checkpoints/key" ] && [ ! -L "$GD/acs/checkpoints/key" ]; then
              KEY="$(head -c 128 "$GD/acs/checkpoints/key" 2>/dev/null || true)"
              printf '%s\n' "$KEY" | grep -qxE '[0-9a-f]{64}' || KEY=""
            fi
            while IFS= read -r LINE; do
              case "$LINE" in
                "restore "*) SUB="${LINE#restore }"; ARG="${SUB#* }"; SUB="${SUB%% *}" ;;
                "refuse "*)
                  printf "F503 ROLLBACK_FAILED: '%s' restores no checkpoint taken in this project: this skill reads a restore only as git stash apply <sha> (or pop), those four words alone, with the full commit id a checkpoint recorded, in the project's repository; git's options before stash, a program that runs git, a restore inside a word and a word the shell expands or escapes are refused.\n" "${LINE#refuse }" >&2
                  exit 2
                  ;;
                "beside "*)
                  printf "F503 ROLLBACK_FAILED: '%s' runs beside a restore: on a line that restores a checkpoint, each other command only reads (git status, log, diff, show or rev-parse, echo, printf with no option, cat, ls, grep, ...), with no variable set or named (PATH, BASH_CMDS, GIT_*, printf -v), no alias or function, no directory change, no file written and no word the shell expands: any of them may make the restore's git another program, or run it elsewhere. Restore with git stash apply <sha> on its own line.\n" "${LINE#beside }" >&2
                  exit 2
                  ;;
                "unread "*)
                  printf "F503 ROLLBACK_FAILED: the rollback skill cannot read the words of a command that names git stash (%s), so it restores no checkpoint taken in this project. Restore with git stash apply <sha>, the full commit id a checkpoint recorded, on its own line.\n" "${LINE#unread }" >&2
                  exit 2
                  ;;
                *) echo "R407 SAFETY_CHECK_FAILED: the rollback skill's check could not read the command" >&2; exit 2 ;;
              esac
              FOUND=""
              if [ -n "$KEY" ]; then
                E="$GD/acs/checkpoints/commits/$ARG"
                if [ -f "$E" ] && [ ! -L "$E" ]; then
                  SIG="$(printf 'acs-checkpoint-commit:%s' "$ARG" | openssl dgst -sha256 -hmac "$KEY" 2>/dev/null | awk '{print $NF}' || true)"
                  HAVE="$(head -c 128 "$E" 2>/dev/null || true)"
                  if printf '%s\n' "$SIG" | grep -qxE '[0-9a-f]{64}' && [ "$HAVE" = "$SIG" ]; then FOUND=1; fi
                fi
              fi
              if [ -z "$FOUND" ]; then
                printf "F503 ROLLBACK_FAILED: 'git stash %s %s' restores no checkpoint taken in this project. Restore with git stash apply <sha>, the full commit id a checkpoint recorded, in the project's repository.\n" "$SUB" "$ARG" >&2
                exit 2
              fi
            done <<EOF
            $LINES
            EOF
            exit 0
---

## Intent

Execute **rollback** to return what a checkpoint captured to the state it had when the checkpoint was taken, whoever changed it since (STANDARD v1.2 §4.4.1). This is the recovery mechanism in the CAVR (Checkpoint-Act-Verify-Rollback) pattern, used when mutations fail or produce undesired outcomes.

A rollback changes the world back, not the account of it: the record of what happened (`.claude/`, which holds the plugin's audit log, `.audit/`, where earlier releases' skills logged, the host's checkpoint and approval state, the trace, the transcript) is never rolled back. It reaches only what its checkpoint captured: a transmission a `send` made since is reported as `not_covered` (`transmitted`), as is a delegate's change outside the checkpoint (`delegated`).

**Success criteria:**
- Everything the rollback concerns is back in its checkpointed state, and `restored` says so
- What could not be restored is listed in `unrestored`, with a reason
- The restored content's digest matches the checkpoint's (`verification`)

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `checkpoint_id` | Yes | string | ID of checkpoint to restore to |
| `scope` | No | string | Part of what the checkpoint captured to restore, in the host's naming (default: all of it). An item it names that the checkpoint did not capture is `unrestored` (`not_captured`) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Find the checkpoint**: Look it up by ID where the host keeps checkpoint content
   - An expired or used checkpoint can still be restored while its content is kept: validity limits what a checkpoint authorises, not what it restores (STANDARD 1.2.0 §4.4.1, §5.2.2)
   - If its content is gone, report `restored: false` with `{item: "*", reason: discarded}`

2) **Read what changed** (read-only): `git diff --name-status <sha> -- <paths>` (tracked changes, for `changes_reverted`) and `git ls-files --others --exclude-standard -- <paths>`; files **created since** are the untracked ones not in the checkpoint's `excluded` and not under `.claude/` or `.audit/` (the record of what happened, never rolled back)

3) **Restore by mechanism**. The git form is one line, a gated `mutate` (a fresh checkpoint and an approval: it overwrites the current state):
   - `restore_kind: stash`: `git restore --source=<sha> --worktree -- <paths> && git restore --source=<sha>^2 --staged -- <paths>`; `restore_kind: head`: `git restore --source=<sha> --staged --worktree -- <paths>`
   - Then, only when files were created since, `&& rm -f -- <created paths>`; never `git clean` with an empty path list
   - `git stash apply <sha>` aborts once a file it touches changed since the checkpoint; a bare `git stash pop` or `apply` is refused (F503)
   - `file_copy`: copy each file back from the manifest, and remove the files created in scope since
   - Never touch `.claude/`, `.audit/` (the record of what happened) or the host's state

4) **Verify** (read-only): `git diff --quiet <sha> -- <paths>` and the untracked list again, for `verification`

5) **Report**: `unrestored` for what failed (`failed`), was never captured (`not_captured`) or is gone (`discarded`); `not_covered` for changes the checkpoint never covered (`outside_scope`, `transmitted`, and `HEAD` when commits were made since). `restored` is true only if `unrestored` is empty; the step completes either way

6) **Ground claims**: the rollback's own record, the restore and the verification commands

## Output Contract

Return a structured object:

```yaml
restored: boolean  # true only if everything the rollback concerns is back; the step completes either way (§4.4.1)
unrestored:  # what the rollback concerns that is not back; empty exactly when restored is true
  - item: string
    reason: failed | conflict | discarded | not_captured | x-...
    detail: string
not_covered:  # changes since the checkpoint that it never covered; they do not make restored false
  - item: string
    reason: transmitted | delegated | outside_scope | x-...
    detail: string
changes_reverted:
  - item: string
    operation: create | modify | delete | other  # what was undone
    summary: string
verification:
  digest: string  # digest of the restored content, computed as the checkpoint's was (over all it captured)
  match: boolean  # whether it matches the checkpoint's digest
previous_state:  # state before rollback
  summary: string
restored_state:  # state after rollback
  summary: string
next_actions: array[string]  # Suggested follow-up
confidence: number  # probability that the state now matches the checkpoint (§4.1.1)
evidence_anchors: [{ref: "rollback:<checkpoint_id>", kind: record}, {ref: "tool:bash:...", kind: tool}, {ref: "file:...", kind: file}]  # the restore's own record grounds the output (STANDARD v1.2 §3.1)
assumptions: []
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `restored` | boolean | True only if everything the rollback concerns is back (workflows gate on `${<step>.restored}`, §12.5 Checked Rollback) |
| `unrestored` | array | Items not back, each with `failed`, `conflict`, `discarded`, `not_captured` or an `x-` reason |
| `not_covered` | array | Changes the checkpoint never covered: `transmitted`, `delegated`, `outside_scope` or an `x-` reason |
| `changes_reverted` | array | Each `item` and the `operation` undone |
| `verification` | object | The restored content's `digest`, and whether it `match`es the checkpoint's |
| `previous_state` | any | State before rollback |
| `restored_state` | any | State after rollback |
| `next_actions` | array | What to do next (re-plan, investigate, etc.) |
| `confidence` | number | Probability, 0.0-1.0, that the state now matches the checkpoint (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Proof of restoration |
| `assumptions` | array | Explicit assumptions made |

An item holds no secret (§6.7): name a file, not its content, and redact a URL's credentials.

## Examples

### Example 1: Git Rollback After Failed Tests

**Input:**
```yaml
checkpoint_id: "chk_20240115_143022_a7b3c9"
```

Reason for the rollback: tests failed after refactoring. The checkpoint's restore point is a stash commit; one file was created since.

**Output:**
```yaml
restored: true
unrestored: []
not_covered: []
changes_reverted:
  - item: "src/api/handlers/user.py"
    operation: modify
    summary: "Reverted refactored get_user() function"
  - item: "src/api/handlers/auth.py"
    operation: modify
    summary: "Reverted auth token validation changes"
  - item: "src/api/handlers/tokens.py"
    operation: create
    summary: "Removed a file the refactoring added"
verification:
  digest: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  match: true
previous_state:
  summary: "3 handler files with refactored, failing code"
restored_state:
  summary: "Handlers as of the checkpoint"
next_actions:
  - "critique: Analyze why refactoring broke tests"
  - "plan: Create new plan with smaller incremental changes"
confidence: 1.0
evidence_anchors:
  - {ref: "rollback:chk_20240115_143022_a7b3c9", kind: record}
  - {ref: "tool:bash:git diff --name-status 4f1d2c3b5a6978877665544332211009988aabbc -- src/api/handlers", kind: tool}
  - {ref: "tool:bash:git restore --source=4f1d2c3b5a6978877665544332211009988aabbc --worktree -- src/api/handlers", kind: tool}
  - {ref: "tool:bash:git diff --quiet 4f1d2c3b5a6978877665544332211009988aabbc -- src/api/handlers", kind: tool}
assumptions:
  - "No commit was made since the checkpoint"
```

**Evidence pattern:** the changes read before the restore, the restore line, and the verification diff.

---

### Example 2: Partial Rollback After a Send

**Input:**
```yaml
checkpoint_id: "chk_20240115_150000_config"
scope: "config/production.yaml config/secrets.env"
```

Reason for the rollback: the config migration caused a service failure, after a notification was sent.

**Output:**
```yaml
restored: false
unrestored:
  - item: "config/secrets.env"
    reason: not_captured
    detail: "excluded from the checkpoint: it holds secrets"
not_covered:
  - item: "send to https://hooks.example.com/deploys (run-7:12)"
    reason: transmitted
changes_reverted:
  - item: "config/production.yaml"
    operation: modify
    summary: "Reverted database connection string changes"
verification:
  digest: "sha256:9b74c9897bac770ffc029102a200c5de0b1d5e5d3c1b0e2f4a6c8e0a2b4c6d8e"
  match: true
previous_state:
  summary: "Migrated database connection string"
restored_state:
  summary: "Original production config; secrets.env as it is now"
next_actions:
  - "inquire: secrets.env was never captured; ask how to restore it"
  - "send: tell the deploy channel the migration was rolled back"
confidence: 0.9
evidence_anchors:
  - {ref: "rollback:chk_20240115_150000_config", kind: record}
  - {ref: "tool:bash:git restore --source=1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d --staged --worktree -- config/production.yaml", kind: tool}
  - {ref: "file:config/production.yaml:1", kind: file}
assumptions:
  - "The notification cannot be recalled; a new send corrects it"
```

## Verification

Apply the following verification patterns:

- [ ] **Rollback Verification**: `verification.match` is true for what was restored (CRITICAL)
- [ ] **Report Complete**: `restored` is true exactly when `unrestored` is empty
- [ ] **State Assertion**: No file created since remains in scope
- [ ] **Evidence Grounding**: Restore command execution is captured

**Verification tools:** Bash (for restore and hash), Git (for the diff and the restore)

## Safety Constraints

- `mutation`: true (modifies files to restore state)
- `requires_checkpoint`: false (but a `checkpoint` MUST precede it: the ontology's `checkpoint` → `rollback` `requires` edge, else V102)
- `requires_approval`: false
- `risk`: medium

**Capability-specific rules:**
- CRITICAL: Never rollback without a checkpoint_id that exists
- CRITICAL: Never report `restored: true` for a rollback that did not complete
- Clean up the files created in scope since the checkpoint
- An expired or used checkpoint can be restored (STANDARD 1.2.0 §5.2.2); the safety layer refuses a restore only when no checkpoint was ever taken (F503)
- Never roll back the record of what happened: `.claude/` (the plugin's audit log), `.audit/` (earlier releases' logs), the host's checkpoint and approval state
- A transmission is not undone: report it `transmitted`, and compensate in a step of its own
- If verification fails, STOP and alert - do not proceed

## Composition Patterns

**Commonly follows:**
- `verify` - When verify returns `passed: false`, trigger rollback (CAVR pattern)
- `mutate` / `execute` - If the side effect fails or verify returns `passed: false`, rollback
- `checkpoint` - Rollback requires prior checkpoint (dependency)

**Commonly precedes:**
- `critique` - After rollback, analyze what went wrong
- `plan` - Create new plan after understanding failure
- `audit` - Record the rollback event

**Anti-patterns:**
- CRITICAL: Never rollback without existing checkpoint
- CRITICAL: Never continue mutations after rollback without new checkpoint
- Never skip verification after rollback
- Never delete checkpoint until rollback verification passes

**Workflow references:**
- See `reference/composition_patterns.md#checkpoint-act-verify-rollback` for CAVR pattern
- See `reference/verification_patterns.md#pattern-4-rollback-verification` for rollback verification
- See `reference/composition_patterns.md#debug-code-change` for rollback-then-critique flow
