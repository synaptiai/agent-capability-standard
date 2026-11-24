# BEGIN secret-scan (source: hooks/secret_scan.sh; tests/test_skill_hooks.py keeps every copy equal)
# secret_in TEXT: status 0 when TEXT holds a credential-shaped value (STANDARD 1.2.0 §6.7), read line by line and again with
# its line breaks read as blanks, as the SDK's and the TypeScript rules read whitespace (password:<newline>value).
# secret_lines TEXT: the same rules, each line read on its own; a caller that joins texts read apart joins them with line
# breaks, each text given once as it is and once with its own line breaks read as blanks.
# secret_values TEXT: what the rules whose match may hold whitespace find in TEXT, one per line, each line read on its own:
# the match, or the value a rule reads out of it (a caller compares what two texts hold).
# The shapes of keys and tokens (the first two may hold whitespace)
SECRET_SPACED='-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----|[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{20,}'
SECRET_ERE="$SECRET_SPACED"'|(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'
SECRET_KEY='(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key)'
# A quote, or an escaped one (\" in JSON text inside a JSON string)
SECRET_Q="\\\\*[\"']"
# A command's option named for a credential (--password, --api-key), and a user option (curl -u user:password; a user of at most 256 characters, so no run is read again from each of its positions)
SECRET_OPT="(^|[^A-Za-z0-9_-])--([A-Za-z0-9]+[_-])*$SECRET_KEY"
SECRET_SEP="([[:space:]]+($SECRET_Q)?|=($SECRET_Q)?|($SECRET_Q)?[[:space:]]*,[[:space:]]*$SECRET_Q)"
SECRET_USER="(^|[^A-Za-z0-9_-])(-[uU]$SECRET_SEP?|--(proxy-)?user$SECRET_SEP)[^[:space:]:\"'\\\\]{0,256}:"
# A quoted value with no whitespace, 8 or more characters, assigned or given to a credential option
SECRET_QUOTED="$SECRET_KEY($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[^[:space:]\"']{8,}[\"']|$SECRET_OPT([[:space:]]+|($SECRET_Q)?[[:space:]]*,[[:space:]]*)$SECRET_Q[^-[:space:]\"'][^[:space:]\"']{7,}[\"']"
# The rules are ASCII, read byte by byte (LC_ALL=C, in a subshell): a multibyte locale sends some of them to a matcher whose time grows with the square of the text
secret_values() (
  LC_ALL=C
  export LC_ALL
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
  printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q((basic|bearer|token|digest|negotiate)[[:space:]]+)?[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
    sed -E "s/\\\\*[\"'][[:space:]]*[])]\$//; s/^.*[:=,][[:space:]]*\\\\*[\"']//" |
    sed -E 's/^([Bb][Aa][Ss][Ii][Cc]|[Bb][Ee][Aa][Rr][Ee][Rr]|[Tt][Oo][Kk][Ee][Nn]|[Dd][Ii][Gg][Ee][Ss][Tt]|[Nn][Ee][Gg][Oo][Tt][Ii][Aa][Tt][Ee])[[:space:]]+//' |
    grep -E '[0-9]' | grep -E '[A-Za-z]'
  # ... and the same after any other scheme
  printf '%s' "$1" | grep -Eio -- "[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*($SECRET_Q)?value($SECRET_Q)?[[:space:]]*[:=][[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}|[[(][[:space:]]*\\\\*[\"'][^[:space:]\"']*($SECRET_KEY|authorization|cookies?)$SECRET_Q[[:space:]]*,[[:space:]]*$SECRET_Q[A-Za-z][A-Za-z0-9._-]* +[A-Za-z0-9._~+/=-]{8,}$SECRET_Q[[:space:]]*[])]" |
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
  return 0
)
secret_lines() (
  LC_ALL=C
  export LC_ALL
  printf '%s' "$1" | grep -Eq -- "$SECRET_ERE" && return 0
  # The password of a URL's userinfo, unless it is a placeholder (its scheme read from the start of its run, once)
  printf '%s' "$1" | grep -Eo -- '(^|[^A-Za-z0-9+.-])[0-9+.-]*[A-Za-z][A-Za-z0-9+.-]*://[^[:space:]/:@]*:[^[:space:]/@]+@' |
    sed -E 's#^.*//[^:]*:##; s#@$##' | grep -Eivq -- '^([$<{*[].*|password|passwd|pwd|pass|secret|token)$' && return 0
  # The rules that read a quoted value, or a value out of a match
  secret_values "$1" | grep -q .
)
secret_in() (
  secret_lines "$1" && return 0
  SECRET_FOLDED="$(printf '%s' "$1" | LC_ALL=C tr '\n\r' '  ')" || return 0
  [ "$SECRET_FOLDED" != "$1" ] && secret_lines "$SECRET_FOLDED"
)
# END secret-scan
