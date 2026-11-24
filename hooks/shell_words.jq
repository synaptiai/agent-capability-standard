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
