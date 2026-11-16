//! Agent manifests and delegation targets (STANDARD v1.2 §5.15.1, §5.15.2).
//!
//! A manifest says which ontology capabilities an agent may exercise and
//! which task inputs it accepts. Its maxima are derived from the ontology,
//! never stated. Manifests are context, like the ontology: the validator and
//! the executor are given them beside the catalogs, and a manifest that
//! cannot be used is refused when loaded.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::ontology::Ontology;
use crate::validate::{Flags, check_cited};
use crate::yaml;

/// More manifests than this in one set is refused: a host has far fewer
/// agents, and each costs a lookup per delegate step.
pub const MAX_MANIFESTS: usize = 1000;

const MEMBERS: &[&str] = &[
    "agent",
    "standard",
    "ontology",
    "capabilities",
    "task",
    "version",
    "description",
];

/// One loaded agent manifest.
#[derive(Debug, Clone, PartialEq)]
pub struct Manifest {
    pub agent: String,
    /// The capability ids it lists, in list order.
    pub capabilities: Vec<String>,
    /// The listed ids the ontology does not define, in list order: the
    /// manifest has no maxima while any is listed (V101 where it is used).
    pub unknown: Vec<String>,
    /// The task inputs it declares, in the form of workflow `inputs`.
    pub task: Option<Map<String, Value>>,
}

impl Manifest {
    /// Its maxima, or with `read_only` its read-only maxima (over the
    /// capabilities whose ontology `mutation` is false). `None` when it
    /// lists a capability the ontology does not define.
    pub fn maxima(&self, ontology: &Ontology, read_only: bool) -> Option<Flags> {
        if !self.unknown.is_empty() {
            return None;
        }
        Some(
            self.capabilities
                .iter()
                .filter_map(|c| ontology.get(c))
                .filter(|node| !(read_only && node.mutation))
                .fold(Flags::NONE, |acc, node| acc.join(Flags::of(node))),
        )
    }
}

/// The agent manifests given to a validator or an executor, by agent name.
#[derive(Debug, Clone, Default)]
pub struct Agents {
    by_agent: BTreeMap<String, Manifest>,
    raw: BTreeMap<String, Value>,
}

impl Agents {
    /// Load manifests (§5.15.1). Refused, with a message naming the agent
    /// and the member: a manifest that does not conform to
    /// `agent_manifest_schema.yaml`, that cites an unsupported standard or
    /// another ontology major (V109), or that names an agent another one
    /// names. A capability id the ontology does not define is kept in
    /// [`Manifest::unknown`], not refused.
    pub fn load(values: &[Value], ontology: &Ontology) -> Result<Agents, String> {
        if values.len() > MAX_MANIFESTS {
            return Err(format!(
                "{} agent manifests given; at most {MAX_MANIFESTS} are accepted",
                values.len()
            ));
        }
        let mut agents = Agents::default();
        for (i, value) in values.iter().enumerate() {
            let manifest = Self::read(value, i, ontology)?;
            let name = manifest.agent.clone();
            if agents.by_agent.contains_key(&name) {
                return Err(format!(
                    "two agent manifests name the agent '{name}'; each agent has one manifest"
                ));
            }
            agents.raw.insert(name.clone(), value.clone());
            agents.by_agent.insert(name, manifest);
        }
        Ok(agents)
    }

    fn read(value: &Value, i: usize, ontology: &Ontology) -> Result<Manifest, String> {
        let Value::Object(m) = value else {
            return Err(format!("agent manifest {i} is not a mapping"));
        };
        let agent = match m.get("agent") {
            Some(Value::String(a)) if !a.is_empty() => a.clone(),
            Some(_) => {
                return Err(format!(
                    "agent manifest {i}: 'agent' must be a non-empty string"
                ));
            }
            None => return Err(format!("agent manifest {i} has no 'agent'")),
        };
        let fail = |what: String| Err(format!("agent manifest '{agent}': {what}"));
        for key in m.keys() {
            if !MEMBERS.contains(&key.as_str()) && !key.starts_with("x-") {
                return fail(format!("unknown member '{key}'"));
            }
        }
        for member in ["standard", "ontology"] {
            if !m.contains_key(member) {
                return fail(format!(
                    "no '{member}': a manifest cites the versions it was written against (§11.6)"
                ));
            }
        }
        let loaded = ontology.version.as_deref().unwrap_or("0");
        if let Some(d) = check_cited(m.get("standard"), m.get("ontology"), loaded, |d, _| d).first()
        {
            return fail(format!("{} {}", d.code.as_str(), d.message));
        }
        for member in ["version", "description"] {
            if m.get(member).is_some_and(|v| !v.is_string()) {
                return fail(format!("'{member}' must be a string"));
            }
        }
        let Some(Value::Array(list)) = m.get("capabilities") else {
            return fail("'capabilities' must be a list of capability ids".to_string());
        };
        let mut capabilities: Vec<String> = Vec::with_capacity(list.len());
        for item in list {
            let Value::String(c) = item else {
                return fail("'capabilities' must be a list of capability ids".to_string());
            };
            let shaped = c.as_bytes().first().is_some_and(u8::is_ascii_lowercase)
                && c.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-');
            if !shaped {
                return fail(format!("'{c}' is not a capability id"));
            }
            if capabilities.contains(c) {
                return fail(format!("lists '{c}' twice"));
            }
            capabilities.push(c.clone());
        }
        let task = match m.get("task") {
            None => None,
            Some(Value::Object(t)) => {
                for (k, v) in t {
                    if let Err(what) = task_input(v) {
                        return fail(format!("task input '{k}': {what}"));
                    }
                }
                Some(t.clone())
            }
            Some(_) => return fail("'task' must be a mapping of task inputs".to_string()),
        };
        let unknown = capabilities
            .iter()
            .filter(|c| ontology.get(c).is_none())
            .cloned()
            .collect();
        Ok(Manifest {
            agent,
            capabilities,
            unknown,
            task,
        })
    }

    pub fn get(&self, agent: &str) -> Option<&Manifest> {
        self.by_agent.get(agent)
    }

    pub fn is_empty(&self) -> bool {
        self.by_agent.is_empty()
    }

    /// The manifests as given, sorted by agent: what a run's snapshot digest
    /// covers.
    pub fn digest_value(&self) -> Value {
        Value::Array(self.raw.values().cloned().collect())
    }
}

/// A task input against `agent_task_input` (§5.15.1): a mapping whose
/// `type` is a type name or a non-empty list of them, `required` a boolean,
/// `description` and `ref` strings and `properties` a mapping; other members
/// are allowed. A manifest that breaks it is refused, so `required: "yes"`
/// never reads as optional.
fn task_input(v: &Value) -> Result<(), String> {
    let Value::Object(m) = v else {
        return Err("must be a mapping".to_string());
    };
    let type_ok = |t: &Value| match t {
        Value::String(_) => true,
        Value::Array(a) => !a.is_empty() && a.iter().all(Value::is_string),
        _ => false,
    };
    if let Some(t) = m.get("type")
        && !type_ok(t)
    {
        return Err("'type' must be a type name or a non-empty list of them".to_string());
    }
    for key in ["required", "description", "properties", "ref"] {
        let Some(v) = m.get(key) else { continue };
        let (ok, what) = match key {
            "required" => (v.is_boolean(), "a boolean"),
            "properties" => (v.is_object(), "a mapping"),
            _ => (v.is_string(), "a string"),
        };
        if !ok {
            return Err(format!(
                "'{key}' must be {what}, found {}",
                yaml::kind_of(v)
            ));
        }
    }
    Ok(())
}

/// The agents a workflow declares (§5.15.2), when it targets 1.2 or later
/// and `agents` is a non-empty list of distinct non-empty strings; `None`
/// otherwise (below 1.2 the field is ignored, W616; a malformed list is
/// S303).
pub fn declared(wf: &Map<String, Value>, target: Option<(u64, u64)>) -> Option<Vec<&str>> {
    if target.is_none_or(|t| t < (1, 2)) {
        return None;
    }
    let list = wf.get("agents")?.as_array()?;
    let mut names: Vec<&str> = Vec::with_capacity(list.len());
    for item in list {
        let s = item.as_str().filter(|s| !s.is_empty())?;
        if names.contains(&s) {
            return None;
        }
        names.push(s);
    }
    (!names.is_empty()).then_some(names)
}

/// A `delegate` step's literal `agent`: a string with no `${`.
pub fn literal_agent(step: &Map<String, Value>) -> Option<&str> {
    step.get("input_bindings")
        .and_then(|b| b.get("agent"))
        .and_then(Value::as_str)
        .filter(|a| !a.contains("${"))
}

/// The step binds a literal `read_only: true`.
pub fn binds_read_only(step: &Map<String, Value>) -> bool {
    step.get("input_bindings").and_then(|b| b.get("read_only")) == Some(&Value::Bool(true))
}

/// What a `delegate` step's target may do (§5.15.2).
#[derive(Debug, Clone, PartialEq)]
pub enum Target {
    /// The workflow declares no `agents`: the step keeps the `delegate`
    /// node's flags, as in 1.1.
    Free,
    /// The target maxima.
    Known(Flags),
    /// The target maxima are unknown: the agents concerned that have no
    /// manifest, and the `(agent, capability)` pairs whose capability the
    /// ontology does not define.
    Unknown {
        missing: Vec<String>,
        unknown: Vec<(String, String)>,
    },
}

impl Target {
    pub fn maxima(&self) -> Option<Flags> {
        match self {
            Target::Known(f) => Some(*f),
            _ => None,
        }
    }

    /// Why the maxima are unknown, for a refusal or a warning.
    pub fn why_unknown(&self) -> Option<String> {
        let Target::Unknown { missing, unknown } = self else {
            return None;
        };
        let mut parts: Vec<String> = Vec::new();
        if !missing.is_empty() {
            let names: Vec<String> = missing.iter().map(|a| format!("'{a}'")).collect();
            parts.push(format!("no manifest was given for {}", names.join(", ")));
        }
        for (agent, id) in unknown {
            parts.push(format!(
                "the manifest of '{agent}' lists '{id}', which the ontology does not define"
            ));
        }
        Some(parts.join("; "))
    }
}

/// The target maxima of a `delegate` step (§5.15.2): [`Target::Free`]
/// unless the workflow declares `agents`; for a literal `agent`, its
/// manifest's maxima; for a computed one, the join over every listed agent;
/// read-only maxima when the step binds a literal `read_only: true`.
pub fn target_maxima(
    agents: &Agents,
    ontology: &Ontology,
    declared: Option<&[&str]>,
    step: &Map<String, Value>,
) -> Target {
    let Some(listed) = declared else {
        return Target::Free;
    };
    let read_only = binds_read_only(step);
    let concerned: Vec<&str> = match literal_agent(step) {
        Some(a) => vec![a],
        None => listed.to_vec(),
    };
    let mut flags = Flags::NONE;
    let mut missing = Vec::new();
    let mut unknown = Vec::new();
    for agent in concerned {
        match agents.get(agent) {
            None => missing.push(agent.to_string()),
            Some(m) => match m.maxima(ontology, read_only) {
                Some(f) => flags = flags.join(f),
                None => unknown.extend(m.unknown.iter().map(|c| (agent.to_string(), c.clone()))),
            },
        }
    }
    if missing.is_empty() && unknown.is_empty() {
        Target::Known(flags)
    } else {
        Target::Unknown { missing, unknown }
    }
}

/// The task inputs a manifest declares that `given` does not, and the names
/// `given` holds that it does not declare (§5.15.2): `(undeclared,
/// missing)`.
pub fn check_task(declared: &Map<String, Value>, given: &[String]) -> (Vec<String>, Vec<String>) {
    let undeclared = given
        .iter()
        .filter(|n| !declared.contains_key(*n))
        .cloned()
        .collect();
    let missing = declared
        .iter()
        .filter(|(n, spec)| spec.get("required") == Some(&Value::Bool(true)) && !given.contains(n))
        .map(|(n, _)| n.clone())
        .collect();
    (undeclared, missing)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ontology::Risk;
    use serde_json::json;

    fn ontology() -> Ontology {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../schemas/capability_ontology.yaml");
        Ontology::load(&path).unwrap()
    }

    fn manifest(agent: &str, caps: &[&str]) -> Value {
        json!({"agent": agent, "standard": "1.2", "ontology": "2.2", "capabilities": caps})
    }

    #[test]
    fn loads_and_refuses() {
        let o = ontology();
        let ok = Agents::load(&[manifest("a", &["retrieve"]), manifest("b", &[])], &o).unwrap();
        assert!(ok.get("a").is_some() && ok.get("b").is_some());
        let x = json!({"agent": "x", "standard": "1.2", "ontology": "2.2",
            "capabilities": [], "x-vendor": 1});
        assert!(Agents::load(&[x], &o).is_ok());
        let unknown = Agents::load(&[manifest("o", &["retrieve", "divine"])], &o).unwrap();
        assert_eq!(unknown.get("o").unwrap().unknown, vec!["divine"]);
        for (bad, why) in [
            (json!([]), "not a mapping"),
            (json!({"standard": "1.2"}), "no 'agent'"),
            (json!({"agent": "", "standard": "1.2"}), "non-empty"),
            (
                json!({"agent": "a", "ontology": "2.2", "capabilities": []}),
                "no 'standard'",
            ),
            (
                json!({"agent": "a", "standard": "1.9", "ontology": "2.2", "capabilities": []}),
                "V109",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "3.0", "capabilities": []}),
                "V109",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2", "capabilities": []}),
                "S303",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2.2"}),
                "'capabilities'",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2.2", "capabilities": ["x", "x"]}),
                "twice",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2.2", "capabilities": [], "task": []}),
                "'task'",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2.2", "capabilities": [], "task": {"t": 1}}),
                "task input 't'",
            ),
            (
                json!({"agent": "a", "standard": "1.2", "ontology": "2.2", "capabilities": [], "flags": {}}),
                "unknown member",
            ),
        ] {
            let err = Agents::load(&[bad], &o).unwrap_err();
            assert!(err.contains(why), "{err} lacks {why}");
        }
        let dup = Agents::load(&[manifest("a", &[]), manifest("a", &[])], &o).unwrap_err();
        assert!(dup.contains("two agent manifests"));
    }

    /// A task input's members are typed as `agent_task_input` says: a
    /// manifest that breaks it is refused, naming the agent, the input and
    /// the member, so `required: "yes"` never makes a required input
    /// optional.
    #[test]
    fn task_inputs_are_typed() {
        let o = ontology();
        let with = |input: Value| {
            let mut m = manifest("db-writer", &["retrieve"]);
            m["task"] = json!({"table": input});
            Agents::load(&[m], &o)
        };
        for good in [
            json!({}),
            json!({"type": "string", "required": true, "description": "d"}),
            json!({"type": ["string", "null"], "properties": {}, "ref": "r", "x-ui": 1}),
        ] {
            assert!(with(good.clone()).is_ok(), "{good}");
        }
        for (bad, why) in [
            (json!({"type": 42}), "'type'"),
            (json!({"type": []}), "'type'"),
            (json!({"type": ["string", 1]}), "'type'"),
            (
                json!({"required": "yes"}),
                "'required' must be a boolean, found string",
            ),
            (json!({"description": 1}), "'description'"),
            (json!({"properties": []}), "'properties'"),
            (json!({"ref": true}), "'ref'"),
        ] {
            let err = with(bad).unwrap_err();
            assert!(
                err.starts_with("agent manifest 'db-writer': task input 'table': ")
                    && err.contains(why),
                "{err} lacks {why}"
            );
        }
    }

    #[test]
    fn maxima_and_targets() {
        let o = ontology();
        let agents = Agents::load(
            &[
                manifest("reader", &["retrieve", "critique"]),
                manifest("writer", &["retrieve", "checkpoint", "mutate"]),
                manifest("oracle", &["retrieve", "divine"]),
            ],
            &o,
        )
        .unwrap();
        let writer = agents.get("writer").unwrap().maxima(&o, false).unwrap();
        assert_eq!(writer.risk, Risk::High);
        assert!(writer.mutation && writer.requires_checkpoint && writer.requires_approval);
        assert_eq!(
            agents.get("writer").unwrap().maxima(&o, true),
            Some(Flags::NONE)
        );
        assert_eq!(agents.get("oracle").unwrap().maxima(&o, false), None);
        let step = |b: Value| json!({"capability": "delegate", "input_bindings": b});
        let lit = step(json!({"agent": "writer", "task": {}}));
        let listed = ["reader", "writer"];
        assert_eq!(
            target_maxima(&agents, &o, None, lit.as_object().unwrap()),
            Target::Free
        );
        assert_eq!(
            target_maxima(&agents, &o, Some(&listed), lit.as_object().unwrap()).maxima(),
            Some(writer)
        );
        let ro = step(json!({"agent": "writer", "read_only": true}));
        assert_eq!(
            target_maxima(&agents, &o, Some(&listed), ro.as_object().unwrap()).maxima(),
            Some(Flags::NONE)
        );
        let computed = step(json!({"agent": "${pick}"}));
        assert_eq!(
            target_maxima(&agents, &o, Some(&listed), computed.as_object().unwrap()).maxima(),
            Some(writer)
        );
        let with_ghost = ["reader", "ghost", "oracle"];
        let t = target_maxima(
            &agents,
            &o,
            Some(&with_ghost),
            computed.as_object().unwrap(),
        );
        assert_eq!(
            t,
            Target::Unknown {
                missing: vec!["ghost".into()],
                unknown: vec![("oracle".into(), "divine".into())]
            }
        );
        assert!(t.why_unknown().unwrap().contains("'ghost'"));
    }

    #[test]
    fn declared_needs_1_2_and_a_clean_list() {
        let wf = |a: Value| json!({"agents": a}).as_object().unwrap().clone();
        assert_eq!(
            declared(&wf(json!(["a", "b"])), Some((1, 2))),
            Some(vec!["a", "b"])
        );
        assert_eq!(declared(&wf(json!(["a"])), Some((1, 1))), None);
        assert_eq!(declared(&wf(json!(["a"])), None), None);
        assert_eq!(declared(&wf(json!([])), Some((1, 2))), None);
        assert_eq!(declared(&wf(json!(["a", "a"])), Some((1, 2))), None);
        assert_eq!(declared(&wf(json!([""])), Some((1, 2))), None);
    }

    #[test]
    fn tasks() {
        let decl = json!({"table": {"type": "string", "required": true}, "rows": {}});
        let (undeclared, missing) = check_task(
            decl.as_object().unwrap(),
            &["rows".to_string(), "colour".to_string()],
        );
        assert_eq!(undeclared, vec!["colour"]);
        assert_eq!(missing, vec!["table"]);
    }
}
