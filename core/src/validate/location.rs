//! Diagnostic locations (STANDARD v1.2 §9.8): the `path` every finding
//! about the catalog document carries, and `catalog` for a finding in
//! another catalog of the set.

use serde_json::Value;

use super::Report;
use crate::catalogs::Namespace;

/// The `field` of a finding about the version header.
pub(crate) const HEADER_FIELD: &str = "# Standard version";

/// Finish a report's locations: a finding in another catalog of the set
/// gets `catalog` and its workflow's own name; every finding about a
/// catalog document gets `path`. A finding about another document (one
/// with `profile` or `tool`) or about the version header gets no `path`.
pub(crate) fn finish(ns: &Namespace<'_>, report: &mut Report) {
    for d in &mut report.diagnostics {
        let loc = &d.location;
        if loc.contains_key("profile")
            || loc.contains_key("tool")
            || loc.get("field").and_then(Value::as_str) == Some(HEADER_FIELD)
        {
            continue;
        }
        let mut workflow: Option<String> = None;
        if let Some(key) = loc.get("workflow").and_then(Value::as_str) {
            let c = ns.catalog_of(key);
            let name = ns.name_of(key).to_string();
            if c != 0 {
                if let Some(id) = ns.id(c) {
                    d.location
                        .insert("catalog".to_string(), Value::String(id.to_string()));
                }
                d.location
                    .insert("workflow".to_string(), Value::String(name.clone()));
            }
            workflow = Some(name);
        }
        let step = d.location.get("step").and_then(Value::as_u64);
        let tokens = d.field_tokens();
        d.location.insert(
            "path".to_string(),
            Value::String(pointer(workflow.as_deref(), step, &tokens)),
        );
    }
}

/// Escape one RFC 6901 reference token.
fn escape(token: &str) -> String {
    token.replace('~', "~0").replace('/', "~1")
}

/// The JSON Pointer of a member: the workflow, then `steps/<step>`, then
/// the field's tokens, each escaped; `""` for the document. It does not
/// consult the document, so a missing member gets the pointer where it
/// would be.
pub(crate) fn pointer(workflow: Option<&str>, step: Option<u64>, tokens: &[String]) -> String {
    let mut out = String::new();
    if let Some(w) = workflow {
        out.push('/');
        out.push_str(&escape(w));
        if let Some(s) = step {
            out.push_str(&format!("/steps/{s}"));
        }
    }
    for t in tokens {
        out.push('/');
        out.push_str(&escape(t));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalogs::CatalogSet;
    use crate::diag::{Code, Diagnostic};
    use serde_json::json;

    #[test]
    fn pointers() {
        let t = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(pointer(None, None, &[]), "");
        assert_eq!(
            pointer(Some("review"), Some(1), &t(&["gates", "0", "when"])),
            "/review/steps/1/gates/0/when"
        );
        assert_eq!(
            pointer(Some("w"), None, &t(&["triggers", "0", "schedule", "cron"])),
            "/w/triggers/0/schedule/cron"
        );
        assert_eq!(
            pointer(None, None, &t(&["catalog", "exports", "1"])),
            "/catalog/exports/1"
        );
        assert_eq!(pointer(Some("a/b~c"), None, &[]), "/a~1b~0c");
    }

    #[test]
    fn other_documents_get_no_path() {
        let doc = json!({"w": {"steps": []}});
        let ns = Namespace::build(CatalogSet::single(&doc, None)).unwrap();
        let mut report = Report::default();
        report.push(
            Diagnostic::new(Code::UnknownField, "p")
                .at("profile", "vision")
                .at("field", "trust_weights.x"),
        );
        report.push(
            Diagnostic::new(Code::SafetyFlagDowngrade, "t")
                .at("tool", "Bash")
                .at("capability", "execute")
                .at("field", "requires_approval"),
        );
        report.push(
            Diagnostic::new(Code::UnsupportedSpecVersion, "h")
                .at("workflow", "w")
                .at("field", HEADER_FIELD),
        );
        report.push(Diagnostic::new(Code::UnknownField, "w").at("workflow", "w"));
        finish(&ns, &mut report);
        let paths: Vec<Option<&Value>> = report
            .diagnostics
            .iter()
            .map(|d| d.location.get("path"))
            .collect();
        assert_eq!(paths[..3], [None, None, None]);
        assert_eq!(paths[3], Some(&json!("/w")));
        assert_eq!(report.diagnostics[0].location["field"], "trust_weights.x");
    }
}
