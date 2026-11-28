---
name: persist
description: Write stable learnings, decisions, and patterns to durable storage like CLAUDE.md or knowledge files. Use when saving project decisions, recording patterns, or updating long-term memory.
argument-hint: "[data] [key] [ttl]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Edit
context: fork
agent: general-purpose
hooks:
  PreToolUse:
    - matcher: "Edit|Write|MultiEdit|NotebookEdit"
      hooks:
        - type: prompt
          prompt: |
            Model-judged additions (STANDARD 1.2.0 §5.18.10): these may refuse
            the call; the checks the Standard requires (approval, the checkpoint,
            rollback history, the destination policy, secrets) are made by code,
            not here.

            PERSIST DATA VALIDATION CHECK

            The tool call follows this prompt as JSON; the target file is
            tool_input.file_path (tool_input.notebook_path for NotebookEdit) and the
            content to write is tool_input.new_string (Edit), tool_input.content
            (Write), each tool_input.edits[].new_string (MultiEdit) or
            tool_input.new_source (NotebookEdit).

            Verify before persisting:
            1. NO credentials, API keys, or secrets in content
            2. NO personally identifiable information (PII)
            3. NO executable code that could be malicious
            4. File is within project scope (not system files)
            5. Content is stable knowledge (not ephemeral data)

            Also check:
            - Is this a duplicate of existing content?
            - Does this contradict existing persisted facts?

            Return ok: true if content is safe to persist.
            Return ok: false, with the specific reason, if validation fails.
          once: false
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # Code-decided checks (STANDARD 1.2.0 §5.18.10): the target file is not
            # a system or credential file, and the content holds no credential
            # (§6.7). Claude Code passes the tool call (Edit, Write, MultiEdit or
            # NotebookEdit) as JSON on stdin, read once here; exit 2 blocks the call and the
            # reason on stderr is shown to Claude. A call that cannot be read is
            # blocked.
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # Each path is read exactly: a command substitution strips the line
            # breaks that end its output, and a file's name may end in one
            # (notes/k and notes/k<newline> are two files), so an x is printed
            # after the path and taken off (with the line break pwd or readlink
            # prints, which every such output must end in).
            TARGET="$(printf '%s' "$INPUT" | jq -j '(.tool_input.file_path // .tool_input.notebook_path // empty), "x"' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            TARGET="${TARGET%x}"
            case "$TARGET" in
              "~/"*) TARGET="${HOME}/${TARGET#??}" ;;
            esac
            NL="$(printf '\nx')"
            NL="${NL%x}"
            # The file the write reaches: symbolic links followed. The deepest
            # directory of the path that exists, as `cd -P` resolves it, then the
            # rest of the path; a target that is itself a link is followed (at
            # most 8 links). Fails on a link it cannot read.
            resolve() {
              R_PATH="$1"
              R_LINKS=0
              while :; do
                case "$R_PATH" in
                  /*) ;;
                  *)
                    R_HERE="$(pwd -P && printf x)" || return 1
                    R_HERE="${R_HERE%x}"
                    case "$R_HERE" in *"$NL") R_HERE="${R_HERE%?}" ;; *) return 1 ;; esac
                    R_PATH="$R_HERE/$R_PATH"
                    ;;
                esac
                R_DIR="${R_PATH%/*}"
                R_REST="${R_PATH##*/}"
                while [ -n "$R_DIR" ] && [ ! -d "$R_DIR" ]; do
                  R_REST="${R_DIR##*/}/$R_REST"
                  R_DIR="${R_DIR%/*}"
                done
                R_DIR="$(cd -P "${R_DIR:-/}" 2>/dev/null && pwd -P && printf x)" || return 1
                R_DIR="${R_DIR%x}"
                case "$R_DIR" in *"$NL") R_DIR="${R_DIR%?}" ;; *) return 1 ;; esac
                R_PATH="${R_DIR%/}/$R_REST"
                [ -L "$R_PATH" ] || break
                R_LINKS=$((R_LINKS + 1))
                [ "$R_LINKS" -le 8 ] || return 1
                # The target exactly: BSD readlink (macOS) prints a target that
                # ends in a line break without one more, so perl reads it where
                # it is installed, and GNU readlink's output otherwise
                if command -v perl >/dev/null 2>&1; then
                  R_TO="$(perl -e 'defined(my $t = readlink $ARGV[0]) or exit 1; print $t, "x"' -- "$R_PATH" 2>/dev/null)" || return 1
                  R_TO="${R_TO%x}"
                else
                  R_TO="$(readlink "$R_PATH" 2>/dev/null && printf x)" || return 1
                  R_TO="${R_TO%x}"
                  case "$R_TO" in *"$NL") R_TO="${R_TO%?}" ;; *) return 1 ;; esac
                fi
                case "$R_TO" in /*) R_PATH="$R_TO" ;; *) R_PATH="${R_PATH%/*}/$R_TO" ;; esac
              done
              printf '%sx' "$R_PATH"
            }
            REAL="$TARGET"
            if [ -n "$TARGET" ]; then
              REAL="$(resolve "$TARGET")" || { echo "F504 CONSTRAINT_VIOLATED: Cannot persist through a symbolic link that cannot be followed" >&2; exit 2; }
              REAL="${REAL%x}"
            fi
            HOME_REAL="$(cd -P "${HOME:-/}" 2>/dev/null && pwd -P)" || HOME_REAL="${HOME:-}"
            # Each check reads the path as written and the file it reaches
            for P in "$TARGET" "$REAL"; do
              # A path with '//', '.' or '..' segments is not compared as written
              # (/tmp/../etc/passwd is /etc/passwd), so it is blocked
              case "$P" in
                *//*|*/./*|*/.|*/../*|*/..|../*|..)
                  echo "F504 CONSTRAINT_VIOLATED: Cannot persist to a path with '//', '.' or '..' segments; give the normalised path" >&2
                  exit 2
                  ;;
              esac
              # Block writes to system directories (/private/etc is macOS's /etc),
              # to credential directories under the home directory, and to Claude
              # Code's own settings there
              case "$P" in
                /etc/*|/private/etc/*|/usr/*|/bin/*|/sbin/*|"${HOME}"/.ssh/*|"${HOME}"/.aws/*|"${HOME}"/.config/*|"${HOME}"/.claude/*|"${HOME_REAL}"/.ssh/*|"${HOME_REAL}"/.aws/*|"${HOME_REAL}"/.config/*|"${HOME_REAL}"/.claude/*)
                  echo "F504 CONSTRAINT_VIOLATED: Cannot persist to system or credential directories" >&2
                  exit 2
                  ;;
              esac
              # Block writes to credential files
              if printf '%s\n' "$P" | grep -qiE "(\.env|credentials|secrets|password|\.pem|\.key)$"; then
                echo "F504 CONSTRAINT_VIOLATED: Cannot persist to credential files" >&2
                exit 2
              fi
            done
            # What the call stores (§5.18.10, §6.7): the text it carries (an Edit's
            # new_string, a Write's content, each new_string of a MultiEdit's edits,
            # a NotebookEdit's new_source), and the lines of the file as it will be
            # after the call that the file does not hold now, so a credential whose
            # key, or whose other half, is already in the file, or that two edits or
            # calls build, is read whole; and each again with the escapes a reader
            # resolves (\uXXXX, \UXXXXXXXX, \xXX, \/ and \") decoded. Each text is
            # read line by line and with its line breaks read as blanks (a value on
            # the line under its name). A credential the changed lines build with the
            # lines around them (a value put under a name the file holds, a name put
            # over a value, a line taken out from between them) is found by reading
            # the changed lines and six lines that are not blank on each side, after
            # the call and before it: a value read more often after it is refused. A
            # call that changes a line of a private key block (from its BEGIN line to
            # its END line, or to the end of the file) is refused: the body lines of a
            # key match no rule of their own. The file is
            # read only when it is a regular file of at most 8 MB; any other existing
            # target is refused. It is read as Claude Code's Edit reads it: a file
            # opening with the bytes FF FE as UTF-16LE (converted with iconv; without
            # it, refused), and CRLF line ends as LF. The edits are applied in order
            # as Claude Code applies them: old_string found as written, else with
            # curly quotes read as straight ones; replace_all honoured; and an empty
            # new_string removes old_string with the line break after it when the
            # file holds that. An old_string the file holds in neither form (Claude
            # Code may still find it, as a \uXXXX escape of a character or the
            # character of one) is refused: this check cannot tell what the file will
            # hold.
            BEFORE=/dev/null
            if [ -n "$REAL" ] && { [ -e "$REAL" ] || [ -L "$REAL" ]; }; then
              [ -f "$REAL" ] || { echo "F504 CONSTRAINT_VIOLATED: Cannot persist to something that is not a regular file" >&2; exit 2; }
              SIZE="$(wc -c < "$REAL" 2>/dev/null | tr -d ' ')" || SIZE=""
              case "$SIZE" in ''|*[!0-9]*) echo "R407 SAFETY_CHECK_FAILED: cannot read the file the call writes" >&2; exit 2 ;; esac
              [ "$SIZE" -le 8388608 ] || { echo "F504 CONSTRAINT_VIOLATED: the file is over 8 MB, more than this check reads; persist to a smaller file" >&2; exit 2; }
              BEFORE="$REAL"
              BOM="$(od -An -tx1 -N2 "$REAL" 2>/dev/null | tr -d ' \n')" || BOM=""
              if [ "$BOM" = "fffe" ]; then
                UTF8="$(mktemp 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the file the call writes" >&2; exit 2; }
                trap 'rm -f "$UTF8"' EXIT
                iconv -f UTF-16LE -t UTF-8 < "$REAL" > "$UTF8" 2>/dev/null || { echo "R407 SAFETY_CHECK_FAILED: cannot read the file the call writes as UTF-16 text (iconv is required)" >&2; exit 2; }
                BEFORE="$UTF8"
              fi
            fi
            EXISTS=false
            [ "$BEFORE" = /dev/null ] || EXISTS=true
            STATUS=0
            READ="$(printf '%s' "$INPUT" | jq -c --rawfile before "$BEFORE" --argjson exists "$EXISTS" '
              # join, in time linear in the text (the builtin join copies the text
              # it has built at each piece: 3.4 s for a 1 MB file of CRLF lines)
              def joined($s): (.[0:1] + (.[1:] | map($s + .))) | add // "";
              def hexval: reduce explode[] as $c (0; . * 16 + (if $c >= 97 then $c - 87 elif $c >= 65 then $c - 55 else $c - 48 end));
              def ishex: explode | all(. >= 48 and . <= 57 or . >= 65 and . <= 70 or . >= 97 and . <= 102);
              def unescape($mark; $n):
                if index($mark) == null then . else
                  split($mark) as $p
                  | $p[0] + ([$p[1:][] | .[:$n] as $h
                      | (if ($h | length) == $n and ($h | ishex) then $h | hexval else -1 end) as $v
                      | if $v >= 32 and ($v < 55296 or ($v > 57343 and $v < 1114112))
                        then ([$v] | implode) + .[$n:] else $mark + . end] | joined(""))
                end;
              def decoded: unescape("\\u"; 4) | unescape("\\U"; 8) | unescape("\\x"; 2)
                | split("\\/") | joined("/") | split("\\\"") | joined("\"");
              def straight: split("\u2018") | joined("\u0027") | split("\u2019") | joined("\u0027")
                | split("\u201c") | joined("\"") | split("\u201d") | joined("\"");
              def replaced($o; $n; $all):
                split($o) as $p
                | if ($p | length) < 2 then null
                  elif $all then $p | joined($n)
                  else $p[0] + $n + ($p[1:] | joined($o)) end;
              def edited($o; $n; $all):
                (if $n == "" and ($o | endswith("\n") | not) and index($o + "\n") != null
                 then $o + "\n" else $o end) as $l
                | replaced($l; $n; $all);
              def apply($e):
                ($e.old_string) as $o | ($e.new_string) as $n | ($e.replace_all == true) as $all
                | if ($o | type) != "string" or ($n | type) != "string" then .
                  elif $o == "" then $n + .
                  else edited($o; $n; $all)
                    // (straight | edited($o | straight; $n; $all))
                    // (if $exists then "" | halt_error(3) else . end) end;
              def counts: reduce (split("\n")[]) as $l ({}; .[$l] += 1);
              def added($b; $a):
                ($b | counts) as $had
                | $a | counts | to_entries | map(select(.value > ($had[.key] // 0)) | .key) | joined("\n");
              def nonblank: . != "" and (explode | any(.[]; . != 32 and . != 9 and . != 11 and . != 12 and . != 13));
              # The lines the call changes in $a (from the first line that differs from the line of $b
              # to the last, counted from each end), with the six lines that are not blank before them and
              # the six after them, and the same lines of $b: no rule of the scan matches across more than
              # five runs of whitespace, so a credential the change builds with the lines around it (a
              # value on the line under its name) is read whole in $a, and one the lines around it held
              # already is read in $b too
              def region($b; $a):
                ($b | split("\n")) as $bl | ($a | split("\n")) as $al
                | ($bl | length) as $nb | ($al | length) as $na | ([$nb, $na] | min) as $n
                | (first(range(0; $n) | select($bl[.] != $al[.])) // $n) as $p
                | (first(range(0; $n - $p) | select($bl[$nb - 1 - .] != $al[$na - 1 - .])) // ($n - $p)) as $s
                | ([limit(6; range($p - 1; -1; -1) | select($al[.] | nonblank))] | if length == 6 then .[-1] else 0 end) as $from
                | ([limit(6; range($na - $s; $na) | select($al[.] | nonblank))] | if length == 6 then .[-1] + 1 else $na end) as $to
                | {lines: $al, start: $p, end: ($na - $s),
                   after: ($al[$from:$to] | joined("\n")), before: ($bl[$from:($to - $na + $nb)] | joined("\n"))};
              def keyhead: index("PRIVATE KEY") != null and index("-----BEGIN ") != null
                and test("-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----");
              def keyend: index("PRIVATE KEY") != null and index("-----END ") != null
                and test("-----END ([A-Z0-9]+ )*PRIVATE KEY( BLOCK)?-----");
              # Whether a changed line is in a private key block, from its BEGIN line to its END line
              # or the end of the text: the body lines of a key match no rule of their own
              def inkey($r):
                first(foreach $r.lines[0:$r.end][] as $l ({i: -1, open: false, hit: false};
                    ($l | keyhead) as $h
                    | .i += 1
                    | .hit = ((.open or $h) and .i >= $r.start)
                    | .open = (if $h then ($l | split("-----BEGIN ") | .[-1]
                                 | test("^[A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----.+-----END ([A-Z0-9]+ )*PRIVATE KEY( BLOCK)?-----") | not)
                               elif .open then ($l | keyend | not)
                               else false end);
                    select(.hit)) | true) // false;
              def blanked: split("\r") | joined(" ") | split("\n") | joined(" ");
              ($before | split("\r\n") | joined("\n")) as $before
              | .tool_input as $t
              | ([$t.new_string, $t.content, $t.new_source,
                  (($t.edits | if type == "array" then .[] else empty end) | objects | .new_string)]
                 | map(select(type == "string"))) as $carried
              | (if ($t.content | type) == "string" then $t.content
                 elif ($t.edits | type) == "array" then reduce ($t.edits[] | objects) as $e ($before; apply($e))
                 elif ($t.old_string | type) == "string" then $before | apply($t)
                 else $before end) as $after
              | ($before | straight) as $b | ($after | straight) as $a
              # Each text read on its own, as it is and with its line breaks read as blanks
              | def lines_of($texts): $texts + [$texts[] | select(index("\n") != null or index("\r") != null) | blanked]
                  | joined("\n") | split("\u0000") | joined(" ");
              # ... and the windows with their line breaks read as blanks (a credential on one line is
              # read in the lines the call adds), and decoded too where that changes either, so what the
              # unchanged lines hold is listed as often on each side
                def sides($r): [$r.after, $r.before] | map(blanked)
                  | (if map(decoded) != . then map(. + "\n" + decoded) else . end) | map(split("\u0000") | joined(" "));
                ($carried + [added($b; $a)] | group_by(.) | map(.[0])) as $texts
              | [lines_of($texts + ($texts | map(decoded) - $texts))]
                + (if ($t.content | type) == "string" or $b == $a then ["", ""] else region($b; $a)
                   | if ($a | contains("PRIVATE KEY")) and inkey(.) then "" | halt_error(4) else sides(.) end end)
            ' 2>/dev/null)" || STATUS=$?
            case "$STATUS" in
              0) ;;
              4) echo "F504 CONSTRAINT_VIOLATED: the call changes a line of a private key block (from its BEGIN line to its END line), so the file would hold what looks like a credential; persist where the secret is kept, not the secret (STANDARD 1.2.0 §6.7)" >&2; exit 2 ;;
              3) echo "R407 SAFETY_CHECK_FAILED: the file does not hold old_string as written (nor with curly quotes read as straight ones), so this check cannot tell what the file will hold; give old_string as the file spells it" >&2; exit 2 ;;
              *) echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call or the file it writes (jq is required)" >&2; exit 2 ;;
            esac
            # The three texts: what the call carries and the lines it adds, and the changed lines
            # with the lines around them as the file will hold them and as it holds them now
            CONTENT="$(printf '%s' "$READ" | jq -r '.[0]' 2>/dev/null)" &&
              AFTER="$(printf '%s' "$READ" | jq -r '.[1]' 2>/dev/null)" &&
              WAS="$(printf '%s' "$READ" | jq -r '.[2]' 2>/dev/null)" ||
              { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call or the file it writes (jq is required)" >&2; exit 2; }
            # BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
            # secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7), read line by line and again with
            # its line breaks read as blanks, as the SDK's and the TypeScript rules read whitespace (password:<newline>value).
            # secret_lines TEXT: the same rules, each line read on its own; a caller that joins texts read apart joins them with line
            # breaks, each text given once as it is and once with its own line breaks read as blanks.
            # secret_values TEXT: what the rules whose match may hold whitespace find in TEXT, one per line, each line read on its own:
            # the match, or the value a rule reads out of it (a caller compares what two texts hold).
            # Each reads TEXT with the JSON escapes some encoders write decoded (secret_decoded), and secret_lines first looks for a
            # value the layer holds itself (secret_held).
            # The shapes of keys and tokens (the first two may hold whitespace)
            SECRET_SPACED='-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}'
            # sk- is read only where a token starts, not after an ASCII letter or digit, since its two letters end common words
            # (task-, risk-, disk-); the longer prefixes are read anywhere
            SECRET_ERE="$SECRET_SPACED"'|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
            # ... and service tokens by their prefix (Stripe, Google, GitLab, npm, Vault, SendGrid) and a Slack webhook's path
            SECRET_ERE="$SECRET_ERE"'|[rs]k_(live|test)_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}|hv[sbr]\.[A-Za-z0-9_-]{24,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{16,}'
            # A signed URL's signature, read in any letter case (grep -i): the value, 16 or more characters, of an X-Amz-Signature
            # (S3 SigV4), X-Goog-Signature (Cloud Storage), sig (Azure SAS) or Signature (S3 SigV2, CloudFront) query parameter, read
            # only after ? or & (as themselves, percent-encoded or as their JSON escapes), so prose such as signature= is not read; the
            # value stops at & and ? in any of those forms (%26, %3F)
            SECRET_SIGNED='([?&]|%3F|%26|\\u00(3F|26))(x-amz-signature|x-goog-signature|sig|signature)(=|%3D|\\u003D)([A-Za-z0-9._~+/=-]|\\/|%([014-9A-F][0-9A-F]|2[0-57-9A-F]|3[0-9A-E])){16,}'
            SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|account[_-]?key|signing[_-]?key|encryption[_-]?key|hmac[_-]?key|master[_-]?key|credential)'
            # A quote, or an escaped one (\" in JSON text inside a JSON string)
            SECRET_Q="\\\\*[\"']"
            # A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password; a user of at most 256 characters, so no run is read again from each of its positions; written {0,255} and one more, since BSD grep refuses a count over 255)
            SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
            SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
            SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]{0,255}[^[:space:]:\"'\\\\]?:"
            # curl's cookie option (-b, --cookie), up to its value, and up to the quote its value opens with
            SECRET_COOKIE_OPT="(^|[^A-Za-z0-9_-])(-b$SECRET_SEP?|--cookie$SECRET_SEP)"
            SECRET_COOKIE_OPTQ="(^|[^A-Za-z0-9_-])(-b([[:space:]]+|=|($SECRET_Q)?[[:space:]]*,[[:space:]]*)?|--cookie([[:space:]]+|=|($SECRET_Q)?[[:space:]]*,[[:space:]]*))$SECRET_Q"
            # A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
            SECRET_QUOTED="$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']"
            # The rules are ASCII, read byte by byte (LC_ALL=C, in a subshell): a multibyte locale sends some of them to a matcher whose time grows with the square of the text
            # secret_held TEXT: status 0 when TEXT holds, as written, the value of AUDIT_HMAC_KEY (the key the plugin's audit log is
            # signed with) or of SECRET_HELD (a value the calling hook holds itself), 4 characters or more: a host recognises the
            # credentials it holds itself (STANDARD 1.2.0 §6.7)
            secret_held() (
              for SECRET_VALUE in "${AUDIT_HMAC_KEY:-}" "${SECRET_HELD:-}"; do
                [ "${#SECRET_VALUE}" -ge 4 ] || continue
                case "$1" in *"$SECRET_VALUE"*) return 0 ;; esac
              done
              return 1
            )
            # secret_decoded TEXT: TEXT with the JSON escapes some encoders write for characters the rules read decoded, \u0022 and
            # \u0027 as an escaped quote (\" and \'), \u0026, \u002b, \u003c, \u003d and \u003e (Go's, Gson's and .NET's HTML-safe
            # escapes, in either case) as the character, and \/ (PHP's) as /; the SDK's and the TypeScript rules decode the same
            secret_decoded() (
              LC_ALL=C
              export LC_ALL
              printf '%s' "$1" | sed -e 's/\\u0022/\\"/g' -e "s/\\\\u0027/\\\\'/g" -e 's/\\u0026/\&/g' -e 's/\\u002[bB]/+/g' \
                -e 's/\\u003[cC]/</g' -e 's/\\u003[dD]/=/g' -e 's/\\u003[eE]/>/g' -e 's#\\/#/#g'
            )
            secret_values() (
              LC_ALL=C
              export LC_ALL
              case "$1" in
                *'\u00'* | *'\/'*)
                  SECRET_TEXT="$(secret_decoded "$1")" || { echo '(unread)'; return 0; }
                  set -- "$SECRET_TEXT"
                  ;;
              esac
              printf '%s' "$1" | grep -Eo -- "$SECRET_SPACED"
              printf '%s' "$1" | grep -Eio -- "$SECRET_QUOTED"
              # An Authorization header's value, 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}" |
                sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -E '[A-Za-z]'
              # ... or after any other scheme (ApiKey, SSWS, Bot) and spaces: the first word may be the scheme or the credential, so both readings count
              printf '%s' "$1" | grep -Eio -- "(proxy-)?authorization($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}" |
                sed -E 's/^.* //' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              # A header's or credential's value given as a name/value pair, or a tuple of exactly two, in text: 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
                sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
                sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
                grep -E '[0-9]' | grep -E '[A-Za-z]'
              # ... and the same after any other scheme
              printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"'\\\\]*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
                sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.* //" |
                grep -E '[0-9]' | grep -E '[A-Za-z]'
              # A user option's password (curl -u user:password), 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eo -- "$SECRET_USER[^[:space:]\"'\\\\]{8,}" |
                sed -E 's/^[^:]*://' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              # An unquoted value of 12 or more characters with letters and digits, assigned or given to a credential option
              printf '%s' "$1" | grep -Eio -- "$SECRET_OPT[[:space:]]+[^-[:space:]\"'][^[:space:]\"']{11,}" |
                sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              printf '%s' "$1" | grep -Eio -- "$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
                sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              # A .netrc entry's password (machine <host> login <user> password <value>), 8 or more characters with letters and digits
              printf '%s' "$1" | grep -Eo -- "(^|[^A-Za-z0-9_-])(machine|login|account|default)[[:space:]]+([^[:space:]]+[[:space:]]+)?password[[:space:]]+[^[:space:]\"']{8,}" |
                sed -E 's/^.*[[:space:]]//' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              # A cookie (name=value) in a Cookie or Set-Cookie header's value (to the end of its line or its closing quote), or in
              # curl's cookie option's value (holding a name and = in its first 64 characters; quoted, or to a blank): a value of 8 or
              # more token characters with letters and digits, a Set-Cookie attribute aside
              {
                printf '%s' "$1" | grep -Eio -- "(set-)?cookie($SECRET_Q)?[[:space:]]*[:=][[:space:]]*($SECRET_Q)?[^[:space:]\"'\\\\][^[:cntrl:]\"'\\\\]*" |
                  sed -E "s/^[^:=]*[:=][[:space:]]*(\\\\*[\"'])?//"
                printf '%s' "$1" | grep -Eo -- "$SECRET_COOKIE_OPTQ[^[:cntrl:]\"'\\\\=]{0,64}=[^[:cntrl:]\"'\\\\]*" |
                  sed -E "s/^.?(-b|--cookie)([[:space:]]+|=|(\\\\*[\"'])?[[:space:]]*,[[:space:]]*)?\\\\*[\"']//"
                printf '%s' "$1" | grep -Eo -- "$SECRET_COOKIE_OPT[^[:space:]\"'\\\\=]{0,64}=[^[:space:]\"'\\\\]*" |
                  sed -E "s/^(.?-b|.?--cookie)([[:space:]]+(\\\\*[\"'])?|=(\\\\*[\"'])?|(\\\\*[\"'])?[[:space:]]*,[[:space:]]*\\\\*[\"'])?//"
              } | tr ';, ' '\n\n\n' | grep -E '^[^=]*=' | grep -Eiv '^(path|domain|expires|max-age|samesite|secure|httponly|partitioned|priority)=' |
                sed -E 's/^[^=]*=//' | grep -Ex '[A-Za-z0-9._~+/=%-]{8,}' | grep -E '[0-9]' | grep -E '[A-Za-z]'
              return 0
            )
            secret_lines() (
              LC_ALL=C
              export LC_ALL
              secret_held "$1" && return 0
              SECRET_TEXT="$1"
              case "$1" in
                *'\u00'* | *'\/'*) SECRET_TEXT="$(secret_decoded "$1")" || return 0 ;;
              esac
              printf '%s' "$SECRET_TEXT" | grep -Eq -- "$SECRET_ERE" && return 0
              printf '%s' "$SECRET_TEXT" | grep -Eiq -- "$SECRET_SIGNED" && return 0
              # The password of a URL's userinfo, unless it is a placeholder (its scheme read from the start of its run, once; its
              # slashes escaped or not)
              printf '%s' "$SECRET_TEXT" | grep -Eo -- '(^|[^A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*:(\\*/){2}[^[:space:]/:@]*:[^[:space:]/@]+@' |
                sed -E 's#^.*/[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
              # The rules that read a quoted value, or a value out of a match
              secret_values "$1" | grep -q .
            )
            secret_in() (
              secret_lines "$1" && return 0
              SECRET_FOLDED="$(printf '%s' "$1" | LC_ALL=C tr '\n\r' '  ')" || return 0
              [ "$SECRET_FOLDED" != "$1" ] && secret_lines "$SECRET_FOLDED"
            )
            # END secret-scan
            # Memory is read back as fact, so a credential is refused, not redacted
            if secret_lines "$CONTENT"; then
              echo "F504 CONSTRAINT_VIOLATED: the content holds what looks like a credential; persist where the secret is kept, not the secret (STANDARD 1.2.0 §6.7)" >&2
              exit 2
            fi
            # A credential the changed lines build with the lines around them: a value the rules
            # read in the file as it will be more often than in the file as it is (a credential
            # those lines held already is listed as often on both sides)
            if [ -n "$AFTER" ]; then
              ADDS="$( { secret_values "$WAS" | sed 's/^/-/'; secret_values "$AFTER" | sed 's/^/+/'; } |
                LC_ALL=C awk '{ k = substr($0, 2); if (substr($0, 1, 1) == "+") n[k]++; else n[k]-- }
                  END { for (k in n) if (n[k] > 0) { print "yes"; exit } print "no" }')"
              case "$ADDS" in
                no) ;;
                yes) echo "F504 CONSTRAINT_VIOLATED: the content holds what looks like a credential; persist where the secret is kept, not the secret (STANDARD 1.2.0 §6.7)" >&2; exit 2 ;;
                *) echo "R407 SAFETY_CHECK_FAILED: cannot compare what the file holds before and after the call (awk is required)" >&2; exit 2 ;;
              esac
            fi
            exit 0
---

## Intent

Execute **persist** to write stable learnings, decisions, and patterns to durable storage for future recall and consistency.

**Success criteria:**
- Content is written to the correct destination
- Existing content is preserved or properly merged
- New content follows established structure/format
- Metadata (timestamp, source) is recorded
- Write is verified successfully

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `data` | Yes | any | Data to store; it round-trips as I-JSON, and data holding a secret is refused (STANDARD v1.2 §4.5, §6.7) |
| `key` | No | string | Storage key; without one the host chooses it and returns it as `key` |
| `ttl` | No | string | Time to live, a duration (§5.10.1) longer than zero, e.g. `30d` or `PT12H`; the entry ends `ttl` after `stored_at` |
| `scope` | No | string | Who can read the entry and how long it lasts: `run`, `session`, `user`, `project`, `global` or an `x-` name (§4.5); the host's default (`session`) when absent |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Validate content**: Ensure content is appropriate for persistence
   - Check content is non-empty and meaningful
   - Verify content type classification
   - Ensure no sensitive data (credentials, PII) is being persisted: data that holds a secret is refused, not redacted, since memory is read back as fact (STANDARD v1.2 §6.7). Persist where the secret is kept (an environment variable's name, a vault path), not the secret
   - Validate content structure if object

2) **Determine scope and destination** (STANDARD v1.2 §4.5): the entry `{key, scope, data, stored_at, expires_at}` goes to the scope's store
   - `session` (the default): this conversation
   - `project`: a file the project keeps (`CLAUDE.md` for decisions and patterns, a specific file for domain knowledge)
   - `user`, `global`, `run`: the store the host provides for them
   - A scope this host does not provide: store nothing, and answer `unsupported_scope`; a `ttl` that is not a duration longer than zero: store nothing, and answer `unsupported_ttl`
   - Data that holds a secret: store nothing, and answer `secret_in_data`

3) **Read existing content**: Load current state of destination
   - Parse structure and sections
   - Identify target section for new content
   - Note existing entries to avoid duplicates

4) **Check for duplicates/conflicts**: Compare new vs existing
   - Exact duplicate: Skip or update timestamp only
   - Similar content: Flag for review
   - Contradiction: Stop and request clarification

5) **Format new content**: Structure for persistence
   - Add timestamp and source metadata
   - Format according to destination conventions
   - Include rationale if decision/pattern

6) **Apply the write**: A persist to a key that holds an entry replaces it
   - To combine with what is there, `recall` it first and persist the combined data
   - Within a file, `append` a new section, or `replace` the entry under the key

7) **Write to destination**: Execute the write operation
   - Use Edit tool for file modifications
   - Preserve file formatting and structure
   - Add section headers if needed

8) **Verify write** (read-after-write, §4.5): read the key back in the scope and compare
   - The data read back equals the data stored; then report `stored: true` with `stored_at` (and `expires_at` for a `ttl`)
   - `stored: false` means nothing was written or replaced: the step completes, and a workflow that depends on the write checks `stored`

## Output Contract

Return a structured object:

```yaml
stored: boolean  # true: a recall of the key in the scope returns the data until the entry ends; false: nothing was written (§4.5)
key: string  # Storage key (destination and section, e.g. "CLAUDE.md#Patterns")
scope: string  # The scope used (§4.5)
stored_at: string  # ISO 8601 date-time the entry was stored
expires_at: string | null  # When the entry ends, for an entry with a ttl
timestamp: string  # Deprecated: the same instant as stored_at
persisted:
  content_type: decision | pattern | fact | context
  content_id: string  # Unique identifier for this persisted item
  destination: string  # File path where content was written
  section: string | null  # Section within file
write_operation:
  strategy: append | replace | merge
  bytes_written: integer
  lines_added: integer
  lines_modified: integer
verification:
  write_confirmed: boolean
  content_present: boolean
  structure_valid: boolean
metadata:
  source: string  # Where this knowledge came from
  related_entries: array[string]  # IDs of related persisted items
  expiry: string | null  # When this knowledge should be reviewed
duplicates_found:
  - existing_id: string
    similarity: number
    action_taken: skipped | updated | merged
confidence: number  # probability that the data was stored as reported (§4.1.1)
evidence_anchors: array[EvidenceAnchor]  # References to verification; each {ref, kind} (STANDARD v1.2 §6.5)
assumptions: array[string]  # Explicit assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `stored` | boolean | True: a later `recall` of the key in the scope returns the data until the entry ends (read-after-write, §4.5); false: nothing was written or replaced |
| `key` | string | Storage key the data lives under (destination and section) |
| `scope` | string | The scope used; a step of a 1.2 workflow that binds `scope` fails unless this echoes it (R402, `unsupported_scope`) |
| `stored_at` | string | ISO 8601 date-time the entry was stored |
| `expires_at` | string | When the entry ends, for an entry with a `ttl`; from then on a `recall` does not find it |
| `timestamp` | string | Deprecated: the same instant as `stored_at`; read `stored_at` (a reference to it is W603) |
| `persisted.content_id` | string | Unique ID for retrieval with `recall` |
| `persisted.destination` | string | File path of storage location |
| `write_operation` | object | Details of the write performed |
| `verification.write_confirmed` | boolean | Whether write was verified |
| `duplicates_found` | array | Any duplicate/similar entries detected |
| `confidence` | number | Probability, 0.0-1.0, that the data was stored as reported (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | References to the written location and its verification |
| `assumptions` | array | Explicit assumptions |

## Examples

### Example 1: Persisting a Project Decision

**Input:**
```yaml
data:
  content_type: decision
  decision: "Use PostgreSQL for all persistent storage"
  rationale: "Strong ACID guarantees, mature ecosystem, team familiarity"
  context: "Evaluated PostgreSQL, MySQL, and MongoDB for new backend service"
  constraints:
    - "Must support complex queries"
    - "Team has PostgreSQL experience"
key: "CLAUDE.md#Architecture Decisions"
scope: project
```

**Output:**
```yaml
stored: true
key: "CLAUDE.md#Architecture Decisions"
scope: project
stored_at: "2024-01-16T10:00:00Z"
expires_at: null
timestamp: "2024-01-16T10:00:00Z"
persisted:
  content_type: decision
  content_id: "decision_db_20240116"
  destination: "CLAUDE.md"
  section: "Architecture Decisions"
write_operation:
  strategy: append
  bytes_written: 256
  lines_added: 8
  lines_modified: 0
verification:
  write_confirmed: true
  content_present: true
  structure_valid: true
metadata:
  source: "conversation:conv_abc123"
  related_entries: []
  expiry: null
duplicates_found: []
confidence: 1.0
evidence_anchors:
  - {ref: "memory:CLAUDE.md#Architecture Decisions", kind: record}
  - {ref: "file:CLAUDE.md:45-52", kind: file}
  - {ref: "verification:re-read:success", kind: tool}
assumptions:
  - "CLAUDE.md is the correct location for architecture decisions"
  - "No conflicting database decisions exist"
```

**What was written to CLAUDE.md:**
```markdown
### Architecture Decisions

#### Database: PostgreSQL [2024-01-16]

**Decision:** Use PostgreSQL for all persistent storage

**Rationale:** Strong ACID guarantees, mature ecosystem, team familiarity

**Context:** Evaluated PostgreSQL, MySQL, and MongoDB for new backend service

**Constraints:**
- Must support complex queries
- Team has PostgreSQL experience
```

---

### Example 2: Detecting Duplicate

**Input:**
```yaml
data:
  content_type: pattern
  pattern: "Wrap external API errors with domain-specific error types"
  rationale: "Prevents leaking implementation details"
key: "CLAUDE.md#Patterns"
```

**Output:**
```yaml
stored: true  # Already present as pattern_err_001; nothing new written
key: "CLAUDE.md#Patterns"
timestamp: "2024-01-16T11:00:00Z"
persisted:
  content_type: pattern
  content_id: null
  destination: "CLAUDE.md"
  section: "Patterns"
write_operation:
  strategy: append
  bytes_written: 0
  lines_added: 0
  lines_modified: 0
verification:
  write_confirmed: false
  content_present: true
  structure_valid: true
metadata:
  source: "conversation:conv_def456"
  related_entries: ["pattern_err_001"]
  expiry: null
duplicates_found:
  - existing_id: "pattern_err_001"
    similarity: 0.95
    action_taken: skipped
confidence: 0.9
evidence_anchors:
  - {ref: "file:CLAUDE.md:134", kind: file}
assumptions:
  - "High similarity indicates same pattern"
  - "Skipping to avoid duplicate"
next_actions:
  - "Consider updating existing pattern if new rationale is better"
```

---

### Example 3: Merging with Existing Content

**Input:**
```yaml
data:
  content_type: fact
  fact: "API rate limit is 1000 requests per minute"
  source: "API documentation v2.3"
key: "docs/api-notes.md#Rate Limits"
```

Merge with the existing entry rather than appending a duplicate.

**Output:**
```yaml
stored: true
key: "docs/api-notes.md#Rate Limits"
timestamp: "2024-01-16T12:00:00Z"
persisted:
  content_type: fact
  content_id: "fact_rate_limit_20240116"
  destination: "docs/api-notes.md"
  section: "Rate Limits"
write_operation:
  strategy: merge
  bytes_written: 64
  lines_added: 1
  lines_modified: 1
verification:
  write_confirmed: true
  content_present: true
  structure_valid: true
metadata:
  source: "API documentation v2.3"
  related_entries: ["fact_rate_limit_20231201"]
  expiry: "2024-07-16"
duplicates_found:
  - existing_id: "fact_rate_limit_20231201"
    similarity: 0.8
    action_taken: merged
confidence: 1.0
evidence_anchors:
  - {ref: "memory:docs/api-notes.md#Rate Limits", kind: record}
  - {ref: "file:docs/api-notes.md:23", kind: file}
  - {ref: "source:API documentation v2.3", kind: x-doc}
assumptions:
  - "New rate limit supersedes previous"
  - "6-month expiry for review"
```

## Verification

- [ ] Content validated for appropriateness (no secrets/PII)
- [ ] Destination file exists or can be created
- [ ] Write operation completed without error
- [ ] Content present in destination after write
- [ ] File structure/formatting preserved

**Verification tools:** Read (to verify write), Edit (to perform write)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: false
- `requires_approval`: false
- `risk`: low

**Capability-specific rules:**
- NEVER persist credentials, API keys, or secrets. Code enforces it: the skill's PreToolUse command hook blocks an `Edit`, `Write`, `MultiEdit` or `NotebookEdit` whose content holds what looks like a credential (`F504 CONSTRAINT_VIOLATED:`, STANDARD v1.2 §6.7, §5.18.10): the text it carries, and the lines the file will hold after it that it does not hold now (so a key already in the file, or a token two edits build, counts), each also with its `\uXXXX`, `\xXX`, `\/` and `\"` escapes decoded. It matches credential shapes (key and token formats, PEM and OpenPGP private keys, bearer tokens, a URL's userinfo password that is not a placeholder, an `Authorization` header's value mixing letters and digits, with no scheme or after any scheme (`ApiKey`, `SSWS`, ...), also given as a name/value pair or a two-element tuple, as a HAR or code writes headers, and a command's user option's password, `curl -u user:<password>`) and assignments to a credential name (`password`, `passphrase`, `token`, `secret_key`, `api_key`, ...), or values given to an option named for one (`--password <value>`), whose value is quoted with no whitespace and 8 or more characters, or unquoted, 12 or more characters, mixing letters and digits, quotes escaped or not; prose such as `token: rotate monthly` passes. The scan is `hooks/secret_scan.sh`, copied into the hook
- NEVER persist PII without explicit user consent
- Validate content does not contain executable code
- Preserve existing file structure and formatting
- Create backup before replacing existing content
- Stop if destination is a system or configuration file

## Composition Patterns

**Commonly follows:**
- `compare` - Persist the option a comparison selected for future reference
- `discover` - Save discovered patterns or relationships
- `recall` - Update existing memories with new context
- `generate` - Save a generated summary as durable knowledge

**Commonly precedes:**
- `recall` - Persisted content becomes available for recall
- `verify` - Verify persisted content is correct
- `audit` - Record what was persisted for compliance

**Anti-patterns:**
- Never persist without checking for duplicates
- Never persist contradictory information without flagging
- Never persist to files outside project scope without approval
- Avoid persisting ephemeral/temporary information

**Workflow references:**
- Pairs with `recall` for the remember/recall cycle
- Final step in many learning workflows
