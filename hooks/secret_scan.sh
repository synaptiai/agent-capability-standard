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
