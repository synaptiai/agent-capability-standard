//! A catalog's manifest (STANDARD v1.2 §5.1.1): its `id`, `version`,
//! `ontology` and `exports`.

use serde_json::{Map, Value};

use super::semantics::{closest, parse_version};
use super::{Context, Report};
use crate::catalogs::{self, Namespace};
use crate::diag::{Code, Diagnostic};
use crate::names;
use crate::yaml;

const MEMBERS: &[&str] = &["id", "version", "ontology", "exports", "description"];

/// Check the manifest of the set's catalog `c`, if it has one. Every
/// finding is at `catalog.<member>`, with `catalog: <id>` for a catalog
/// other than the primary.
pub(crate) fn check_manifest(ctx: &Context, ns: &Namespace<'_>, c: usize, report: &mut Report) {
    let doc = ns.doc(c);
    let Some(m) = catalogs::manifest(doc) else {
        return;
    };
    let other = (c != 0).then(|| ns.id(c)).flatten();
    let at = |d: Diagnostic| match other {
        Some(id) => d.at("catalog", id),
        None => d,
    };
    let s303 = |field: String, message: String| {
        at(Diagnostic::new(Code::SchemaValidationFailed, message)).at("field", field)
    };
    for (member, ok, shape) in [
        (
            "id",
            m.get("id")
                .and_then(Value::as_str)
                .is_some_and(names::is_catalog_id),
            "a catalog id: segments [a-z0-9][a-z0-9_-]* joined by '.'",
        ),
        (
            "version",
            m.get("version")
                .and_then(Value::as_str)
                .is_some_and(names::is_semver),
            "a Semantic Versioning 2.0.0 version, such as 1.0.0",
        ),
    ] {
        match m.get(member) {
            None => report.push(
                at(Diagnostic::new(
                    Code::MissingRequiredField,
                    format!("the catalog manifest has no '{member}'"),
                ))
                .at("field", format!("catalog.{member}")),
            ),
            Some(v) if !ok => report.push(s303(
                format!("catalog.{member}"),
                format!("catalog '{member}' must be {shape}; found {}", shown(v)),
            )),
            Some(_) => {}
        }
    }
    if let Some(v) = m.get("ontology") {
        match v.as_str().and_then(parse_version) {
            None => report.push(s303(
                "catalog.ontology".into(),
                format!(
                    "catalog 'ontology' must be a version MAJOR.MINOR[.PATCH]; found {}",
                    shown(v)
                ),
            )),
            Some((major, _)) => {
                let loaded = ctx.ontology.version.as_deref().unwrap_or("0");
                let loaded_major = loaded.split('.').next().and_then(|m| m.parse::<u64>().ok());
                if loaded_major.is_some_and(|l| l != major) {
                    report.push(
                        at(Diagnostic::new(
                            Code::UnsupportedSpecVersion,
                            format!(
                                "the catalog is written against ontology {}, but this validator uses ontology {loaded}; another major is not compatible (§5.1.1)",
                                v.as_str().unwrap_or_default()
                            ),
                        ))
                        .at("field", "catalog.ontology"),
                    );
                }
            }
        }
    }
    if let Some(v) = m.get("description")
        && !v.is_string()
    {
        report.push(s303(
            "catalog.description".into(),
            format!(
                "catalog 'description' must be a string, found {}",
                yaml::kind_of(v)
            ),
        ));
    }
    check_exports(doc, m, &at, report);
    for key in m.keys() {
        if MEMBERS.contains(&key.as_str()) || key.starts_with("x-") {
            continue;
        }
        let mut d = at(Diagnostic::new(
            Code::UnknownField,
            format!("unknown field 'catalog.{key}' is ignored"),
        ))
        .at_field_key("catalog", key);
        if let Some(k) = closest(key, MEMBERS) {
            d = d.suggest(format!("did you mean '{k}'?"));
        }
        report.push(d);
    }
    // A manifest is new in 1.2: its file's header is its Standard version
    // (§11.5), which serves as the manifest's `standard` (§11.6).
    if let Some(header) = ns.header(c)
        && let Some((major, minor)) = parse_version(header)
        && (major, minor) < (1, 2)
    {
        report.push(
            at(Diagnostic::new(
                Code::VersionFeatureMismatch,
                format!(
                    "the catalog targets standard {header} by the file's '# Standard version' header, but a catalog manifest is new in 1.2 and a {major}.{minor} consumer does not know it"
                ),
            ))
            .at("field", "catalog")
            .suggest("declare a 1.2 header"),
        );
    }
}

fn check_exports(
    doc: &Value,
    m: &Map<String, Value>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Some(v) = m.get("exports") else {
        return;
    };
    let Value::Array(items) = v else {
        report.push(
            at(Diagnostic::new(
                Code::SchemaValidationFailed,
                format!(
                    "catalog 'exports' must be a list of workflow names, found {}",
                    yaml::kind_of(v)
                ),
            ))
            .at("field", "catalog.exports"),
        );
        return;
    };
    let workflows: Vec<&str> = doc
        .as_object()
        .into_iter()
        .flat_map(|d| d.iter())
        .filter(|(k, w)| {
            !k.starts_with("x-") && !(k.as_str() == "catalog" && w.get("steps").is_none())
        })
        .map(|(k, _)| k.as_str())
        .collect();
    let mut seen: Vec<&str> = Vec::new();
    for (i, item) in items.iter().enumerate() {
        let field = format!("catalog.exports[{i}]");
        let Value::String(name) = item else {
            report.push(
                at(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!(
                        "catalog 'exports' entries must be strings, found {}",
                        yaml::kind_of(item)
                    ),
                ))
                .at("field", field),
            );
            continue;
        };
        if seen.contains(&name.as_str()) {
            report.push(
                at(Diagnostic::new(
                    Code::SchemaValidationFailed,
                    format!("catalog 'exports' lists '{name}' twice"),
                ))
                .at("field", field),
            );
            continue;
        }
        seen.push(name);
        if !workflows.contains(&name.as_str()) {
            let mut d = at(Diagnostic::new(
                Code::UnresolvedTarget,
                format!("catalog 'exports' names '{name}', which is not a workflow of the catalog"),
            ))
            .at("field", field);
            if let Some(k) = closest(name, &workflows) {
                d = d.suggest(format!("did you mean '{k}'?"));
            }
            report.push(d);
        }
    }
}

fn shown(v: &Value) -> String {
    match v {
        Value::String(s) => format!("'{s}'"),
        other => other.to_string(),
    }
}
