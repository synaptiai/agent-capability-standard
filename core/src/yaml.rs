//! Hardened YAML 1.2 loading into JSON values.
//!
//! The core reads workflow catalogs, the ontology and schema files itself, so
//! it carries the same guards as `grounded_agency/utils/safe_yaml.py`: a file
//! size limit and refusal to follow symlinks. Because it builds values
//! directly from parser events it also bounds what PyYAML does not: nesting
//! depth, and the memory that anchors and aliases can multiply.
//!
//! Only JSON-representable documents are accepted: mapping keys must be
//! strings, keys must be unique (YAML 1.2), numbers must be finite and fit in
//! 64 bits, and tags other than the core schema and the non-specific `!` are
//! rejected.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};
use std::fmt;
use std::io::{ErrorKind, Read};
use std::path::Path;

use saphyr::{Scalar, parse_core_schema_fp};
use saphyr_parser::{Event, Parser, ScalarStyle, Span, SpannedEventReceiver, Tag};
use serde_json::{Map, Number, Value};

/// Default size limit for YAML files (1 MiB), as `safe_yaml.DEFAULT_MAX_BYTES`.
pub const DEFAULT_MAX_BYTES: u64 = 1024 * 1024;
/// Size limit for the ontology and catalogs (10 MiB), as `safe_yaml.ONTOLOGY_MAX_BYTES`.
pub const ONTOLOGY_MAX_BYTES: u64 = 10 * 1024 * 1024;
/// Maximum nesting depth of collections, including collections spliced in by aliases.
pub const MAX_DEPTH: usize = 128;
/// Budget, per document, for data copied because of anchors and aliases.
///
/// Weight is one unit per node plus one per byte of string content (keys
/// included), so both node fan-out ("billion laughs") and one large scalar
/// aliased many times are bounded. Only anchors that some alias references are
/// ever copied.
pub const MAX_ALIAS_WEIGHT: usize = 1_000_000;

/// Why a YAML file or string could not be loaded.
#[derive(Debug, Clone, PartialEq)]
pub enum YamlError {
    NotFound(String),
    Symlink(String),
    TooLarge {
        path: String,
        size: u64,
        max: u64,
    },
    /// An operating-system error other than the ones above.
    Io {
        message: String,
        kind: ErrorKind,
    },
    /// Malformed YAML or a document outside the accepted subset.
    Parse {
        message: String,
        line: usize,
        col: usize,
    },
}

impl fmt::Display for YamlError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            YamlError::NotFound(p) => write!(f, "file not found: {p}"),
            YamlError::Symlink(p) => write!(f, "refusing to follow symlink: {p}"),
            YamlError::TooLarge { path, size, max } => write!(
                f,
                "YAML file exceeds size limit: {path} is {size} bytes (limit: {max} bytes)"
            ),
            YamlError::Io { message, .. } => write!(f, "{message}"),
            YamlError::Parse { message, line, col } => {
                write!(f, "{message} at line {line} column {col}")
            }
        }
    }
}

impl std::error::Error for YamlError {}

fn io_error(shown: &str, e: &std::io::Error) -> YamlError {
    YamlError::Io {
        message: format!("{shown}: {e}"),
        kind: e.kind(),
    }
}

/// Load a single-document YAML file with the size and symlink guards.
pub fn load_file(path: &Path, max_bytes: u64) -> Result<Value, YamlError> {
    let text = read_guarded(path, max_bytes)?;
    load_str(&text)
}

/// Read a file as UTF-8, refusing symlinks and files over `max_bytes`.
pub fn read_guarded(path: &Path, max_bytes: u64) -> Result<String, YamlError> {
    let shown = path.display().to_string();
    let mut file = open_no_follow(path)?;
    let meta = file.metadata().map_err(|e| io_error(&shown, &e))?;
    if meta.is_dir() {
        return Err(YamlError::Io {
            message: format!("{shown}: is a directory"),
            kind: ErrorKind::IsADirectory,
        });
    }
    if meta.len() > max_bytes {
        return Err(YamlError::TooLarge {
            path: shown,
            size: meta.len(),
            max: max_bytes,
        });
    }
    let mut buf = String::new();
    // Read at most one byte past the limit, so a file that grows between the
    // size check and the read cannot slip through.
    file.by_ref()
        .take(max_bytes.saturating_add(1))
        .read_to_string(&mut buf)
        .map_err(|e| io_error(&shown, &e))?;
    if buf.len() as u64 > max_bytes {
        return Err(YamlError::TooLarge {
            path: shown,
            size: buf.len() as u64,
            max: max_bytes,
        });
    }
    Ok(buf)
}

#[cfg(unix)]
fn open_no_follow(path: &Path) -> Result<std::fs::File, YamlError> {
    use std::os::unix::fs::OpenOptionsExt;
    let shown = path.display().to_string();
    std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|e| match e.raw_os_error() {
            Some(libc::ELOOP) => YamlError::Symlink(shown.clone()),
            _ if e.kind() == ErrorKind::NotFound => YamlError::NotFound(shown.clone()),
            _ => io_error(&shown, &e),
        })
}

#[cfg(not(unix))]
fn open_no_follow(path: &Path) -> Result<std::fs::File, YamlError> {
    let shown = path.display().to_string();
    match std::fs::symlink_metadata(path) {
        Ok(m) if m.file_type().is_symlink() => return Err(YamlError::Symlink(shown)),
        Err(e) if e.kind() == ErrorKind::NotFound => return Err(YamlError::NotFound(shown)),
        _ => {}
    }
    std::fs::File::open(path).map_err(|e| io_error(&shown, &e))
}

/// Parse a YAML string holding at most one document. An empty stream is `null`.
pub fn load_str(text: &str) -> Result<Value, YamlError> {
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);

    // Pass 1: which anchors does any alias use? Only those are ever copied.
    let mut scan = AliasScan::default();
    feed(text, &mut scan)?;

    // Pass 2: build the values.
    let mut builder = Builder {
        referenced: scan.referenced,
        ..Builder::default()
    };
    feed(text, &mut builder)?;
    if let Some(err) = builder.error {
        return Err(err);
    }
    match builder.docs.len() {
        0 => Ok(Value::Null),
        1 => Ok(builder.docs.pop().unwrap_or(Value::Null)),
        n => Err(YamlError::Parse {
            message: format!("expected a single document, found {n}"),
            line: 1,
            col: 1,
        }),
    }
}

/// Pass the parser's events to `recv`, one at a time. saphyr's own `load`
/// recurses once per nesting level, so a deeply nested input could overflow
/// the stack before any limit is checked; here the depth is counted as the
/// events arrive and the parse stops at `MAX_DEPTH`.
fn feed<'a, R: SpannedEventReceiver<'a>>(text: &'a str, recv: &mut R) -> Result<(), YamlError> {
    let mut depth = 0usize;
    for item in Parser::new_from_str(text) {
        let (ev, span) = item.map_err(scan_error)?;
        match ev {
            Event::SequenceStart(..) | Event::MappingStart(..) => {
                depth += 1;
                if depth > MAX_DEPTH {
                    return Err(YamlError::Parse {
                        message: format!("nesting deeper than {MAX_DEPTH} levels"),
                        line: span.start.line(),
                        col: span.start.col() + 1,
                    });
                }
            }
            Event::SequenceEnd | Event::MappingEnd => depth = depth.saturating_sub(1),
            _ => {}
        }
        recv.on_event(ev, span);
    }
    Ok(())
}

fn scan_error(e: saphyr_parser::ScanError) -> YamlError {
    let m = e.marker();
    YamlError::Parse {
        message: e.info().to_string(),
        line: m.line(),
        col: m.col() + 1,
    }
}

#[derive(Default)]
struct AliasScan {
    referenced: HashSet<usize>,
}

impl<'input> SpannedEventReceiver<'input> for AliasScan {
    fn on_event(&mut self, ev: Event<'input>, _span: Span) {
        if let Event::Alias(id) = ev {
            self.referenced.insert(id);
        }
    }
}

enum Frame {
    Seq {
        items: Vec<Value>,
        anchor: usize,
    },
    Map {
        map: Map<String, Value>,
        key: Option<String>,
        anchor: usize,
    },
}

#[derive(Default)]
struct Builder {
    stack: Vec<Frame>,
    docs: Vec<Value>,
    referenced: HashSet<usize>,
    anchors: HashMap<usize, Value>,
    alias_weight: usize,
    error: Option<YamlError>,
}

/// A tag's meaning for scalar and collection resolution.
enum TagKind<'a> {
    None,
    /// The non-specific tag `!`: a string (YAML 1.2 §6.9.1).
    NonSpecific,
    /// A core-schema tag, by suffix (`str`, `int`, `map`, ...).
    Core(&'a str),
    Other(String),
}

const CORE_PREFIX: &str = "tag:yaml.org,2002:";

fn classify<'a>(tag: Option<&'a Tag>) -> TagKind<'a> {
    let Some(t) = tag else {
        return TagKind::None;
    };
    // saphyr reports `!` as an empty handle with suffix `!`.
    if (t.handle.is_empty() && t.suffix == "!") || (t.handle == "!" && t.suffix.is_empty()) {
        return TagKind::NonSpecific;
    }
    if t.is_yaml_core_schema() {
        return TagKind::Core(t.suffix.as_str());
    }
    // The verbatim form `!<tag:yaml.org,2002:str>` names the same tag as `!!str`.
    if t.handle.is_empty() {
        if let Some(rest) = t.suffix.strip_prefix(CORE_PREFIX) {
            return TagKind::Core(rest);
        }
    }
    TagKind::Other(format!("{}{}", t.handle, t.suffix))
}

fn is_decimal_int(s: &str) -> bool {
    let digits = s.strip_prefix(['-', '+']).unwrap_or(s);
    !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit())
}

/// A YAML 1.2 core-schema integer: decimal, `0x` hex or `0o` octal.
fn core_int(s: &str) -> Option<Result<Number, String>> {
    if is_decimal_int(s) {
        let n = s.parse::<i64>().map(Number::from).or_else(|_| {
            s.strip_prefix('+')
                .unwrap_or(s)
                .parse::<u64>()
                .map(Number::from)
        });
        return Some(n.map_err(|_| format!("integer '{s}' does not fit in 64 bits")));
    }
    let (radix, body) = match s.strip_prefix("0x") {
        Some(h) => (16, h),
        None => (8, s.strip_prefix("0o")?),
    };
    if body.is_empty() || !body.chars().all(|c| c.is_digit(radix)) {
        return None;
    }
    Some(
        i64::from_str_radix(body, radix)
            .map(Number::from)
            .or_else(|_| u64::from_str_radix(body, radix).map(Number::from))
            .map_err(|_| format!("integer '{s}' does not fit in 64 bits")),
    )
}

fn finite(f: f64, shown: &str) -> Result<Value, String> {
    Number::from_f64(f)
        .map(Value::Number)
        .ok_or_else(|| format!("non-finite float '{shown}' is not representable"))
}

/// Resolve one scalar to a JSON value under the YAML 1.2 core schema.
fn resolve_scalar(v: &str, style: ScalarStyle, tag: TagKind<'_>) -> Result<Value, String> {
    match tag {
        TagKind::Other(t) => Err(format!("unsupported YAML tag '{t}'")),
        TagKind::NonSpecific => Ok(Value::String(v.to_owned())),
        // An explicit core tag decides the type whatever the quoting style.
        TagKind::Core(suffix) => match suffix {
            "str" => Ok(Value::String(v.to_owned())),
            "null" => match v {
                "" | "~" | "null" | "Null" | "NULL" => Ok(Value::Null),
                _ => Err(format!("scalar '{v}' does not match tag !!null")),
            },
            "bool" => match v {
                "true" | "True" | "TRUE" => Ok(Value::Bool(true)),
                "false" | "False" | "FALSE" => Ok(Value::Bool(false)),
                _ => Err(format!("scalar '{v}' does not match tag !!bool")),
            },
            "int" => match core_int(v) {
                Some(n) => n.map(Value::Number),
                None => Err(format!("scalar '{v}' does not match tag !!int")),
            },
            "float" => match core_int(v) {
                // An integer written under !!float is that number as a float.
                Some(Ok(n)) => finite(n.as_f64().unwrap_or(f64::NAN), v),
                Some(Err(e)) => Err(e),
                None => match parse_core_schema_fp(v) {
                    Some(f) => finite(f, v),
                    None => Err(format!("scalar '{v}' does not match tag !!float")),
                },
            },
            other => Err(format!("tag !!{other} cannot apply to a scalar")),
        },
        TagKind::None => {
            if style != ScalarStyle::Plain {
                return Ok(Value::String(v.to_owned()));
            }
            if v.is_empty() {
                return Ok(Value::Null);
            }
            // Integers are resolved here so that values beyond i64 stay exact
            // (or fail) instead of degrading to a float.
            if let Some(n) = core_int(v) {
                return n.map(Value::Number);
            }
            match Scalar::parse_from_cow(Cow::Borrowed(v)) {
                Scalar::Null => Ok(Value::Null),
                Scalar::Boolean(b) => Ok(Value::Bool(b)),
                Scalar::Integer(i) => Ok(Value::Number(i.into())),
                Scalar::FloatingPoint(f) => finite(f.into_inner(), v),
                Scalar::String(s) => Ok(Value::String(s.into_owned())),
            }
        }
    }
}

/// Nesting depth of a value (a scalar is 0, `[]` is 1) and its copy weight.
fn depth_and_weight(v: &Value) -> (usize, usize) {
    let mut max_depth = 0;
    let mut weight = 0;
    let mut stack = vec![(v, 0usize)];
    while let Some((v, d)) = stack.pop() {
        weight += 1;
        match v {
            Value::String(s) => weight += s.len(),
            Value::Array(a) => {
                max_depth = max_depth.max(d + 1);
                stack.extend(a.iter().map(|x| (x, d + 1)));
            }
            Value::Object(m) => {
                max_depth = max_depth.max(d + 1);
                for (k, x) in m {
                    weight += k.len();
                    stack.push((x, d + 1));
                }
            }
            _ => {}
        }
    }
    (max_depth, weight)
}

impl Builder {
    fn fail(&mut self, message: impl Into<String>, span: Span) {
        if self.error.is_none() {
            self.error = Some(YamlError::Parse {
                message: message.into(),
                line: span.start.line(),
                col: span.start.col() + 1,
            });
        }
    }

    fn charge(&mut self, weight: usize, span: Span) -> bool {
        self.alias_weight = self.alias_weight.saturating_add(weight);
        if self.alias_weight > MAX_ALIAS_WEIGHT {
            self.fail(
                format!("anchors and aliases copy more than {MAX_ALIAS_WEIGHT} weight units"),
                span,
            );
            return false;
        }
        true
    }

    /// Attach a finished node to its parent (or emit it as a document).
    fn complete(&mut self, value: Value, anchor: usize, span: Span) {
        if anchor > 0 && self.referenced.contains(&anchor) {
            let (_, weight) = depth_and_weight(&value);
            if !self.charge(weight, span) {
                return;
            }
            self.anchors.insert(anchor, value.clone());
        }
        match self.stack.last_mut() {
            None => self.docs.push(value),
            Some(Frame::Seq { items, .. }) => items.push(value),
            Some(Frame::Map { map, key, .. }) => match key.take() {
                Some(k) => {
                    map.insert(k, value);
                }
                None => match value {
                    Value::String(k) => {
                        if map.contains_key(&k) {
                            self.fail(format!("duplicate mapping key '{k}'"), span);
                        } else {
                            *key = Some(k);
                        }
                    }
                    other => self.fail(
                        format!("mapping keys must be strings, found {}", kind_of(&other)),
                        span,
                    ),
                },
            },
        }
    }

    fn open(&mut self, frame: Frame, tag: Option<&Tag>, expected: &str, span: Span) {
        match classify(tag) {
            TagKind::None | TagKind::NonSpecific => {}
            TagKind::Core(suffix) if suffix == expected => {}
            TagKind::Core(suffix) => {
                return self.fail(format!("tag !!{suffix} cannot apply to a {expected}"), span);
            }
            TagKind::Other(t) => return self.fail(format!("unsupported YAML tag '{t}'"), span),
        }
        if self.stack.len() >= MAX_DEPTH {
            return self.fail(format!("nesting deeper than {MAX_DEPTH} levels"), span);
        }
        self.stack.push(frame);
    }

    fn alias(&mut self, id: usize, span: Span) {
        let Some(value) = self.anchors.get(&id) else {
            return self.fail("alias to an unknown anchor", span);
        };
        let (depth, weight) = depth_and_weight(value);
        if self.stack.len() + depth > MAX_DEPTH {
            return self.fail(
                format!("alias would nest deeper than {MAX_DEPTH} levels"),
                span,
            );
        }
        let value = value.clone();
        if self.charge(weight, span) {
            self.complete(value, 0, span);
        }
    }
}

impl<'input> SpannedEventReceiver<'input> for Builder {
    fn on_event(&mut self, ev: Event<'input>, span: Span) {
        if self.error.is_some() {
            return;
        }
        match ev {
            Event::Nothing | Event::StreamStart | Event::StreamEnd | Event::DocumentStart(_) => {}
            Event::DocumentEnd => {
                self.anchors.clear();
                self.alias_weight = 0;
            }
            Event::Scalar(v, style, anchor, tag) => {
                match resolve_scalar(&v, style, classify(tag.as_deref())) {
                    Ok(value) => self.complete(value, anchor, span),
                    Err(message) => self.fail(message, span),
                }
            }
            Event::SequenceStart(anchor, tag) => {
                let frame = Frame::Seq {
                    items: Vec::new(),
                    anchor,
                };
                self.open(frame, tag.as_deref(), "seq", span);
            }
            Event::MappingStart(anchor, tag) => {
                let frame = Frame::Map {
                    map: Map::new(),
                    key: None,
                    anchor,
                };
                self.open(frame, tag.as_deref(), "map", span);
            }
            Event::SequenceEnd => match self.stack.pop() {
                Some(Frame::Seq { items, anchor }) => {
                    self.complete(Value::Array(items), anchor, span);
                }
                _ => self.fail("unbalanced sequence end", span),
            },
            Event::MappingEnd => match self.stack.pop() {
                Some(Frame::Map {
                    map,
                    key: None,
                    anchor,
                }) => self.complete(Value::Object(map), anchor, span),
                _ => self.fail("unbalanced mapping end", span),
            },
            Event::Alias(id) => self.alias(id, span),
        }
    }
}

/// A short name for a value's JSON kind, for messages.
pub fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn err(text: &str) -> String {
        load_str(text).unwrap_err().to_string()
    }

    #[test]
    fn loads_core_schema_scalars() {
        let v = load_str(
            "a: 1\nb: 1.5\nc: true\nd: null\ne: ~\nf: text\ng: '1'\nh: 0x10\ni: 0o17\nj:\n",
        )
        .unwrap();
        assert_eq!(
            v,
            json!({"a": 1, "b": 1.5, "c": true, "d": null, "e": null, "f": "text", "g": "1",
                   "h": 16, "i": 15, "j": null})
        );
    }

    #[test]
    fn yaml_1_2_does_not_coerce_yes_no_on_off() {
        let v = load_str("on: yes\noff: no\n").unwrap();
        assert_eq!(v, json!({"on": "yes", "off": "no"}));
    }

    #[test]
    fn explicit_core_tags_win_over_quoting() {
        let v = load_str("a: !!int '42'\nb: !!float '1.5'\nc: !!null ''\nd: !!bool \"true\"\ne: !!null\nf: !!float 3\n")
            .unwrap();
        assert_eq!(
            v,
            json!({"a": 42, "b": 1.5, "c": null, "d": true, "e": null, "f": 3.0})
        );
    }

    #[test]
    fn verbatim_core_tags_equal_shorthand() {
        assert_eq!(
            load_str("x: !<tag:yaml.org,2002:str> 5\n").unwrap(),
            json!({"x": "5"})
        );
    }

    #[test]
    fn big_integers_stay_exact_or_fail() {
        assert_eq!(
            load_str("x: 18446744073709551615\n").unwrap(),
            json!({"x": 18446744073709551615u64})
        );
        assert!(err("x: 99999999999999999999\n").contains("does not fit in 64 bits"));
        assert!(err("x: !!int 99999999999999999999\n").contains("does not fit in 64 bits"));
    }

    #[test]
    fn preserves_key_order() {
        let v = load_str("z: 1\na: 2\nm: 3\n").unwrap();
        let keys: Vec<_> = v.as_object().unwrap().keys().cloned().collect();
        assert_eq!(keys, ["z", "a", "m"]);
    }

    #[test]
    fn empty_stream_is_null() {
        assert_eq!(load_str("").unwrap(), Value::Null);
        assert_eq!(load_str("# only a comment\n").unwrap(), Value::Null);
    }

    #[test]
    fn rejects_multiple_documents() {
        assert!(err("a: 1\n---\nb: 2\n").contains("single document"));
    }

    #[test]
    fn rejects_duplicate_keys() {
        assert!(err("a: 1\na: 2\n").contains("duplicate mapping key 'a'"));
    }

    #[test]
    fn rejects_non_string_keys() {
        assert!(err("200: ok\n").contains("mapping keys must be strings"));
        assert!(err("? [a]\n: b\n").contains("mapping keys must be strings"));
    }

    #[test]
    fn rejects_non_finite_floats() {
        assert!(err("x: .inf\n").contains("non-finite"));
        assert!(err("x: .nan\n").contains("non-finite"));
        assert!(err("x: 1e400\n").contains("non-finite"));
    }

    #[test]
    fn rejects_unknown_tags_and_accepts_non_specific() {
        assert!(err("x: !custom 5\n").contains("unsupported YAML tag"));
        assert_eq!(load_str("x: ! 5\n").unwrap(), json!({"x": "5"}));
        assert_eq!(load_str("x: !!str 5\n").unwrap(), json!({"x": "5"}));
        assert!(err("x: !!int abc\n").contains("does not match tag !!int"));
        assert!(err("x: !!map [1]\n").contains("cannot apply to a seq"));
    }

    #[test]
    fn resolves_aliases() {
        let v = load_str("a: &x [1, 2]\nb: *x\n").unwrap();
        assert_eq!(v, json!({"a": [1, 2], "b": [1, 2]}));
    }

    #[test]
    fn bounds_alias_fan_out() {
        let mut doc = String::from("a0: &a0 [x, x, x, x, x, x, x, x, x, x]\n");
        for i in 1..8 {
            let prev = format!("*a{}", i - 1);
            doc.push_str(&format!(
                "a{i}: &a{i} [{}]\n",
                [prev.as_str(); 10].join(", ")
            ));
        }
        assert!(err(&doc).contains("anchors and aliases copy more than"));
    }

    #[test]
    fn deep_compact_sequences_stop_at_the_limit() {
        // saphyr's recursive loader overflows the stack on these; the event
        // loop stops at MAX_DEPTH instead.
        let doc = format!("w:\n  steps:\n  {}x\n", "- ".repeat(20_000));
        assert!(err(&doc).contains("nesting deeper than"));
    }

    #[test]
    fn bounds_large_scalar_aliased_many_times() {
        let big = "y".repeat(100_000);
        let refs = ["*s"; 20].join(", ");
        assert!(err(&format!("a: &s {big}\nb: [{refs}]\n")).contains("copy more than"));
    }

    #[test]
    fn unreferenced_anchors_are_not_copied() {
        // Nested anchors no alias uses cost nothing, however large.
        let big = "z".repeat(2_000_000);
        let mut doc = String::new();
        for i in 0..100 {
            doc.push_str(&format!("&a{i} ["));
        }
        doc.push_str(&big);
        doc.push_str(&"]".repeat(100));
        assert!(load_str(&doc).is_ok());
    }

    #[test]
    fn bounds_nesting_depth() {
        let deep = "[".repeat(MAX_DEPTH + 1) + &"]".repeat(MAX_DEPTH + 1);
        assert!(err(&deep).contains("nesting deeper"));
        let ok = "[".repeat(MAX_DEPTH) + &"]".repeat(MAX_DEPTH);
        assert!(load_str(&ok).is_ok());
    }

    #[test]
    fn aliases_cannot_exceed_nesting_depth() {
        let half = 100;
        let doc = format!(
            "a: &a {}{}\nb: {}*a{}\n",
            "[".repeat(half),
            "]".repeat(half),
            "[".repeat(half),
            "]".repeat(half)
        );
        assert!(err(&doc).contains("alias would nest deeper"));
    }

    #[test]
    fn reports_position_of_syntax_errors() {
        match load_str("a: [1, 2\n").unwrap_err() {
            YamlError::Parse { line, .. } => assert!(line >= 1),
            other => panic!("unexpected {other:?}"),
        }
    }

    #[test]
    fn strips_bom() {
        assert_eq!(load_str("\u{feff}a: 1\n").unwrap(), json!({"a": 1}));
    }

    #[cfg(unix)]
    #[test]
    fn file_guards() {
        let dir = std::env::temp_dir().join(format!("acs-yaml-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let real = dir.join("real.yaml");
        std::fs::write(&real, "a: 1\n").unwrap();
        assert_eq!(
            load_file(&real, DEFAULT_MAX_BYTES).unwrap(),
            json!({"a": 1})
        );
        assert_eq!(load_file(&real, u64::MAX).unwrap(), json!({"a": 1}));
        assert!(matches!(
            load_file(&real, 2),
            Err(YamlError::TooLarge { .. })
        ));
        let link = dir.join("link.yaml");
        let _ = std::fs::remove_file(&link);
        std::os::unix::fs::symlink(&real, &link).unwrap();
        assert!(matches!(
            load_file(&link, DEFAULT_MAX_BYTES),
            Err(YamlError::Symlink(_))
        ));
        assert!(matches!(
            load_file(&dir.join("missing.yaml"), DEFAULT_MAX_BYTES),
            Err(YamlError::NotFound(_))
        ));
        assert!(matches!(
            load_file(&dir, DEFAULT_MAX_BYTES),
            Err(YamlError::Io {
                kind: ErrorKind::IsADirectory,
                ..
            })
        ));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
