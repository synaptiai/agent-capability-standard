//! Binding references: `${root.path[0][1:3]: type}` (STANDARD §5.3).

use std::fmt;

/// One path segment after the root.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Seg {
    Field(String),
    Index(usize),
    Slice(Option<usize>, Option<usize>),
}

impl fmt::Display for Seg {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Seg::Field(n) => write!(f, ".{n}"),
            Seg::Index(i) => write!(f, "[{i}]"),
            Seg::Slice(a, b) => {
                let s = |x: &Option<usize>| x.map(|v| v.to_string()).unwrap_or_default();
                write!(f, "[{}:{}]", s(a), s(b))
            }
        }
    }
}

/// A parsed reference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ref {
    /// The text between `${` and `}`, as written.
    pub raw: String,
    pub root: String,
    pub path: Vec<Seg>,
    /// The type annotation text after `:`, if any (validated by `types`).
    pub annotation: Option<String>,
}

impl Ref {
    /// The path after the root, as written (`a.b[0]` → `b[0]`).
    pub fn path_text(&self) -> String {
        let s: String = self.path.iter().map(Seg::to_string).collect();
        s.strip_prefix('.').map(str::to_string).unwrap_or(s)
    }
}

/// Why a `${...}` body does not parse. `annotation` marks an annotation that
/// names no type (B205); anything else is a malformed reference.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RefError {
    pub msg: String,
    pub annotation: bool,
}

impl RefError {
    fn path(msg: String) -> Self {
        Self {
            msg,
            annotation: false,
        }
    }
}

impl std::fmt::Display for RefError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.msg)
    }
}

/// A `${...}` occurrence in a string: byte span and parse result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RefMatch {
    pub start: usize,
    pub end: usize,
    pub parsed: Result<Ref, RefError>,
}

/// Every `${...}` in `s`, left to right. An unterminated `${` is reported as a
/// match that runs to the end of the string.
pub fn find_refs(s: &str) -> Vec<RefMatch> {
    let mut out = Vec::new();
    let mut i = 0;
    while let Some(off) = s[i..].find("${") {
        let start = i + off;
        let body_start = start + 2;
        match s[body_start..].find('}') {
            Some(close) => {
                let end = body_start + close + 1;
                out.push(RefMatch {
                    start,
                    end,
                    parsed: parse_ref(&s[body_start..body_start + close]),
                });
                i = end;
            }
            None => {
                out.push(RefMatch {
                    start,
                    end: s.len(),
                    parsed: Err(RefError::path(format!(
                        "unterminated reference '{}'",
                        &s[start..]
                    ))),
                });
                break;
            }
        }
    }
    out
}

fn is_ident_start(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_'
}

/// Identifier characters after the first. `-` is accepted because the v1.0
/// validator accepted any store name without `.`, and hyphenated names occur.
fn is_ident(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '-'
}

/// Whether `s` is a valid reference identifier (store, input or field name).
pub fn is_identifier(s: &str) -> bool {
    let mut chars = s.chars();
    chars.next().is_some_and(is_ident_start) && chars.all(is_ident)
}

/// Parse the text inside `${...}`.
pub fn parse_ref(body: &str) -> Result<Ref, RefError> {
    let raw = body.to_string();
    // The annotation starts at the first ':' outside brackets (slices use ':').
    let mut depth = 0i32;
    let mut split = None;
    for (idx, c) in body.char_indices() {
        match c {
            '[' => depth += 1,
            ']' => depth -= 1,
            ':' if depth == 0 => {
                split = Some(idx);
                break;
            }
            _ => {}
        }
    }
    let (path_part, annotation) = match split {
        Some(idx) => {
            let ann = body[idx + 1..].trim();
            if ann.is_empty() {
                return Err(RefError {
                    msg: format!("empty type annotation in '${{{raw}}}'"),
                    annotation: true,
                });
            }
            (&body[..idx], Some(ann.to_string()))
        }
        None => (body, None),
    };
    let p = path_part.trim();
    let bad = |why: &str| {
        Err(RefError::path(format!(
            "malformed reference '${{{raw}}}': {why}"
        )))
    };
    let mut chars = p.char_indices().peekable();
    let root_end = match chars.peek() {
        Some(&(_, c)) if is_ident_start(c) => {
            let mut end = p.len();
            for (i, c) in p.char_indices() {
                if !is_ident(c) {
                    end = i;
                    break;
                }
            }
            end
        }
        _ => return bad("expected an identifier"),
    };
    let root = p[..root_end].to_string();
    let mut path = Vec::new();
    let mut rest = &p[root_end..];
    while !rest.is_empty() {
        if let Some(r) = rest.strip_prefix('.') {
            let end = r.find(|c: char| !is_ident(c)).unwrap_or(r.len());
            let name = &r[..end];
            if name.is_empty() || !name.starts_with(is_ident_start) {
                return bad("expected a field name after '.'");
            }
            path.push(Seg::Field(name.to_string()));
            rest = &r[end..];
        } else if let Some(r) = rest.strip_prefix('[') {
            let Some(close) = r.find(']') else {
                return bad("unclosed '['");
            };
            let inner = &r[..close];
            let num = |t: &str| -> Result<Option<usize>, RefError> {
                if t.is_empty() {
                    return Ok(None);
                }
                if !t.bytes().all(|b| b.is_ascii_digit()) {
                    return Err(RefError::path(format!(
                        "malformed reference '${{{raw}}}': bad index '{t}'"
                    )));
                }
                if t.len() > 1 && t.starts_with('0') {
                    return Err(RefError::path(format!(
                        "malformed reference '${{{raw}}}': leading zeros in index '{t}'"
                    )));
                }
                t.parse::<usize>().map(Some).map_err(|_| {
                    RefError::path(format!("malformed reference '${{{raw}}}': index too large"))
                })
            };
            match inner.split_once(':') {
                Some((a, b)) => path.push(Seg::Slice(num(a)?, num(b)?)),
                None => match num(inner)? {
                    Some(n) => path.push(Seg::Index(n)),
                    None => return bad("empty index"),
                },
            }
            rest = &r[close + 1..];
        } else {
            return bad(&format!("unexpected '{rest}'"));
        }
    }
    Ok(Ref {
        raw,
        root,
        path,
        annotation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn r(s: &str) -> Ref {
        parse_ref(s).unwrap()
    }

    #[test]
    fn parses_paths_and_annotations() {
        let x = r("a_out.b.c: array<object>");
        assert_eq!(x.root, "a_out");
        assert_eq!(x.path, [Seg::Field("b".into()), Seg::Field("c".into())]);
        assert_eq!(x.annotation.as_deref(), Some("array<object>"));
        assert_eq!(r("x:number").annotation.as_deref(), Some("number"));
        assert_eq!(r(" x.y ").root, "x");
        assert!(parse_ref("x . y").is_err());
    }

    #[test]
    fn parses_index_and_slices() {
        let x = r("s.labels[0][1:3][:2][4:]");
        assert_eq!(
            x.path,
            [
                Seg::Field("labels".into()),
                Seg::Index(0),
                Seg::Slice(Some(1), Some(3)),
                Seg::Slice(None, Some(2)),
                Seg::Slice(Some(4), None)
            ]
        );
        assert_eq!(x.path_text(), "labels[0][1:3][:2][4:]");
        assert_eq!(
            r("s.items[0:5]: array<object>").annotation.as_deref(),
            Some("array<object>")
        );
    }

    #[test]
    fn rejects_malformed() {
        assert_eq!(r("s-1.x-y").path, [Seg::Field("x-y".into())]);
        assert!(is_identifier("a_b-c") && !is_identifier("-a") && !is_identifier("a.b"));
        for bad in [
            "", "1abc", "a.", "a..b", "a[", "a[x]", "a[]", "a.b c", "-a", "a:", "a[01]", "a[1:02]",
        ] {
            assert!(parse_ref(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn finds_all_refs() {
        let m = find_refs("${a} == ${b.c} && ${d");
        assert_eq!(m.len(), 3);
        assert_eq!(m[0].parsed.as_ref().unwrap().root, "a");
        assert_eq!(m[1].parsed.as_ref().unwrap().root, "b");
        assert!(m[2].parsed.is_err());
        assert!(find_refs("no refs here").is_empty());
    }
}
