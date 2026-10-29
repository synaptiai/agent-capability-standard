//! Canonical JSON (RFC 8785, JCS) and the digests built on it: approval
//! bindings (STANDARD v1.1 §5.14) and run snapshots (design-114 §16.5).

use std::fmt::Write as _;

use hmac::{Hmac, Mac};
use serde_json::Value;
use sha2::{Digest, Sha256};

/// The RFC 8785 serialization of `value`: object members sorted by their
/// UTF-16 code units, no insignificant whitespace, numbers as ECMAScript
/// prints them. Iterative, so deep values cannot exhaust the stack.
pub fn canonical(value: &Value) -> String {
    enum Item<'a> {
        Value(&'a Value),
        Text(&'static str),
        Key(&'a str),
    }
    let mut out = String::new();
    let mut stack = vec![Item::Value(value)];
    while let Some(item) = stack.pop() {
        match item {
            Item::Text(t) => out.push_str(t),
            Item::Key(k) => {
                string(k, &mut out);
                out.push(':');
            }
            Item::Value(v) => match v {
                Value::Null => out.push_str("null"),
                Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
                Value::Number(n) => out.push_str(&number(n)),
                Value::String(s) => string(s, &mut out),
                Value::Array(a) => {
                    out.push('[');
                    stack.push(Item::Text("]"));
                    for (i, x) in a.iter().enumerate().rev() {
                        stack.push(Item::Value(x));
                        if i > 0 {
                            stack.push(Item::Text(","));
                        }
                    }
                }
                Value::Object(m) => {
                    out.push('{');
                    stack.push(Item::Text("}"));
                    let mut keys: Vec<&String> = m.keys().collect();
                    keys.sort_by(|a, b| a.encode_utf16().cmp(b.encode_utf16()));
                    for (i, k) in keys.iter().enumerate().rev() {
                        stack.push(Item::Value(&m[k.as_str()]));
                        stack.push(Item::Key(k));
                        if i > 0 {
                            stack.push(Item::Text(","));
                        }
                    }
                }
            },
        }
    }
    out
}

/// A JSON string as ECMAScript's `JSON.stringify` writes it.
fn string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

/// A number as ECMAScript's `Number.prototype.toString` prints its binary64
/// value (RFC 8785 §3.2.2.3), ties between equally short forms included.
fn number(n: &serde_json::Number) -> String {
    let x = n.as_f64().unwrap_or(0.0);
    if x == 0.0 {
        return "0".into();
    }
    ryu_js::Buffer::new().format_finite(x).to_string()
}

/// SHA-256 of `text`, as lowercase hex.
pub fn sha256_hex(text: &str) -> String {
    hex(&Sha256::digest(text.as_bytes()))
}

/// SHA-256 (hex) of the canonical JSON of `value`.
pub fn digest(value: &Value) -> String {
    sha256_hex(&canonical(value))
}

/// HMAC-SHA-256 of `text` under `key`, as lowercase hex.
pub fn hmac_hex(key: &[u8], text: &str) -> String {
    // HMAC takes keys of any length.
    let mut mac = Hmac::<Sha256>::new_from_slice(key).expect("HMAC accepts any key length");
    mac.update(text.as_bytes());
    hex(&mac.finalize().into_bytes())
}

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        let _ = write!(s, "{b:02x}");
    }
    s
}

/// Compare two hex digests, ignoring case, in time independent of where
/// they differ.
pub fn same_digest(a: &str, b: &str) -> bool {
    a.len() == b.len()
        && a.bytes().zip(b.bytes()).fold(0u8, |acc, (x, y)| {
            acc | (x.to_ascii_lowercase() ^ y.to_ascii_lowercase())
        }) == 0
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn rfc8785_examples() {
        // RFC 8785 §3.2.3 sorting example (keys by UTF-16 code units).
        let v: Value = serde_json::from_str(
            r#"{"€": "Euro Sign", "\r": "Carriage Return", "דּ": "Hebrew Letter Dalet With Dagesh", "1": "One", "😀": "Emoji: Grinning Face", "\u0080": "Control", "ö": "Latin Small Letter O With Diaeresis"}"#,
        )
        .unwrap();
        let order: Vec<String> = canonical(&v)
            .split("\":\"")
            .skip(1)
            .map(|s| s.split('"').next().unwrap().to_string())
            .collect();
        assert_eq!(
            order,
            [
                "Carriage Return",
                "One",
                "Control",
                "Latin Small Letter O With Diaeresis",
                "Euro Sign",
                "Emoji: Grinning Face",
                "Hebrew Letter Dalet With Dagesh"
            ]
        );
        assert_eq!(
            canonical(&json!({"b": [1, true, null], "a": "x\ny\u{1}"})),
            r#"{"a":"x\ny\u0001","b":[1,true,null]}"#
        );
    }

    #[test]
    fn numbers_print_as_ecmascript() {
        let cases: &[(f64, &str)] = &[
            (0.0, "0"),
            (-0.0, "0"),
            (1.0, "1"),
            (-1.5, "-1.5"),
            (1e21, "1e+21"),
            (1e20, "100000000000000000000"),
            (123456789012345680000.0, "123456789012345680000"),
            (0.000001, "0.000001"),
            (0.0000001, "1e-7"),
            (1.5e-7, "1.5e-7"),
            (5e-324, "5e-324"),
            (1.7976931348623157e308, "1.7976931348623157e+308"),
            (333333333.3333333, "333333333.3333333"),
            (9007199254740992.0, "9007199254740992"),
            // Ties: ECMAScript picks the even digit (node 20 output).
            (78229954655726.0 + 0.125, "78229954655726.12"),
            (-(850188129030802.0 + 0.25), "-850188129030802.2"),
        ];
        for (x, want) in cases {
            let n = serde_json::Number::from_f64(*x).unwrap();
            assert_eq!(number(&n), *want, "{x}");
        }
        assert_eq!(canonical(&json!(10)), "10");
    }

    #[test]
    fn digests() {
        assert_eq!(
            sha256_hex(""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        // RFC 4231 test case 2.
        assert_eq!(
            hmac_hex(b"Jefe", "what do ya want for nothing?"),
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        );
        assert_eq!(
            digest(&json!({"b": 1, "a": 2})),
            digest(&json!({"a": 2, "b": 1}))
        );
        assert!(same_digest("ab", "ab"));
        assert!(!same_digest("ab", "ac"));
        assert!(!same_digest("ab", "abc"));
        assert!(same_digest("AB", "ab"));
    }
}
