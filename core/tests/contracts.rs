//! The schema dialect at ontology load (STANDARD v1.2 §4.1.2): a contract's
//! same-file `$ref` names a node of the ontology; one whose `$ref` names
//! nothing, is cyclic or nests deeper than the limit is refused; and a context built from documents in memory resolves and
//! validates exactly as one read from disk.

use std::path::{Path, PathBuf};

use acs_core::validate::{Context, LoadError, validate_catalog, validate_catalog_file};
use acs_core::yaml;
use serde_json::{Value, json};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn ontology() -> Value {
    yaml::load_file(
        &root().join("schemas/capability_ontology.yaml"),
        yaml::ONTOLOGY_MAX_BYTES,
    )
    .unwrap()
}

/// The repository ontology with `retrieve`'s output contract replaced.
fn with_retrieve_output(output: Value) -> Value {
    let mut doc = ontology();
    for node in doc["nodes"].as_array_mut().unwrap() {
        if node["id"] == "retrieve" {
            node["output_schema"] = output.clone();
        }
    }
    doc
}

/// Every schema document under `schemas/`, keyed by its repository path.
fn repository_documents() -> Vec<(String, Value)> {
    let mut out = Vec::new();
    let mut stack = vec![root().join("schemas")];
    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let rel = path
                .strip_prefix(root())
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            let value = match path.extension().and_then(|e| e.to_str()) {
                Some("yaml" | "yml") => yaml::load_file(&path, yaml::ONTOLOGY_MAX_BYTES).ok(),
                Some("json") => serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).ok(),
                _ => None,
            };
            if let Some(v) = value {
                out.push((rel, v));
            }
        }
    }
    out
}

fn refused(doc: &Value, documents: Vec<(String, Value)>) -> String {
    match Context::from_values(doc, documents) {
        Err(LoadError::Invalid(m)) => m,
        Err(other) => panic!("not an invalid ontology: {other}"),
        Ok(_) => panic!("the ontology loaded"),
    }
}

#[test]
fn a_ref_that_names_nothing_is_refused() {
    let doc = with_retrieve_output(json!({"$ref": "schemas/nowhere.yaml#/x"}));
    let m = refused(&doc, repository_documents());
    assert!(m.contains("output schema of capability 'retrieve'"), "{m}");
    assert!(m.contains("schemas/nowhere.yaml#/x"), "{m}");
}

#[test]
fn a_cyclic_ref_is_refused() {
    let doc = with_retrieve_output(json!({"type": "object", "properties": {
        "a": {"$ref": "a.yaml#/A"}}}));
    let mut documents = repository_documents();
    documents.push(("a.yaml".into(), json!({"A": {"$ref": "a.yaml#/A"}})));
    let m = refused(&doc, documents);
    assert!(m.contains("'a.yaml#/A' at '/properties/a'"), "{m}");
}

/// The repository ontology with a top-level `x-defs` and `retrieve`'s
/// output contract replaced.
fn with_local_defs(defs: Value, output: Value) -> Value {
    let mut doc = with_retrieve_output(output);
    doc["x-defs"] = defs;
    doc
}

#[test]
fn a_same_file_ref_names_a_node_of_the_ontology() {
    // §4.1.2: `$ref: "#<pointer>"` names a node of the file it is in, here
    // the ontology, from memory and from disk alike; a same-file ref inside
    // what it names resolves there too.
    let doc = with_local_defs(
        json!({"Thing": {"type": "object", "properties": {"inner": {"$ref": "#/x-defs/Inner"}}},
               "Inner": {"type": "string"}}),
        json!({"type": "object", "properties": {"x_local": {"$ref": "#/x-defs/Thing"}}}),
    );
    let expected = json!({"type": "object", "properties": {"x_local": {
        "type": "object", "properties": {"inner": {"type": "string"}}}}});
    let ctx = Context::from_values(&doc, repository_documents())
        .unwrap_or_else(|e| panic!("a same-file ref loads: {e}"));
    assert_eq!(ctx.contracts_json()["retrieve"]["output"], expected);
    let dir = std::env::temp_dir().join(format!("acs-same-file-ref-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("ontology.json");
    std::fs::write(&path, serde_json::to_string(&doc).unwrap()).unwrap();
    let from_disk = Context::load(&path, &root());
    std::fs::remove_dir_all(&dir).unwrap();
    let from_disk = from_disk.unwrap_or_else(|e| panic!("from disk: {e}"));
    assert_eq!(from_disk.contracts_json()["retrieve"]["output"], expected);
}

#[test]
fn a_same_file_ref_that_names_nothing_or_cycles_is_refused() {
    let doc = with_local_defs(
        json!({}),
        json!({"type": "object", "properties": {"x_local": {"$ref": "#/x-defs/Nowhere"}}}),
    );
    let m = refused(&doc, repository_documents());
    assert!(
        m.contains("'#/x-defs/Nowhere' at '/properties/x_local'"),
        "{m}"
    );
    let doc = with_local_defs(
        json!({"Loop": {"$ref": "#/x-defs/Loop"}}),
        json!({"$ref": "#/x-defs/Loop"}),
    );
    let m = refused(&doc, repository_documents());
    assert!(m.contains("'#/x-defs/Loop'"), "{m}");
}

/// A chain of `refs` `$ref`s ending at a schema.
fn chain(refs: usize) -> Vec<(String, Value)> {
    let mut out = repository_documents();
    let mut doc = serde_json::Map::new();
    for i in 0..refs {
        doc.insert(
            format!("r{i}"),
            json!({"$ref": format!("c.yaml#/r{}", i + 1)}),
        );
    }
    doc.insert(format!("r{refs}"), json!({"type": "object"}));
    out.push(("c.yaml".into(), Value::Object(doc)));
    out
}

#[test]
fn a_chain_deeper_than_twelve_is_refused() {
    // The contract's own $ref is the first of the chain.
    let doc = with_retrieve_output(json!({"$ref": "c.yaml#/r0"}));
    if let Err(e) = Context::from_values(&doc, chain(11)) {
        panic!("a chain of twelve loads: {e}");
    }
    let m = refused(&doc, chain(12));
    assert!(m.contains("nests deeper than 12"), "{m}");
}

#[test]
fn the_repository_ontology_loads_from_memory_as_from_disk() {
    let root = root();
    let disk = Context::load(&root.join("schemas/capability_ontology.yaml"), &root).unwrap();
    let memory = Context::from_values(&ontology(), repository_documents()).unwrap();
    assert_eq!(disk.contracts_json(), memory.contracts_json());
    let fixtures = root.join("tests/fixtures");
    let mut checked = 0;
    for entry in std::fs::read_dir(&fixtures).unwrap() {
        let path = entry.unwrap().path();
        if !path.to_string_lossy().ends_with(".workflow_catalog.yaml") {
            continue;
        }
        let Ok(on_disk) = validate_catalog_file(&disk, &path) else {
            continue;
        };
        let text = std::fs::read_to_string(&path).unwrap();
        let catalog = yaml::load_str(&text).unwrap();
        let header = acs_core::validate::header_version(&text);
        let in_memory = validate_catalog(&memory, &catalog, header.as_deref());
        assert_eq!(
            serde_json::to_value(&on_disk.diagnostics).unwrap(),
            serde_json::to_value(&in_memory.diagnostics).unwrap(),
            "{}",
            path.display()
        );
        checked += 1;
    }
    assert!(checked > 50, "{checked}");
}
