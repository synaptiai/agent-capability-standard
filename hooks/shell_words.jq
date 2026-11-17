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
