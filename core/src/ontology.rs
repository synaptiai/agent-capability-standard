//! The capability ontology (`schemas/capability_ontology.yaml`).

use std::path::Path;

use indexmap::IndexMap;
use serde_json::Value;

use crate::yaml::{self, YamlError};

/// Risk level of a capability or step. Ordered: `Low < Medium < High`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Risk {
    Low,
    Medium,
    High,
}

impl Risk {
    pub fn parse(s: &str) -> Option<Risk> {
        match s {
            "low" => Some(Risk::Low),
            "medium" => Some(Risk::Medium),
            "high" => Some(Risk::High),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Risk::Low => "low",
            Risk::Medium => "medium",
            Risk::High => "high",
        }
    }
}

/// One capability node.
#[derive(Debug, Clone)]
pub struct Capability {
    pub id: String,
    pub layer: String,
    pub risk: Risk,
    pub mutation: bool,
    pub requires_checkpoint: bool,
    pub requires_approval: bool,
    /// A step may declare `mutation: false` for this capability (STANDARD
    /// v1.1 §5.2; set on `audit`, whose writes are append-only).
    pub mutation_overridable: bool,
    pub input_schema: Value,
    pub output_schema: Value,
}

/// The seven edge types of `spec/EDGE_TYPES.md`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EdgeType {
    Requires,
    SoftRequires,
    Enables,
    Precedes,
    ConflictsWith,
    AlternativeTo,
    Specializes,
}

impl EdgeType {
    pub fn parse(s: &str) -> Option<EdgeType> {
        Some(match s {
            "requires" => EdgeType::Requires,
            "soft_requires" => EdgeType::SoftRequires,
            "enables" => EdgeType::Enables,
            "precedes" => EdgeType::Precedes,
            "conflicts_with" => EdgeType::ConflictsWith,
            "alternative_to" => EdgeType::AlternativeTo,
            "specializes" => EdgeType::Specializes,
            _ => return None,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Edge {
    pub from: String,
    pub to: String,
    pub kind: EdgeType,
}

/// The loaded ontology: capabilities in file order, plus edges.
#[derive(Debug, Clone, Default)]
pub struct Ontology {
    pub capabilities: IndexMap<String, Capability>,
    pub edges: Vec<Edge>,
}

fn flag(node: &serde_json::Map<String, Value>, key: &str, id: &str) -> Result<bool, String> {
    match node.get(key) {
        None => Ok(false),
        Some(Value::Bool(b)) => Ok(*b),
        Some(_) => Err(format!("capability '{id}': '{key}' must be a boolean")),
    }
}

impl Ontology {
    pub fn load(path: &Path) -> Result<Ontology, String> {
        let doc = yaml::load_file(path, yaml::ONTOLOGY_MAX_BYTES)
            .map_err(|e: YamlError| format!("cannot load ontology: {e}"))?;
        Ontology::from_value(&doc)
    }

    pub fn from_value(doc: &Value) -> Result<Ontology, String> {
        let nodes = doc
            .get("nodes")
            .and_then(Value::as_array)
            .ok_or("ontology has no 'nodes' list")?;
        let mut capabilities = IndexMap::new();
        for node in nodes {
            let node = node.as_object().ok_or("ontology node is not a mapping")?;
            let id = node
                .get("id")
                .and_then(Value::as_str)
                .ok_or("ontology node without a string 'id'")?
                .to_string();
            let risk = match node.get("risk").and_then(Value::as_str) {
                None => Risk::Low,
                Some(r) => Risk::parse(r)
                    .ok_or_else(|| format!("capability '{id}': unknown risk '{r}'"))?,
            };
            let cap = Capability {
                layer: node
                    .get("layer")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                risk,
                mutation: flag(node, "mutation", &id)?,
                requires_checkpoint: flag(node, "requires_checkpoint", &id)?,
                requires_approval: flag(node, "requires_approval", &id)?,
                mutation_overridable: flag(node, "mutation_overridable", &id)?,
                input_schema: node.get("input_schema").cloned().unwrap_or(Value::Null),
                output_schema: node.get("output_schema").cloned().unwrap_or(Value::Null),
                id: id.clone(),
            };
            // An override may only drop a mutation no other control
            // protects (STANDARD v1.1 §5.2).
            if cap.mutation_overridable
                && (!cap.mutation
                    || cap.risk != Risk::Low
                    || cap.requires_checkpoint
                    || cap.requires_approval)
            {
                return Err(format!(
                    "capability '{id}': mutation_overridable needs mutation: true, risk: low \
                     and neither requires_checkpoint nor requires_approval"
                ));
            }
            if capabilities.insert(id.clone(), cap).is_some() {
                return Err(format!("duplicate capability id '{id}'"));
            }
        }
        let mut edges = Vec::new();
        for e in doc
            .get("edges")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let get = |k: &str| e.get(k).and_then(Value::as_str);
            let (Some(from), Some(to), Some(kind)) = (get("from"), get("to"), get("type")) else {
                return Err("ontology edge needs string 'from', 'to' and 'type'".into());
            };
            let kind =
                EdgeType::parse(kind).ok_or_else(|| format!("unknown edge type '{kind}'"))?;
            edges.push(Edge {
                from: from.to_string(),
                to: to.to_string(),
                kind,
            });
        }
        Ok(Ontology {
            capabilities,
            edges,
        })
    }

    pub fn get(&self, id: &str) -> Option<&Capability> {
        self.capabilities.get(id)
    }

    /// Sources of edges of `kind` that point at `to`, in file order.
    pub fn incoming(&self, to: &str, kind: EdgeType) -> Vec<&str> {
        self.edges
            .iter()
            .filter(|e| e.kind == kind && e.to == to)
            .map(|e| e.from.as_str())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn loads_nodes_and_edges() {
        let doc = json!({
            "nodes": [
                {"id": "checkpoint", "layer": "VERIFY", "risk": "low", "mutation": true},
                {"id": "mutate", "layer": "EXECUTE", "risk": "high", "mutation": true,
                 "requires_checkpoint": true, "requires_approval": true}
            ],
            "edges": [{"from": "checkpoint", "to": "mutate", "type": "requires"}]
        });
        let o = Ontology::from_value(&doc).unwrap();
        let m = o.get("mutate").unwrap();
        assert_eq!(m.risk, Risk::High);
        assert!(m.requires_checkpoint && m.requires_approval && !m.mutation_overridable);
        assert_eq!(o.incoming("mutate", EdgeType::Requires), ["checkpoint"]);
    }

    #[test]
    fn mutation_overridable_only_where_harmless() {
        let node = |extra: Value| {
            let mut n = json!({"id": "x", "layer": "L", "mutation": true,
                "mutation_overridable": true});
            for (k, v) in extra.as_object().unwrap() {
                n[k] = v.clone();
            }
            Ontology::from_value(&json!({"nodes": [n], "edges": []}))
        };
        assert!(node(json!({})).is_ok());
        for bad in [
            json!({"mutation": false}),
            json!({"risk": "medium"}),
            json!({"requires_checkpoint": true}),
            json!({"requires_approval": true}),
        ] {
            let err = node(bad.clone()).err().unwrap_or_default();
            assert!(err.contains("mutation_overridable"), "{bad}: {err}");
        }
    }

    #[test]
    fn rejects_malformed_ontologies() {
        assert!(Ontology::from_value(&json!({})).is_err());
        assert!(Ontology::from_value(&json!({"nodes": [{"id": "a"}, {"id": "a"}]})).is_err());
        assert!(Ontology::from_value(&json!({"nodes": [{"id": "a", "risk": "extreme"}]})).is_err());
        assert!(
            Ontology::from_value(
                &json!({"nodes": [], "edges": [{"from": "a", "to": "b", "type": "x"}]})
            )
            .is_err()
        );
    }

    #[test]
    fn loads_the_repository_ontology() {
        let path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../schemas/capability_ontology.yaml");
        let o = Ontology::load(&path).unwrap();
        assert_eq!(o.capabilities.len(), 36);
        assert!(o.get("send").unwrap().requires_approval);
    }
}
