//! Grounding (STANDARD v1.2 §3.1, §5.20, §6.5): evidence anchors, the kind
//! and inference-method grammars, grounding policies, and the check of one
//! output against a policy. Pure functions, no I/O: the executor, the
//! Python package (`_core.check_grounding`) and the vectors of
//! `tests/conformance/grounding/check.json` share them.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::ontology::Ontology;
use crate::refs::{Ref, Seg};

/// The evidence-anchor kinds §6.5 defines. Any other kind is a vendor kind
/// (`x-…`, [`vendor`]).
pub const KINDS: &[&str] = &[
    "file",
    "url",
    "tool",
    "log",
    "sensor",
    "human_note",
    "api",
    "record",
];

/// A vendor name: `x-`, then a lowercase letter or a digit, then lowercase
/// letters, digits, `_`, `.` or `-`.
pub fn vendor(v: &str) -> bool {
    let Some(rest) = v.strip_prefix("x-") else {
        return false;
    };
    let mut chars = rest.chars();
    chars
        .next()
        .is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c))
}

/// Whether `k` is an evidence-anchor kind (§6.5): one of [`KINDS`] or a
/// vendor kind. The one grammar of anchor kinds: grounding policies,
/// profiles' `required_anchor_types` and anchors all use it.
pub fn is_kind(k: &str) -> bool {
    KINDS.contains(&k) || vendor(k)
}

/// The inference methods §4.1.1 lists. Any other method is a vendor one
/// (`x-…`, [`vendor`]).
pub const METHODS: &[&str] = &[
    "model_knowledge",
    "deduction",
    "induction",
    "abduction",
    "analogy",
    "statistical",
    "simulation",
    "assumption",
];

/// Whether `m` is an inference method of §4.1.1's vocabulary: one of
/// [`METHODS`] or a vendor method.
pub fn is_method(m: &str) -> bool {
    METHODS.contains(&m) || vendor(m)
}

/// Whether `d` is a digest of §6.5's form: `sha256:` and 64 lower-case
/// hexadecimal digits.
pub fn digest_ok(d: &str) -> bool {
    d.strip_prefix("sha256:").is_some_and(|h| {
        h.len() == 64
            && h.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

/// Whether `v` is an evidence anchor (§6.5): an object whose `ref` is a
/// non-empty string, whose `kind` is a kind ([`is_kind`]) and whose
/// `digest`, when present, has §6.5's form. Anything else in an
/// `evidence_anchors` list is a deprecated legacy form.
pub fn is_anchor(v: &Value) -> bool {
    let Some(m) = v.as_object() else {
        return false;
    };
    m.get("ref")
        .and_then(Value::as_str)
        .is_some_and(|r| !r.is_empty())
        && m.get("kind").and_then(Value::as_str).is_some_and(is_kind)
        && m.get("digest")
            .is_none_or(|d| d.as_str().is_some_and(digest_ok))
}

/// A grounding policy (§5.20): the outputs of the capabilities it
/// `require`s must be grounded, by anchors of the `kinds` it lists (any
/// kind when absent), attested by the host when `attested`.
///
/// Deserializing one refuses a member other than `require`, `kinds`,
/// `attested` and extension members `x-...`: a host's misspelt `kinds` or
/// `attested` would otherwise turn its check off without a word.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize)]
pub struct Policy {
    pub require: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kinds: Option<Vec<String>>,
    #[serde(default)]
    pub attested: bool,
}

/// The members of a grounding policy; any other is refused unless it is an
/// extension member (`x-...`).
pub const POLICY_KEYS: &[&str] = &["require", "kinds", "attested"];

/// The member of a host's policy that is not one (`'<key>' is not ...`).
pub fn unknown_member<'a>(keys: impl IntoIterator<Item = &'a String>) -> Option<String> {
    keys.into_iter()
        .find(|k| !POLICY_KEYS.contains(&k.as_str()) && !k.starts_with("x-"))
        .map(|k| {
            format!(
                "'{k}' is not a member of a grounding policy ({}, or an extension member x-...)",
                POLICY_KEYS.join(", ")
            )
        })
}

impl<'de> Deserialize<'de> for Policy {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Repr {
            require: Vec<String>,
            #[serde(default)]
            kinds: Option<Vec<String>>,
            #[serde(default)]
            attested: bool,
            #[serde(flatten)]
            other: serde_json::Map<String, Value>,
        }
        let r = Repr::deserialize(d)?;
        if let Some(e) = unknown_member(r.other.keys()) {
            return Err(serde::de::Error::custom(e));
        }
        Ok(Policy {
            require: r.require,
            kinds: r.kinds,
            attested: r.attested,
        })
    }
}

impl Policy {
    /// A policy, with its shape checked: `require` a non-empty list of
    /// distinct capability ids; `kinds`, when given, a non-empty list of
    /// distinct anchor kinds ([`is_kind`]). Whether the ids are the
    /// ontology's is [`Policy::check_ids`]'s question.
    pub fn new(
        require: Vec<String>,
        kinds: Option<Vec<String>>,
        attested: bool,
    ) -> Result<Policy, String> {
        if require.is_empty() {
            return Err("require must list at least one capability".into());
        }
        if let Some((i, id)) = repeated(&require) {
            return Err(format!("require[{i}]: '{id}' is listed twice"));
        }
        if let Some(kinds) = &kinds {
            if kinds.is_empty() {
                return Err("kinds, when given, must list at least one anchor kind".into());
            }
            if let Some((i, k)) = kinds.iter().enumerate().find(|(_, k)| !is_kind(k)) {
                return Err(format!(
                    "kinds[{i}]: '{k}' is not an anchor kind ({}, or a vendor kind x-...)",
                    KINDS.join(", ")
                ));
            }
            if let Some((i, k)) = repeated(kinds) {
                return Err(format!("kinds[{i}]: '{k}' is listed twice"));
            }
        }
        Ok(Policy {
            require,
            kinds,
            attested,
        })
    }

    /// `Err` names the first required id the ontology does not define
    /// (V101), with the closest id as a hint.
    pub fn check_ids(&self, ontology: &Ontology) -> Result<(), String> {
        let Some((i, id)) = self
            .require
            .iter()
            .enumerate()
            .find(|(_, id)| ontology.get(id).is_none())
        else {
            return Ok(());
        };
        let known: Vec<&str> = ontology.capabilities.keys().map(String::as_str).collect();
        let hint = crate::validate::semantics::closest(id, &known)
            .map(|c| format!("; did you mean '{c}'?"))
            .unwrap_or_default();
        Err(format!(
            "require[{i}]: '{id}' is not a capability of the ontology (V101){hint}"
        ))
    }

    /// Whether the policy covers outputs of `capability`.
    pub fn requires(&self, capability: &str) -> bool {
        self.require.iter().any(|r| r == capability)
    }

    /// The policy a workflow's `grounding` states, which the validator has
    /// checked (§5.20); `None` when it is not a policy's shape.
    pub fn from_value(v: &Value) -> Option<Policy> {
        let strings = |v: &Value| -> Option<Vec<String>> {
            v.as_array()?
                .iter()
                .map(|x| x.as_str().map(str::to_string))
                .collect()
        };
        let m = v.as_object()?;
        let require = strings(m.get("require")?)?;
        let kinds = match m.get("kinds") {
            None => None,
            Some(k) => Some(strings(k)?),
        };
        let attested = match m.get("attested") {
            None => false,
            Some(a) => a.as_bool()?,
        };
        Policy::new(require, kinds, attested).ok()
    }
}

/// Whether the reference `bound` covers the reference `cited` (§5.20): the
/// same root, and each segment of `bound`'s path matches `cited`'s segment
/// at the same position (the same field or index; a bound slice `[a:b]`
/// matches an index `i` with `a <= i < b`, or a slice `[c:d]` within it,
/// absent bounds being the start and the end). `cited` may go on past
/// `bound`'s path.
pub fn covers(bound: &Ref, cited: &Ref) -> bool {
    bound.root == cited.root
        && cited.path.len() >= bound.path.len()
        && bound
            .path
            .iter()
            .zip(&cited.path)
            .all(|(b, c)| segment_covers(b, c))
}

fn segment_covers(b: &Seg, c: &Seg) -> bool {
    match (b, c) {
        (Seg::Field(x), Seg::Field(y)) => x == y,
        (Seg::Index(i), Seg::Index(j)) => i == j,
        (Seg::Slice(start, end), Seg::Index(i)) => {
            start.unwrap_or(0) <= *i && end.is_none_or(|e| *i < e)
        }
        (Seg::Slice(start, end), Seg::Slice(from, to)) => {
            start.unwrap_or(0) <= from.unwrap_or(0)
                && match (end, to) {
                    (None, _) => true,
                    (Some(e), Some(t)) => t <= e,
                    (Some(_), None) => false,
                }
        }
        _ => false,
    }
}

/// The body of a reference without its annotation (`r.items[0:3]`).
pub fn body(r: &Ref) -> String {
    let path: String = r.path.iter().map(Seg::to_string).collect();
    format!("{}{path}", r.root)
}

/// The references a step's `input_bindings` make (§5.20): every `${…}` in
/// the value that parses, its annotation dropped, sorted and without
/// repeats.
pub fn bound_refs(v: &Value) -> Vec<Ref> {
    fn walk(v: &Value, out: &mut Vec<Ref>) {
        match v {
            Value::String(s) => out.extend(
                crate::refs::find_refs(s)
                    .into_iter()
                    .filter_map(|m| m.parsed.ok())
                    .map(plain),
            ),
            Value::Array(a) => a.iter().for_each(|x| walk(x, out)),
            Value::Object(m) => m.values().for_each(|x| walk(x, out)),
            _ => {}
        }
    }
    let mut out = Vec::new();
    walk(v, &mut out);
    out.sort_by(|a, b| a.raw.cmp(&b.raw));
    out.dedup_by(|a, b| a.raw == b.raw);
    out
}

/// A reference as a bound reference: no annotation, and `raw` its body.
fn plain(mut r: Ref) -> Ref {
    r.annotation = None;
    r.raw = body(&r);
    r
}

/// The largest index an `acs:` reference or a bound reference a caller
/// gives may hold: I-JSON's 2^53 - 1 (RFC 7493), the largest a JSON number
/// carries exactly, so every implementation reads the same reference.
pub const MAX_INDEX: u64 = (1 << 53) - 1;

/// Whether every index and slice bound of `r` is at most [`MAX_INDEX`].
fn indices_ok(r: &Ref) -> bool {
    let ok = |i: usize| i as u64 <= MAX_INDEX;
    r.path.iter().all(|s| match s {
        Seg::Field(_) => true,
        Seg::Index(i) => ok(*i),
        Seg::Slice(a, b) => a.is_none_or(ok) && b.is_none_or(ok),
    })
}

/// Reference bodies a caller gives (`r.items[0:3]`; for a call, its
/// argument names) as bound references. `Err` names the first that is not
/// a reference body (§5.3, without `${`, `}` and an annotation, and no
/// index above [`MAX_INDEX`]).
pub fn parse_bound(bodies: &[String]) -> Result<Vec<Ref>, String> {
    bodies
        .iter()
        .enumerate()
        .map(|(i, b)| match crate::refs::parse_ref(b) {
            Ok(r) if !indices_ok(&r) => Err(format!(
                "bound_refs[{i}]: '{b}' holds an index above 2^53 - 1 (I-JSON)"
            )),
            Ok(r) if r.annotation.is_none() && b.trim() == b => Ok(plain(r)),
            Ok(_) => Err(format!(
                "bound_refs[{i}]: '{b}' is not a reference body (no annotation or spaces)"
            )),
            Err(e) => Err(format!("bound_refs[{i}]: {e}")),
        })
        .collect()
}

/// How an output passed a grounding policy (§5.20).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    /// At least one anchor counts.
    Grounded,
    /// No anchor counts, and the output is marked inferred.
    Inferred,
}

/// An output that passed: how, and what its `evidence_anchors` held.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Checked {
    pub status: Status,
    /// Anchors that count toward the policy.
    pub counted: usize,
    /// Items that are not evidence anchors (the deprecated legacy forms).
    pub legacy: usize,
    /// Anchors whose availability is not established (neither an `acs:`
    /// citation nor listed in `evidence_seen`).
    pub unattested: usize,
}

/// §5.20's check of one output against one policy (its `kinds` and
/// `attested`; whether it requires the capability is the caller's
/// question). `bound` holds the references the step's `input_bindings` make
/// (for a call, its argument names); `seen` is the host's `evidence_seen`,
/// `None` when absent. `Err` is the message of an F505.
pub fn check(
    output: &Value,
    policy: &Policy,
    bound: &[Ref],
    seen: Option<&[String]>,
) -> Result<Checked, String> {
    let Some(items) = output.get("evidence_anchors").and_then(Value::as_array) else {
        return Err("evidence_anchors is not a list (§4.1.1)".into());
    };
    let (mut counted, mut legacy, mut excluded, mut unattested, mut withheld) = (0, 0, 0, 0, 0);
    for (i, item) in items.iter().enumerate() {
        let r = item.get("ref").and_then(Value::as_str);
        let kind = item.get("kind").and_then(Value::as_str);
        let established = if let Some(cited) = r.and_then(|r| r.strip_prefix("acs:")) {
            // Item 2: a citation of a workflow value.
            let r = r.unwrap_or_default();
            if kind != Some("record") {
                let k = kind.map_or_else(|| "no kind".to_string(), |k| format!("kind '{k}'"));
                return Err(format!(
                    "evidence_anchors[{i}] cites a workflow value ('{r}') with {k}; an acs: anchor is of kind record (§6.5)"
                ));
            }
            let cited = match crate::refs::parse_ref(cited) {
                Ok(c) if c.annotation.is_none() && indices_ok(&c) => c,
                _ => {
                    return Err(format!(
                        "evidence_anchors[{i}] cites '{r}', whose rest is not a reference body (§5.3, without ${{, }}, a type annotation and an index above 2^53 - 1) (§6.5)"
                    ));
                }
            };
            if !bound.iter().any(|b| covers(b, &cited)) {
                let binds = if bound.is_empty() {
                    "no reference is bound".to_string()
                } else {
                    let list: Vec<String> = bound.iter().map(body).collect();
                    format!("the bound references are {}", list.join(", "))
                };
                return Err(format!(
                    "evidence_anchors[{i}] cites '{r}', which no reference bound for the output's producer covers ({binds}) (§3.1, §5.20)"
                ));
            }
            true
        } else if is_anchor(item) {
            // Item 3: any other evidence anchor.
            let r = r.unwrap_or_default();
            match seen {
                Some(seen) if !seen.iter().any(|s| s == r) => {
                    return Err(format!(
                        "evidence_anchors[{i}] cites '{r}', which the host's evidence_seen does not list: its producer did not have it (§3.1, §5.20)"
                    ));
                }
                Some(_) => true,
                None => false,
            }
        } else {
            // Item 4: a deprecated legacy form, which does not count.
            legacy += 1;
            continue;
        };
        if !established {
            unattested += 1;
        }
        let kind = kind.unwrap_or_default();
        if policy
            .kinds
            .as_ref()
            .is_some_and(|ks| !ks.iter().any(|k| k == kind))
        {
            excluded += 1;
        } else if policy.attested && !established {
            withheld += 1;
        } else {
            counted += 1;
        }
    }
    let checked = |status| Checked {
        status,
        counted,
        legacy,
        unattested,
    };
    if counted > 0 {
        return Ok(checked(Status::Grounded));
    }
    // Nothing counts: the output must be marked inferred.
    let method = output.get("inference_method");
    let confidence = output.get("confidence");
    let method_ok = method.and_then(Value::as_str).is_some_and(is_method);
    let confidence_ok = confidence
        .filter(|c| c.is_number())
        .and_then(Value::as_f64)
        .is_some_and(|c| (0.0..=1.0).contains(&c));
    if method_ok && confidence_ok {
        return Ok(checked(Status::Inferred));
    }
    let mut why = Vec::new();
    if items.is_empty() {
        why.push("it has no evidence anchors".to_string());
    }
    if legacy > 0 {
        why.push(if legacy == 1 {
            "1 item that is not an evidence anchor, which does not count".to_string()
        } else {
            format!("{legacy} items that are not evidence anchors, which do not count")
        });
    }
    if excluded > 0 {
        why.push(format!(
            "{excluded} anchor{} of kinds the policy does not list",
            plural(excluded)
        ));
    }
    if withheld > 0 {
        why.push(format!(
            "{withheld} anchor{} whose availability is not established",
            plural(withheld)
        ));
    }
    let mut marking = Vec::new();
    match method {
        None => marking.push("no inference_method".to_string()),
        Some(m) if !method_ok => marking.push(format!(
            "an inference_method {m} outside §4.1.1's vocabulary"
        )),
        _ => {}
    }
    match confidence {
        None => marking.push("no confidence".to_string()),
        Some(c) if !confidence_ok => {
            marking.push(format!("a confidence {c} that is not from 0 to 1"))
        }
        _ => {}
    }
    Err(format!(
        "no evidence anchor counts toward the grounding policy ({}), and the output is not marked inferred: it has {} (an inference_method of §4.1.1's vocabulary and a confidence from 0 to 1, §3.1)",
        why.join("; "),
        marking.join(" and ")
    ))
}

fn plural(n: usize) -> &'static str {
    if n == 1 { "" } else { "s" }
}

/// The first item equal to an earlier one, with its index.
fn repeated(items: &[String]) -> Option<(usize, &str)> {
    items
        .iter()
        .enumerate()
        .find(|(i, x)| items[..*i].contains(x))
        .map(|(i, x)| (i, x.as_str()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn kinds() {
        for k in KINDS {
            assert!(is_kind(k));
        }
        for k in ["x-scan", "x-0", "x-a.b_c-d"] {
            assert!(is_kind(k), "{k}");
        }
        for k in ["", "File", "x-", "x-A", "x-_a", "x-a b", "document", "x-é"] {
            assert!(!is_kind(k), "{k}");
        }
    }

    #[test]
    fn policy_shape() {
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        let p = Policy::new(s(&["search", "retrieve"]), Some(s(&["file", "x-db"])), true).unwrap();
        assert!(p.requires("search") && !p.requires("send"));
        assert!(Policy::new(s(&["search"]), None, false).is_ok());
        for (require, kinds) in [
            (s(&[]), None),
            (s(&["a", "a"]), None),
            (s(&["a"]), Some(s(&[]))),
            (s(&["a"]), Some(s(&["file", "file"]))),
            (s(&["a"]), Some(s(&["paper"]))),
        ] {
            assert!(
                Policy::new(require.clone(), kinds.clone(), false).is_err(),
                "{require:?} {kinds:?}"
            );
        }
        // Absent kinds stay absent, not empty.
        let v = serde_json::to_value(Policy::new(s(&["a"]), None, false).unwrap()).unwrap();
        assert_eq!(v, json!({"require": ["a"], "attested": false}));
        let back: Policy = serde_json::from_value(json!({"require": ["a"]})).unwrap();
        assert_eq!(back, Policy::new(s(&["a"]), None, false).unwrap());
    }

    #[test]
    fn a_host_policy_refuses_a_member_it_does_not_define() {
        // A misspelt `kinds` or `attested` would turn the check off.
        for (v, key) in [
            (json!({"require": ["a"], "kind": ["file"]}), "kind"),
            (json!({"require": ["a"], "atested": true}), "atested"),
        ] {
            let e = serde_json::from_value::<Policy>(v).unwrap_err().to_string();
            assert!(
                e.contains(&format!("'{key}' is not a member of a grounding policy")),
                "{e}"
            );
        }
        // An extension member is kept out of the policy, not refused.
        let p: Policy =
            serde_json::from_value(json!({"require": ["a"], "attested": true, "x-note": 1}))
                .unwrap();
        assert_eq!(p, Policy::new(vec!["a".into()], None, true).unwrap());
    }

    #[test]
    fn methods_digests_and_anchors() {
        for m in METHODS {
            assert!(is_method(m));
        }
        assert!(is_method("x-acme.rules"));
        assert!(!is_method("llm-reasoning") && !is_method("Deduction") && !is_method(""));
        let hex = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";
        assert!(digest_ok(&format!("sha256:{hex}")));
        for d in [
            hex.to_string(),
            format!("sha256:{}", hex.to_uppercase()),
            format!("sha256:{}", &hex[1..]),
            format!("sha1:{hex}"),
        ] {
            assert!(!digest_ok(&d), "{d}");
        }
        assert!(is_anchor(&json!({"ref": "file:a", "kind": "file"})));
        assert!(is_anchor(
            &json!({"ref": "a", "kind": "x-db", "digest": format!("sha256:{hex}"), "x-n": 1})
        ));
        for v in [
            json!("file:a"),
            json!({"ref": "file:a"}),
            json!({"ref": "", "kind": "file"}),
            json!({"ref": "a", "kind": "tool_output"}),
            json!({"ref": "a", "kind": "file", "digest": "sha256:0"}),
            json!({"ref": "a", "kind": "file", "digest": null}),
            json!({"ref": 1, "kind": "file"}),
        ] {
            assert!(!is_anchor(&v), "{v}");
        }
    }

    fn r(body: &str) -> Ref {
        crate::refs::parse_ref(body).unwrap()
    }

    #[test]
    fn coverage() {
        let yes = [
            ("r", "r"),
            ("r", "r.data"),
            ("r.data", "r.data[0].x"),
            ("r.items[2:5]", "r.items[2]"),
            ("r.items[2:5]", "r.items[4].url"),
            ("r.items[2:]", "r.items[40]"),
            ("r.items[:3]", "r.items[0]"),
            ("r.items[0:10]", "r.items[2:4]"),
            ("r.items[0:10]", "r.items[:10]"),
            ("r.items[2:]", "r.items[3:]"),
            ("r.items[1]", "r.items[1].a"),
        ];
        for (b, c) in yes {
            assert!(covers(&r(b), &r(c)), "{b} covers {c}");
        }
        let no = [
            ("r", "s"),
            ("r.data", "r"),
            ("r.data.x", "r.secret"),
            ("r.items[2:5]", "r.items[5]"),
            ("r.items[2:5]", "r.items[1]"),
            ("r.items[0:3]", "r.items[1:5]"),
            ("r.items[0:3]", "r.items[1:]"),
            ("r.items[1]", "r.items[2]"),
            ("r.items[1]", "r.items[1:2]"),
            ("r.items[0]", "r.items.x"),
            ("search_out.results[0]", "search_out.results"),
        ];
        for (b, c) in no {
            assert!(!covers(&r(b), &r(c)), "{b} does not cover {c}");
        }
    }

    #[test]
    fn bound_references() {
        let v = json!({
            "a": "${r.data[0:2]}",
            "b": "x ${s.a} y ${s.a: string} ${bad.[}",
            "c": [{"d": "${r.data[0:2]: array<object>}"}, 3]
        });
        let bodies: Vec<String> = bound_refs(&v).iter().map(body).collect();
        assert_eq!(bodies, ["r.data[0:2]", "s.a"]);
        assert!(bound_refs(&json!({"q": "plain"})).is_empty());
        let parsed = parse_bound(&["path".into(), "r.items[2:5]".into()]).unwrap();
        assert_eq!(parsed[1].raw, "r.items[2:5]");
        for bad in ["r: string", "r.[", "", " r"] {
            assert!(parse_bound(&[bad.to_string()]).is_err(), "{bad}");
        }
    }

    #[test]
    fn policy_from_a_workflow_value() {
        let p = Policy::from_value(
            &json!({"require": ["search"], "kinds": ["file"], "attested": true}),
        )
        .unwrap();
        assert_eq!(p.kinds.as_deref(), Some(&["file".to_string()][..]));
        assert!(p.attested);
        assert!(Policy::from_value(&json!({"require": ["search"]})).is_some());
        for v in [
            json!({"kinds": ["file"]}),
            json!({"require": []}),
            json!({"require": ["a"], "attested": "yes"}),
            json!(["a"]),
        ] {
            assert!(Policy::from_value(&v).is_none(), "{v}");
        }
    }

    #[test]
    fn messages_say_why() {
        let p = Policy::new(vec!["search".into()], Some(vec!["file".into()]), true).unwrap();
        let out = json!({"evidence_anchors": [
            "legacy",
            {"ref": "log:1", "kind": "log"},
            {"ref": "file:a", "kind": "file"}
        ], "inference_method": "guess", "confidence": 2});
        let e = check(&out, &p, &[], None).unwrap_err();
        for part in [
            "1 item that is not an",
            "1 anchor of kinds",
            "1 anchor whose availability",
            "\"guess\" outside",
            "confidence 2 that",
        ] {
            assert!(e.contains(part), "{part}: {e}");
        }
        let e = check(
            &json!({"evidence_anchors": [{"ref": "acs:s.results[7]", "kind": "record"}]}),
            &p,
            &[r("s.results[0:3]")],
            None,
        )
        .unwrap_err();
        assert!(
            e.contains("s.results[0:3]") && e.contains("evidence_anchors[0]"),
            "{e}"
        );
    }

    #[test]
    fn ids_against_the_ontology() {
        let ontology = Ontology::from_value(&json!({"nodes": [
            {"id": "classify", "layer": "UNDERSTAND"},
            {"id": "search", "layer": "PERCEIVE"}
        ]}))
        .unwrap();
        let p = |ids: &[&str]| {
            Policy::new(ids.iter().map(|x| x.to_string()).collect(), None, false).unwrap()
        };
        assert!(p(&["search", "classify"]).check_ids(&ontology).is_ok());
        let e = p(&["search", "clasify"]).check_ids(&ontology).unwrap_err();
        assert!(
            e.contains("require[1]") && e.contains("V101") && e.contains("'classify'"),
            "{e}"
        );
    }
}
