---
name: send
description: Emit a message or event to an external system with policy enforcement and approval gates. Use when publishing messages, calling APIs, sending notifications, or triggering external workflows. REQUIRES EXPLICIT APPROVAL.
argument-hint: "[destination] [payload] [protocol]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Read, Grep, Bash
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

            OUTBOUND COMMUNICATION SAFETY CHECK

            The tool call follows this prompt as JSON; the command is tool_input.command.

            This skill sends data to external systems. Verify:
            1. The destination is one the destination policy allows (checked by
               code where a policy is in force, STANDARD 1.2.0 §4.4.2); judge it
               here only when none is.
            2. No sensitive data (API keys, passwords, PII) in payload

            CRITICAL: External sends are IRREVERSIBLE.

            Return ok: true only if ALL conditions are verified.
            Return ok: false, with the specific violation as the reason, if any check fails.
          once: false
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # Block a request to localhost or a loopback, private, link-local or
            # unspecified address written as its host (a host-specific destination
            # rule, STANDARD 1.2.0 §5.18.10, F504), and a request whose destination
            # this check cannot read: one whose text the shell expands or escapes, or
            # whose connection an option, a setting or a file redirects. It reads every
            # command that names curl, wget or http, or a file that sets where requests
            # go, in any quoting (quotes, backslashes and line continuations removed),
            # or that holds $'...' or $"..." (which can spell any name) or a /dev/ path
            # the shell expands: its words as the shell passes them, the requests of
            # curl, wget and HTTPie (http) as those tools read them (options
            # abbreviated or in a cluster; a host with or without a scheme,
            # http:/host, host:/path, in any numeric form, every word after -- a URL;
            # curl only with -q first and wget only with --no-config read as an
            # option, so no configuration file is read, HTTPie only where its
            # configuration file sets no default options, and no ipfs:// URL, which
            # goes to a gateway) wherever the tool runs: as the program of its
            # command, after !, if, while and the other reserved words, or after a
            # program that runs the one a later word names (env, sudo, timeout, ...)
            # with only options, numbers and such programs' and tools' names between
            # (an option's value may name a tool, env -C http curl, so each word
            # naming a tool there is read as the request's program, at most 8);
            # given to any other program
            # (prlimit, a loader, head, an unknown one) it is refused, since that
            # program may run it unread or copy it. Also git's settings, the
            # variables that set where a request goes (assigned, exported, read or
            # looped over, BASH_ALIASES and BASH_CMDS among them), alias, hash and
            # enable, which give a program another name, a copy or a link of the tool
            # (whatever comes before the copier), xargs feeding it, code a shell or
            # an interpreter runs from a word, a pipe or a file, and any URL a
            # program is given, curl's --url value (and no URL read from a file,
            # --url @file or an operand @file), a setting file in any spelling
            # (/etc//hosts, a .. segment) or by its last component where the line
            # may change the directory (cd, --output-dir, -P) or runs in /etc.
            # In every command, a word the shell may expand (a
            # glob, in any letter case, a brace, an extglob pattern) to the name of
            # curl, wget or http, or to a file that sets where a request goes (a
            # leading dot matched by a glob too where the command may turn on
            # dotglob), is refused. A request another program makes with no such name in its text
            # (a program named by a variable, a copy made earlier under another name,
            # an interpreter's code), a name that resolves to an internal address, and
            # a redirect a server answers with, are not read here; the plugin's
            # pre-tool-use hook gates every such call. Skill hooks stay registered for
            # the rest of the session, so a command with no such name is left alone.
            # Claude Code passes the tool call as JSON on stdin; exit 2 blocks the call
            # and the reason on stderr is shown to Claude. A call that cannot be read
            # is blocked (R407).
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # The command with its quotes, backslashes and line breaks removed: c''url,
            # c\url, "cu"rl and cu\<newline>rl name curl; $'\x63url' spells it (also
            # after a line continuation, $\<newline>'...'), and /dev/${t}cp is /dev/tcp
            JOINED="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // "" | split("\\\n") | add // ""' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            NAMED=false
            printf '%s\n' "$CMD" | tr -d "\"'\\\\\n" | grep -qiE "(curl|wget|http|ipfs|dev/tcp|dev/udp|etc/hosts|resolv\.conf|(^|[^A-Za-z0-9_.-])hosts($|[^A-Za-z0-9_.-]))" && NAMED=true
            case "$CMD$JOINED" in *"\$'"* | *'$"'*) NAMED=true ;; esac
            printf '%s\n' "$CMD" | grep -qE '/dev/[^[:space:];&|<>/]*[$`\\]|[$`][^[:space:];&|<>]*/(tcp|udp)/' && NAMED=true
            if [ "$NAMED" = false ]; then
              # Read below: a word the shell may expand to the name of curl, wget or http
              # (an extglob pattern too: @(, !(, +(; *( and ?( hold * and ?)
              case "$CMD" in
                *'*'* | *'?'* | *'['* | *'{'* | *'@('* | *'!('* | *'+('*) ;;
                *) exit 0 ;;
              esac
            fi
            INTERNAL="F504 CONSTRAINT_VIOLATED: the send skill does not send to localhost or a loopback, private, link-local or unspecified address written as the host (internal network access)"
            # IPv4 in dotted-decimal form: 0/8, 127/8 (loopback), 10/8, 172.16/12,
            # 192.168/16 and 169.254/16 (link-local, cloud metadata); also as the
            # first labels of a name (127.0.0.1.nip.io resolves to 127.0.0.1).
            ADDR4='(0(\.[0-9]+){3}|127(\.[0-9]+){3}|10(\.[0-9]+){3}|192\.168(\.[0-9]+){2}|172\.(1[6-9]|2[0-9]|3[01])(\.[0-9]+){2}|169\.254(\.[0-9]+){2})(\.[a-z0-9-]+)*'
            # IPv6 literals: ::1, ::, ::ffff:<IPv4> (mapped), fc00::/7 (unique
            # local), fe80::/10 (link-local).
            ADDR6='\[(::|0*:|f[cd][0-9a-f]*:|fe[89ab][0-9a-f]*:)[^]]*\]'
            # IPv4 in another form a resolver accepts, as a URL's host: one to three
            # parts (127.1, 2130706433), or a part in hex (0x7f) or octal (0177).
            NUMERIC='((0x[0-9a-f]*|[0-9]+)\.){0,2}(0x[0-9a-f]*|[0-9]+)|([0-9a-fx.]*\.)?(0x[0-9a-f]*|0[0-9]+)(\.[0-9a-fx]*)*'
            # The address must stand where a host does: after a URL scheme, a user@,
            # a space or a quote, and before a port, a path, a query or the end; a
            # host may end in the root's dot (localhost., 127.0.0.1.). Host names
            # are case-insensitive, so the match is too.
            AFTER="\.?([:/?#[:space:]\"']|\$)"
            if [ "$NAMED" = false ]; then :
            elif printf '%s\n' "$CMD" | grep -qiE "(^|[[:space:]\"']|://|@)(localhost|${ADDR4}|${ADDR6})${AFTER}" \
              || printf '%s\n' "$CMD" | grep -qiE "(://|@)(${NUMERIC})${AFTER}"; then
              echo "$INTERNAL" >&2
              exit 2
            fi
            # Options and settings that send the request elsewhere than its URL's
            # host: curl's --resolve, --connect-to, a Unix socket, a proxy (-x in any
            # short option cluster), a DNS server, options read from a file (-K);
            # wget's -e/--execute (wgetrc commands, a proxy among them) and URLs read
            # from a file (-i); a *_proxy variable set on the line.
            if [ "$NAMED" = false ]; then :
            elif printf '%s\n' "$CMD" | grep -qiE -- "(^|[[:space:]\"'])(--resolve|--connect-to|--unix-socket|--abstract-unix-socket|--proxy[a-z0-9-]*|--preproxy|--socks[a-z0-9-]*|--doh-url|--dns-servers|--config|--execute|--input-file)([=[:space:]\"']|\$)" \
              || { printf '%s\n' "$CMD" | grep -qi curl && printf '%s\n' "$CMD" | grep -qE -- "(^|[[:space:]\"'])-[A-Za-z0-9]*[xK]"; } \
              || { printf '%s\n' "$CMD" | grep -qi wget && printf '%s\n' "$CMD" | grep -qE -- "(^|[[:space:]\"'])-[A-Za-z0-9]*[ei]"; } \
              || printf '%s\n' "$CMD" | grep -qiE -- "(^|[[:space:]\"';&|])[a-z_]*proxy="; then
              echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose connection an option or a proxy setting redirects (--resolve, --connect-to, a socket, a proxy, a DNS server, options or URLs read from a file): the address it reaches is not the one this check reads" >&2
              exit 2
            fi
            # Text the shell expands or escapes can be any host or option
            [ "$NAMED" = false ] || case "$CMD" in
              *'$'* | *'`'* | *'\'* | *'<('* | *'>('*)
                echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose text the shell expands or escapes (\$, a backtick, \\, <( or >()): the host it reaches is not the one this check reads. Write the command on one line with literal values; curl reads a credential header from a file with -H @file" >&2
                exit 2
                ;;
            esac
            # HTTPie reads default options (a proxy among them) from its configuration
            # file, and has no option to skip it: a request is run only where the
            # file it reads holds none (curl and wget are run with -q and --no-config)
            HTTPIE_DEFAULTS=false
            for F in "${HTTPIE_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/httpie}/config.json" "$HOME/.httpie/config.json"; do
              if [ -e "$F" ] || [ -L "$F" ]; then
                jq -e 'type == "object" and ((.default_options // []) == [])' "$F" >/dev/null 2>&1 || HTTPIE_DEFAULTS=true
              fi
            done
            # The words, as the shell passes them, of each simple command, and the
            # host each request names (jq reads a command of up to 16384 bytes in well
            # under a second)
            READER="$(cat <<'JQ'
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

            # 0/8, 127/8, 10/8, 172.16/12, 192.168/16, 169.254/16 and 100.64/10 (shared
            # address space, where a cloud's metadata service may be: 100.100.100.200).
            def internal4($v): ($v < 16777216) or ($v >= 2130706432 and $v < 2147483648)
              or ($v >= 167772160 and $v < 184549376) or ($v >= 2886729728 and $v < 2887778304)
              or ($v >= 3232235520 and $v < 3232301056) or ($v >= 2851995648 and $v < 2852061184)
              or ($v >= 1681915904 and $v < 1686110208);
            def part_value: if test("^0x[0-9a-f]*$") then (.[2:] | explode | reduce .[] as $c (0; . * 16 + (if $c >= 97 then $c - 87 else $c - 48 end)))
              elif test("^0[0-7]*$") then (explode | reduce .[] as $c (0; . * 8 + $c - 48))
              elif test("^[1-9][0-9]*$") then (if length > 10 then 1e12 else tonumber end)
              else null end;
            # A host written as numbers, the way inet_aton reads it: the address, or
            # null when it is a name, or "bad" when its numbers hold no address.
            def ipv4: (split(".") | map(part_value)) as $p
              | if ($p | length) > 4 or ($p | any(. == null)) then null
                else ($p | length) as $n
                | if ($p[:-1] | any(. > 255)) or $p[-1] >= pow(256; 5 - $n) then "bad"
                  else reduce range(0; $n - 1) as $i ($p[-1]; . + $p[$i] * pow(256; 3 - $i)) end end;
            # "internal", "unreadable" or null for one authority ([user@]host[:port]);
            # $m is the whole word, for its scheme.
            def host_verdict($m):
              . as $auth | ($auth | sub("^.*@"; "")) as $hp
              | if $auth | test("[^A-Za-z0-9._~:@!$&()*+,;=\\[\\]-]") then "unreadable"
                elif $hp | test("^\\[[0-9A-Fa-f:.]+\\](:[0-9]*)?$") then
                  (if $hp | ascii_downcase | test("^\\[(::|0*:|f[cd][0-9a-f]*:|fe[89ab][0-9a-f]*:)") then "internal" else null end)
                elif $hp | test("^[A-Za-z0-9._-]*(:[0-9]*)?$") | not then "unreadable"
                else ($hp | sub(":[0-9]*$"; "") | ascii_downcase | sub("\\.$"; "")) as $h
                | if $h == "" then (if $m | test("^file:"; "i") then null else "unreadable" end)
                  elif $h == "localhost" or ($h | endswith(".localhost")) or $h == "localhost.localdomain" or $h == "ip6-localhost" or $h == "ip6-loopback" then "internal"
                  elif ($h | test("^[0-9][0-9a-fx.]*$")) and (($h | ipv4) != null) then
                    ($h | ipv4) as $v | if $v == "bad" then "unreadable" elif internal4($v) then "internal" else null end
                  elif $h | test("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+\\.") then
                    ($h | capture("^(?<a>[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+)\\.").a | ipv4) as $v
                    | if ($v | type) == "number" and internal4($v) then "internal" else null end
                  else null end
                end;
            # "internal", "unreadable", "expands" or null for a word a request may take
            # as its URL, read as curl, wget and HTTPie read one:
            # [scheme://][user@]host[:port][/path][?query][#fragment]. A scheme followed
            # by one slash is read both ways: curl takes http:/host as http://host, and
            # wget takes host:/path as an FTP host.
            def destination($m; $tool):
              if $m | test("\u0001") and (test("^[A-Za-z][A-Za-z0-9+.-]*://[^/\u0001]*/") | not) then "expands"
              elif $tool == "http" and ($m | startswith(":")) then "internal"
              else
                (if $m | test("^[A-Za-z][A-Za-z0-9+.-]*://") then [$m | sub("^[A-Za-z][A-Za-z0-9+.-]*:/+"; "")]
                 elif $m | test("^[A-Za-z][A-Za-z0-9+.-]*:/") then [($m | sub("^[A-Za-z][A-Za-z0-9+.-]*:/+"; "")), $m]
                 else [$m] end) as $readings
                | first($readings[] | sub("[/?#].*$"; "") | host_verdict($m) | select(. != null)) // null
              end;

            def tables: {
              curl: {danger_long: ["--resolve", "--connect-to", "--unix-socket", "--abstract-unix-socket", "--proxy", "--preproxy", "--socks", "--doh-url", "--dns-servers", "--config", "--variable", "--expand-", "--alt-svc", "--ipfs-gateway"],
                     danger_short: "[xK]",
                     arg_short: "ECbcdDFPHhmoUQreXYytzTuAwxK",
                     arg_long: ["--aws-sigv4", "--cacert", "--capath", "--cert", "--cert-type", "--ciphers", "--connect-timeout", "--continue-at", "--cookie", "--cookie-jar", "--create-file-mode", "--crlfile", "--curves", "--data", "--data-ascii", "--data-binary", "--data-raw", "--data-urlencode", "--delegation", "--dns-interface", "--dns-ipv4-addr", "--dns-ipv6-addr", "--dump-header", "--egd-file", "--engine", "--etag-compare", "--etag-save", "--expect100-timeout", "--form", "--form-string", "--ftp-account", "--ftp-alternative-to-user", "--ftp-method", "--ftp-port", "--ftp-ssl-ccc-mode", "--happy-eyeballs-timeout-ms", "--header", "--help", "--hostpubmd5", "--hostpubsha256", "--hsts", "--interface", "--json", "--keepalive-time", "--key", "--key-type", "--krb", "--libcurl", "--limit-rate", "--local-port", "--login-options", "--mail-auth", "--mail-from", "--mail-rcpt", "--max-filesize", "--max-redirs", "--max-time", "--netrc-file", "--noproxy", "--oauth2-bearer", "--output", "--output-dir", "--parallel-max", "--pass", "--pinnedpubkey", "--proto", "--proto-default", "--proto-redir", "--pubkey", "--quote", "--random-file", "--range", "--rate", "--referer", "--request", "--request-target", "--retry", "--retry-delay", "--retry-max-time", "--sasl-authzid", "--service-name", "--speed-limit", "--speed-time", "--stderr", "--telnet-option", "--tftp-blksize", "--time-cond", "--tls-max", "--tls13-ciphers", "--tlsauthtype", "--tlspassword", "--tlsuser", "--trace", "--trace-ascii", "--trace-config", "--upload-file", "--url-query", "--user", "--user-agent", "--write-out"]},
              wget: {danger_long: ["--execute", "--input-file", "--input-metalink", "--config", "--use-askpass", "--proxy", "--dns-servers", "--bind-dns-address"],
                     danger_short: "[ei]",
                     arg_short: "oaBtOTwQPUlARDIXnei",
                     arg_long: ["--output-file", "--append-output", "--base", "--tries", "--retry-on-http-error", "--output-document", "--start-pos", "--progress", "--timeout", "--dns-timeout", "--connect-timeout", "--read-timeout", "--wait", "--waitretry", "--quota", "--bind-address", "--limit-rate", "--restrict-file-names", "--prefer-family", "--user", "--password", "--local-encoding", "--remote-encoding", "--directory-prefix", "--cut-dirs", "--http-user", "--http-password", "--default-page", "--header", "--compression", "--referer", "--user-agent", "--load-cookies", "--save-cookies", "--post-data", "--post-file", "--method", "--body-data", "--body-file", "--secure-protocol", "--certificate", "--certificate-type", "--private-key", "--private-key-type", "--ca-certificate", "--ca-directory", "--crl-file", "--pinnedpubkey", "--random-file", "--ciphers", "--ftp-user", "--ftp-password", "--warc-file", "--warc-header", "--warc-max-size", "--warc-dedup", "--warc-tempdir", "--level", "--backups", "--accept", "--reject", "--accept-regex", "--reject-regex", "--regex-type", "--domains", "--exclude-domains", "--follow-tags", "--ignore-tags", "--include-directories", "--exclude-directories", "--report-speed", "--rejected-log"]},
              http: {danger_long: ["--proxy"],
                     danger_short: "^$",
                     arg_short: "aAopPs",
                     arg_long: ["--auth", "--auth-type", "--output", "--print", "--history-print", "--style", "--session", "--session-read-only", "--timeout", "--max-redirects", "--max-headers", "--verify", "--cert", "--cert-key", "--cert-key-pass", "--ssl", "--ciphers", "--pretty", "--format-options", "--response-charset", "--response-mime", "--boundary", "--default-scheme", "--raw"]}};

            # Files that set where a request goes (curl's and wget's configuration, the
            # resolver's, curl's IPFS gateway, HTTPie's), and bash's /dev/tcp and
            # /dev/udp, which open a connection.
            def setting_files: "curlrc|wgetrc|/etc/hosts|resolv\\.conf|\\.ipfs(/|$)|httpie/config|/dev/(tcp|udp)/";
            # The same files as the paths a word the shell expands (a glob, a brace)
            # may name, by their last components: a pattern must match each, a
            # leading dot only by a dot.
            def setting_paths: [[".curlrc"], [".config", "curlrc"], [".wgetrc"], ["etc", "wgetrc"], ["etc", "hosts"], ["etc", "resolv.conf"], ["resolve", "resolv.conf"], [".ipfs", "gateway"], ["httpie", "config.json"], [".httpie", "config.json"]];
            # A word read as a path: repeated slashes and . segments taken out
            # (/etc//hosts and /etc/./hosts are /etc/hosts), its last component, and
            # whether it climbs (a .. segment, which a link may send anywhere).
            def tidy: startswith("/") as $abs | split("/") | map(select(. != "" and . != ".")) | join("/") | if $abs then "/" + . else . end;
            def last_name: sub("[?#].*$"; "") | tidy | split("/") | .[-1] // "" | ascii_downcase;
            def climbs: split("/") | any(. == "..");
            # The last components of the files that set where a request goes.
            def setting_names: ["hosts", "resolv.conf", "gateway", "config.json", "curlrc", ".curlrc", "wgetrc", ".wgetrc"];
            # A word that names such a file: as written, tidied, or by its last
            # component past a .. segment.
            def setting_word: (.d | test(setting_files; "i")) or (.d | tidy | test(setting_files; "i"))
              or ((.d | climbs) and (.d | last_name | IN(setting_names[])));
            # A word that may change the directory a later name, or a name a tool takes
            # from a URL, is read in: cd, pushd and popd, curl's --output-dir, wget's
            # -P and --directory-prefix, a wrapper's --chdir, -C or -D.
            def moves_dir: IN("cd", "pushd", "popd") or test("^--(output-dir|directory-prefix|chdir)") or test("^-[A-Za-z]*[PCD]");
            # Variables that send a request elsewhere or change the program that runs:
            # curl's and wget's configuration directories and files, a CA bundle, the
            # resolver's, a proxy, git's (GIT_CONFIG_*, GIT_SSH_COMMAND, ...) and the
            # loader's, and bash's tables of aliases and of the programs names run
            # (BASH_ALIASES[g]=curl, BASH_CMDS[x]=/usr/bin/curl). A variable is set
            # without a = as well (for NAME in, read NAME, printf -v NAME, getopts,
            # declare -n ref=NAME, then export NAME or set -a), so the name itself is
            # refused, as a word or a word's part; HOME, PATH, ENV, IFS and
            # XDG_CONFIG_HOME, as a word of their own, NAME=..., -vNAME or a
            # nameref's =NAME.
            def setting_vars: "(^-[A-Za-z]*|[^A-Za-z0-9_]|^)(CURL_HOME|WGETRC|SSL_CERT_FILE|SSL_CERT_DIR|CURL_CA_BUNDLE|REQUESTS_CA_BUNDLE|HOSTALIASES|RES_OPTIONS|LOCALDOMAIN|IPFS_GATEWAY|IPFS_PATH|SYSTEM_WGETRC|HTTPIE_CONFIG_DIR|BASH_ENV|BASH_ALIASES|BASH_CMDS|GIT_[A-Za-z0-9_]*|LD_[A-Za-z0-9_]*|DYLD_[A-Za-z0-9_]*|[A-Za-z_]*_[Pp][Rr][Oo][Xx][Yy])([^A-Za-z0-9_]|$)";
            def plain_vars: "^(-[A-Za-z]*)?(HOME|XDG_CONFIG_HOME|PATH|ENV|IFS)(\\+?=.*)?$|=(HOME|XDG_CONFIG_HOME|PATH|ENV|IFS)$";
            # (A long option's value is the tool's: check_request reads it.)
            def sensitive_var: (startswith("--") | not) and (test(setting_vars) or test(plain_vars));
            # git's settings this check lets a command give (git -c NAME=VALUE, git
            # config NAME): any other may send its requests elsewhere or run a command
            # (http.*, url.*, alias.*, core.pager, core.fsmonitor, credential.*, ...).
            def git_settings: "^(user\\.|color\\.|advice\\.|init\\.defaultbranch|core\\.quotepath|i18n\\.|column\\.|log\\.)";
            # Programs that run a command line or code given to them as a word, read
            # from a pipe or a file, or run the program a later word names (sh -c '...',
            # trap '...' EXIT, awk 'BEGIN{system(...)}', sed '1e ...', find -exec).
            def shells: "^(sh|bash|zsh|dash|ksh|mksh|fish|busybox|toybox|eval|exec|source|\\.|trap|alias|ssh|su|sudo|doas|runuser|xargs|parallel|env|nohup|timeout|nice|command|builtin|time|watch|script|setsid|stdbuf|ionice|taskset|chrt|flock|chroot|nsenter|unshare|firejail|strace|ltrace|systemd-run|tmux|screen|docker|podman|kubectl|at|batch|expect|tclsh|wish|gdb|vi|vim|nvim|ex|ed|emacs|less|more|sqlite3|psql|mysql|make|gmake|awk|gawk|mawk|nawk|sed|gsed|find|python[0-9.]*|node|nodejs|deno|bun|perl|ruby|php|lua|osascript|pwsh|powershell)$";
            # git's options that run a command line given as a word.
            def git_runs: "^(-x|--exec|--extcmd|foreach|--exec=.*|--extcmd=.*)$";
            # A word holding a command line that runs a request tool, by its name or
            # its path, or that names it as a value (sh -c '/usr/bin/curl ...;',
            # eval 'alias g=curl').
            def embedded: test("\\s") and test("(^|[\\s;&|(\"'`!=/])(curl|wget|https?)([\\s;&|)\"'`]|$)"; "i");
            # Programs that copy or link a file (cp /usr/bin/curl fetch), and programs
            # that read a request's words from their input (xargs curl).
            def copiers: ["cp", "ln", "install", "mv", "rsync", "dd", "tee", "cat", "scp", "link", "ditto", "gcp", "gln", "ginstall", "busybox", "toybox"];
            def feeders: ["xargs", "parallel"];
            def tools: ["curl", "wget", "http", "https"];
            def name_of: sub("^.*/"; "");
            # The words before a command's program that bash reads as its own (! curl,
            # if curl ...; then, while, until, coproc, a group's {).
            def reserved: ["!", "if", "then", "elif", "else", "do", "while", "until", "coproc", "{", "}", "fi", "done", "esac"];
            # Programs that run the program a later word names, after options and
            # numbers (timeout 5 curl, nice -n 10 curl, env -i curl, sudo curl).
            def wrappers: ["env", "nohup", "timeout", "nice", "command", "builtin", "exec", "eval", "time", "sudo", "doas", "runuser", "setsid", "stdbuf", "ionice", "taskset", "chrt", "nsenter", "unshare", "firejail", "strace", "ltrace", "systemd-run", "watch", "busybox", "toybox"];
            def option_or_number: test("^-") or test("^([0-9]+(\\.[0-9]+)?[smhdkKMG]?|0[xX][0-9a-fA-F]+)$");
            # Programs that neither run nor copy a word they are given (which curl
            # wget, echo curl), and package managers, which given a tool's bare name
            # install its package (apt-get install -y curl).
            def non_runners: ["which", "whereis", "type", "echo", "printf"];
            def installers: ["apt-get", "apt", "dnf", "yum", "apk", "brew", "pacman", "zypper"];
            # Builtins that give a program another name (alias get=curl, hash -p
            # /usr/bin/curl x, enable -f lib.so x) or define a function.
            def renamers: ["alias", "hash", "enable", "function"];

            # Brace expansion, as bash makes it of a word: a group opens at the first
            # { that a } closes, and runs to the first } after a , or .. at its own
            # level (bash closes no group at a } before its first comma: {a},b} gives
            # a} and b); a group that is a list gives its parts (split at its own
            # commas), each expanded again, a sequence x..y its elements, and the text
            # after the group is expanded again. Bash 5.2 and 5.3 differ on the rest
            # ($v): 5.2 reads a group as a list when a comma is anywhere in it, nested
            # included ({a..b{c,d}} gives a..bc and a..bd), and keeps a group that is
            # neither as written; 5.3 reads it as a list only when a comma is at its
            # own level, and of a group that is neither keeps the { as written and
            # expands what follows it ({a..bc} and {a..bd}). brace_words gives the
            # words of both readings (the hook runs under whichever bash the user has),
            # each once where they differ. A sequence of numbers gives digits
            # (\u0006). null for more than 256 words (both readings' together), groups
            # 32 deep, more than 512 braces and commas in a word, or more than 8 {
            # tried for one group, in either reading.
            def brace_marks: [match("[{},]|\\.\\.(?!\\})"; "g") | {o: .offset, t: .string}];
            def brace_close($m; $k): first(foreach range($k + 1; $m | length) as $j ({l: 0, c: 0, at: null};
                $m[$j].t as $t
                | if $t == "}" and .l == 0 and .c > 0 then .at = $j
                  elif $t == "{" then .l += 1 | .at = null
                  elif $t == "}" then (if .l > 0 then .l -= 1 else . end) | .at = null
                  elif .l == 0 then .c += 1 | .at = null
                  else .at = null end;
                select(.at != null) | .at)) // null;
            def brace_parts: . as $a
              | (reduce ([match("[{},]"; "g") | {o: .offset, t: .string}][]) as $x ({l: 0, cuts: []};
                  if $x.t == "{" then .l += 1
                  elif $x.t == "}" then (if .l > 0 then .l -= 1 else . end)
                  elif .l == 0 then .cuts += [$x.o]
                  else . end) | [-1] + .cuts + [$a | length]) as $b
              | [range(0; ($b | length) - 1) as $i | $a[$b[$i] + 1:$b[$i + 1]]];
            def brace_expand($depth; $v): . as $w | brace_marks as $m
              | [range(0; $m | length) | select($m[.].t == "{" and (($m[.].o == 0 and $w[1:2] == "}") | not))] as $opens
              | if ($m | length) > 512 or $depth > 32 then null
                else (first($opens[:8][] as $k | brace_close($m; $k) as $c | select($c != null) | [$m[$k].o, $m[$c].o]) // null) as $g
                | if $g == null then (if ($opens | length) > 8 then null else [$w] end)
                  else $w[:$g[0]] as $pre | $w[$g[0] + 1:$g[1]] as $body | $w[$g[1] + 1:] as $post
                  | ($body | brace_parts) as $parts
                  | (if ($body | test(",")) and ($v == 52 or ($parts | length) > 1) then
                       [$parts[] | brace_expand($depth + 1; $v)] | if any(.[]; . == null) then null else add end
                     elif $body | test("^-?[0-9]+\\.\\.-?[0-9]+(\\.\\.-?[0-9]+)?$") then ["\u0006"]
                     elif $body | test("^[A-Za-z]\\.\\.[A-Za-z](\\.\\.-?[0-9]+)?$") then
                       [($body | explode) as $c | range([$c[0], $c[3]] | min; ([$c[0], $c[3]] | max) + 1) | [.] | implode]
                     elif $v == 52 then ["{" + $body + "}"]
                     else false end) as $mid
                  | if $mid == false then
                      ($w[$g[0] + 1:] | brace_expand($depth + 1; $v)) as $rest
                      | if $rest == null then null else [$rest[] | $pre + "{" + .] end
                    else ($post | brace_expand($depth + 1; $v)) as $tail
                    | if $mid == null or $tail == null or ($mid | length) * ($tail | length) > 256 then null
                      else [$mid[] as $a | $tail[] as $b | $pre + $a + $b] end
                    end
                  end
                end;
            def brace_words: brace_expand(0; 52) as $a | brace_expand(0; 53) as $b
              | if $a == null or $b == null then null elif $a == $b then $a
                else $a + $b | unique | if length > 256 then null else . end end;
            # A glob as the shell matches it (in any letter case: shopt -s nocaseglob),
            # its quotes removed before: each bracket expression read as bash reads
            # one (glob_marks; [[:alpha:]], [[=l=]], []l] and [l"]"] included).
            def glob_of: ascii_downcase | glob_text(true) | glob_marks(true);
            # A run of the command's text (split at blanks and operators, quotes and
            # backslashes removed) that the shell may expand to the name of curl, wget or
            # http: c?rl, /usr/bin/c[u]rl, cu{r,r}l, wg?t, in any letter case (shopt -s
            # nocaseglob: /usr/bin/CU?L). A pattern with no letter or digit of its own
            # (*) names none, and one that matches more than 5 characters (a bracket
            # expression is one, a * none) names none.
            # (the words a run gives, quotes and backslashes removed, braces
            # expanded: null for more than brace_words gives)
            def run_words: explode | map(select(. != 34 and . != 39 and . != 92)) | implode | brace_words;
            def may_expand_to_tool($ws):
              $ws == null
                or any($ws[]; sub("^.*/"; "") | select(ascii_downcase | test("[a-z0-9]")) | glob_of
                       | select(glob_min <= 5) | marks_regex as $re | any(tools[]; test($re)));
            # A run of the command's text the shell may expand to a file that sets where
            # a request goes: tee ~/.cu{r,r}lrc, /etc/ho?ts. Its last component must
            # hold a letter or a digit (ls /etc/* names none). A glob matches a leading
            # dot only by a dot, unless the command may turn on dotglob ($dots: shopt,
            # GLOBIGNORE, BASHOPTS, or a file sourced or text evaluated, which may
            # run either).
            # (A name is matched by a component's glob_of: no regex is built from a
            # glob that matches more characters than the name has.)
            def name_matches($g): ((($dots | not) and startswith(".") and ($g | test("^[\u0001\u0002]"))) | not)
              and ($g | glob_min) <= length and test($g | marks_regex);
            def may_expand_to_setting_file($ws):
              $ws == null
                or any($ws[]; (split("/") | map(select(. != "" and . != "."))) as $parts
                       | ($parts | length) > 0 and ($parts[-1] | test("[A-Za-z0-9]"))
                         and (($parts | map(glob_of)) as $globs
                              | any(setting_paths[]; . as $f | ($f | length) as $n
                                    | ($globs | length) >= $n
                                      and all(range(0; $n); . as $i | $f[$n - 1 - $i] | name_matches($globs[($globs | length) - 1 - $i])))));
            # The simple commands with whether each reads its input from a pipe or a
            # redirection (echo '...' | sh, sh < file, sh <<< '...').
            # (Its words leave out a redirection's target.)
            def fed_commands: tokens as $t | ($t | length) as $n
              | ([-1] + [range(0; $n) | select($t[.].op and ($t[.].op | test("[<>]") | not))] + [$n]) as $b
              | [range(0; ($b | length) - 1) as $k
                 | {fed: (($b[$k] >= 0 and ($t[$b[$k]].op == "|" or ($t[$b[$k]].op == "&" and $b[$k] > 0 and ($t[$b[$k] - 1].op // "") == "|")))
                          or any($t[($b[$k] + 1):$b[$k + 1]][]; .op and (.op | test("^[0-9]*(<|<<<|<>)$")))),
                    words: [range($b[$k] + 1; $b[$k + 1]) as $i | $t[$i]
                            | select(.word and (($i > 0 and ($t[$i - 1].op // "" | takes_target)) | not)) | word(.word)]}
                 | select(.words | length > 0)];
            # Whether a simple command fed from a pipe or a redirection runs the code
            # it reads there: a shell given no -c (cat cmds | sh, sh -s < f), an
            # interpreter given no code option and no script (| python3, python3 -),
            # or a program given /dev/stdin.
            def code_shells: "^(sh|bash|zsh|dash|ksh|mksh|fish|ash|csh|tcsh)$";
            def interpreters: "^(python[0-9.]*|node|nodejs|deno|bun|perl|ruby|php|lua|osascript|pwsh|powershell|tclsh|wish|expect)$";
            def runs_its_input: .words as $ws
              | any(range(0; $ws | length) as $i | ($ws[$i].d | name_of) as $n | ($ws[$i + 1:] | map(.d)) as $rest
                    | if $ws[$i].d | IN("/dev/stdin", "/dev/fd/0", "/proc/self/fd/0") then true
                      elif $n | test(code_shells) then any($rest[]; test("^-[A-Za-z]*c")) | not
                      elif $n | test(interpreters) then
                        (any($rest[]; test("^-[A-Za-z]*[cemErpn]") or startswith("--eval")) or any($rest[]; startswith("-") | not)) | not
                      else false end; .);

            # An operand: a URL, read as the tool reads one. curl 8.13 and later reads
            # the URLs of an operand or a --url value that starts with @ from that file
            # (@- from its input), which this check does not read.
            def operand($tool; $d; $m):
              .pos += 1
              | if $tool == "http" and .pos > 2 and (($d | test("^[^@/]*?(==|:=@|:=|=@|=)") and ($d | split("=")[0] | test("@") | not)) or ($d | test("^[A-Za-z0-9_-]+:[^0-9/@][^@]*$"))) then .
                # an IPFS URL goes to the gateway IPFS_GATEWAY or a file names
                elif $d | test("^ip[fn]s:"; "i") then .out = {kind: "redirect", word: $d}
                elif $tool == "curl" and ($d | startswith("@")) then .out = {kind: "redirect", word: $d}
                else destination($m; $tool) as $why | if $why != null then .out = {kind: $why, word: $d} else . end
                end;
            # The words of a request: curl's, wget's or HTTPie's, after the tool's name.
            # Every word after -- is an operand (a URL), and wget's --no-config counts
            # only where wget reads it as an option: not as an option's value (-O
            # --no-config) nor after --. curl's --url takes the next word as a URL (an
            # operand here), and curl 8.16 and later reads --url=VALUE (or an
            # abbreviation of --url, which an earlier curl reads as an unknown or an
            # ambiguous option) as one too.
            def check_request($tool; $words; $runs):
              tables[$tool] as $t
              | reduce $words[] as $w ({skip: false, end: false, noconfig: false, pos: 0, out: null};
                  if .out != null then .
                  elif .skip then .skip = false
                  elif (.end | not) and $w.d == "--" then .end = true
                  elif (.end | not) and ($w.d | test("^-.")) then
                    if $w.d | startswith("--") then ($w.d | sub("=.*$"; "")) as $name
                      | if [$t.danger_long[] | . as $dl | ($name | startswith($dl)) or (($name | length) >= 3 and ($dl | startswith($name)))] | any
                        then .out = {kind: "redirect", word: $w.d}
                        elif $tool == "curl" and ($name | length) >= 4 and ("--url" | startswith($name)) and ($w.d | contains("=")) then
                          operand("curl"; $w.d | sub("^[^=]*="; ""); $w.m | sub("^[^=]*="; ""))
                        else .skip = (($w.d | contains("=") | not) and any($t.arg_long[]; . == $name))
                          | .noconfig = (.noconfig or $w.d == "--no-config")
                        end
                    else ($w.d[1:] | explode | map([.] | implode)) as $letters
                      | (first(range(0; $letters | length) as $i | select($t.arg_short | contains($letters[$i])) | $i) // null) as $at
                      # The flags of a cluster run to the first letter that takes an
                      # argument; the rest of the word, if any, is that argument.
                      | if $letters[:(if $at == null then ($letters | length) else $at + 1 end)] | any(test($t.danger_short))
                        then .out = {kind: "redirect", word: $w.d}
                        else .skip = ($at != null and $at == ($letters | length) - 1) end
                    end
                  else operand($tool; $w.d; $w.m)
                  end)
              # curl reads ~/.curlrc (a proxy, a host) unless -q is its first word; wget
              # reads ~/.wgetrc and /etc/wgetrc unless given --no-config; HTTPie its
              # configuration file's default options
              | if .out != null then .out
                elif .pos == 0 or ($runs | not) then null
                elif $tool == "curl" and (($words[0].d // "") | . == "--disable" or test("^-q") | not) then {kind: "config", word: "curl without -q first"}
                elif $tool == "wget" and (.noconfig | not) then {kind: "config", word: "wget without --no-config read as an option"}
                elif $tool == "http" and $httpie_defaults then {kind: "config", word: "http (its configuration file sets default options)"}
                else null end;

            # The first refusal of a simple command, or null. Its program is its first
            # word that is not a reserved word ($p). A word naming a tool (its name,
            # its path, a redirection's target) is read wherever it stands: the tool
            # runs as the program, or after wrappers with only options and numbers
            # between (sudo, timeout 5); a word given to a program that neither runs
            # nor copies it (which, echo; a package manager, by its bare name) is not
            # run; given to any other program, which may run it unread or copy it, it
            # is refused. A wrapper's option may take a tool's name as its value (env
            # -C http curl, sudo -u http curl: curl runs, not http), so a word naming a
            # tool may stand between the wrapper and the tool, and where a wrapper runs
            # one, every word naming a tool is read as a request with that tool's
            # grammar ($reads), at most 8 of them: the command is refused when any
            # reading refuses.
            def check_command($words):
              ($words | map(select(.target | not))) as $args
              | (first(range(0; $args | length) as $i | select($args[$i].d | IN(reserved[]) | not) | $i) // null) as $p
              | (if $p == null then "" else $args[$p].d | name_of end) as $prog
              | ($prog | IN(tools[])) as $runs_tool
              | [range(0; $args | length) | select(. != $p and ($args[.].d | name_of | IN(tools[])))] as $tool_words
              | any($words[]; .target and (.d | name_of | IN(tools[]))) as $tool_target
              | (($tool_words | length) > 0 or $tool_target) as $given
              | (($prog | IN(non_runners[]))
                 or (($prog | IN(installers[])) and ($tool_target | not) and all($tool_words[]; $args[.].d | test("/") | not))) as $inert
              # (the tool runs: it is the program, or wrappers run it, with only
              # options, numbers, wrappers and words naming a tool between, which run
              # to the first other word, $q)
              | (if $p == null then 0
                 else first(range($p + 1; $args | length) as $i
                            | select($args[$i].d | option_or_number or (name_of | IN(wrappers[]) or IN(tools[])) | not) | $i)
                      // ($args | length) end) as $q
              | ($runs_tool
                 or (($tool_words | length) > 0 and ($prog | IN(wrappers[])) and $tool_words[-1] < $q)) as $runs
              | (if $runs_tool then [$p] elif $runs then $tool_words else $tool_words[:1] end) as $reads
              | $reads[0] as $at
              | (if $runs_tool then $p else $tool_words[-1] end) as $last
              | if $p != null and $args[$p].assign then {kind: "assign", word: $args[$p].d}
                elif any($words[]; setting_word) then
                  {kind: "file", word: first($words[] | select(setting_word) | .d)}
                elif any($words[]; .d | sensitive_var) then
                  {kind: "assign", word: first($words[] | select(.d | sensitive_var) | .d)}
                # alias, hash and enable give a program another name, unread (a
                # word of echo or which, which run nothing, aside)
                elif ($inert | not) and any($args[]; .d | IN(renamers[])) then
                  {kind: "alias", word: first($args[] | select(.d | IN(renamers[])) | .d)}
                # A copy or a link of the tool runs under another name, unread: a
                # copier anywhere in a command that names the tool, but as the
                # tool's own word (curl -q https://example.com/install)
                elif $given and ($runs_tool | not) and ($inert | not)
                     and any($args[$p:][]; .d | name_of | IN(copiers[])) then
                  {kind: "copy", word: ($words | map(.d) | join(" "))}
                # xargs and parallel give the tool words from their input, unread
                elif $last != null and any($args[:$last][]; .d | name_of | IN(feeders[])) then
                  {kind: "feeds", word: ($args | map(.d) | join(" "))}
                else
                  # git's settings (git -c NAME=VALUE, --config-env, git config NAME),
                  # and a URL any program is given
                  (first(range(0; $args | length) as $i | select($args[$i].d | name_of == "git") | $i) // null) as $git
                  | (if $git == null then null
                     else first(range($git + 1; $args | length) as $i
                                | $args[$i].d as $d
                                | select(($d == "--config-env" or ($d | startswith("--config-env=")))
                                         or ($d | startswith("-c") and ((if $d == "-c" then ($args[$i + 1].d // "") else $d[2:] end) | ascii_downcase | test(git_settings) | not))
                                         or ($d == "config" and any($args[$i + 1:][]; .d | test("^[A-Za-z0-9-]+\\.") and (ascii_downcase | test(git_settings) | not))))
                                | {kind: "redirect", word: $d}) // null
                     end) as $g
                  | if $g != null then $g
                    elif ($reads | length) > 8 then {kind: "many", word: ($words | map(.d) | join(" "))}
                    else (first($reads[] as $j
                                | ($args[$j].d | name_of | if . == "https" then "http" else . end) as $tool
                                | check_request($tool; $args[$j + 1:]; $inert | not) | select(. != null)) // null) as $r
                    | if $r != null then $r
                      elif $given and ($runs | not) and ($inert | not) then
                        {kind: "argument", word: ($words | map(.d) | join(" "))}
                      else (first($args[:($at // ($args | length))][] | select(.m | test("^[A-Za-z][A-Za-z0-9+.-]*:/")) | destination(.m; "url") as $why | select($why != null) | {kind: $why, word: .d}) // null)
                      end
                    end
                end;

            (.cwd // "") as $cwd
            | .tool_input.command // ""
            | if utf8bytelength > 16384 then "long "
              # In every command: a word the shell may expand to a request tool's name,
              # or to a file that sets where a request goes, in the command as written
              # and with its line continuations joined (c?\<newline>rl)
              else ([.] + (if contains("\\\n") then [split("\\\n") | add] else [] end)
                    | map(scan("[^\\s;&|()<>]*[*?\\[\\]{}][^\\s;&|()<>]*")) | unique | map({run: ., ws: run_words})) as $runs
                | (first($runs[] | select(may_expand_to_tool(.ws)) | .run) // null) as $p
                | (first($runs[] | select(may_expand_to_setting_file(.ws)) | .run) // null) as $f
                | commands as $c
                | if $p != null then "program \($p | .[:200])"
                elif $f != null then "file \($f | .[:200])"
                # an extglob pattern (c@(u)rl, once shopt -s extglob has run) may
                # expand to any name; its words are not read here
                elif $c.why == "extglob" then "program an extglob pattern"
                elif $named | not then "ok"
                else
                  if $c.why != null then "expands \($c.why)"
                  elif any($c.cmds[][]; .braces) then "expands brace"
                  # A command line inside a word, where a program that runs one is in the
                  # command (sh -c '...', echo '...' | sh, trap '...' EXIT, sed '1e ...',
                  # git rebase -x '...'), and code a shell or an interpreter reads from a
                  # pipe or a redirection: their words are not read here
                  elif (any($c.cmds[][]; .d | name_of | test(shells))
                        or any($c.cmds[]; any(.[]; .d | name_of == "git") and any(.[]; .d | test(git_runs))))
                       and any($c.cmds[][]; .d | embedded) then
                    "nested \(first($c.cmds[][] | select(.d | embedded) | .d) | .[:200])"
                  elif any(fed_commands[]; .fed and runs_its_input) then
                    "nested \(first(fed_commands[] | select(.fed and runs_its_input) | .words | map(.d) | join(" ")) | .[:200])"
                  # A name of such a file (or a URL ending in one, which curl -O and
                  # wget write under it) where the line may change the directory it is
                  # read in, or the call runs in /etc, ~/.ipfs or HTTPie's: cd /etc &&
                  # ... >> hosts, curl --output-dir /etc -o hosts, wget -P /etc
                  elif (any($c.cmds[][]; .d | moves_dir) or ($cwd | ascii_downcase | tidy | test("(^|/)(etc|\\.ipfs|\\.?httpie)$")))
                       and any($c.cmds[][]; .d | last_name | IN(setting_names[])) then
                    "file \(first($c.cmds[][] | select(.d | last_name | IN(setting_names[]))) | .d | .[:200])"
                  else (first($c.cmds[] | check_command(.) | select(. != null)) // null) as $r
                  | if $r == null then "ok" else "\($r.kind) \($r.word | .[:200])" end
                  end
                end
              end
            JQ
            )"
            # Whether the command may turn on dotglob, so that a glob matches a
            # leading dot: shopt, GLOBIGNORE, BASHOPTS, or a file it sources or text
            # it evaluates (quotes and backslashes removed)
            DOTS=false
            printf '%s\n' "$CMD" | tr -d "\"'\\\\" | grep -qE '(shopt|GLOBIGNORE|BASHOPTS|SHELLOPTS|dotglob)|(^|[[:space:];&|(])(\.|source|eval)([[:space:]]|$)' && DOTS=true
            VERDICT="$(printf '%s' "$INPUT" | jq -r --argjson named "$NAMED" --argjson httpie_defaults "$HTTPIE_DEFAULTS" --argjson dots "$DOTS" "$READER" 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: the send skill's check could not read the command" >&2; exit 2; }
            KIND="${VERDICT%% *}"
            WORD="${VERDICT#* }"
            case "$KIND" in
              ok) exit 0 ;;
              internal) echo "$INTERNAL: $WORD" >&2 ;;
              redirect) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose connection an option or a proxy setting redirects ($WORD), in any spelling (quoted, abbreviated, --proxy1.0, git -c http.*), nor curl's --variable and --expand-* options, which build text when the command runs, nor an ipfs:// or ipns:// URL, which goes to the gateway IPFS_GATEWAY or a file names, nor curl's --url @file or an @file operand, which curl 8.13 and later reads URLs from: the address it reaches is not the one this check reads" >&2 ;;
              file) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a command that names bash's /dev/tcp or /dev/udp, which open a connection, or a file that sets where a request goes (.curlrc, .wgetrc, /etc/hosts, resolv.conf, ~/.ipfs/gateway, HTTPie's config.json), by its name in any spelling (/etc//hosts, a .. segment), by a glob or a brace the shell may expand to it, or by its last component (or a URL's, which curl -O and wget name a file after) where the command may change the directory it is read in (cd, --output-dir, -P) or runs in /etc: $WORD" >&2 ;;
              config) echo "F504 CONSTRAINT_VIOLATED: the send skill runs curl only with -q as its first option and wget only with --no-config read as an option (not an option's value, not after --), wherever the tool runs (after !, if, while, a wrapper or a program this check does not know), so no configuration file (.curlrc, .wgetrc, /etc/wgetrc) sets a proxy or a host this check does not read, and HTTPie only where its configuration file sets no default options: $WORD" >&2 ;;
              assign) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a command with a variable set on its line, nor one that names CURL_HOME, HOME, XDG_CONFIG_HOME, WGETRC, SYSTEM_WGETRC, IPFS_GATEWAY, IPFS_PATH, HTTPIE_CONFIG_DIR, PATH, a CA bundle, a proxy, git's or the loader's variables, with or without a value (export NAME, read NAME, for NAME in, printf -v NAME): '$WORD': a setting changes where the request goes, unseen by this check" >&2 ;;
              nested) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request inside a command line given as a word (sh -c, trap, awk's system, sed's e, an interpreter's code, git rebase -x), nor code a shell or an interpreter reads from a pipe or a file, in a command that names curl, wget or http: '$WORD', whose destination this check cannot read; run curl, wget or http directly" >&2 ;;
              copy) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a command that copies or links curl, wget or http ('$WORD'), whatever comes before the copier (!, if, a wrapper): the copy runs under another name, unread by this check" >&2 ;;
              argument) echo "F504 CONSTRAINT_VIOLATED: the send skill runs curl, wget or http only as a command's program, or after a program that runs the one a later word names (env, sudo, timeout, nice, ...) with only options, numbers and the names of such programs or tools between; it does not give one to another program ('$WORD': prlimit, a loader, head, gzip, an unknown program), which may run it unread or copy it" >&2 ;;
              many) echo "F504 CONSTRAINT_VIOLATED: the send skill reads at most 8 words naming curl, wget or http after a program that runs another (env, sudo, ...): a wrapper's option may take a tool's name as its value (env -C http curl), so each such word is read as the request's program, and this command holds more ('$WORD')" >&2 ;;
              alias) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run alias, hash, enable or a function definition in a command that names curl, wget or http ('$WORD'): each gives a program another name, which this check does not read" >&2 ;;
              feeds) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose words xargs or parallel read from their input ('$WORD'): the host it reaches is not one this check reads; write each URL in the command" >&2 ;;
              program) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a command with a word the shell may expand to the name of curl, wget or http ('$WORD': a glob in any letter case, a brace or an extglob pattern, c?rl, CU?L, cu{r,r}l, c@(u)rl): the program it runs is not one this check reads; name the program literally" >&2 ;;
              expands) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose text the shell expands or escapes (an unquoted brace, a glob character *, ?, [ or ] before a URL's path, an unclosed quote, a here-document): the host it reaches is not the one this check reads. Quote each URL whole, and send a payload from a file with -d @file" >&2 ;;
              unreadable) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a request whose host this check cannot read ($WORD): a host is a name of ASCII letters, digits, dots and hyphens, or an IPv6 literal, with a port of digits, no percent-encoding and no braces or brackets curl expands" >&2 ;;
              long) echo "F504 CONSTRAINT_VIOLATED: the send skill does not run a command longer than 16384 bytes that names curl, wget or http or holds a glob or a brace, which this check does not read; send a long payload from a file with -d @file" >&2 ;;
              *) echo "R407 SAFETY_CHECK_FAILED: the send skill's check could not read the command" >&2 ;;
            esac
            exit 2
    - matcher: "Edit|Write|MultiEdit|NotebookEdit"
      hooks:
        - type: command
          timeout: 30
          onFailure: block
          command: |
            # Host-specific addition (STANDARD 1.2.0 §5.18.10, F504): the Bash hook
            # refuses a command that names a file that sets where a request goes, so
            # an Edit, Write, MultiEdit or NotebookEdit of one is refused too: curl's
            # and wget's configuration (.curlrc, curlrc, .wgetrc, wgetrc), the
            # resolver's (/etc/hosts, resolv.conf), curl's IPFS gateway
            # (.ipfs/gateway) and HTTPie's (httpie/config.json), by the path as
            # written and the file it reaches (links followed; a link that cannot be
            # followed is refused), in any letter case, and a path through a ..
            # segment whose last component is such a file's. Claude Code passes the tool
            # call as JSON on stdin; exit 2 blocks the call and the reason on stderr
            # is shown to Claude. A call that cannot be read is blocked (R407).
            INPUT="$(jq -c . 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            # The path exactly as given: a command substitution strips the line
            # breaks that end its output, and a file's name may end in one (x and
            # x<newline> are two files), so an x is printed after it and taken off.
            TARGET="$(printf '%s' "$INPUT" | jq -j '(.tool_input.file_path // .tool_input.notebook_path // empty), "x"' 2>/dev/null)" || { echo "R407 SAFETY_CHECK_FAILED: cannot read the tool call (jq is required)" >&2; exit 2; }
            TARGET="${TARGET%x}"
            [ -n "$TARGET" ] || exit 0
            REFUSE="F504 CONSTRAINT_VIOLATED: the send skill does not edit or write a file that sets where a request goes (.curlrc, .wgetrc, /etc/hosts, resolv.conf, ~/.ipfs/gateway, HTTPie's config.json): '$TARGET'"
            REACHED="$TARGET"
            if [ -L "$TARGET" ]; then
              REACHED="$(readlink -f -- "$TARGET" 2>/dev/null)" || { echo "$REFUSE" >&2; exit 2; }
            elif [ -e "$TARGET" ] || [ -d "$(dirname -- "$TARGET")" ]; then
              REACHED="$(readlink -f -- "$TARGET" 2>/dev/null)" || REACHED="$TARGET"
            fi
            for P in "$TARGET" "$REACHED"; do
              # In lower case (a file system may ignore case), repeated slashes and ./
              # segments removed (each of /././, read until none is left)
              SEEN="$(printf '%s\n' "$P" | tr 'A-Z' 'a-z' | sed -e 's#//*#/#g' -e ':a' -e 's#/\./#/#g' -e 'ta' -e 's#^\./##')"
              # A path with a .. segment reaches what the links on its way decide
              # (/etc/x/../hosts, a parent that does not exist yet): one whose last
              # component is such a file's is refused
              case "$SEEN" in
                */.. | */../* | ../* | ..)
                  case "${SEEN##*/}" in
                    hosts | resolv.conf | gateway | config.json | *curlrc | *wgetrc)
                      echo "$REFUSE" >&2
                      exit 2
                      ;;
                  esac
                  ;;
              esac
              case "$SEEN" in
                *curlrc | *wgetrc | */etc/hosts | etc/hosts | *resolv.conf | */.ipfs/gateway | .ipfs/gateway | */httpie/config.json | httpie/config.json | */.httpie/config.json | .httpie/config.json)
                  echo "$REFUSE" >&2
                  exit 2
                  ;;
              esac
            done
            exit 0
---

## Intent

Send a message, event, or payload to an external destination with full policy enforcement, approval gates, and audit trail. This capability handles external side effects that cannot be undone: the checkpoint before it restores the agent's own state, not the transmission, so a send is made safe before it happens (STANDARD v1.2 §4.4.2).

**CRITICAL: This capability requires explicit user approval before execution.**

**Success criteria:**
- Message delivered to destination successfully
- All policy constraints verified before sending
- Approval gate passed (explicit user confirmation)
- Complete audit trail of what was sent
- Delivery confirmation obtained where possible

**Compatible schemas:**
- `schemas/output_schema.yaml`

## Inputs

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `destination` | Yes | string | Where the data goes, in the host's naming (a URL, an address, a queue or a channel); checked against the destination policies in force (STANDARD v1.2 §4.4.2) |
| `payload` | Yes | any | Data to send |
| `protocol` | No | string | Communication protocol (http, grpc, smtp, amqp, etc.) |

Inputs not listed here are outside the capability's contract: a workflow step that binds them gets W604 (STANDARD v1.1 §5.5).

## Procedure

1) **Verify approval**: Confirm explicit user approval exists
   - Check the approval is valid and recent
   - BLOCK send if approval is missing or expired
   - Log approval verification for audit

2) **Verify checkpoint**: Confirm recovery point exists
   - Validate that a checkpoint was created before this send
   - BLOCK send if checkpoint is missing
   - The checkpoint restores the agent's own state, not the transmission (§4.4.2): once delivered, the data cannot be recalled, and a later rollback reports the send as `not_covered` (`transmitted`)

3) **Validate destination**: Ensure the destination is permitted
   - Where a destination policy is in force (the host's, or an applied profile's `allowed_destinations`), code checks it before approval and refuses a destination it does not allow (F504, STANDARD v1.2 §4.4.2); never try another destination to get around a refusal
   - In a workflow, a `constrain` step with the destination as `target` records the check, and the approval `shows` the destination (§12.5, Guarded Send)
   - Verify destination format matches protocol

4) **Apply constraints**: Enforce policy limits
   - Check rate limits have not been exceeded
   - Verify message size within bounds
   - Validate message format against schema
   - Apply `constrain` capability rules

5) **Prepare payload**: Format message for transmission
   - Serialize according to protocol requirements
   - Add required headers/metadata
   - Generate message ID for tracking
   - Record payload summary (not full content if sensitive)

6) **Execute send**: Transmit to destination
   - Use appropriate protocol handler
   - Pass the pass's idempotency key to a destination that accepts one (an `Idempotency-Key` header, a message de-duplication id)
   - Capture response or confirmation
   - Handle timeouts gracefully
   - Retry: a retry carries the same idempotency key; never transmit twice under one key; when unsure whether an earlier attempt delivered, do not send again (report `outcome_unknown`, §4.4.2)

7) **Verify delivery**: Confirm successful transmission
   - Check response status/acknowledgment
   - Log delivery confirmation
   - Capture any error responses

8) **Audit trail**: Record complete send operation
   - What was sent (summary, not sensitive content)
   - Where it was sent
   - When it was sent
   - Delivery status
   - Approval reference

## Output Contract

Return a structured object:

```yaml
sent: boolean  # true when the transport accepted the message (delivery.status sent or queued)
response: any  # Recipient's response or delivery receipt, if any
timestamp: string  # ISO 8601 date-time of send
message:
  destination: string  # Where message was sent
  payload_type: string  # Type of content sent
  payload_summary: string  # Non-sensitive summary of payload
  message_id: string | null  # Tracking ID if available
delivery:
  status: sent | queued | failed  # Delivery outcome
  retry_count: integer  # Number of retry attempts
  response_code: integer | null  # HTTP status or protocol response
  error: string | null  # Error message if failed
constraints_applied:
  - constraint: string  # What constraint was checked
    enforced: boolean  # Whether it passed
    details: string | null  # Additional context
approval:
  token: string  # Approval token used
  timestamp: string  # When approval was given
  scope: string  # What was approved
compensation:  # How the effect can be compensated, if known; nothing performs it automatically (§4.4.2)
  strategy: string
  inverse_effects: array[string]
confidence: number  # probability that the message was delivered as reported (§4.1.1)
evidence_anchors: [{ref: "sent:<idempotency_key>", kind: record}, {ref: "log:timestamp", kind: log}, {ref: "api:response", kind: api}]  # a message sent is grounded by its record, under the pass's idempotency key (STANDARD v1.2 §3.1)
assumptions: []  # Explicit assumptions
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `sent` | boolean | Whether the message was sent (accepted by the transport) |
| `response` | any | Recipient's response or delivery receipt, or null |
| `timestamp` | string | ISO 8601 date-time of send |
| `message` | object | Details of what was sent (destination, payload type, non-sensitive summary, message ID) |
| `delivery` | object | Outcome of send operation |
| `constraints_applied` | array | Policy checks performed |
| `approval` | object | Approval gate information |
| `compensation` | object | How the transmission's effect can be compensated (`strategy`, `inverse_effects`), in the form of `TransitionRule.rollback`; a workflow that compensates does so in a send of its own (§4.4.2) |
| `confidence` | number | Probability, 0.0-1.0, that the message was delivered as reported (§4.1.1) |
| `evidence_anchors` | array of evidence anchors (§6.5) | Logs, responses, confirmations |
| `assumptions` | array | Explicit assumptions (e.g., "network stable") |

## Examples

### Example 1: API Webhook Notification

**Input:**
```yaml
destination: "https://api.partner.com/webhooks/order-updates"
payload:
  event: "order.completed"
  order_id: "ORD-12345"
  timestamp: "2024-01-15T10:30:00Z"
  customer_notified: true
protocol: "http"
```

Approval and the checkpoint come from the workflow (an approved step after a `checkpoint` step), not from inputs. A preceding `constrain` step enforces the policy: at most 100 sends per hour, to `api.partner.com` only.

**Output:**
```yaml
sent: true
response:
  received: true
timestamp: "2024-01-15T10:30:15Z"
message:
  destination: "https://api.partner.com/webhooks/order-updates"
  payload_type: "order.completed event"
  payload_summary: "Order completion notification for ORD-12345"
  message_id: "msg-abc123"
delivery:
  status: sent
  retry_count: 0
  response_code: 200
  error: null
constraints_applied:
  - constraint: "rate_limit: 100/hour"
    enforced: true
    details: "Current rate: 45/hour"
  - constraint: "destination policy (STANDARD v1.2 §4.4.2)"
    enforced: true
    details: "https://api.partner.com/webhooks/* allows it"
approval:
  token: "approve-send-2024-01-15-001"
  timestamp: "2024-01-15T10:30:00Z"
  scope: "Send order notification to partner API"
confidence: 0.95
evidence_anchors:
  - {ref: "sent:run-4f2a:7", kind: record}
  - {ref: "log:2024-01-15T10:30:15Z:send-success", kind: log}
  - {ref: "api:response:200-OK", kind: api}
assumptions:
  - "Partner API is available and processing webhooks"
```

**Evidence pattern:** HTTP response code and body confirmation, timestamped log entry.

---

### Example 2: Email Notification (with failure)

**Input:**
```yaml
destination: "smtp://mail.company.com:587"
payload:
  to: "user@example.com"
  subject: "Action Required: Review pending"
  body: "You have 3 items awaiting review..."
protocol: "smtp"
```

**Output:**
```yaml
sent: false
response: null
timestamp: "2024-01-15T11:00:05Z"
message:
  destination: "smtp://mail.company.com:587"
  payload_type: "email"
  payload_summary: "Email to user@example.com regarding pending review"
  message_id: null
delivery:
  status: failed
  retry_count: 3
  response_code: null
  error: "Connection timeout after 30s - SMTP server unreachable"
constraints_applied:
  - constraint: "recipient_validation"
    enforced: true
    details: "Email format valid"
approval:
  token: "approve-email-2024-01-15-002"
  timestamp: "2024-01-15T11:00:00Z"
  scope: "Send review notification email"
confidence: 0.0
evidence_anchors:
  - {ref: "log:2024-01-15T11:00:05Z:smtp-timeout", kind: log}
  - {ref: "error:connection-refused", kind: tool}
assumptions:
  - "SMTP server should be available on port 587"
next_actions:
  - "Verify SMTP server status"
  - "Check network connectivity"
  - "Retry with backup mail server if available"
```

## Verification

- [ ] Approval token is valid and not expired
- [ ] Checkpoint reference exists
- [ ] Destination passes policy validation
- [ ] All constraints were checked before send
- [ ] Delivery status is accurately reported
- [ ] Audit trail is complete

**Verification tools:** Read (for logs), Bash (for health checks)

## Safety Constraints

- `mutation`: true
- `requires_checkpoint`: true
- `requires_approval`: true
- `risk`: high

**Capability-specific rules:**
- NEVER send without explicit user approval (CRITICAL)
- NEVER send without a valid checkpoint reference
- ALWAYS validate destination against policy before sending
- ALWAYS log what was sent for audit (sanitize sensitive data)
- DO NOT retry indefinitely - respect retry limits
- BLOCK sends to destinations the destination policy does not allow, where one is in force (code refuses them with F504, §4.4.2)
- NEVER transmit twice under one idempotency key; when unsure whether an earlier attempt delivered, do not send again
- If approval token is missing, REQUEST approval before proceeding
- Never send credentials, API keys, or secrets in payloads

**APPROVAL GATE REQUIREMENT:**
Before any send operation, the user must explicitly approve:
1. What will be sent (summary)
2. Where it will be sent (destination)
3. Why it is being sent (context)

The approval must be captured with a token that is recorded in this operation's audit trail.

## Composition Patterns

**Commonly follows:**
- `constrain` - Apply policy limits before sending (recommended; warning W601 if no constrain step runs first)
- `checkpoint` - Create recovery point before external send (REQUIRED)
- `plan` - Sends are typically part of a larger plan
- `transform` - Format data before sending

**Commonly precedes:**
- `audit` - Record what was sent for compliance
- `verify` - Confirm delivery where possible
- `receive` - May expect response from destination

**Anti-patterns:**
- NEVER send without `constrain` check (policy bypass)
- NEVER send without `checkpoint` (no state recovery)
- NEVER send without explicit approval (unauthorized action)
- NEVER retry failed sends indefinitely (resource exhaustion)

**Workflow references:**
- See `reference/composition_patterns.md#anti-patterns` for send safety rules
- See `reference/composition_patterns.md#digital-twin-sync-loop` for send in sync context
