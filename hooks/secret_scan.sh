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
  # An unquoted value of 12 or more characters with letters and digits
  printf '%s' "$1" | grep -Eio -- "$SECRET_KEY[\"']?[[:space:]]*[:=][[:space:]]*[^[:space:]\"']{12,}" |
    sed -E 's/^[^:=]*[:=][[:space:]]*//' | grep -E '[0-9]' | grep -Eq '[A-Za-z]'
}
# END secret-scan
