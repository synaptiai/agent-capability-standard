//! A JSON-in, JSON-out interface for WebAssembly hosts. The Standard has no
//! text on it: this is the reference implementation's packaging, which the
//! TypeScript package `@synaptiai/acs-core` wraps (`packages/acs-core/src/wasm.ts`).
//!
//! Three C-ABI exports, no wasm-bindgen. Every buffer that crosses the
//! boundary is a `Box<[u8]>` of exactly its length: allocated with
//! `vec![0u8; len].into_boxed_slice()` and released with `Box::from_raw` on a
//! slice pointer of that length, so allocation and release use one layout,
//! for every length, 0 included. A request is a JSON object `{"op": ...}`;
//! the answer is `{"ok": <value>}` or `{"error": {"kind", "message",
//! "diagnostics"?}}`. Contexts and runs live in handle tables.
//!
//! The pointer type is `usize`-wide on every target, so the same exports run
//! natively, which is how `core/tests/wasm.rs` tests them.

use std::cell::RefCell;
use std::collections::HashMap;
use std::ptr;

use serde_json::{Map, Value, json};

use crate::diag::Diagnostic;
use crate::exec::{
    Attendance, RecordMode, Response, RestoreOptions, ResumeOptions, Run, SetOptions, Snapshot,
    StartOptions,
};
use crate::expr::check::{Checker, RootInfo, Scope};
use crate::profile::Policy;
use crate::validate::{self, Context, Report};
use crate::{grounding, yaml};

/// A zeroed buffer of `len` bytes for the caller to fill.
#[unsafe(no_mangle)]
pub extern "C" fn acs_alloc(len: usize) -> *mut u8 {
    Box::into_raw(vec![0u8; len].into_boxed_slice()).cast::<u8>()
}

/// Release a buffer from `acs_alloc` or `acs_call`, with the length it has.
///
/// # Safety
/// `ptr` and `len` are exactly a pointer and length that `acs_alloc(len)`
/// returned, or a result of `acs_call` with `len` = 4 + its stated length,
/// not released before.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acs_free(ptr: *mut u8, len: usize) {
    // SAFETY: by the contract above, (ptr, len) is a Box<[u8]> that
    // Box::into_raw produced and nothing has freed: the same layout.
    drop(unsafe { Box::from_raw(ptr::slice_from_raw_parts_mut(ptr, len)) });
}

/// Answer the JSON request in `ptr[..len]`. The result is a new buffer: a
/// 4-byte little-endian length `n`, then `n` bytes of JSON. Release it with
/// `acs_free(result, 4 + n)`; release the request buffer as usual.
///
/// # Safety
/// `ptr[..len]` is readable and initialised (a buffer from `acs_alloc(len)`).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acs_call(ptr: *const u8, len: usize) -> *mut u8 {
    // SAFETY: the caller guarantees ptr[..len] is a live, initialised buffer.
    let request = unsafe { std::slice::from_raw_parts(ptr, len) };
    let mut body = dispatch(request).into_bytes();
    let n = match u32::try_from(body.len()) {
        Ok(n) => n,
        Err(_) => {
            body = too_large();
            u32::try_from(body.len()).unwrap_or(0)
        }
    };
    let mut out = Vec::with_capacity(4 + body.len());
    out.extend_from_slice(&n.to_le_bytes());
    out.extend_from_slice(&body);
    // into_boxed_slice shrinks the allocation to the length.
    Box::into_raw(out.into_boxed_slice()).cast::<u8>()
}

fn too_large() -> Vec<u8> {
    error("too_large", "the answer is larger than 4 GiB", None).into_bytes()
}

#[derive(Default)]
struct Handles {
    contexts: HashMap<u32, Context>,
    runs: HashMap<u32, Run>,
    next: u32,
}

impl Handles {
    fn issue(&mut self) -> u32 {
        self.next = self.next.wrapping_add(1).max(1);
        self.next
    }
}

thread_local! {
    static HANDLES: RefCell<Handles> = RefCell::new(Handles::default());
}

/// Why a request failed: `{"error": {"kind", "message", "diagnostics"?}}`.
struct Fail {
    kind: &'static str,
    message: String,
    diagnostics: Option<Value>,
}

impl Fail {
    fn new(kind: &'static str, message: impl Into<String>) -> Fail {
        Fail {
            kind,
            message: message.into(),
            diagnostics: None,
        }
    }

    fn with(kind: &'static str, message: impl Into<String>, diagnostics: &[Diagnostic]) -> Fail {
        Fail {
            kind,
            message: message.into(),
            diagnostics: Some(serde_json::to_value(diagnostics).unwrap_or(Value::Null)),
        }
    }
}

fn error(kind: &str, message: &str, diagnostics: Option<Value>) -> String {
    let mut e = json!({"kind": kind, "message": message});
    if let Some(d) = diagnostics {
        e["diagnostics"] = d;
    }
    json!({ "error": e }).to_string()
}

/// Answer one request, as JSON text. Safe; every input path is checked, so
/// none panics (a panic would abort a WebAssembly instance).
pub fn dispatch(request: &[u8]) -> String {
    let answer = std::str::from_utf8(request)
        .map_err(|e| Fail::new("bad_request", format!("the request is not UTF-8: {e}")))
        .and_then(|text| {
            crate::exec::read_json(text)
                .map_err(|e| Fail::new("bad_request", format!("the request is not JSON: {e}")))
        })
        .and_then(|value| match value {
            Value::Object(req) => match req.get("op") {
                Some(Value::String(op)) => {
                    let op = op.clone();
                    HANDLES.with(|h| answer(&op, &req, &mut h.borrow_mut()))
                }
                _ => Err(Fail::new("bad_request", "the request has no string 'op'")),
            },
            _ => Err(Fail::new("bad_request", "the request is not a JSON object")),
        });
    match answer {
        Ok(v) => json!({ "ok": v }).to_string(),
        Err(f) => error(f.kind, &f.message, f.diagnostics),
    }
}

type Req = Map<String, Value>;

fn member<'a>(req: &'a Req, key: &str) -> Result<&'a Value, Fail> {
    req.get(key)
        .ok_or_else(|| Fail::new("bad_request", format!("'{key}' is required")))
}

fn string<'a>(req: &'a Req, key: &str) -> Result<&'a str, Fail> {
    member(req, key)?
        .as_str()
        .ok_or_else(|| Fail::new("bad_request", format!("'{key}' must be a string")))
}

fn handle(req: &Req, key: &str) -> Result<u32, Fail> {
    member(req, key)?
        .as_u64()
        .and_then(|h| u32::try_from(h).ok())
        .ok_or_else(|| Fail::new("bad_request", format!("'{key}' must be a handle")))
}

fn time(v: &Value, key: &str) -> Result<u64, Fail> {
    v.as_u64().ok_or_else(|| {
        Fail::new(
            "bad_request",
            format!("'{key}' must be a time in milliseconds"),
        )
    })
}

fn list(req: &Req, key: &str) -> Result<Vec<Value>, Fail> {
    match req.get(key) {
        None | Some(Value::Null) => Ok(Vec::new()),
        Some(Value::Array(a)) => Ok(a.clone()),
        Some(_) => Err(Fail::new("bad_request", format!("'{key}' must be a list"))),
    }
}

/// The version a request states in `key`: a string or `null`, required.
fn header(req: &Req, key: &str, at: &str) -> Result<Option<String>, Fail> {
    match req.get(key) {
        Some(Value::String(h)) => Ok(Some(h.clone())),
        Some(Value::Null) => Ok(None),
        _ => Err(Fail::new(
            "bad_request",
            format!(
                "{at}header is required: the version the catalog's header declares (catalog.parse returns it), or null"
            ),
        )),
    }
}

fn context<'h>(h: &'h Handles, req: &Req) -> Result<&'h Context, Fail> {
    let id = handle(req, "context")?;
    h.contexts
        .get(&id)
        .ok_or_else(|| Fail::new("unknown_handle", format!("no context {id}")))
}

fn run<'h>(h: &'h mut Handles, req: &Req) -> Result<&'h mut Run, Fail> {
    let id = handle(req, "run")?;
    h.runs
        .get_mut(&id)
        .ok_or_else(|| Fail::new("unknown_handle", format!("no run {id}")))
}

fn report_json(report: &Report) -> Value {
    serde_json::to_value(report).unwrap_or(Value::Null)
}

/// Load `profiles`, refusing them when they have an error.
fn policy(ctx: &Context, profiles: &[Value]) -> Result<(Policy, Report), Fail> {
    let mut report = Report::default();
    let policy = Policy::load(profiles, &ctx.ontology, &mut report);
    let errors: Vec<Diagnostic> = report.errors().cloned().collect();
    if errors.is_empty() {
        Ok((policy, report))
    } else {
        Err(Fail::with(
            "bad_request",
            "the domain profiles are refused (STANDARD v1.2 §5.21.2)",
            &errors,
        ))
    }
}

fn hex(text: &str) -> Result<Vec<u8>, Fail> {
    let bad = || Fail::new("bad_request", "'key_hex' must be hexadecimal");
    if !text.len().is_multiple_of(2) {
        return Err(bad());
    }
    (0..text.len())
        .step_by(2)
        .map(|i| {
            text.get(i..i + 2)
                .and_then(|b| u8::from_str_radix(b, 16).ok())
                .ok_or_else(bad)
        })
        .collect()
}

fn key(req: &Req) -> Result<Option<Vec<u8>>, Fail> {
    match req.get("key_hex") {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(k)) => hex(k).map(Some),
        Some(_) => Err(Fail::new("bad_request", "'key_hex' must be a string")),
    }
}

/// The reference roots of an `expr.check` request: each root's schema and
/// whether it is always present.
struct JsonScope<'a>(&'a Map<String, Value>);

impl Scope for JsonScope<'_> {
    fn root(&self, name: &str) -> Option<RootInfo<'_>> {
        let r = self.0.get(name)?;
        Some(RootInfo {
            schema: r.get("schema"),
            always_present: r
                .get("always_present")
                .and_then(Value::as_bool)
                .unwrap_or(false),
        })
    }
}

/// A request's `attendance`: `attended` (the default) or `unattended`.
fn attendance(o: &Req) -> Result<Attendance, Fail> {
    match o.get("attendance").and_then(Value::as_str) {
        None | Some("attended") => Ok(Attendance::Attended),
        Some("unattended") => Ok(Attendance::Unattended),
        Some(other) => Err(Fail::new(
            "bad_request",
            format!("attendance must be 'attended' or 'unattended', not '{other}'"),
        )),
    }
}

/// A request's `actor_identity`, when it gives one (null is none).
fn actor(o: &Req) -> Option<Value> {
    o.get("actor_identity").filter(|v| !v.is_null()).cloned()
}

/// The members of a catalog set a request gives (STANDARD v1.2 §5.1.1,
/// §5.15.1): `catalogs`, the other catalogs, each `{catalog, header}` with
/// `header` its header's version or `null` (required, as for `validate`),
/// and `agents`, agent manifests. Absent or `null`, none.
fn set_options(o: &Req) -> Result<SetOptions, Fail> {
    let catalogs = list(o, "catalogs")?
        .into_iter()
        .enumerate()
        .map(|(i, c)| {
            let Value::Object(m) = c else {
                return Err(Fail::new(
                    "bad_request",
                    format!("catalogs[{i}] must be an object {{catalog, header}}"),
                ));
            };
            let catalog = member(&m, "catalog")
                .map_err(|_| {
                    Fail::new("bad_request", format!("catalogs[{i}].catalog is required"))
                })?
                .clone();
            Ok((catalog, header(&m, "header", &format!("catalogs[{i}]."))?))
        })
        .collect::<Result<Vec<_>, Fail>>()?;
    Ok(SetOptions {
        catalogs,
        agents: list(o, "agents")?,
    })
}

fn start_options(ctx: &Context, o: &Req) -> Result<StartOptions, Fail> {
    let header = header(o, "header", "options.")?;
    let attendance = attendance(o)?;
    let records = match o.get("records").and_then(Value::as_str) {
        None | Some("approvals") => RecordMode::Approvals,
        Some("actions") => RecordMode::Actions,
        Some(other) => {
            return Err(Fail::new(
                "bad_request",
                format!("records must be 'approvals' or 'actions', not '{other}'"),
            ));
        }
    };
    let grounding = list(o, "grounding")?
        .into_iter()
        .enumerate()
        .map(|(i, v)| {
            let p: grounding::Policy = serde_json::from_value(v)
                .map_err(|e| Fail::new("bad_request", format!("grounding[{i}]: {e}")))?;
            let p = grounding::Policy::new(p.require, p.kinds, p.attested)
                .map_err(|e| Fail::new("bad_request", format!("grounding[{i}].{e}")))?;
            p.check_ids(&ctx.ontology)
                .map_err(|e| Fail::new("bad_request", format!("grounding[{i}].{e}")))?;
            Ok(p)
        })
        .collect::<Result<Vec<_>, Fail>>()?;
    let destinations =
        serde_json::from_value::<Vec<Vec<String>>>(Value::Array(list(o, "destinations")?))
            .map_err(|_| {
                Fail::new(
                    "bad_request",
                    "destinations must be a list of lists of strings",
                )
            })?;
    Ok(StartOptions {
        attendance,
        run_id: string(o, "run_id")?.to_string(),
        now_ms: time(member(o, "now_ms")?, "now_ms")?,
        actor_identity: actor(o),
        header,
        records,
        profiles: list(o, "profiles")?,
        grounding,
        destinations,
    })
}

fn answer(op: &str, req: &Req, h: &mut Handles) -> Result<Value, Fail> {
    match op {
        "version" => Ok(json!({
            "core": env!("CARGO_PKG_VERSION"),
            "standard": "1.2.0",
            "spec_versions": crate::validate::semantics::SUPPORTED_VERSIONS
                .iter()
                .map(|(a, b)| format!("{a}.{b}"))
                .collect::<Vec<_>>(),
            "ontology_major": 2,
        })),
        "yaml.parse" => {
            let text = string(req, "text")?;
            let max = req
                .get("max_bytes")
                .and_then(Value::as_u64)
                .unwrap_or(yaml::DEFAULT_MAX_BYTES);
            if text.len() as u64 > max {
                return Err(Fail::new(
                    "yaml",
                    format!("the text is larger than {max} bytes"),
                ));
            }
            yaml::load_str(text).map_err(|e| Fail::new("yaml", e.to_string()))
        }
        "catalog.parse" => {
            let text = string(req, "text")?;
            if text.len() as u64 > yaml::ONTOLOGY_MAX_BYTES {
                return Err(Fail::new("yaml", "the catalog is too large"));
            }
            let catalog = yaml::load_str(text).map_err(|e| Fail::new("yaml", e.to_string()))?;
            Ok(json!({"catalog": catalog, "header": validate::header_version(text)}))
        }
        "context.new" => {
            let ontology = member(req, "ontology")?;
            let documents = match req.get("documents") {
                None | Some(Value::Null) => Vec::new(),
                Some(Value::Object(m)) => m.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
                Some(_) => {
                    return Err(Fail::new(
                        "bad_request",
                        "'documents' must map paths to documents",
                    ));
                }
            };
            let ctx = Context::from_values(ontology, documents)
                .map_err(|e| Fail::new("load", e.to_string()))?;
            let id = h.issue();
            h.contexts.insert(id, ctx);
            Ok(json!({ "context": id }))
        }
        "context.drop" => {
            let id = handle(req, "context")?;
            h.contexts.remove(&id);
            Ok(Value::Null)
        }
        "context.contracts" => Ok(context(h, req)?.contracts_json()),
        "validate" => {
            let ctx = context(h, req)?;
            let set = set_options(req)?;
            let options = validate::Options {
                header: header(req, "header", "")?,
                profiles: list(req, "profiles")?,
                catalogs: set.catalogs,
                agents: set.agents,
            };
            let catalog = member(req, "catalog")?;
            validate::validate_with(ctx, catalog, &options)
                .map(|r| report_json(&r))
                .map_err(|e| Fail::new("load", e.to_string()))
        }
        "profile.check" => {
            let ctx = context(h, req)?;
            let mut report = Report::default();
            Policy::load(&list(req, "profiles")?, &ctx.ontology, &mut report);
            Ok(json!({ "diagnostics": report.diagnostics }))
        }
        "profile.flags" => {
            let ctx = context(h, req)?;
            let (policy, _) = policy(ctx, &list(req, "profiles")?)?;
            let capability = string(req, "capability")?;
            let declared = match req.get("declared") {
                None | Some(Value::Null) => None,
                Some(Value::Object(m)) => Some(m),
                Some(_) => return Err(Fail::new("bad_request", "'declared' must be an object")),
            };
            policy
                .flags_json(&ctx.ontology, capability, declared)
                .ok_or_else(|| {
                    Fail::new(
                        "bad_request",
                        format!("capability '{capability}' not found in ontology (V101)"),
                    )
                })
        }
        "profile.policy" => {
            let ctx = context(h, req)?;
            Ok(policy(ctx, &list(req, "profiles")?)?.0.rules_json())
        }
        "expr.eval" => {
            let src = string(req, "expr")?;
            let bindings = match req.get("bindings") {
                None | Some(Value::Null) => Map::new(),
                Some(Value::Object(m)) => m.clone(),
                Some(_) => return Err(Fail::new("bad_request", "'bindings' must be an object")),
            };
            Ok(match crate::expr::parse(src) {
                Err(_) => json!({"error": "V108"}),
                Ok(e) => match crate::expr::eval::eval_condition(&e, &bindings) {
                    Ok(v) => json!({ "value": v }),
                    Err(_) => json!({"error": "R405"}),
                },
            })
        }
        "expr.check" => {
            let src = string(req, "expr")?;
            let scope = match req.get("scope") {
                None | Some(Value::Null) => Map::new(),
                Some(Value::Object(m)) => m.clone(),
                Some(_) => return Err(Fail::new("bad_request", "'scope' must be an object")),
            };
            let scope = JsonScope(&scope);
            let codes: Vec<&'static str> = match crate::expr::parse(src) {
                Err(e) => vec![e.kind.code().as_str()],
                Ok(e) => {
                    let mut c = Checker::new(&scope);
                    c.check_condition(&e);
                    c.findings.iter().map(|f| f.code.as_str()).collect()
                }
            };
            Ok(json!({ "codes": codes }))
        }
        "run.start" => {
            let ctx = context(h, req)?;
            let options = match req.get("options") {
                Some(Value::Object(o)) => o,
                _ => return Err(Fail::new("bad_request", "'options' must be an object")),
            };
            let set = set_options(options)?;
            let options = start_options(ctx, options)?;
            // A run reports its profiles' warnings (W602-W604), as the
            // validator and `profile.check` do (§5.21.4): a host applying
            // profiles only through `run.start` sees them here.
            let mut loaded = Report::default();
            if !options.profiles.is_empty() {
                Policy::load(&options.profiles, &ctx.ontology, &mut loaded);
            }
            let inputs = match req.get("inputs") {
                None | Some(Value::Null) => Map::new(),
                Some(Value::Object(m)) => m.clone(),
                Some(_) => return Err(Fail::new("bad_request", "'inputs' must be an object")),
            };
            let catalog = member(req, "catalog")?;
            let workflow = string(req, "workflow")?;
            let started =
                Run::start_set(ctx, catalog, &set, workflow, inputs, options).map_err(|e| {
                    let message = e.to_string();
                    match e {
                        crate::exec::StartError::Invalid(d) => Fail::with("start", message, &d),
                        _ => Fail::new("start", message),
                    }
                })?;
            let id = h.issue();
            h.runs.insert(id, started);
            Ok(json!({ "run": id, "warnings": loaded.diagnostics }))
        }
        "run.restore" => {
            let ctx = context(h, req)?;
            let snapshot: Snapshot = serde_json::from_value(member(req, "snapshot")?.clone())
                .map_err(|e| Fail::new("bad_request", format!("malformed snapshot: {e}")))?;
            let key = key(req)?;
            let options = RestoreOptions {
                actor_identity: actor(req),
            };
            let restored = Run::restore_set(
                ctx,
                member(req, "catalog")?,
                &set_options(req)?,
                &snapshot,
                key.as_deref(),
                options,
            )
            .map_err(|e| Fail::new("restore", e.to_string()))?;
            let id = h.issue();
            h.runs.insert(id, restored);
            Ok(json!({ "run": id }))
        }
        "run.next" => {
            serde_json::to_value(run(h, req)?.next()).map_err(|e| Fail::new("run", e.to_string()))
        }
        "run.trace" => {
            // With `since`, the events whose `seq` is at least `since`.
            let since = match req.get("since") {
                None | Some(Value::Null) => None,
                Some(v) => Some(time(v, "since")?),
            };
            let events = run(h, req)?.trace();
            let from = since.map_or(0, |s| {
                events.partition_point(|e| e["seq"].as_u64().is_some_and(|q| q < s))
            });
            Ok(Value::Array(events[from..].to_vec()))
        }
        "run.trace_seq" => Ok(json!(run(h, req)?.trace_seq())),
        "run.action_records" => Ok(Value::Array(run(h, req)?.action_records().to_vec())),
        "run.finished" => Ok(Value::Bool(run(h, req)?.is_finished())),
        "run.submit" => {
            let id = member(req, "id")?
                .as_u64()
                .ok_or_else(|| Fail::new("bad_request", "'id' must be an action id"))?;
            let response: Response = serde_json::from_value(member(req, "response")?.clone())
                .map_err(|e| Fail::new("bad_request", format!("malformed response: {e}")))?;
            let now = time(member(req, "now_ms")?, "now_ms")?;
            run(h, req)?
                .submit(id, response, now)
                .map_err(|e| Fail::new("submit", e.to_string()))?;
            Ok(Value::Null)
        }
        "run.tick" => {
            let now = time(member(req, "now_ms")?, "now_ms")?;
            Ok(json!({ "changed": run(h, req)?.tick(now) }))
        }
        // The host protocol's run operations (STANDARD v1.2 §5.19.2).
        "run.run_id" => Ok(json!(run(h, req)?.run_id())),
        "run.wake_at" => Ok(json!(run(h, req)?.wake_at())),
        "run.cancel" => {
            let reason = string(req, "reason")?.to_string();
            let now = time(member(req, "now_ms")?, "now_ms")?;
            run(h, req)?
                .cancel(&reason, now)
                .map_err(|e| Fail::new("run", e.to_string()))?;
            Ok(Value::Null)
        }
        "run.resume" => {
            let options = ResumeOptions {
                attendance: attendance(req)?,
                now_ms: time(member(req, "now_ms")?, "now_ms")?,
                actor_identity: actor(req),
            };
            run(h, req)?
                .resume(options)
                .map_err(|e| Fail::new("run", e.to_string()))?;
            Ok(Value::Null)
        }
        "run.take_trace" => Ok(Value::Array(run(h, req)?.take_trace())),
        "run.take_records" => Ok(Value::Array(run(h, req)?.take_records())),
        "run.taken_sha256" => {
            let (records, trace) = run(h, req)?.taken_heads();
            Ok(json!({ "records": records, "trace": trace }))
        }
        "run.run_record" => Ok(run(h, req)?.run_record().unwrap_or(Value::Null)),
        "run.snapshot" => {
            let key = key(req)?;
            serde_json::to_value(run(h, req)?.snapshot(key.as_deref()))
                .map_err(|e| Fail::new("run", e.to_string()))
        }
        "run.drop" => {
            let id = handle(req, "run")?;
            h.runs.remove(&id);
            Ok(Value::Null)
        }
        other => Err(Fail::new("unknown_op", format!("unknown op '{other}'"))),
    }
}
