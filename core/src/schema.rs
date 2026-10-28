//! JSON-Schema-like documents: `$ref` resolution and path navigation.
//!
//! Workflow inputs, `output_conforms_to` and ontology contracts reference
//! schema files relative to a schema root (the repository root). References
//! that try to leave the root, or name absolute paths, resolve to nothing.

use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Mutex, PoisonError};

use serde_json::Value;

use crate::refs::Seg;
use crate::yaml;

/// Maximum `$ref` hops followed while resolving one node.
const MAX_REF_DEPTH: usize = 12;

/// Most schema nodes one validation may produce by resolving refs (a
/// catalog's inputs, or the ontology's contracts). The repository's largest
/// schema expands to a few thousand; this bounds memory however refs fan out.
pub const MAX_EXPANDED_NODES: usize = 200_000;

/// Loads schema files under one root, caching each file.
pub struct SchemaStore {
    root: PathBuf,
    cache: Mutex<HashMap<PathBuf, Option<Arc<Value>>>>,
}

impl SchemaStore {
    pub fn new(root: impl Into<PathBuf>) -> SchemaStore {
        SchemaStore {
            root: root.into(),
            cache: Mutex::new(HashMap::new()),
        }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Forget every cached file, so the next lookup reads the disk again.
    pub fn clear_cache(&self) {
        self.cache
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clear();
    }

    /// The path a repository-relative reference names, if it stays under the root.
    pub fn locate(&self, rel: &str) -> Option<PathBuf> {
        let p = Path::new(rel);
        if rel.is_empty()
            || p.components()
                .any(|c| !matches!(c, Component::Normal(_) | Component::CurDir))
        {
            return None;
        }
        Some(self.root.join(p))
    }

    /// Whether a repository-relative file exists (and is under the root).
    pub fn file_exists(&self, rel: &str) -> bool {
        self.locate(rel).is_some_and(|p| p.is_file())
    }

    /// Load a schema file (`.yaml`, `.yml` or `.json`); `None` if absent or unreadable.
    pub fn document(&self, rel: &str) -> Option<Arc<Value>> {
        let path = self.locate(rel)?;
        let cached = self
            .cache
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .get(&path)
            .cloned();
        if let Some(hit) = cached {
            return hit;
        }
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(str::to_ascii_lowercase);
        let doc = match ext.as_deref() {
            Some("yaml" | "yml") => yaml::load_file(&path, yaml::DEFAULT_MAX_BYTES).ok(),
            Some("json") => yaml::read_guarded(&path, yaml::DEFAULT_MAX_BYTES)
                .ok()
                .and_then(|t| serde_json::from_str(&t).ok()),
            _ => None,
        }
        .map(Arc::new);
        self.cache
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .insert(path, doc.clone());
        doc
    }

    /// Resolve `file#/json/pointer` (or a bare file) to the node it names.
    pub fn resolve_ref(&self, r: &str) -> Option<Value> {
        let (file, pointer) = match r.split_once('#') {
            Some((f, p)) => (f, p),
            None => (r, ""),
        };
        let doc = self.document(file)?;
        json_pointer(&doc, pointer).cloned()
    }

    /// Replace every `$ref` in `node` with what it names, merging sibling keys
    /// over the target, as the reference validator always has. Every node
    /// produced is charged to `budget`, which the caller shares across all
    /// the resolutions one validation keeps in memory.
    pub fn resolve_node(&self, node: &Value, budget: &mut usize) -> Result<Value, TooLarge> {
        self.expand(node, None, &mut Vec::new(), budget)
    }

    /// Resolve `r` and every `$ref` inside what it names; a `#/...` ref
    /// there resolves against the file it appears in. `Ok(None)` when `r`
    /// names nothing. Charged to `budget` as [`Self::resolve_node`] is.
    pub fn resolve_ref_deep(&self, r: &str, budget: &mut usize) -> Result<Option<Value>, TooLarge> {
        let Some(target) = self.resolve_ref(r) else {
            return Ok(None);
        };
        let file = r.split_once('#').map_or(r, |(f, _)| f).to_string();
        let mut chain = vec![absolute(r, None)];
        self.expand(&target, Some(&file), &mut chain, budget)
            .map(Some)
    }

    /// `chain` holds the refs being expanded: at most `MAX_REF_DEPTH` hops,
    /// and a ref already on it (a cycle), or one that names nothing usable,
    /// is kept as it is. Every node produced spends one unit of `budget`,
    /// kept refs included: refs that fan out can multiply a small file into
    /// an exponentially large tree, so expansion stops there.
    fn expand(
        &self,
        node: &Value,
        base: Option<&str>,
        chain: &mut Vec<String>,
        budget: &mut usize,
    ) -> Result<Value, TooLarge> {
        if let Value::Object(m) = node {
            if let Some(Value::String(r)) = m.get("$ref") {
                let abs = absolute(r, base);
                let target = if chain.len() >= MAX_REF_DEPTH || chain.contains(&abs) {
                    None
                } else {
                    self.resolve_ref(&abs)
                };
                let Some(Value::Object(target)) = target else {
                    return charged(node, budget);
                };
                let mut merged = target;
                for (k, v) in m {
                    if k != "$ref" {
                        merged.insert(k.clone(), v.clone());
                    }
                }
                let file = abs
                    .split_once('#')
                    .map_or(abs.as_str(), |(f, _)| f)
                    .to_string();
                chain.push(abs);
                let out = self.expand(&Value::Object(merged), Some(&file), chain, budget);
                chain.pop();
                return out;
            }
        }
        *budget = budget.checked_sub(1).ok_or(TooLarge)?;
        Ok(match node {
            Value::Object(m) => Value::Object(
                m.iter()
                    .map(|(k, v)| Ok((k.clone(), self.expand(v, base, chain, budget)?)))
                    .collect::<Result<_, TooLarge>>()?,
            ),
            Value::Array(a) => Value::Array(
                a.iter()
                    .map(|v| self.expand(v, base, chain, budget))
                    .collect::<Result<_, TooLarge>>()?,
            ),
            other => other.clone(),
        })
    }
}

/// `node` cloned as it is, each of its nodes charged to `budget`.
fn charged(node: &Value, budget: &mut usize) -> Result<Value, TooLarge> {
    fn charge(v: &Value, budget: &mut usize) -> Result<(), TooLarge> {
        *budget = budget.checked_sub(1).ok_or(TooLarge)?;
        match v {
            Value::Object(m) => m.values().try_for_each(|c| charge(c, budget)),
            Value::Array(a) => a.iter().try_for_each(|c| charge(c, budget)),
            _ => Ok(()),
        }
    }
    charge(node, budget)?;
    Ok(node.clone())
}

/// A schema whose `$ref`s expand to more than [`MAX_EXPANDED_NODES`] nodes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TooLarge;

impl std::fmt::Display for TooLarge {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "its $refs expand to more than {MAX_EXPANDED_NODES} schema nodes"
        )
    }
}

/// A ref made absolute: `#/...` names a node of the file it appears in.
fn absolute(r: &str, base: Option<&str>) -> String {
    match (r.strip_prefix('#'), base) {
        (Some(pointer), Some(file)) => format!("{file}#{pointer}"),
        _ => r.to_string(),
    }
}

/// RFC 6901 JSON pointer lookup; `""` and `"/"`-less pointers name the root.
pub fn json_pointer<'a>(doc: &'a Value, pointer: &str) -> Option<&'a Value> {
    let p = pointer.strip_prefix('/').unwrap_or(pointer);
    if p.is_empty() {
        return Some(doc);
    }
    let mut cur = doc;
    for raw in p.split('/') {
        let part = raw.replace("~1", "/").replace("~0", "~");
        cur = match cur {
            Value::Object(m) => m.get(&part)?,
            Value::Array(a) => a.get(part.parse::<usize>().ok()?)?,
            _ => return None,
        };
    }
    Some(cur)
}

/// The result of selecting one path segment on a schema node.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Step<'a> {
    /// The segment selects this schema node.
    Node(&'a Value),
    /// The segment is allowed but nothing is known about what it selects.
    Untyped,
    /// The segment cannot apply to this node (B201).
    Invalid,
}

/// The type names a node declares, or `None` when it declares none. Handles
/// a single name, the ontology's `a|b` shorthand and JSON Schema type lists.
fn type_names(s: &Value) -> Option<Vec<&str>> {
    match s.get("type")? {
        Value::String(t) => Some(t.split('|').map(str::trim).collect()),
        Value::Array(ts) => Some(ts.iter().filter_map(Value::as_str).collect()),
        _ => None,
    }
}

/// Whether a value of this schema could be an object: it declares no type,
/// `any`, `object`, or a union including one of them, or has `properties`.
fn may_be_object(s: &Value) -> bool {
    match type_names(s) {
        None => true,
        Some(names) => names.iter().any(|n| matches!(*n, "object" | "any")),
    }
}

/// Whether a value of this schema could be an array.
fn may_be_array(s: &Value) -> bool {
    match type_names(s) {
        None => !s.get("properties").is_some_and(Value::is_object),
        Some(names) => names.iter().any(|n| matches!(*n, "array" | "any")),
    }
}

/// Select field `name` on `node`. A field must name a declared property; an
/// undeclared key is allowed where `additionalProperties` permits it or the
/// object declares no properties. There is no implicit projection: a field on
/// a node that can only be an array is invalid (select an element with `[n]`).
pub fn field<'a>(node: &'a Value, name: &str) -> Step<'a> {
    if !may_be_object(node) {
        return Step::Invalid;
    }
    let props = node.get("properties").and_then(Value::as_object);
    if let Some(child) = props.and_then(|p| p.get(name)) {
        return Step::Node(child);
    }
    match node.get("additionalProperties") {
        Some(ap @ Value::Object(_)) => Step::Node(ap),
        Some(Value::Bool(true)) => Step::Untyped,
        Some(_) => Step::Invalid,
        None if props.is_none() => Step::Untyped,
        None => Step::Invalid,
    }
}

/// Select an element (`[n]`) of `node`: its `items`, untyped if it declares
/// none, invalid if the node cannot be an array.
pub fn index(node: &Value) -> Step<'_> {
    if !may_be_array(node) {
        return Step::Invalid;
    }
    match node.get("items") {
        Some(items) => Step::Node(items),
        None => Step::Untyped,
    }
}

/// Whether a slice (`[a:b]`) applies to `node`; a slice keeps the array.
pub fn slice_ok(node: &Value) -> bool {
    may_be_array(node)
}

/// The schema node a reference path selects, `Some(&Value::Null)` when the
/// path is allowed but untyped, or `None` when it leaves the schema (B201).
pub fn node_at<'a>(schema: &'a Value, path: &[Seg]) -> Option<&'a Value> {
    static UNTYPED: Value = Value::Null;
    let mut cur = schema;
    for seg in path {
        // Nothing is known below an untyped node.
        if cur.is_null() {
            return Some(&UNTYPED);
        }
        let step = match seg {
            Seg::Field(name) => field(cur, name),
            Seg::Index(_) => index(cur),
            Seg::Slice(..) => {
                if slice_ok(cur) {
                    Step::Node(cur)
                } else {
                    Step::Invalid
                }
            }
        };
        cur = match step {
            Step::Node(n) => n,
            Step::Untyped => &UNTYPED,
            Step::Invalid => return None,
        };
    }
    Some(cur)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn pointer_lookup() {
        let doc = json!({"a": {"b/c": [10, {"d~e": 1}]}});
        assert_eq!(json_pointer(&doc, "/a/b~1c/0"), Some(&json!(10)));
        assert_eq!(json_pointer(&doc, "/a/b~1c/1/d~0e"), Some(&json!(1)));
        assert_eq!(json_pointer(&doc, ""), Some(&doc));
        assert_eq!(json_pointer(&doc, "/missing"), None);
    }

    #[test]
    fn path_navigation() {
        let s = json!({"type": "object", "properties": {
            "items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}},
            "n": {"type": "integer"}}});
        let field = |n: &str| Seg::Field(n.to_string());
        assert_eq!(
            node_at(&s, &[field("n")]),
            Some(&json!({"type": "integer"}))
        );
        // No implicit projection through arrays.
        assert_eq!(node_at(&s, &[field("items"), field("id")]), None);
        assert_eq!(
            node_at(&s, &[field("items"), Seg::Index(0), field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert!(node_at(&s, &[field("items"), Seg::Slice(Some(0), Some(2))]).is_some());
        assert_eq!(node_at(&s, &[field("n"), Seg::Index(0)]), None);
        // An object declared only by `properties` cannot be indexed.
        let obj = json!({"properties": {"x": {"type": "string"}}});
        assert_eq!(node_at(&obj, &[Seg::Index(3)]), None);
        // Nullable arrays index like arrays.
        let nullable =
            json!({"type": ["array", "null"], "items": {"properties": {"id": {"type": "string"}}}});
        assert_eq!(
            node_at(&nullable, &[Seg::Index(0), field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert_eq!(node_at(&nullable, &[field("id")]), None);
        assert_eq!(node_at(&s, &[field("missing")]), None);
        // Undeclared keys: only where additionalProperties allows them.
        let open = json!({"type": "object", "additionalProperties": true, "properties": {"k": {}}});
        assert_eq!(node_at(&open, &[field("zzz")]), Some(&Value::Null));
        let typed = json!({"type": "object", "additionalProperties": {"type": "number"}});
        assert_eq!(
            node_at(&typed, &[field("zzz")]),
            Some(&json!({"type": "number"}))
        );
        assert_eq!(
            node_at(&json!({"type": "object"}), &[field("zzz")]),
            Some(&Value::Null)
        );
        assert_eq!(node_at(&json!({"type": "string"}), &[field("zzz")]), None);
    }

    #[test]
    fn refuses_paths_outside_the_root() {
        let store = SchemaStore::new("/nonexistent-root");
        assert!(store.locate("../etc/passwd").is_none());
        assert!(store.locate("/etc/passwd").is_none());
        assert!(store.locate("schemas/x.yaml").is_some());
    }

    #[test]
    fn resolves_refs_in_repository_schemas() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        let store = SchemaStore::new(root);
        let ws = store
            .resolve_ref("schemas/world_state_schema.yaml#/world_state")
            .unwrap();
        assert!(ws.is_object());
        assert!(
            store
                .resolve_ref("schemas/world_state_schema.yaml#/nope")
                .is_none()
        );
        assert!(store.resolve_ref("schemas/absent.yaml#/x").is_none());
        let node = store
            .resolve_node(
                &json!({"$ref": "schemas/world_state_schema.yaml#/world_state", "description": "x"}),
                &mut { MAX_EXPANDED_NODES },
            )
            .unwrap();
        assert_eq!(node["description"], "x");
    }

    #[test]
    fn fanned_out_refs_stop_at_the_node_budget() {
        // Each level refers to the next six times: 6^12 nodes from 3 KB.
        let dir = std::env::temp_dir().join(format!("acs-ref-bomb-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let mut doc = String::new();
        for k in 0..13 {
            doc.push_str(&format!("a{k}:\n  type: object\n  properties:\n"));
            for p in 0..6 {
                doc.push_str(&format!("    p{p}: {{$ref: '#/a{}'}}\n", k + 1));
            }
        }
        doc.push_str("a13: {type: string}\n");
        std::fs::write(dir.join("bomb.yaml"), doc).unwrap();
        let store = SchemaStore::new(&dir);
        let start = std::time::Instant::now();
        let fresh = || MAX_EXPANDED_NODES;
        assert_eq!(
            store.resolve_ref_deep("bomb.yaml#/a0", &mut fresh()),
            Err(TooLarge)
        );
        assert_eq!(
            store.resolve_node(&json!({"$ref": "bomb.yaml#/a0"}), &mut fresh()),
            Err(TooLarge)
        );
        assert!(start.elapsed() < std::time::Duration::from_secs(5));
        // A shallow corner of the same file still resolves.
        assert!(
            store
                .resolve_ref_deep("bomb.yaml#/a12", &mut fresh())
                .unwrap()
                .is_some()
        );
        // The budget is shared: many small resolutions add up.
        let mut shared = fresh();
        let mut failed = false;
        // About 93 nodes each.
        for _ in 0..5_000 {
            if store
                .resolve_ref_deep("bomb.yaml#/a11", &mut shared)
                .is_err()
            {
                failed = true;
                break;
            }
        }
        assert!(failed, "a shared budget must run out");
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn refs_kept_unexpanded_are_charged_too() {
        // Leaves keep a ref that names nothing, beside a large payload:
        // those copies count against the budget like expanded nodes.
        let dir = std::env::temp_dir().join(format!("acs-ref-kept-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let payload: Vec<String> = (0..200).map(|i| format!("k{i}: {i}")).collect();
        let mut doc = String::new();
        for k in 0..6 {
            doc.push_str(&format!("a{k}:\n  properties:\n"));
            for p in 0..6 {
                doc.push_str(&format!("    p{p}: {{$ref: '#/a{}'}}\n", k + 1));
            }
        }
        doc.push_str(&format!(
            "a6: {{$ref: '#/missing', payload: {{{}}}}}\n",
            payload.join(", ")
        ));
        std::fs::write(dir.join("kept.yaml"), doc).unwrap();
        let store = SchemaStore::new(&dir);
        assert_eq!(
            store.resolve_ref_deep("kept.yaml#/a0", &mut { MAX_EXPANDED_NODES }),
            Err(TooLarge)
        );
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn repository_schemas_are_far_inside_the_node_budget() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        let store = SchemaStore::new(&root);
        for r in [
            "schemas/world_state_schema.yaml#/world_state",
            "schemas/event_schema.yaml#/event",
        ] {
            let mut budget = MAX_EXPANDED_NODES;
            let node = store.resolve_ref(r).unwrap();
            store
                .expand(
                    &node,
                    Some(r.split('#').next().unwrap()),
                    &mut vec![r.into()],
                    &mut budget,
                )
                .unwrap();
            let used = MAX_EXPANDED_NODES - budget;
            assert!(used * 10 < MAX_EXPANDED_NODES, "{r} used {used}");
        }
        // All the ontology's contracts together, as `Context::load` resolves
        // them, under one budget.
        let ontology =
            crate::ontology::Ontology::load(&root.join("schemas/capability_ontology.yaml"))
                .unwrap();
        let mut budget = MAX_EXPANDED_NODES;
        for cap in ontology.capabilities.values() {
            for v in [&cap.input_schema, &cap.output_schema] {
                store.resolve_node(v, &mut budget).unwrap();
            }
        }
        let used = MAX_EXPANDED_NODES - budget;
        assert!(used * 10 < MAX_EXPANDED_NODES, "contracts used {used}");
    }

    #[test]
    fn same_file_refs_resolve_and_only_hops_count() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
        let store = SchemaStore::new(root);
        // event_schema's event uses `#/types/...` refs of its own file.
        let event = store
            .resolve_ref_deep("schemas/event_schema.yaml#/event", &mut {
                MAX_EXPANDED_NODES
            })
            .unwrap()
            .unwrap();
        let confidence = &event["properties"]["uncertainty"]["properties"]["confidence"];
        assert_eq!(confidence["type"], "number", "{event}");
        // Deep schemas resolve whatever their nesting: only hops count.
        let ws = store
            .resolve_ref_deep("schemas/world_state_schema.yaml#/world_state", &mut {
                MAX_EXPANDED_NODES
            })
            .unwrap()
            .unwrap();
        assert!(
            !ws.to_string().contains("\"$ref\""),
            "unresolved refs remain"
        );
    }
}
