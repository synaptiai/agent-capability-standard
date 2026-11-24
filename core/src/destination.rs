//! Destination policies (STANDARD v1.2 §4.4.2): which destinations a `send`
//! may reach. A policy is a list of patterns; a destination is allowed by a
//! policy when one of its patterns matches it, and by the policies in force
//! when every one of them allows it.
//!
//! A pattern is an exact destination, a prefix ending in `*` whose last
//! character before the `*` is one of `/ : @ . ? #` (and which, when it
//! starts an authority with `//`, finishes it with `/`, `?` or `#`), or a
//! suffix starting with `*@` or `*.`, where what the `*` covers may hold
//! only ASCII letters, digits, `.`, `-`, `_` and `+`. Strings compare by
//! code point, with no case folding or Unicode normalisation. The vectors
//! are `tests/conformance/destinations/match.json`.

/// A checked pattern.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Pattern {
    Exact(String),
    /// What the destination starts with (the pattern without its `*`).
    Prefix(String),
    /// What the destination ends with (the pattern without its `*`).
    Suffix(String),
}

impl Pattern {
    /// Whether the pattern matches `destination`.
    pub fn matches(&self, destination: &str) -> bool {
        match self {
            Pattern::Exact(e) => destination == e,
            Pattern::Prefix(p) => destination.starts_with(p.as_str()),
            Pattern::Suffix(s) => {
                destination.len() > s.len()
                    && destination.ends_with(s.as_str())
                    // A char boundary: `s` is a whole str at the end.
                    && destination[..destination.len() - s.len()]
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b'_' | b'+'))
            }
        }
    }
}

/// Characters a prefix pattern may end with before its `*`.
const PREFIX_ENDS: &[char] = &['/', ':', '@', '.', '?', '#'];

/// Check one pattern (§4.4.2). `Err` says which form was expected.
pub fn check_pattern(p: &str) -> Result<Pattern, String> {
    if p.is_empty() {
        return Err("a pattern is not empty".into());
    }
    let stars = p.matches('*').count();
    if stars == 0 {
        return Ok(Pattern::Exact(p.to_string()));
    }
    if stars > 1 {
        return Err(format!(
            "'{p}' has more than one '*'; a pattern is exact, a prefix ending in '*' or a suffix starting with '*'"
        ));
    }
    if let Some(prefix) = p.strip_suffix('*') {
        let Some(last) = prefix.chars().last() else {
            return Err(
                "'*' alone allows every destination; name a prefix such as https:* or https://hooks.example.com/*".into(),
            );
        };
        if !PREFIX_ENDS.contains(&last) {
            return Err(format!(
                "the prefix of '{p}' must end with one of / : @ . ? # before its '*', as in https://hooks.example.com/*"
            ));
        }
        if let Some(i) = prefix.find("//")
            && !prefix[i + 2..].contains(['/', '?', '#'])
        {
            return Err(format!(
                "the prefix of '{p}' starts an authority it does not finish: put '/', '?' or '#' after the host, as in https://hooks.example.com/*"
            ));
        }
        return Ok(Pattern::Prefix(prefix.to_string()));
    }
    if let Some(suffix) = p.strip_prefix('*') {
        if suffix.chars().count() < 2 || !(suffix.starts_with('@') || suffix.starts_with('.')) {
            return Err(format!(
                "the suffix of '{p}' must start with '@' or '.' and name something after it, as in *@example.com or *.example.com"
            ));
        }
        return Ok(Pattern::Suffix(suffix.to_string()));
    }
    Err(format!(
        "'{p}' has a '*' in the middle; a pattern is exact, a prefix ending in '*' or a suffix starting with '*'"
    ))
}

/// A checked destination policy.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Policy {
    patterns: Vec<Pattern>,
}

impl Policy {
    /// Check every pattern. `Err` lists each invalid one with its index.
    pub fn parse<S: AsRef<str>>(patterns: &[S]) -> Result<Policy, Vec<(usize, String)>> {
        let mut ok = Vec::with_capacity(patterns.len());
        let mut errors = Vec::new();
        for (i, p) in patterns.iter().enumerate() {
            match check_pattern(p.as_ref()) {
                Ok(q) => ok.push(q),
                Err(e) => errors.push((i, e)),
            }
        }
        if errors.is_empty() {
            Ok(Policy { patterns: ok })
        } else {
            Err(errors)
        }
    }

    /// Whether one of the policy's patterns matches. An empty policy allows
    /// nothing.
    pub fn allows(&self, destination: &str) -> bool {
        self.patterns.iter().any(|p| p.matches(destination))
    }
}

/// The first invalid pattern of any policy, as "policy i, pattern j: …".
pub fn check_policies(policies: &[Vec<String>]) -> Result<(), String> {
    for (i, policy) in policies.iter().enumerate() {
        for (j, p) in policy.iter().enumerate() {
            check_pattern(p).map_err(|e| format!("policy {i}, pattern {j}: {e}"))?;
        }
    }
    Ok(())
}

/// Whether every policy allows `destination` (none in force: allowed). An
/// invalid pattern matches nothing, so it fails closed; callers refuse
/// invalid policies when they load them.
pub fn allowed(policies: &[Vec<String>], destination: &str) -> bool {
    policies.iter().all(|policy| {
        policy
            .iter()
            .any(|p| check_pattern(p).is_ok_and(|q| q.matches(destination)))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    #[test]
    fn vectors() {
        let text = include_str!("../../tests/conformance/destinations/match.json");
        // Non-ASCII characters are escapes, so the NFC and NFD forms stay
        // distinct in the file.
        assert!(text.is_ascii());
        let doc: Value = serde_json::from_str(text).unwrap();
        let patterns = doc["patterns"].as_array().unwrap();
        assert!(!patterns.is_empty());
        for case in patterns {
            let p = case["pattern"].as_str().unwrap();
            let valid = case["valid"].as_bool().unwrap();
            assert_eq!(check_pattern(p).is_ok(), valid, "{p:?}");
            assert_eq!(Policy::parse(&[p]).is_ok(), valid, "{p:?}");
            assert_eq!(
                check_policies(&[vec![p.to_string()]]).is_ok(),
                valid,
                "{p:?}"
            );
        }
        let matches = doc["matches"].as_array().unwrap();
        assert!(!matches.is_empty());
        for case in matches {
            let policies: Vec<Vec<String>> =
                serde_json::from_value(case["policies"].clone()).unwrap();
            let d = case["destination"].as_str().unwrap();
            let expected = case["allowed"].as_bool().unwrap();
            assert_eq!(allowed(&policies, d), expected, "{policies:?} {d:?}");
            let parsed: Vec<Policy> = policies.iter().map(|p| Policy::parse(p).unwrap()).collect();
            assert_eq!(
                parsed.iter().all(|p| p.allows(d)),
                expected,
                "{policies:?} {d:?}"
            );
        }
    }

    #[test]
    fn errors_name_each_invalid_pattern() {
        let e = Policy::parse(&["ops", "*", "a*b", "https://x.example/*"]).unwrap_err();
        assert_eq!(e.iter().map(|(i, _)| *i).collect::<Vec<_>>(), [1, 2]);
        let e = check_policies(&[vec!["ok".into()], vec!["ok".into(), "**".into()]]).unwrap_err();
        assert!(e.starts_with("policy 1, pattern 1: "), "{e}");
        // An invalid pattern allows nothing.
        assert!(!allowed(&[vec!["*".into()]], "anything"));
    }
}
