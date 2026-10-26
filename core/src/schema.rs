//! JSON-Schema-like documents: `$ref` resolution and path navigation.
//!
//! Workflow inputs, `output_conforms_to` and ontology contracts reference
//! schema files relative to a schema root (the repository root). References
//! that try to leave the root, or name absolute paths, resolve to nothing.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::rc::Rc;

use serde_json::{Map, Value};

use crate::refs::Seg;
use crate::yaml;

/// Maximum `$ref` hops followed while resolving one node.
const MAX_REF_DEPTH: usize = 12;

/// Loads schema files under one root, caching each file.
pub struct SchemaStore {
    root: PathBuf,
    cache: RefCell<HashMap<PathBuf, Option<Rc<Value>>>>,
}

impl SchemaStore {
    pub fn new(root: impl Into<PathBuf>) -> SchemaStore {
        SchemaStore {
            root: root.into(),
            cache: RefCell::new(HashMap::new()),
        }
    }

    pub fn root(&self) -> &Path {
        &self.root
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
    pub fn document(&self, rel: &str) -> Option<Rc<Value>> {
        let path = self.locate(rel)?;
        if let Some(hit) = self.cache.borrow().get(&path) {
            return hit.clone();
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
        .map(Rc::new);
        self.cache.borrow_mut().insert(path, doc.clone());
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
    /// over the target, as the reference validator always has.
    pub fn resolve_node(&self, node: &Value) -> Value {
        self.resolve_inner(node, 0)
    }

    fn resolve_inner(&self, node: &Value, depth: usize) -> Value {
        if depth > MAX_REF_DEPTH {
            return node.clone();
        }
        match node {
            Value::Object(m) => {
                if let Some(Value::String(r)) = m.get("$ref") {
                    if let Some(Value::Object(target)) = self.resolve_ref(r) {
                        let mut merged = target;
                        for (k, v) in m {
                            if k != "$ref" {
                                merged.insert(k.clone(), v.clone());
                            }
                        }
                        return self.resolve_inner(&Value::Object(merged), depth + 1);
                    }
                    return node.clone();
                }
                let out: Map<String, Value> = m
                    .iter()
                    .map(|(k, v)| (k.clone(), self.resolve_inner(v, depth + 1)))
                    .collect();
                Value::Object(out)
            }
            Value::Array(a) => {
                Value::Array(a.iter().map(|v| self.resolve_inner(v, depth + 1)).collect())
            }
            other => other.clone(),
        }
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

/// `type: array`, or a type list that includes `array` (e.g. nullable arrays).
fn is_array_schema(s: &Value) -> bool {
    match s.get("type") {
        Some(Value::String(t)) => t == "array",
        Some(Value::Array(ts)) => ts.iter().any(|t| t == "array"),
        _ => false,
    }
}

/// Declares a type, or is an object by virtue of `properties`.
fn is_typed(s: &Value) -> bool {
    s.get("type").is_some() || s.get("properties").is_some()
}

fn items_of(s: &Value) -> &Value {
    static EMPTY: Value = Value::Null;
    s.get("items").unwrap_or(&EMPTY)
}

/// The schema node a reference path selects, or `None` if the path leaves the
/// schema. A field selected on an array applies to its items (implicit
/// projection, as STANDARD v1.0 validators have always done); `[n]` selects
/// the items; a slice keeps the array.
pub fn node_at<'a>(schema: &'a Value, path: &[Seg]) -> Option<&'a Value> {
    let mut cur = schema;
    for seg in path {
        match seg {
            Seg::Field(name) => {
                if is_array_schema(cur) {
                    cur = items_of(cur);
                }
                cur = cur.get("properties")?.as_object()?.get(name)?;
            }
            // Indexing a node that declares no type cannot be checked, so it
            // stays untyped; indexing a node of another type is an error.
            Seg::Index(_) => {
                if is_array_schema(cur) {
                    cur = items_of(cur);
                } else if is_typed(cur) {
                    return None;
                }
            }
            Seg::Slice(..) => {
                if !is_array_schema(cur) && is_typed(cur) {
                    return None;
                }
            }
        }
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
        assert_eq!(
            node_at(&s, &[field("items"), field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert_eq!(
            node_at(&s, &[field("items"), Seg::Index(0), field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert!(node_at(&s, &[field("items"), Seg::Slice(Some(0), Some(2))]).is_some());
        assert_eq!(node_at(&s, &[field("n"), Seg::Index(0)]), None);
        // An object declared only by `properties` cannot be indexed.
        let obj = json!({"properties": {"x": {"type": "string"}}});
        assert_eq!(node_at(&obj, &[Seg::Index(3)]), None);
        // Nullable arrays index and project like arrays.
        let nullable =
            json!({"type": ["array", "null"], "items": {"properties": {"id": {"type": "string"}}}});
        assert_eq!(
            node_at(&nullable, &[Seg::Index(0), field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert_eq!(
            node_at(&nullable, &[field("id")]),
            Some(&json!({"type": "string"}))
        );
        assert_eq!(node_at(&s, &[field("missing")]), None);
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
        let node = store.resolve_node(
            &json!({"$ref": "schemas/world_state_schema.yaml#/world_state", "description": "x"}),
        );
        assert_eq!(node["description"], "x");
    }
}
