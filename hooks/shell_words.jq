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
