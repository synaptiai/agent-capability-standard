# BEGIN secret-member (source: hooks/secret_member.jq; tests/test_skill_hooks.py keeps every copy equal)
# acs_held(false): whether JSON data holds, in a member named for a
# credential, a value redaction replaces that is not a placeholder: the rule
# the SDK redactor applies to data (grounded_agency/state/redaction.py,
# _secret_member_value; STANDARD 1.2.0 §6.7). A member is secret when its
# name ends in a credential name or names a header that carries one
# (Authorization, Cookie), when it is the value of a name/value pair whose
# name is such a name ({"name": "Authorization", "value": ...}), the second
# of a [name, value] tuple, or inside a secret member. Its value counts when
# it is a number, or a string of 4 or more characters other than [REDACTED]
# that is not a placeholder (<...>, ${...}, ****, password, token, ...).
# Names are compared in ASCII lower case, as the SDK compares them (re.ASCII,
# IGNORECASE), with string functions: jq compiles a regular expression at
# each test, about 0.4 ms a member, so a record of 1 MB took 22 s. A name
# outside ASCII (utf8bytelength differs from length) is also tested with
# Unicode case folding, so this rule finds a name the SDK does not in rare
# spellings, never the reverse; a placeholder is matched in ASCII only, so
# no rare spelling hides a value. A copy sits in a single-quoted shell
# string, so this text holds no single quote.
def acs_names: ["password", "passwd", "passphrase", "pwd", "secret", "secret_key", "secret-key", "secretkey", "token", "api_key", "api-key", "apikey", "access_key", "access-key", "accesskey", "client_secret", "client-secret", "clientsecret", "private_key", "private-key", "privatekey", "authorization", "cookie", "cookies"];
def acs_name: (ascii_downcase as $n | any(acs_names[]; . as $s | $n | endswith($s)))
  or (utf8bytelength != length and test("\\A[\\s\\S]*(password|passwd|passphrase|pwd|secret|secret[_-]?key|token|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|authorization|cookies?)\\z"; "i"));
def acs_is($words): (ascii_downcase | IN($words[])) or (utf8bytelength != length and test("\\A(" + ($words | join("|")) + ")\\z"; "i"));
def acs_scalar: (type == "string" and length >= 4 and . != "[REDACTED]") or type == "number";
def acs_placeholder: type == "string"
  and (((.[0:1] | IN("$", "<", "{", "*", "[")) and (contains("\n") | not))
       or (ascii_downcase | IN("password", "passwd", "pwd", "pass", "secret", "token")));
def acs_held($secret):
  if $secret and acs_scalar then (acs_placeholder | not)
  elif type == "object" then
    (($secret | not) and any(to_entries[]; (.key | acs_is(["name", "key", "header"])) and (.value | type == "string" and acs_name))) as $pair
    | any(to_entries[]; .key as $k | .value | acs_held($secret or ($k | acs_name) or ($pair and ($k | acs_is(["value"])))))
  elif type == "array" then
    (($secret | not) and length == 2 and (.[0] | type == "string" and acs_name)) as $tuple
    | any(to_entries[]; .key as $i | .value | acs_held($secret or ($tuple and $i == 1)))
  else false end;
# END secret-member
