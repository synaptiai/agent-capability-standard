//! Catalog manifests, catalog sets and qualified workflow ids (STANDARD
//! v1.2 §5.1.1).
//!
//! A validator or executor is given one catalog and, optionally, others: a
//! catalog set. Its workflows form one namespace keyed by the primary
//! catalog's workflow names and, for another catalog's workflows,
//! `<catalog id>/<name>`. With one catalog the keys are the names, so a
//! single catalog resolves exactly as in 1.1. [`Resolver::resolve`] is the
//! one resolution function the validator and the executor share.

use std::collections::{HashMap, HashSet};

use indexmap::IndexMap;
use serde_json::{Map, Value};

use crate::names;

/// A catalog and its header's version (§11.5).
pub type Member<'a> = (&'a Value, Option<&'a str>);

/// A catalog and, optionally, other catalogs (§5.1.1).
#[derive(Clone, Copy)]
pub struct CatalogSet<'a> {
    pub primary: &'a Value,
    pub header: Option<&'a str>,
    pub others: &'a [Member<'a>],
}

impl<'a> CatalogSet<'a> {
    pub fn single(primary: &'a Value, header: Option<&'a str>) -> Self {
        CatalogSet {
            primary,
            header,
            others: &[],
        }
    }
}

/// A catalog's manifest (§5.1.1): its top-level `catalog` value, when that
/// is a mapping without `steps` (with `steps` it is a workflow, as in 1.1).
pub fn manifest(doc: &Value) -> Option<&Map<String, Value>> {
    doc.get("catalog")
        .and_then(Value::as_object)
        .filter(|m| !m.contains_key("steps"))
}

/// The manifest's `id`, when it is a string.
pub fn manifest_id(doc: &Value) -> Option<&str> {
    manifest(doc)?.get("id")?.as_str()
}

/// What an `invoke` target resolves to (§5.1.1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Resolved {
    /// A workflow of the set, by its namespace key.
    Key(String),
    /// A qualified id of another catalog of the set that has the workflow
    /// but does not export it (V107; R402 at run time).
    NotExported { catalog: String, name: String },
    /// A qualified id of the invoking catalog or another catalog of the set
    /// that has no workflow of that name (V107; R402 at run time).
    Missing { catalog: String, name: String },
    /// Anything else: a bare name the invoking catalog lacks, or a qualified
    /// id of a catalog not in the set (W607; R402 at run time).
    Unresolved,
}

impl Resolved {
    pub fn key(&self) -> Option<&str> {
        match self {
            Resolved::Key(k) => Some(k),
            _ => None,
        }
    }
}

/// Resolves `invoke` targets over a catalog set. Catalog index 0 is the
/// primary.
#[derive(Debug, Clone, Default)]
pub struct Resolver {
    ids: Vec<Option<String>>,
    exports: Vec<HashSet<String>>,
    names: Vec<HashSet<String>>,
    origin: HashMap<String, usize>,
}

impl Resolver {
    fn key(&self, catalog: usize, name: &str) -> String {
        match (catalog, self.ids.get(catalog).and_then(Option::as_deref)) {
            (0, _) | (_, None) => name.to_string(),
            (_, Some(id)) => format!("{id}/{name}"),
        }
    }

    /// The catalog a namespace key belongs to (the primary for an unknown
    /// key).
    pub fn catalog_of(&self, key: &str) -> usize {
        self.origin.get(key).copied().unwrap_or(0)
    }

    /// Whether `target`, named by a step of `caller`, resolves through its
    /// qualified form (§5.1.1): it names no workflow of the caller's own
    /// catalog, and a workflow of a catalog of the set by its id. A 1.1
    /// consumer cannot resolve it (§11.5).
    pub fn resolves_qualified(&self, caller: &str, target: &str) -> bool {
        let own = self.catalog_of(caller);
        !self.names.get(own).is_some_and(|n| n.contains(target))
            && matches!(self.resolve(caller, target), Resolved::Key(_))
    }

    /// Resolve `target`, named by a step of the workflow `caller` (a
    /// namespace key), exactly as §5.1.1 orders it.
    pub fn resolve(&self, caller: &str, target: &str) -> Resolved {
        if target.starts_with("x-") {
            return Resolved::Unresolved;
        }
        let own = self.catalog_of(caller);
        if self.names.get(own).is_some_and(|n| n.contains(target)) {
            return Resolved::Key(self.key(own, target));
        }
        let Some((id, name)) = names::split_qualified(target) else {
            return Resolved::Unresolved;
        };
        let Some(c) = self.ids.iter().position(|i| i.as_deref() == Some(id)) else {
            return Resolved::Unresolved;
        };
        let (catalog, name_s) = (id.to_string(), name.to_string());
        if !self.names[c].contains(name) {
            return Resolved::Missing {
                catalog,
                name: name_s,
            };
        }
        if c != own && !self.exports[c].contains(name) {
            return Resolved::NotExported {
                catalog,
                name: name_s,
            };
        }
        Resolved::Key(self.key(c, name))
    }
}

/// One workflow of the namespace.
#[derive(Clone, Copy)]
struct Entry<'a> {
    catalog: usize,
    value: &'a Value,
}

/// The workflows of a catalog set, by namespace key, in catalog order then
/// document order.
pub struct Namespace<'a> {
    pub resolver: Resolver,
    entries: IndexMap<String, Entry<'a>>,
    docs: Vec<&'a Value>,
    headers: Vec<Option<&'a str>>,
    names: HashMap<String, String>,
}

impl<'a> Namespace<'a> {
    /// Build the namespace. Refused: another catalog that is not a
    /// mapping, has no manifest or no string `id`, or two catalogs with one
    /// `id` (§5.1.1).
    pub fn build(set: CatalogSet<'a>) -> Result<Namespace<'a>, String> {
        let mut docs = vec![set.primary];
        let mut headers = vec![set.header];
        for (i, (doc, header)) in set.others.iter().enumerate() {
            if !doc.is_object() {
                return Err(format!("catalog {} of the set is not a mapping", i + 1));
            }
            if manifest_id(doc).is_none() {
                return Err(format!(
                    "catalog {} of the set has no manifest with a string 'id'; every catalog given beside the one validated or run needs one (§5.1.1)",
                    i + 1
                ));
            }
            docs.push(doc);
            headers.push(*header);
        }
        let ids: Vec<Option<String>> = docs
            .iter()
            .map(|d| manifest_id(d).map(str::to_string))
            .collect();
        let mut seen = HashSet::new();
        for id in ids.iter().flatten() {
            if !seen.insert(id.as_str()) {
                return Err(format!(
                    "two catalogs of the set have the id '{id}'; ids are unique in a set (§5.1.1)"
                ));
            }
        }
        let mut resolver = Resolver {
            ids,
            ..Resolver::default()
        };
        let mut entries = IndexMap::new();
        let mut names = HashMap::new();
        for (c, doc) in docs.iter().enumerate() {
            let exports: HashSet<String> = manifest(doc)
                .and_then(|m| m.get("exports"))
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect();
            resolver.exports.push(exports);
            let mut own = HashSet::new();
            let Some(map) = doc.as_object() else {
                resolver.names.push(own);
                continue;
            };
            for (name, value) in map {
                if name.starts_with("x-") || (name == "catalog" && manifest(doc).is_some()) {
                    continue;
                }
                own.insert(name.clone());
                let key = resolver.key(c, name);
                if entries.contains_key(&key) {
                    continue;
                }
                resolver.origin.insert(key.clone(), c);
                names.insert(key.clone(), name.clone());
                entries.insert(key, Entry { catalog: c, value });
            }
            resolver.names.push(own);
        }
        Ok(Namespace {
            resolver,
            entries,
            docs,
            headers,
            names,
        })
    }

    /// The namespace's own copy of `key`, when it has one.
    pub fn get_key(&self, key: &str) -> Option<&str> {
        self.entries.get_key_value(key).map(|(k, _)| k.as_str())
    }

    pub fn get(&self, key: &str) -> Option<&'a Value> {
        self.entries.get(key).map(|e| e.value)
    }

    /// Every workflow: its key and value, in catalog then document order.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &'a Value)> {
        self.entries.iter().map(|(k, e)| (k.as_str(), e.value))
    }

    /// A key's position in namespace order (the order of reports).
    pub fn position(&self, key: &str) -> Option<usize> {
        self.entries.get_index_of(key)
    }

    pub fn catalog_of(&self, key: &str) -> usize {
        self.entries.get(key).map_or(0, |e| e.catalog)
    }

    /// The workflow's name in its own catalog.
    pub fn name_of<'k>(&'k self, key: &'k str) -> &'k str {
        self.names.get(key).map_or(key, String::as_str)
    }

    pub fn header_of(&self, key: &str) -> Option<&'a str> {
        self.headers[self.catalog_of(key)]
    }

    pub fn doc(&self, i: usize) -> &'a Value {
        self.docs[i]
    }

    pub fn header(&self, i: usize) -> Option<&'a str> {
        self.headers[i]
    }

    pub fn id(&self, i: usize) -> Option<&str> {
        self.resolver.ids.get(i).and_then(Option::as_deref)
    }

    pub fn len(&self) -> usize {
        self.docs.len()
    }

    pub fn is_empty(&self) -> bool {
        false
    }

    /// The set has more than the primary catalog.
    pub fn is_set(&self) -> bool {
        self.docs.len() > 1
    }

    /// The catalog index of the catalog whose id is `id`.
    pub fn index_of_id(&self, id: &str) -> Option<usize> {
        self.resolver
            .ids
            .iter()
            .position(|i| i.as_deref() == Some(id))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn lib() -> Value {
        json!({
            "catalog": {"id": "acs.fixtures.lib", "version": "1.0.0", "exports": ["shared_check"]},
            "shared_check": {"steps": []},
            "inner": {"steps": []}
        })
    }

    #[test]
    fn resolves_the_four_outcomes() {
        let primary = json!({
            "catalog": {"id": "acs.fixtures.main", "version": "1.0.0"},
            "a": {"steps": []},
            "inner": {"steps": []},
            "x-vendor": 1
        });
        let lib = lib();
        let others = [(&lib, Some("1.2.0"))];
        let ns = Namespace::build(CatalogSet {
            primary: &primary,
            header: None,
            others: &others,
        })
        .unwrap();
        let keys: Vec<&str> = ns.iter().map(|(k, _)| k).collect();
        assert_eq!(
            keys,
            [
                "a",
                "inner",
                "acs.fixtures.lib/shared_check",
                "acs.fixtures.lib/inner"
            ]
        );
        let r = &ns.resolver;
        assert_eq!(r.resolve("a", "inner"), Resolved::Key("inner".into()));
        assert_eq!(
            r.resolve("a", "acs.fixtures.lib/shared_check"),
            Resolved::Key("acs.fixtures.lib/shared_check".into())
        );
        assert!(matches!(
            r.resolve("a", "acs.fixtures.lib/inner"),
            Resolved::NotExported { .. }
        ));
        assert!(matches!(
            r.resolve("a", "acs.fixtures.lib/nope"),
            Resolved::Missing { .. }
        ));
        assert_eq!(r.resolve("a", "other.cat/x"), Resolved::Unresolved);
        assert_eq!(r.resolve("a", "nope"), Resolved::Unresolved);
        assert_eq!(r.resolve("a", "x-vendor"), Resolved::Unresolved);
        // Own-qualified ids, present and missing.
        assert_eq!(
            r.resolve("a", "acs.fixtures.main/inner"),
            Resolved::Key("inner".into())
        );
        assert!(matches!(
            r.resolve("a", "acs.fixtures.main/zzz"),
            Resolved::Missing { .. }
        ));
        // A bare name inside the library means the library's workflow,
        // and a library may name its own unexported workflow.
        assert_eq!(
            r.resolve("acs.fixtures.lib/shared_check", "inner"),
            Resolved::Key("acs.fixtures.lib/inner".into())
        );
        assert_eq!(
            r.resolve("acs.fixtures.lib/shared_check", "acs.fixtures.lib/inner"),
            Resolved::Key("acs.fixtures.lib/inner".into())
        );
        assert_eq!(ns.name_of("acs.fixtures.lib/inner"), "inner");
        assert_eq!(ns.header_of("acs.fixtures.lib/inner"), Some("1.2.0"));
    }

    #[test]
    fn refuses_bad_sets() {
        let primary = json!({"w": {"steps": []}});
        let bare = json!({"w": {"steps": []}});
        let lib = lib();
        for (others, why) in [
            (vec![(&bare, None)], "no manifest"),
            (vec![(&lib, None), (&lib, None)], "two catalogs"),
        ] {
            let err = Namespace::build(CatalogSet {
                primary: &primary,
                header: None,
                others: &others,
            })
            .err()
            .unwrap();
            assert!(err.contains(why), "{err}");
        }
    }

    #[test]
    fn a_catalog_mapping_with_steps_is_a_workflow() {
        let doc = json!({"catalog": {"steps": []}});
        assert!(manifest(&doc).is_none());
        let ns = Namespace::build(CatalogSet::single(&doc, None)).unwrap();
        assert!(ns.get("catalog").is_some());
    }
}
