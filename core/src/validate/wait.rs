//! Waiting for events (STANDARD v1.1 §5.13, design-114 §12; `wait@1`).

use std::collections::{HashMap, HashSet};
use std::time::Duration;

use serde_json::{Map, Value};

use super::bindings::{Checker, Mode};
use super::extensions::{Declared, count, duration_field, enum_field, s303, s304, string_field};
use super::semantics::{self, Placed};
use super::{Context, Report, Scope, StepLoc};
use crate::diag::{Code, Diagnostic};
use crate::yaml;

const WAIT_KEYS: &[&str] = &["event_type", "source_kind", "correlate", "liveness"];
const LIVENESS_KEYS: &[&str] = &["mode", "interval", "failure_threshold"];
const DEFAULT_FAILURE_THRESHOLD: u64 = 3;

/// Where the event schema's source kinds may be found under the schema
/// root: the repository layout, then a skill's co-located copy.
const SOURCE_KINDS: &[&str] = &[
    "schemas/event_schema.yaml#/event/properties/source/properties/kind/enum",
    "event_schema.yaml#/event/properties/source/properties/kind/enum",
];

/// Check a step's `wait` block.
pub(crate) fn check(
    ctx: &Context,
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    checker: &Checker<'_>,
    scope: &Scope,
    report: &mut Report,
) {
    let Some(value) = step.get("wait") else {
        return;
    };
    if !declared.require(
        "wait@1",
        "'wait'",
        |d| loc.locate(d).at("field", "wait"),
        report,
    ) {
        return;
    }
    let at = |d: Diagnostic| loc.locate(d);
    // Checked even when the block is malformed: the legacy leniency for
    // timeouts does not apply to a waiting step.
    let timeout = timeout(step, &at, report);
    let Value::Object(wait) = value else {
        report.push(s303(
            &at,
            "wait",
            format!("'wait' must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    host(loc, step, report);
    semantics::unknown_fields(wait, WAIT_KEYS, "wait", &at, report);
    if !wait.contains_key("event_type") {
        report.push(s304(
            &at,
            "wait.event_type",
            "wait has no 'event_type'".into(),
        ));
    }
    string_field(wait, "event_type", "wait", &at, report);
    if let Some(kind) = string_field(wait, "source_kind", "wait", &at, report) {
        source_kind(ctx, kind, &at, report);
    }
    match wait.get("correlate") {
        None => {}
        Some(Value::Object(c)) => {
            for (key, v) in c {
                let field = format!("wait.correlate.{key}");
                // A waiting delegate correlates by its delegation's task_id.
                if loc.capability == "delegate" && key == "task_id" {
                    report.push(s303(
                        &at,
                        &field,
                        "a waiting delegate's result is matched by its delegation's task_id; do not set it".into(),
                    ));
                    continue;
                }
                if references(v, &field, &at, report) {
                    checker.scan(v, scope, Mode::Existence, &field, report);
                }
            }
        }
        Some(other) => report.push(s303(
            &at,
            "wait.correlate",
            format!(
                "wait.correlate must map keys to references, found {}",
                yaml::kind_of(other)
            ),
        )),
    }
    if let Some(liveness) = wait.get("liveness") {
        self::liveness(liveness, timeout, &at, report);
    }
}

/// `wait` is for `receive`, `delegate` (delegate, then wait for that
/// delegate's result), or `synchronize` over at least two distinct agents.
fn host(loc: &StepLoc<'_>, step: &Map<String, Value>, report: &mut Report) {
    let ok = match loc.capability {
        "receive" | "delegate" => true,
        "synchronize" => step
            .get("input_bindings")
            .and_then(|b| b.get("agents"))
            .and_then(Value::as_array)
            .is_some_and(|a| {
                // A repeated agent would be waited for twice.
                let distinct: std::collections::HashSet<String> =
                    a.iter().map(Value::to_string).collect();
                a.len() >= 2 && distinct.len() == a.len()
            }),
        _ => false,
    };
    if !ok {
        report.push(
            loc.diag(
                Code::SchemaValidationFailed,
                format!(
                    "'wait' is for receive, delegate, or synchronize with a literal 'agents' list of at least two distinct agents; not '{}'",
                    loc.capability
                ),
            )
            .at("field", "wait"),
        );
    }
}

/// A step's `delay` (§5.13), when `wait@1` is declared and it is a
/// positive duration: the executor waits that long before the step.
pub(crate) fn delay(step: &Map<String, Value>, declared: &Declared) -> Option<Duration> {
    let Some(Value::String(text)) = step.get("delay") else {
        return None;
    };
    crate::duration::parse(text)
        .ok()
        .filter(|d| declared.has("wait@1") && !d.is_zero())
}

/// The catalog's workflows that can wait (§5.13): a step, handlers
/// included, waits for an event or a delay, or invokes a catalog workflow
/// that can. A run it invokes shares the caller's checkpoints, and a
/// child's handler may wait before the caller retries or recovers, so W608
/// counts such an `invoke` as a wait. A backward search from the workflows
/// that wait themselves, over who invokes whom: linear in the catalog.
pub(crate) fn workflows_that_wait(workflows: &Map<String, Value>) -> HashSet<&str> {
    let mut callers: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut queue: Vec<&str> = Vec::new();
    for (name, wf) in workflows.iter().filter(|(n, _)| !n.starts_with("x-")) {
        let Some(map) = wf.as_object() else { continue };
        // Declarations are read again only to decide this: their
        // diagnostics come from each workflow's own check.
        let declared = Declared::read(map, &|d| d, &mut Report::default());
        let steps = map
            .get("steps")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_object);
        let mut waits = false;
        for s in steps {
            waits |= (declared.has("wait@1") && s.get("wait").is_some_and(Value::is_object))
                || delay(s, &declared).is_some();
            if s.get("capability").and_then(Value::as_str) == Some("invoke") {
                if let Some((target, _)) = super::invoke::target(s) {
                    callers.entry(target).or_default().push(name.as_str());
                }
            }
        }
        if waits {
            queue.push(name.as_str());
        }
    }
    let mut waiting: HashSet<&str> = queue.iter().copied().collect();
    while let Some(name) = queue.pop() {
        for &caller in callers.get(name).into_iter().flatten() {
            if waiting.insert(caller) {
                queue.push(caller);
            }
        }
    }
    waiting
}

/// `delay` needs `wait@1` (V106) and must be a positive duration (S303).
pub(crate) fn check_delay(
    loc: &StepLoc<'_>,
    step: &Map<String, Value>,
    declared: &Declared,
    report: &mut Report,
) {
    let Some(value) = step.get("delay") else {
        return;
    };
    if !declared.require(
        "wait@1",
        "'delay'",
        |d| loc.locate(d).at("field", "delay"),
        report,
    ) {
        return;
    }
    let at = |d: Diagnostic| loc.locate(d);
    if duration_field(value, "delay", &at, report).is_some_and(|d| d.is_zero()) {
        report.push(s303(&at, "delay", "delay must be longer than zero".into()));
    }
    // Its group runs at the same time: whether the others wait is unclear.
    if step.contains_key("parallel_group") {
        report.push(s303(
            &at,
            "delay",
            "a step in a parallel_group cannot delay: the group runs concurrently".into(),
        ));
    }
}

/// Whether `value` is a string holding a `${...}` reference, else S303.
pub(crate) fn references(
    value: &Value,
    field: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> bool {
    // A template around a reference is a string, not the value referenced.
    let ok = value.as_str().is_some_and(super::refs_whole);
    if !ok {
        // An unquoted typed reference reads as a mapping (W612 in a binding);
        // here it is unusable, so say how to fix it.
        let msg = match value
            .as_object()
            .and_then(super::bindings::mangled_reference)
        {
            Some(rebuilt) => format!(
                "{field} must be a reference; YAML read '{rebuilt}' as a mapping because of ': ' inside the reference; quote the value"
            ),
            None => {
                format!("{field} must be a reference such as \"${{step.field}}\", found {value}")
            }
        };
        report.push(s303(at, field, msg));
    }
    ok
}

/// A waiting step needs an enforceable `timeout` (S304 / S303). A timeout
/// that is not a string is already reported by the step's field shapes.
fn timeout(
    step: &Map<String, Value>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) -> Option<Duration> {
    match step.get("timeout") {
        None | Some(Value::Null) => {
            report.push(s304(
                at,
                "timeout",
                "a step with 'wait' needs a 'timeout' (a duration): a wait must end".into(),
            ));
            None
        }
        Some(t @ Value::String(_)) => duration_field(t, "timeout", at, report),
        Some(_) => None,
    }
}

fn source_kind(
    ctx: &Context,
    kind: &str,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let Some(kinds) = SOURCE_KINDS
        .iter()
        .find_map(|r| ctx.schemas.resolve_ref(r))
        .and_then(|v| v.as_array().cloned())
    else {
        report.push(
            at(Diagnostic::new(
                Code::SchemaNotFound,
                "wait.source_kind: cannot load the event source kinds (event_schema.yaml)",
            ))
            .at("field", "wait.source_kind"),
        );
        return;
    };
    if !kinds.iter().any(|k| k.as_str() == Some(kind)) {
        let names: Vec<&str> = kinds.iter().filter_map(Value::as_str).collect();
        report.push(s303(
            at,
            "wait.source_kind",
            format!(
                "wait.source_kind '{kind}' is not an event source kind ({})",
                names.join(", ")
            ),
        ));
    }
}

fn liveness(
    value: &Value,
    timeout: Option<Duration>,
    at: &dyn Fn(Diagnostic) -> Diagnostic,
    report: &mut Report,
) {
    let field = "wait.liveness";
    let Value::Object(l) = value else {
        report.push(s303(
            at,
            field,
            format!("{field} must be a mapping, found {}", yaml::kind_of(value)),
        ));
        return;
    };
    semantics::unknown_fields(l, LIVENESS_KEYS, field, at, report);
    if !l.contains_key("mode") {
        report.push(s304(
            at,
            &format!("{field}.mode"),
            format!("{field} has no 'mode'"),
        ));
    }
    enum_field(l, "mode", &["push", "probe"], field, at, report);
    let interval = match l.get("interval") {
        None => {
            report.push(s304(
                at,
                &format!("{field}.interval"),
                format!("{field} has no 'interval'"),
            ));
            None
        }
        Some(v) => duration_field(v, &format!("{field}.interval"), at, report),
    };
    if interval.is_some_and(|d| d.is_zero()) {
        report.push(s303(
            at,
            &format!("{field}.interval"),
            format!("{field}.interval must be longer than zero"),
        ));
    }
    let threshold = match l.get("failure_threshold") {
        None => Some(DEFAULT_FAILURE_THRESHOLD),
        Some(v) => match count(v).filter(|&n| n >= 1) {
            Some(n) => Some(n),
            None => {
                report.push(s303(
                    at,
                    &format!("{field}.failure_threshold"),
                    format!(
                        "{field}.failure_threshold must be an integer of at least 1, found {v}"
                    ),
                ));
                None
            }
        },
    };
    // Liveness must be able to fail before the timeout does, or it adds
    // nothing.
    if let (Some(interval), Some(threshold), Some(timeout)) = (interval, threshold, timeout) {
        let window = u32::try_from(threshold)
            .ok()
            .and_then(|t| interval.checked_mul(t));
        if window.is_none_or(|w| w >= timeout) {
            report.push(s303(
                at,
                field,
                format!(
                    "{field}: interval × failure_threshold must be shorter than the step's timeout ({} × {threshold} ≥ {})",
                    show(interval),
                    show(timeout)
                ),
            ));
        }
    }
}

fn show(d: Duration) -> String {
    let ms = d.as_millis();
    if ms % 1000 == 0 {
        format!("{}s", ms / 1000)
    } else {
        format!("{ms}ms")
    }
}

/// The latest step of a kind seen so far, and the latest one before it
/// that is not concurrent with it, so the latest one that runs before any
/// later step is found in O(1).
#[derive(Clone, Copy)]
struct Latest {
    pos: usize,
    other: Option<usize>,
}

fn record(latest: &mut Option<Latest>, placed: &[Placed<'_>], pos: usize) {
    let other = latest.map(|l| {
        if placed[l.pos].concurrent_with(&placed[pos]) {
            l.other
        } else {
            Some(l.pos)
        }
    });
    *latest = Some(Latest {
        pos,
        other: other.flatten(),
    });
}

/// The position of the latest recorded step that runs before `pos`.
fn before(latest: Option<Latest>, placed: &[Placed<'_>], pos: usize) -> Option<usize> {
    let l = latest?;
    if placed[l.pos].concurrent_with(&placed[pos]) {
        l.other
    } else {
        Some(l.pos)
    }
}

/// The wait that a step's latest checkpoint no longer covers, if any: the
/// checkpoint at position `c` was taken before a wait that runs before the
/// step — one listed after it (`w > c`), or one running alongside it in its
/// parallel group (the checkpoint may finish before the wait does).
fn stale(
    c: Option<usize>,
    w: Option<usize>,
    group_waits: &HashMap<&str, usize>,
    placed: &[Placed<'_>],
) -> Option<usize> {
    let c = c?;
    if let Some(w) = w.filter(|&w| w > c) {
        return Some(w);
    }
    placed[c]
        .parallel_group
        .and_then(|g| group_waits.get(g).copied())
}

/// W608: a step that requires a checkpoint whose latest checkpoint was
/// taken before a wait. A wait can last hours and the run may resume in
/// another process; the world may have changed, so a checkpoint taken
/// before it no longer covers the step. A step that waits itself acts
/// after its own wait. Handlers (`handlers`: each with its earliest
/// targeter's position) are judged at their targeter, which may itself
/// have waited.
pub(crate) fn spans_checkpoint(
    workflow: &str,
    placed: &[Placed<'_>],
    handlers: &[(Placed<'_>, usize)],
    report: &mut Report,
) {
    let mut by_targeter: HashMap<usize, Vec<&Placed<'_>>> = HashMap::new();
    for (h, t) in handlers.iter().filter(|(h, _)| h.requires_checkpoint) {
        by_targeter.entry(*t).or_default().push(h);
    }
    let mut checkpoint: Option<Latest> = None;
    let mut wait: Option<Latest> = None;
    let mut group_waits: HashMap<&str, usize> = HashMap::new();
    for (pos, p) in placed.iter().enumerate() {
        // Before recording `p`, the trackers hold what runs before it.
        let c = before(checkpoint, placed, pos);
        let covers = |waits_itself: bool| {
            if waits_itself {
                c.map(|_| pos)
            } else {
                stale(c, before(wait, placed, pos), &group_waits, placed)
            }
        };
        let mut flag = |step: &Placed<'_>, w: usize| {
            let Some(c) = c else { return };
            // The step's own wait, or a handler's own delay.
            let detail = if w == pos && (step.index == p.index || step.delays) {
                "but it waits before acting; take a new checkpoint after the wait".to_string()
            } else if placed[w].nested {
                format!(
                    "but step {} invokes a workflow that waits; take a new checkpoint after the invoke",
                    placed[w].index
                )
            } else {
                format!(
                    "but step {} waits after it; take a new checkpoint after the wait",
                    placed[w].index
                )
            };
            report.push(
                Diagnostic::new(
                    Code::WaitSpansCheckpoint,
                    format!(
                        "'{}' relies on the checkpoint at step {}, {detail}",
                        step.capability, placed[c].index
                    ),
                )
                .at("workflow", workflow)
                .at("step", step.index)
                .at("capability", step.capability)
                .at("wait_step", placed[w].index),
            );
        };
        // A waiting delegate delegates before it waits; a delay comes
        // before anything the step does; an invoke uses its checkpoint
        // before the run it invokes waits.
        let waits_before_acting = p.delays || (p.waits && !p.nested && p.capability != "delegate");
        if p.requires_checkpoint {
            if let Some(w) = covers(waits_before_acting) {
                flag(p, w);
            }
        }
        // A handler runs after its targeter, which may have waited, and
        // may delay itself before acting.
        for h in by_targeter.get(&pos).into_iter().flatten() {
            if let Some(w) = covers(false).or(if p.waits || h.delays {
                c.map(|_| pos)
            } else {
                None
            }) {
                flag(h, w);
            }
        }
        if p.capability == "checkpoint" {
            record(&mut checkpoint, placed, pos);
        }
        if p.waits {
            record(&mut wait, placed, pos);
            if let Some(g) = p.parallel_group {
                group_waits.insert(g, pos);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::super::tests::codes;

    #[test]
    fn an_unquoted_typed_reference_gets_a_quoting_hint() {
        // `- ${p.steps: array<object>}` unquoted is read as a mapping.
        let mangled = json!({"${p.steps": "array<object>}"});
        let mut report = super::super::Report::default();
        assert!(!super::references(
            &mangled,
            "approval.shows[0]",
            &|d| d,
            &mut report
        ));
        let [d] = report.diagnostics.as_slice() else {
            panic!("{:?}", report.diagnostics)
        };
        assert_eq!(d.code.as_str(), "S303");
        assert!(d.message.contains("quote the value"), "{}", d.message);
    }

    fn catalog(steps: Value, requires: &[&str]) -> Value {
        json!({"w": {"goal": "g", "risk": "low", "spec_version": "1.1",
                     "workflow_extensions": {"requires": requires},
                     "steps": steps}})
    }

    fn receive(store: &str, timeout: Value, wait: Value) -> Value {
        json!({"capability": "receive", "purpose": "p", "store_as": store,
               "timeout": timeout, "wait": wait})
    }

    fn st(cap: &str, store: &str) -> Value {
        json!({"capability": cap, "purpose": "p", "store_as": store})
    }

    fn mutate(store: &str) -> Value {
        json!({"capability": "mutate", "purpose": "p", "store_as": store,
               "input_bindings": {"target": "t", "operation": {}}})
    }

    fn in_group(mut step: Value, group: &str) -> Value {
        step["parallel_group"] = json!(group);
        step
    }

    fn errors_and_warnings(c: Value) -> Vec<&'static str> {
        codes(c).into_iter().filter(|c| *c != "W601").collect()
    }

    #[test]
    fn a_valid_wait() {
        let wait = json!({"event_type": "job.done", "source_kind": "agent",
                          "correlate": {"job": "${p.steps}"},
                          "liveness": {"mode": "probe", "interval": "10m"}});
        let c = catalog(
            json!([st("plan", "p"), receive("r", json!("2h"), wait)]),
            &["wait@1"],
        );
        assert_eq!(codes(c), Vec::<&str>::new());
    }

    #[test]
    fn hosts() {
        let wait = json!({"event_type": "e"});
        let sync = |agents: Value| {
            json!({"capability": "synchronize", "purpose": "p", "store_as": "s",
                   "timeout": "1h", "wait": wait,
                   "input_bindings": {"agents": agents, "state": {}}})
        };
        let c = |step: Value| catalog(json!([step]), &["wait@1"]);
        assert_eq!(codes(c(sync(json!(["a", "b"])))), Vec::<&str>::new());
        assert_eq!(codes(c(sync(json!(["a"])))), ["S303"]);
        assert_eq!(codes(c(sync(json!(["a", "a"])))), ["S303"]);
        let mut retrieve = st("retrieve", "r");
        retrieve["input_bindings"] = json!({"target": "t"});
        retrieve["timeout"] = json!("1h");
        retrieve["wait"] = wait.clone();
        assert_eq!(codes(c(retrieve)), ["S303"]);
        // A delegate step can wait for its delegate's result, matched by
        // the delegation's task_id, which the author may not set.
        let delegate = json!({"capability": "delegate", "purpose": "p", "store_as": "d",
                              "timeout": "1h", "wait": wait,
                              "input_bindings": {"task": {"t": 1}, "agent": "a"}});
        assert_eq!(codes(c(delegate.clone())), Vec::<&str>::new());
        let mut pinned = delegate.clone();
        pinned["wait"]["correlate"] = json!({"task_id": "${d}"});
        assert_eq!(codes(c(pinned)), ["S303"]);
        // A waiting delegate that raises requires_checkpoint acts (delegates)
        // before its wait: a checkpoint just before it is not stale.
        let mut acting = delegate;
        acting["requires_checkpoint"] = json!(true);
        let steps = json!([
            {"capability": "checkpoint", "purpose": "p", "store_as": "cp",
             "input_bindings": {"scope": "s"}},
            acting
        ]);
        assert_eq!(codes(catalog(steps, &["wait@1"])), Vec::<&str>::new());
    }

    #[test]
    fn shape() {
        let c = |timeout: Value, wait: Value| {
            codes(catalog(json!([receive("r", timeout, wait)]), &["wait@1"]))
        };
        assert_eq!(c(json!("1h"), json!("e")), ["S303"]);
        assert_eq!(c(json!("1h"), json!({})), ["S304"]);
        assert_eq!(c(json!("1h"), json!({"event_type": 3})), ["S303"]);
        assert_eq!(c(json!("1h"), json!({"event_type": "e", "x": 1})), ["W604"]);
        assert_eq!(
            c(json!("1h"), json!({"event_type": "e", "source_kind": "x"})),
            ["S303"]
        );
        assert_eq!(
            c(json!("1h"), json!({"event_type": "e", "correlate": []})),
            ["S303"]
        );
        assert_eq!(
            c(
                json!("1h"),
                json!({"event_type": "e", "correlate": {"k": "${nope}"}})
            ),
            ["B202"]
        );
    }

    #[test]
    fn timeout_is_required_and_strict() {
        let wait = json!({"event_type": "e"});
        let c = |step: Value| codes(catalog(json!([step]), &["wait@1"]));
        let mut no_timeout = st("receive", "r");
        no_timeout["wait"] = wait.clone();
        assert_eq!(c(no_timeout), ["S304"]);
        assert_eq!(c(receive("r", Value::Null, wait.clone())), ["S304"]);
        // Free text is W614 elsewhere, but a wait must be enforceable.
        assert_eq!(c(receive("r", json!("two hours"), wait.clone())), ["S303"]);
        // Without the declaration the wait is not checked; the timeout is
        // a legacy one.
        let undeclared = catalog(json!([receive("r", json!("two hours"), wait)]), &[]);
        assert_eq!(codes(undeclared), ["W614", "V106"]);
    }

    #[test]
    fn liveness() {
        let c = |timeout: &str, liveness: Value| {
            codes(catalog(
                json!([receive(
                    "r",
                    json!(timeout),
                    json!({"event_type": "e", "liveness": liveness})
                )]),
                &["wait@1"],
            ))
        };
        let ok: Vec<&str> = Vec::new();
        assert_eq!(c("31m", json!({"mode": "push", "interval": "10m"})), ok);
        assert_eq!(
            c("30m", json!({"mode": "push", "interval": "10m"})),
            ["S303"]
        );
        assert_eq!(
            c(
                "30m",
                json!({"mode": "push", "interval": "10m", "failure_threshold": 2})
            ),
            ok
        );
        assert_eq!(c("1h", json!({"interval": "10m"})), ["S304"]);
        assert_eq!(
            c("1h", json!({"mode": "poll", "interval": "10m"})),
            ["S303"]
        );
        assert_eq!(c("1h", json!({"mode": "push"})), ["S304"]);
        assert_eq!(c("1h", json!({"mode": "push", "interval": "0s"})), ["S303"]);
        assert_eq!(
            c(
                "1h",
                json!({"mode": "push", "interval": "1m", "failure_threshold": 0})
            ),
            ["S303"]
        );
        assert_eq!(c("1h", json!("push")), ["S303"]);
        // A huge window cannot overflow.
        assert_eq!(
            c(
                "1h",
                json!({"mode": "push", "interval": "P100000000D", "failure_threshold": 4000000000u64})
            ),
            ["S303"]
        );
    }

    #[test]
    fn delays() {
        let observe = |delay: Value| {
            let mut o = st("observe", "o");
            o["input_bindings"] = json!({"target": "t"});
            o["delay"] = delay;
            o
        };
        let c = |steps: Value, requires: &[&str]| errors_and_warnings(catalog(steps, requires));
        assert!(c(json!([observe(json!("1m"))]), &["wait@1"]).is_empty());
        assert_eq!(c(json!([observe(json!("1m"))]), &[]), ["V106"]);
        assert_eq!(c(json!([observe(json!("0s"))]), &["wait@1"]), ["S303"]);
        assert_eq!(c(json!([observe(json!("soon"))]), &["wait@1"]), ["S303"]);
        assert_eq!(c(json!([observe(json!(60))]), &["wait@1"]), ["S303"]);
        // A delay is a wait: a checkpoint before it covers nothing after it,
        // and a mutation that delays acts after its own delay.
        assert_eq!(
            c(
                json!([st("checkpoint", "c"), observe(json!("1m")), mutate("m")]),
                &["wait@1"]
            ),
            ["W608"]
        );
        let mut delayed = mutate("m");
        delayed["delay"] = json!("5m");
        assert_eq!(
            c(json!([st("checkpoint", "c"), delayed]), &["wait@1"]),
            ["W608"]
        );
        // A delegate delays before it delegates.
        let delegate = json!({"capability": "delegate", "purpose": "p", "store_as": "d",
                              "requires_checkpoint": true, "delay": "1m",
                              "input_bindings": {"task": {"t": 1}, "agent": "a"}});
        assert_eq!(
            c(json!([st("checkpoint", "c"), delegate]), &["wait@1"]),
            ["W608"]
        );
        // So does a handler, judged at the step that escalates to it.
        let escalating = json!({"capability": "observe", "purpose": "p", "store_as": "o",
            "input_bindings": {"target": "t"},
            "failure_modes": [{"condition": "c", "on_error": "R402", "action": "escalate",
                               "recovery": {"goto_step": "h"}}]});
        let handler = json!({"capability": "invoke", "purpose": "p", "store_as": "h",
            "handler": true, "requires_checkpoint": true, "delay": "1m",
            "workflow_id": "page", "input_bindings": {"workflow": "page", "input": {}}});
        let found = c(
            json!([st("checkpoint", "c"), escalating, handler]),
            &["wait@1", "recovery@1"],
        );
        assert!(found.contains(&"W608"), "{found:?}");
        // In a parallel group the others' timing would be unclear.
        let mut grouped = observe(json!("1m"));
        grouped["parallel_group"] = json!("g");
        assert_eq!(c(json!([grouped]), &["wait@1"]), ["S303"]);
    }

    #[test]
    fn an_invoke_of_a_waiting_workflow_spans_a_checkpoint() {
        let call = |target: &str| {
            json!({"capability": "invoke", "purpose": "p", "store_as": format!("i_{target}"),
                   "workflow_id": target, "input_bindings": {"workflow": target, "input": {}}})
        };
        let wf = |steps: Value| {
            json!({"goal": "g", "risk": "low", "spec_version": "1.1",
                   "workflow_extensions": {"requires": ["wait@1"]}, "steps": steps})
        };
        let waiting = wf(json!([receive(
            "r",
            json!("1h"),
            json!({"event_type": "e"})
        )]));
        let quiet = wf(json!([st("observe", "o")]));
        let mut delayed = st("observe", "o");
        delayed["delay"] = json!("1m");
        // Only its handler waits: the caller retries or recovers after it.
        let mut escalates = wf(json!([
            {"capability": "observe", "purpose": "p", "store_as": "o",
             "input_bindings": {"target": "t"},
             "failure_modes": [{"condition": "c", "on_error": "R402", "action": "escalate",
                                "recovery": {"goto_step": "h"}}]},
            {"capability": "invoke", "purpose": "p", "store_as": "h", "handler": true,
             "workflow_id": "waits", "input_bindings": {"workflow": "waits", "input": {}}}
        ]));
        escalates["workflow_extensions"]["requires"] = json!(["wait@1", "recovery@1"]);
        let with = |steps: Value| {
            let c = json!({"w": wf(steps), "waits": waiting, "quiet": quiet,
                           "relays": wf(json!([call("waits")])),
                           "delays": wf(json!([delayed])), "escalates": escalates});
            let report = super::super::validate_catalog(&super::super::tests::ctx(), &c, None);
            report
                .diagnostics
                .iter()
                .filter(|d| d.code.as_str() == "W608")
                .map(|d| (d.location["step"].clone(), d.message.clone()))
                .collect::<Vec<_>>()
        };
        // A run it invokes waits, so the checkpoint before it is stale.
        let found = with(json!([st("checkpoint", "c"), call("waits"), mutate("m")]));
        let [(step, message)] = found.as_slice() else {
            panic!("{found:?}")
        };
        assert_eq!(step, &json!(2));
        assert!(
            message.contains("step 1 invokes a workflow that waits"),
            "{message}"
        );
        // Transitively, too.
        assert_eq!(
            with(json!([st("checkpoint", "c"), call("relays"), mutate("m")])).len(),
            1
        );
        // A delay, a handler's wait, and a target named only in the
        // bindings count as well.
        for target in ["delays", "escalates"] {
            let found = with(json!([st("checkpoint", "c"), call(target), mutate("m")]));
            assert_eq!(found.len(), 1, "{target}: {found:?}");
        }
        let mut by_binding = call("waits");
        by_binding.as_object_mut().unwrap().remove("workflow_id");
        assert_eq!(
            with(json!([st("checkpoint", "c"), by_binding, mutate("m")])).len(),
            1
        );
        // A workflow that does not wait, or a checkpoint after the invoke.
        assert!(with(json!([st("checkpoint", "c"), call("quiet"), mutate("m")])).is_empty());
        assert!(with(json!([call("waits"), st("checkpoint", "c"), mutate("m")])).is_empty());
    }

    #[test]
    fn a_wait_between_checkpoint_and_mutation_is_w608() {
        let wait = json!({"event_type": "e"});
        let c = |steps: Value| errors_and_warnings(catalog(steps, &["wait@1"]));
        let r = || receive("r", json!("1h"), wait.clone());
        assert_eq!(
            c(json!([st("checkpoint", "c"), r(), mutate("m")])),
            ["W608"]
        );
        // A checkpoint after the wait covers the mutation.
        assert_eq!(
            c(json!([
                st("checkpoint", "c"),
                r(),
                st("checkpoint", "c2"),
                mutate("m")
            ])),
            Vec::<&str>::new()
        );
        // A wait before the only checkpoint is fine.
        assert_eq!(
            c(json!([r(), st("checkpoint", "c"), mutate("m")])),
            Vec::<&str>::new()
        );
        // A wait running alongside the mutation does not precede it, but
        // one running alongside the checkpoint may outlast it.
        assert_eq!(
            c(json!([
                st("checkpoint", "c"),
                in_group(r(), "g"),
                in_group(mutate("m"), "g")
            ])),
            Vec::<&str>::new()
        );
        assert_eq!(
            c(json!([
                in_group(st("checkpoint", "c"), "g"),
                in_group(r(), "g"),
                mutate("m")
            ])),
            ["W608"]
        );
        // A checkpoint running alongside the mutation does not count; the
        // one before it does, and the wait sits after that one.
        assert_eq!(
            c(json!([
                st("checkpoint", "c"),
                r(),
                in_group(st("checkpoint", "c2"), "g"),
                in_group(mutate("m"), "g")
            ])),
            ["W608"]
        );
        // Reported for each covered step.
        assert_eq!(
            c(json!([
                st("checkpoint", "c"),
                r(),
                mutate("m"),
                mutate("m2")
            ])),
            ["W608", "W608"]
        );
    }

    #[test]
    fn w608_follows_concurrency_not_list_order() {
        let wait = json!({"event_type": "e"});
        let c = |steps: Value| errors_and_warnings(catalog(steps, &["wait@1"]));
        let r = || receive("r", json!("1h"), wait.clone());
        // The wait shares the checkpoint's group: the checkpoint may finish
        // first, whichever is listed first.
        assert_eq!(
            c(json!([
                in_group(r(), "g"),
                in_group(st("checkpoint", "c"), "g"),
                mutate("m")
            ])),
            ["W608"]
        );
        assert_eq!(
            c(json!([
                in_group(r(), "g"),
                receive("r2", json!("1h"), wait.clone()),
                in_group(st("checkpoint", "c"), "g"),
                mutate("m")
            ])),
            ["W608"]
        );
        // A wait in another group before the checkpoint is fine.
        assert_eq!(
            c(json!([
                in_group(r(), "h"),
                in_group(st("checkpoint", "c"), "g"),
                mutate("m")
            ])),
            Vec::<&str>::new()
        );
    }

    #[test]
    fn w608_for_a_step_that_waits_itself() {
        let sync = json!({"capability": "synchronize", "purpose": "p", "store_as": "s",
                          "timeout": "1h", "requires_checkpoint": true,
                          "wait": {"event_type": "e"},
                          "input_bindings": {"agents": ["a", "b"], "state": {}}});
        assert_eq!(
            errors_and_warnings(catalog(json!([st("checkpoint", "c"), sync]), &["wait@1"])),
            ["W608"]
        );
    }

    #[test]
    fn w608_for_handlers() {
        let mut r = receive("r", json!("1h"), json!({"event_type": "e"}));
        r["failure_modes"] = json!([{"condition": "c", "action": "escalate",
                                     "on_error": "R401",
                                     "recovery": {"goto_step": "hand"}}]);
        let hand = json!({"capability": "invoke", "purpose": "p", "store_as": "hand",
                          "handler": true, "workflow_id": "h",
                          "requires_checkpoint": true});
        let mut c = catalog(
            json!([st("checkpoint", "c"), r, hand]),
            &["wait@1", "recovery@1"],
        );
        c["h"] = json!({"goal": "g", "risk": "low", "spec_version": "1.1",
                        "steps": [{"capability": "observe", "purpose": "p", "store_as": "o"}]});
        assert_eq!(codes(c), ["W608"]);
    }

    #[test]
    fn a_malformed_wait_still_checks_the_timeout() {
        let c = |timeout: Value, wait: Value| {
            codes(catalog(json!([receive("r", timeout, wait)]), &["wait@1"]))
        };
        assert_eq!(c(json!("forever"), Value::Null), ["S303", "S303"]);
        // A non-string timeout is reported once, by the field shapes.
        assert_eq!(c(json!(3600), json!({"event_type": "e"})), ["S303"]);
    }

    #[test]
    fn correlate_values_are_references() {
        let c = |correlate: Value| {
            codes(catalog(
                json!([
                    st("plan", "p"),
                    receive(
                        "r",
                        json!("1h"),
                        json!({"event_type": "e", "correlate": correlate})
                    )
                ]),
                &["wait@1"],
            ))
        };
        assert_eq!(c(json!({"k": "${p.steps}"})), Vec::<&str>::new());
        assert_eq!(c(json!({"k": 3})), ["S303"]);
        assert_eq!(c(json!({"k": "literal"})), ["S303"]);
        assert_eq!(c(json!({"k": {"x": "${p}"}})), ["S303"]);
    }

    #[test]
    fn a_huge_threshold_is_not_saturated() {
        let liveness = json!({"mode": "push", "interval": "1ms",
                              "failure_threshold": 5_000_000_000u64});
        let c = codes(catalog(
            json!([receive(
                "r",
                json!("50d"),
                json!({"event_type": "e", "liveness": liveness})
            )]),
            &["wait@1"],
        ));
        assert_eq!(c, ["S303"]);
    }
}
