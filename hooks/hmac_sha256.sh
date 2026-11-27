# BEGIN hmac-sha256 (source: hooks/hmac_sha256.sh; tests/test_hmac_sha256.py keeps every copy equal)
# HMAC-SHA-256 (RFC 2104) built on openssl's SHA-256, so that the key is on
# no command line: `openssl dgst -hmac KEY` would put the key in the process
# list, which any process of the user can read. The key and the pads reach
# od and openssl only through a pipe from the shell's builtin printf. It is
# POSIX sh (the rollback skill's hook runs under sh), so it has no local
# variables: every name it sets starts with hmac_.
# hmac_pads KEY: sets hmac_ipad and hmac_opad from KEY (hashed first when it
# is over 64 bytes, then padded with zero bytes to 64 bytes), XOR 0x36 and
# XOR 0x5c, as printf escapes (\ooo): a variable cannot hold a zero byte.
# Status 1, with both empty, for an empty key or when od, awk or openssl
# fails.
# hmac_hex: prints the HMAC-SHA-256, in hex, of standard input under the key
# hmac_pads was given last. Status 1, printing nothing, when openssl fails.
hmac_ipad=""
hmac_opad=""
hmac_pad_awk() {
  awk '
    function xor8(a, c, r, p) {
      r = 0
      for (p = 1; p < 256; p *= 2) if (int(a / p) % 2 != int(c / p) % 2) r += p
      return r
    }
    { for (f = 1; f <= NF; f++) b[n++] = $f + 0 }
    END {
      if (n > 64) { print "long"; exit }
      i = ""
      o = ""
      for (k = 0; k < 64; k++) {
        v = (k < n) ? b[k] : 0
        i = i sprintf("\\%03o", xor8(v, 54))
        o = o sprintf("\\%03o", xor8(v, 92))
      }
      print n + 0, i, o
    }'
}
hmac_pads() {
  hmac_ipad=""
  hmac_opad=""
  hmac_pad=$(printf '%s' "$1" | od -An -v -tu1 | hmac_pad_awk) || hmac_pad=""
  if [ "$hmac_pad" = long ]; then
    hmac_pad=$(printf '%s' "$1" | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tu1 | hmac_pad_awk) || hmac_pad=""
    case "$hmac_pad" in "32 "*) ;; *) hmac_pad="" ;; esac
  fi
  case "$hmac_pad" in
    "" | "0 "* | *[!0-9\ \\]*) hmac_pad="" ;;
  esac
  hmac_pad=${hmac_pad#* }
  hmac_ipad=${hmac_pad% *}
  hmac_opad=${hmac_pad#* }
  hmac_pad=""
  if [ "${#hmac_ipad}" != 256 ] || [ "${#hmac_opad}" != 256 ]; then
    hmac_ipad=""
    hmac_opad=""
    return 1
  fi
}
hmac_hex() {
  [ -n "$hmac_ipad" ] || return 1
  # shellcheck disable=SC2059 # the pads are escapes for printf to expand
  hmac_inner=$({ printf "$hmac_ipad"; cat; } | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tu1 | awk '{ for (f = 1; f <= NF; f++) printf "\\%03o", $f }') || hmac_inner=""
  [ "${#hmac_inner}" = 128 ] || return 1
  # shellcheck disable=SC2059
  hmac_out=$({ printf "$hmac_opad"; printf "$hmac_inner"; } | openssl dgst -sha256 -binary 2>/dev/null | od -An -v -tx1 | tr -d ' \n') || hmac_out=""
  case "$hmac_out" in *[!0-9a-f]*) return 1 ;; esac
  [ "${#hmac_out}" = 64 ] || return 1
  printf '%s' "$hmac_out"
}
# END hmac-sha256
