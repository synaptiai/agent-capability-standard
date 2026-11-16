//! The reference executor (design-114 §16): a deterministic, sans-IO state
//! machine. The host asks for the next [`Action`], performs it, and submits
//! a [`Response`]; time enters only through the `now_ms` the host passes.
//! The same catalog, inputs, responses and times always give the same
//! actions, trace and snapshot.

pub mod canonical;
mod machine;
pub mod program;
mod quorum;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::diag::Diagnostic;
use crate::validate::{self, Context};
use crate::{destination, grounding};
use machine::Machine;
use program::Program;

/// Nested `invoke` runs, the root included.
pub const MAX_FRAMES: usize = 4;
/// The snapshot format this executor writes. It also reads version 1, the
/// format before Standard 1.2, whose terminal action held copies of the
/// records, outputs and deferrals (§5.19.4).
pub const SNAPSHOT_VERSION: u32 = 2;
/// Times (ms since the epoch) are capped at 9999-12-31T23:59:59.999Z: every
/// time stays an exact JSON number (I-JSON, RFC 7493, below 2^53) and an
/// RFC 3339 timestamp (a four-digit year).
pub const MAX_TIME: u64 = 253_402_300_799_999;
/// The deepest value a run accepts from its host or its inputs; a snapshot
/// nests it a few levels deeper and still parses.
pub const MAX_VALUE_DEPTH: usize = 100;

/// Values a run takes in must be I-JSON (RFC 7493), so that snapshots and
/// approval digests (RFC 8785) represent them exactly: integers within
/// ±2^53, and at most [`MAX_VALUE_DEPTH`] levels deep.
pub(crate) fn ijson(value: &Value) -> Result<(), String> {
    let limit = 1u64 << 53;
    let mut stack = vec![(value, 0usize)];
    while let Some((v, depth)) = stack.pop() {
        if depth > MAX_VALUE_DEPTH {
            return Err(format!(
                "a value nests deeper than {MAX_VALUE_DEPTH} levels"
            ));
        }
        match v {
            Value::Number(n) => {
                let exact = n.as_u64().is_none_or(|u| u <= limit)
                    && n.as_i64().is_none_or(|i| i.unsigned_abs() <= limit);
                if !exact {
                    return Err(format!(
                        "the integer {n} is outside ±2^53 and has no exact JSON (I-JSON) form"
                    ));
                }
            }
            Value::Array(a) => stack.extend(a.iter().map(|x| (x, depth + 1))),
            Value::Object(m) => stack.extend(m.values().map(|x| (x, depth + 1))),
            _ => {}
        }
    }
    Ok(())
}

/// The largest integer magnitude JSON text may hold for a run: 2^53.
const MAX_EXACT_INTEGER: &str = "9007199254740992";

/// Read JSON text as a host value (§5.14): an integer literal (no fraction
/// or exponent) of magnitude above 2^53 is refused, including one too long
/// for 64 bits, which serde_json would read as a binary64 value; so is an
/// object in which a member name appears twice, of which serde_json would
/// keep the last. The value must also be I-JSON ([`ijson`]).
pub fn read_json(text: &str) -> Result<Value, String> {
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'"' => {
                // Skip the string, escapes included; an unterminated one is
                // left for the parser to report.
                i += 1;
                while i < bytes.len() && bytes[i] != b'"' {
                    i += if bytes[i] == b'\\' { 2 } else { 1 };
                }
                i += 1;
            }
            b'-' | b'0'..=b'9' => {
                let start = i;
                while i < bytes.len()
                    && matches!(bytes[i], b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9')
                {
                    i += 1;
                }
                let token = &text[start..i];
                let digits = token.strip_prefix('-').unwrap_or(token);
                let integer = !token.contains(['.', 'e', 'E']);
                let too_large = digits.len() > MAX_EXACT_INTEGER.len()
                    || (digits.len() == MAX_EXACT_INTEGER.len() && digits > MAX_EXACT_INTEGER);
                if integer && too_large {
                    return Err(format!(
                        "the integer {token} is outside ±2^53 and has no exact JSON (I-JSON) form"
                    ));
                }
            }
            _ => i += 1,
        }
    }
    let Strict(value) = serde_json::from_str(text).map_err(|e| e.to_string())?;
    ijson(&value)?;
    Ok(value)
}

/// A JSON value read so that a member name repeated in one object is an
/// error (I-JSON, RFC 7493 §2.3): parsed, the value could not show it.
struct Strict(Value);

impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        d.deserialize_any(StrictVisitor).map(Strict)
    }
}

struct StrictVisitor;

impl<'de> serde::de::Visitor<'de> for StrictVisitor {
    type Value = Value;

    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str("a JSON value")
    }

    fn visit_bool<E>(self, v: bool) -> Result<Value, E> {
        Ok(Value::Bool(v))
    }

    fn visit_i64<E>(self, v: i64) -> Result<Value, E> {
        Ok(v.into())
    }

    fn visit_u64<E>(self, v: u64) -> Result<Value, E> {
        Ok(v.into())
    }

    fn visit_f64<E>(self, v: f64) -> Result<Value, E> {
        Ok(serde_json::Number::from_f64(v).map_or(Value::Null, Value::Number))
    }

    fn visit_str<E>(self, v: &str) -> Result<Value, E> {
        Ok(Value::String(v.to_owned()))
    }

    fn visit_string<E>(self, v: String) -> Result<Value, E> {
        Ok(Value::String(v))
    }

    fn visit_unit<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }

    fn visit_seq<A: serde::de::SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut items = Vec::new();
        while let Some(Strict(v)) = seq.next_element()? {
            items.push(v);
        }
        Ok(Value::Array(items))
    }

    fn visit_map<A: serde::de::MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut members = Map::new();
        while let Some(name) = map.next_key::<String>()? {
            if members.contains_key(&name) {
                return Err(serde::de::Error::custom(format!(
                    "the member name {name:?} appears twice in one object, which I-JSON forbids"
                )));
            }
            let Strict(v) = map.next_value()?;
            members.insert(name, v);
        }
        Ok(Value::Object(members))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Attendance {
    Attended,
    Unattended,
}

/// Which action records a run writes (§6.4): the 1.1 records of approved,
/// refused and deferred actions, or a record of every action.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordMode {
    #[default]
    Approvals,
    Actions,
}

impl RecordMode {
    fn is_default(&self) -> bool {
        *self == RecordMode::default()
    }
}

/// How a run starts (§5.19.2). There is no `Default`: every construction
/// names every member, so no caller leaves the catalog's `header` out by
/// accident (§11.5).
#[derive(Debug, Clone)]
pub struct StartOptions {
    pub attendance: Attendance,
    pub run_id: String,
    pub now_ms: u64,
    /// Who runs the workflow (`agent_identity`, §5.17): every action record
    /// carries it as `actor_identity`.
    pub actor_identity: Option<Value>,
    /// The version the catalog's `# Standard version:` header declares, or
    /// none for a catalog without one (§11.5): a host that loaded the
    /// catalog from a file passes the version its header declares. The run
    /// validates the catalog with it, as a validator reading the file would.
    pub header: Option<String>,
    /// Which action records the run writes (§6.4).
    pub records: RecordMode,
    /// Domain profiles to apply (§5.21), as given. They are checked when
    /// the run starts (an error refuses it), cover every step of the run
    /// and of its nested runs, and are saved with it.
    pub profiles: Vec<Value>,
    /// The host's grounding policies (§5.20): each applies to the steps of
    /// the run and of its nested runs. A policy that requires a capability
    /// the ontology does not define is refused (`StartError::Grounding`).
    pub grounding: Vec<grounding::Policy>,
    /// The host's destination policies (§4.4.2): with the applied
    /// profiles' `allowed_destinations`, the policies a `send` step's
    /// destination must meet. A policy that holds an invalid pattern is
    /// refused (`StartError::Policy`).
    pub destinations: Vec<Vec<String>>,
}

/// What a run is given besides its catalog: the other catalogs of its
/// catalog set, each with its header's version (§5.1.1), and the agent
/// manifests of the agents it may delegate to (§5.15.1). A snapshot restores
/// only against the same set and manifests (the digest covers them when
/// given).
#[derive(Debug, Clone, Default)]
pub struct SetOptions {
    pub catalogs: Vec<(Value, Option<String>)>,
    pub agents: Vec<Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Completed,
    Escalated,
    Deferred,
    ReplanRequired,
}

/// What the host should do next (§5.19.1).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Action {
    /// The run's identifier (§5.19.2): with `id`, the action's delivery key
    /// (§5.19.4).
    #[serde(default)]
    pub run_id: String,
    pub id: u64,
    /// The workflows of the nested runs, root first.
    pub frame: Vec<String>,
    #[serde(flatten)]
    pub body: Body,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub enum Body {
    InvokeCapability {
        step: usize,
        capability: String,
        store_as: Option<String>,
        domain: Option<String>,
        inputs: Value,
        deadline: Option<u64>,
        attempt: u32,
        /// The pass's idempotency key (§4.4.2): `<run_id>:<n>`, `n` the `id`
        /// of the pass's first `InvokeCapability`, the same for every attempt
        /// of the pass. Always present on an action this executor issues;
        /// absent only on a pending action read from a state that predates
        /// keys, which `restore` fills in (§5.19.4).
        #[serde(default, skip_serializing_if = "Option::is_none")]
        idempotency_key: Option<String>,
        /// A waiting `delegate` delegated again (§5.13): the `task_id` of
        /// the delegation this one replaces, which the host may cancel.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        replaces: Option<Value>,
    },
    CreateCheckpoint {
        step: usize,
    },
    Rollback {
        step: usize,
        checkpoint_id: String,
    },
    RequestApproval {
        step: usize,
        approver: Value,
        mode: String,
        shown: Value,
        digest: String,
        expires_at: Option<u64>,
        /// A resumed run asks about a queued action (§5.14.1): the
        /// `action_id` of the record its deferral left, on every request of
        /// the step while the step continues that action.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        queued_action_id: Option<String>,
    },
    RecheckSource {
        step: usize,
        source: String,
        compare: String,
    },
    AwaitEvent {
        step: usize,
        event_type: String,
        source_kind: Option<String>,
        correlate: Map<String, Value>,
        accept_from: Option<Vec<String>>,
        /// `identity@1`: accepted `authenticated_by` values and trust classes.
        #[serde(default)]
        sender_check: Option<Vec<String>>,
        #[serde(default)]
        accept_trust_classes: Option<Vec<String>>,
        /// `identity@1`: the principal a waiting delegate's host attested
        /// for the delegation (`effective.identity`); only its results are
        /// kept (§5.17).
        #[serde(default, skip_serializing_if = "Option::is_none")]
        delegate_principal: Option<String>,
        liveness: Option<Value>,
        deadline: Option<u64>,
    },
    Sleep {
        until: u64,
    },
    Completed {
        outcome: Outcome,
        /// The cause of an escalation.
        cause: Option<String>,
        /// A gate ended the run (`action: end`, §5.6): `{step, message}`.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        ended: Option<Value>,
        outputs: Value,
        action_records: Vec<Value>,
        /// Steps deferred to a queue, or deferred because they depend on
        /// one (§5.14): `{frame, step, store_as, reason, action_id}`.
        deferred: Vec<Value>,
    },
    Failed {
        code: String,
        step: Option<usize>,
        message: String,
        /// The reason the failure came with (§5.19.7), if any.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason: Option<String>,
        /// A cancelled run (R408, §5.19.5): the latest checkpoint the run
        /// knows of, which the host may restore itself.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        checkpoint_id: Option<String>,
        action_records: Vec<Value>,
        /// As for `Completed`: deferrals made before the run failed.
        deferred: Vec<Value>,
    },
}

impl Body {
    pub fn kind(&self) -> &'static str {
        match self {
            Body::InvokeCapability { .. } => "InvokeCapability",
            Body::CreateCheckpoint { .. } => "CreateCheckpoint",
            Body::Rollback { .. } => "Rollback",
            Body::RequestApproval { .. } => "RequestApproval",
            Body::RecheckSource { .. } => "RecheckSource",
            Body::AwaitEvent { .. } => "AwaitEvent",
            Body::Sleep { .. } => "Sleep",
            Body::Completed { .. } => "Completed",
            Body::Failed { .. } => "Failed",
        }
    }

    pub fn is_terminal(&self) -> bool {
        matches!(self, Body::Completed { .. } | Body::Failed { .. })
    }
}

/// The host's answer to the pending action.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub enum Response {
    Output {
        value: Value,
        /// The refs of the evidence the host attests the output's producer
        /// had for this answer (§3.1, §5.20). Absent attests nothing; an
        /// empty list attests that the producer had none.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        evidence_seen: Option<Vec<String>>,
    },
    Error {
        code: String,
        #[serde(default)]
        message: String,
        /// Why, as a token (§5.19.7). Any value deserialises: one outside
        /// the grammar is ignored (and traced), never refused.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason: Option<Value>,
    },
    Checkpoint {
        checkpoint_id: String,
    },
    /// The checkpoint is restored: everything it captured is back
    /// (§4.4.1). `not_covered` lists changes since the checkpoint that it
    /// never covered (a transmission, a delegate's change elsewhere).
    RolledBack {
        #[serde(default, skip_serializing_if = "Option::is_none")]
        not_covered: Option<Vec<Value>>,
    },
    Decision {
        decision_id: String,
        decision: String,
        #[serde(default)]
        approvers: Vec<String>,
        digest: String,
        /// `identity@1`: who decided, as the host attests them (§5.17), one
        /// `agent_identity` per principal. Checked in `submit`; ignored
        /// without the extension.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        approver_identities: Option<Value>,
    },
    Current {
        value: Value,
    },
    Event {
        event: Value,
        #[serde(default)]
        principal: Option<String>,
        /// The sender's `agent_identity` (§5.17). Its `principal`, when both
        /// are given, must equal `principal`.
        #[serde(default)]
        identity: Option<Value>,
    },
    LivenessLost,
}

impl Response {
    pub fn kind(&self) -> &'static str {
        match self {
            Response::Output { .. } => "Output",
            Response::Error { .. } => "Error",
            Response::Checkpoint { .. } => "Checkpoint",
            Response::RolledBack { .. } => "RolledBack",
            Response::Decision { .. } => "Decision",
            Response::Current { .. } => "Current",
            Response::Event { .. } => "Event",
            Response::LivenessLost => "LivenessLost",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum StartError {
    /// The catalog does not validate; the run never starts.
    Invalid(Vec<Diagnostic>),
    Inputs(String),
    Program(String),
    /// The actor identity is not an `agent_identity`.
    Identity(String),
    /// A start option this executor does not implement yet.
    Unsupported(String),
    /// The catalog header's version is not a version (§11.5).
    Header(String),
    /// A grounding policy is malformed or requires a capability the
    /// ontology does not define (§5.20, V101).
    Grounding(String),
    /// A destination policy holds an invalid pattern (§4.4.2).
    Policy(String),
}

impl fmt::Display for StartError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            StartError::Invalid(d) => {
                let codes: Vec<&str> = d.iter().map(|d| d.code.as_str()).collect();
                write!(
                    f,
                    "the catalog does not validate ({}); a workflow is only run once it validates",
                    codes.join(", ")
                )
            }
            StartError::Inputs(m) | StartError::Program(m) => f.write_str(m),
            StartError::Identity(m) => write!(f, "actor_identity: {m}"),
            StartError::Grounding(m) => f.write_str(m),
            StartError::Policy(m) => write!(f, "destination policy: {m}"),
            StartError::Unsupported(m) => write!(f, "this executor does not implement {m} yet"),
            StartError::Header(h) => write!(
                f,
                "header: '{h}' is not a version (MAJOR.MINOR[.PATCH]); pass the version the catalog's header declares, or none"
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum SubmitError {
    Finished,
    WrongAction {
        pending: u64,
        got: u64,
    },
    Unexpected {
        action: &'static str,
        response: &'static str,
    },
    /// A value in the response is not I-JSON.
    Malformed(String),
}

impl fmt::Display for SubmitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SubmitError::Finished => f.write_str("the run has finished"),
            SubmitError::WrongAction { pending, got } => write!(
                f,
                "the response answers action {got}, but action {pending} is pending"
            ),
            SubmitError::Unexpected { action, response } => {
                write!(f, "a {response} response does not answer a {action} action")
            }
            SubmitError::Malformed(m) => write!(f, "malformed response: {m}"),
        }
    }
}

/// A run that cannot be cancelled (§5.19.5).
#[derive(Debug, Clone, PartialEq)]
pub enum CancelError {
    /// The run ended, and not `deferred`: how it ended.
    Ended(String),
}

impl fmt::Display for CancelError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CancelError::Ended(how) => write!(
                f,
                "the run has ended ({how}); only a run that has not ended, or one that ended deferred, can be cancelled (§5.19.5)"
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum RestoreError {
    Malformed(String),
    Digest,
    Hmac,
    Catalog,
    Version(u64),
    Start(StartError),
    /// The actor the host restores the run for is not the run's (§5.17).
    Actor(String),
}

impl fmt::Display for RestoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RestoreError::Malformed(m) => write!(f, "malformed snapshot: {m}"),
            RestoreError::Digest => f.write_str("the snapshot's SHA-256 does not match its state"),
            RestoreError::Hmac => f.write_str("the snapshot's HMAC does not match (or is missing)"),
            RestoreError::Catalog => {
                f.write_str("the snapshot was taken against a different catalog")
            }
            RestoreError::Version(v) => write!(f, "unsupported snapshot version {v}"),
            RestoreError::Start(e) => write!(f, "{e}"),
            RestoreError::Actor(m) => write!(f, "actor_identity: {m}"),
        }
    }
}

/// How a host restores a saved run (§5.19.4).
#[derive(Debug, Clone, Default)]
pub struct RestoreOptions {
    /// The actor the host continues the run for (§5.17): its principal must
    /// be the run's. `None` checks nothing.
    pub actor_identity: Option<Value>,
}

/// How a host resumes a run that ended `deferred` (§5.14.1).
#[derive(Debug, Clone)]
pub struct ResumeOptions {
    /// The run's attendance from now on.
    pub attendance: Attendance,
    pub now_ms: u64,
    /// Who carries the run on (§5.17): `None` keeps the run's actor.
    pub actor_identity: Option<Value>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ResumeError {
    /// Only a run that ended `deferred` can be resumed (§5.14.1).
    NotDeferred(String),
    /// The new actor is not an `agent_identity`.
    Identity(String),
    /// The state does not keep what resumption needs: the nested run of a
    /// deferred invoke step, or which steps ran ahead (§5.14.1).
    NotKept(String),
}

impl fmt::Display for ResumeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ResumeError::NotDeferred(m) => write!(
                f,
                "only a run that ended deferred can be resumed (§5.14.1); {m}"
            ),
            ResumeError::Identity(m) => write!(f, "actor_identity: {m}"),
            ResumeError::NotKept(m) => write!(
                f,
                "the saved state does not keep {m}, which resuming needs (§5.14.1); cancel the run and start a new one"
            ),
        }
    }
}

/// A checkpoint the run knows of. A checkpoint authorises one step that
/// requires one, and stops authorising when a wait completes after it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Checkpoint {
    pub id: String,
    pub valid: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct StepError {
    pub code: String,
    pub message: String,
    /// The reason the failure came with (§5.19.7).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

/// The current step's working state.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub(crate) struct StepState {
    pub attempt: u32,
    pub inputs: Value,
    pub output: Option<Value>,
    pub error: Option<StepError>,
    /// Index into the run's action records.
    pub record: Option<usize>,
    /// The recheck source's value as approved.
    pub baseline: Option<Value>,
    /// After a recheck saw a change and asked again: the value to approve.
    pub rebaseline: Option<Value>,
    /// ...and the value approved before it, shown with the change.
    pub previous: Option<Value>,
    /// Events dropped while waiting, by reason.
    pub dropped: Map<String, Value>,
    /// The step's output holds an item from an always-ask trust class, or
    /// its nested run used one (§5.17).
    #[serde(default)]
    pub always_ask: bool,
    /// An applied profile requires a person for the step (§5.21.3), and
    /// the trace says so: traced once per step. It marks nothing.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub person: bool,
    /// A `delegate` step that waits (§5.13): the delegation's output, once
    /// the host has delegated; the step then waits for the result.
    #[serde(default)]
    pub delegated: Option<Value>,
    /// The deadline the delegation started under: the wait keeps it, so
    /// one `timeout` bounds both phases.
    #[serde(default)]
    pub deadline: Option<u64>,
    /// The `task_id` of a delegation a retry replaces.
    #[serde(default)]
    pub replaces: Option<Value>,
    /// An after-gate with `action: end` fired (its message, or null): the
    /// run ends once the step's failure modes are checked, unless one fires.
    #[serde(default)]
    pub ending: Option<Value>,
    /// The checkpoint the step used or, for a `checkpoint` step, took: its
    /// action records name it (§6.4).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub checkpoint_id: Option<String>,
    /// The step has started its pass (§5.19.5): the executor issued a
    /// `CreateCheckpoint`, `InvokeCapability` or `AwaitEvent` for it, started
    /// its nested run, or evaluated its quorum. A cancelled run records such
    /// a step in record mode `actions`.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub started: bool,
    /// The pass's idempotency key (§4.4.2), once the step has called its
    /// capability: every attempt of the pass carries it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "stage")]
pub(crate) enum Stage {
    Begin,
    /// `delay` (§5.13): sleeping before the step goes on.
    Delay {
        until: u64,
    },
    /// The condition and before-gates passed (and any delay is over): the
    /// step's inputs are resolved next.
    Ready,
    Checkpoint,
    Approval,
    Recheck,
    Execute,
    Backoff {
        until: u64,
    },
    After,
    Failure,
}

/// One running workflow; nested `invoke` runs push frames.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Frame {
    pub workflow: String,
    pub inputs: Map<String, Value>,
    pub stores: Map<String, Value>,
    /// The resolved inputs each stored step ran with.
    pub ran_inputs: Map<String, Value>,
    /// `${_recovery.*}`: context injected by recovery loops.
    pub recovery: Option<Value>,
    /// `step:failure_mode` → loops taken.
    pub loops: Map<String, Value>,
    pub step: usize,
    pub stage: Stage,
    pub cur: StepState,
    /// While running a handler: the code that caused the escalation.
    pub escalation: Option<String>,
    /// Steps of this frame deferred to a queue, or deferred because they
    /// depend on one (§5.14), in list order. The frame ends `deferred` when
    /// any is.
    #[serde(default)]
    pub deferred: Vec<usize>,
    /// For a deferred invoke step: the capabilities its nested run deferred
    /// (transitively), so ontology order sees through nested runs.
    #[serde(default)]
    pub nested_caps: BTreeMap<usize, Vec<String>>,
    /// Stores and inputs that hold, or were computed from, an item from an
    /// always-ask trust class (§5.17): a step reading one needs a person's
    /// approval.
    #[serde(default)]
    pub always_ask: BTreeSet<String>,
    /// Invoked by a marked step: every step of this run is marked.
    #[serde(default)]
    pub marked: bool,
    /// A recovery loop back to (or to before) waiting delegates: the
    /// delegation each one's next delegation replaces, in step order.
    #[serde(default)]
    pub replaces: Vec<Replacement>,
    /// A gate ended this run (`action: end`): `{step, message}`.
    #[serde(default)]
    pub ended: Option<Value>,
    /// During a resumption (§5.14.1): the steps of this frame still to run,
    /// in the order they run (step order; a deferred handler last).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resume: Option<Vec<usize>>,
    /// For a deferred `invoke` step: the nested run that ended `deferred`
    /// under it, kept so that a resumption continues it.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub parked: BTreeMap<usize, Frame>,
    /// During a resumption: the cause of the escalation whose deferred
    /// handler runs after the normal-flow steps.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pending_escalation: Option<String>,
    /// During a resumption: the queued action a re-entered step continues
    /// (§5.14.1), until the step goes on, carries the action out, is
    /// deferred again or its run leaves it. A recovery loop that runs the
    /// step again before then keeps it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub queued: Option<Queued>,
    /// While a step of this frame is deferred: the steps that began since,
    /// and were not deferred themselves (they ran ahead, §5.14). `None` while
    /// nothing is deferred, and in a state saved before this was tracked:
    /// such a frame with deferred steps cannot be resumed.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ahead: Option<BTreeSet<usize>>,
}

/// The queued action step `step` of a frame continues: the index of the
/// record its deferral left (§5.14.1).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Queued {
    pub step: usize,
    pub record: usize,
}

/// A delegation to name as replaced when step `step` next delegates.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Replacement {
    pub step: usize,
    pub task_id: Value,
}

/// What the pending action is waiting for, beyond the action itself.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "purpose")]
pub(crate) enum Purpose {
    Capability,
    Event,
    Checkpoint,
    FailureCheckpoint {
        mode: usize,
    },
    GateRollback {
        message: String,
    },
    FailureRollback {
        mode: usize,
    },
    Approval {
        digest: String,
        expires_at: Option<u64>,
        min: u64,
    },
    Recheck,
    Sleep,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct Pending {
    pub action: Action,
    pub purpose: Purpose,
    pub deadline: Option<u64>,
}

/// Everything that changes during a run, and all a snapshot holds.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct State {
    pub version: u32,
    pub run_id: String,
    pub root: String,
    pub attendance: Attendance,
    pub catalog_digest: String,
    pub now: u64,
    pub next_id: u64,
    pub frames: Vec<Frame>,
    pub pending: Option<Pending>,
    /// How the run ended: the head of its terminal action, whose records,
    /// outputs and deferrals `next()` derives from the state (§5.19.1).
    pub finished: Option<Terminal>,
    pub checkpoints: Vec<Checkpoint>,
    pub used_decisions: BTreeSet<String>,
    pub records: Vec<Value>,
    pub trace: Vec<Value>,
    /// Every deferral of the run, in order, across nested runs.
    #[serde(default)]
    pub deferrals: Vec<Deferral>,
    /// Who runs the workflow (§5.17), recorded on every action record.
    #[serde(default)]
    pub actor_identity: Option<Value>,
    /// The catalog header's version the run started with (§11.5): a
    /// restored run validates the catalog with it again. The members below
    /// are left out of a snapshot while they have their default, so a 1.1
    /// run's snapshot is unchanged.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub header: Option<String>,
    /// The action records the run writes (§6.4).
    #[serde(default, skip_serializing_if = "RecordMode::is_default")]
    pub records_mode: RecordMode,
    /// The domain profiles applied, as given (§5.21).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub profiles: Vec<Value>,
    /// The host's grounding policies (§5.20).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub grounding: Vec<grounding::Policy>,
    /// The host's destination policies (§4.4.2).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub destinations: Vec<Vec<String>>,
    /// The run was resumed (§5.14.1): a queued record it writes again,
    /// superseding it included, takes the time and actor of then.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub resumed: bool,
    /// Trace events the host took (`take_trace`, §5.19.4): `seq` goes on
    /// from here.
    #[serde(default, skip_serializing_if = "is_zero_u64")]
    pub trace_base: u64,
    /// Action records the host took (`take_records`): record indices, and
    /// the `<n>` of `action_id`, count them.
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub records_base: usize,
    /// The chain heads over what the host took, in order (§5.19.4): each
    /// item taken replaces `h` by `sha256_hex(h ‖ canonical_json(item))`,
    /// from the empty string. A state that verifies so vouches for them.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub records_taken_sha256: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub trace_taken_sha256: String,
}

fn is_zero_u64(n: &u64) -> bool {
    *n == 0
}

fn is_zero_usize(n: &usize) -> bool {
    *n == 0
}

/// How a run ended: what its terminal action holds besides the records,
/// outputs and deferrals, which the state already holds (§5.19.1).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub(crate) struct Terminal {
    pub id: u64,
    pub frame: Vec<String>,
    #[serde(flatten)]
    pub end: End,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind")]
pub(crate) enum End {
    Completed {
        outcome: Outcome,
        cause: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        ended: Option<Value>,
    },
    Failed {
        code: String,
        step: Option<usize>,
        message: String,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reason: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        checkpoint_id: Option<String>,
    },
}

impl End {
    /// How the run ended, in words: its outcome, or its code.
    pub(crate) fn describe(&self) -> String {
        match self {
            End::Completed { outcome, .. } => serde_json::to_value(outcome)
                .ok()
                .and_then(|v| v.as_str().map(str::to_string))
                .unwrap_or_default(),
            End::Failed { code, .. } => format!("failed with {code}"),
        }
    }

    /// The end of the terminal action `body`, if it is one.
    fn of(body: &Body) -> Option<End> {
        match body {
            Body::Completed {
                outcome,
                cause,
                ended,
                ..
            } => Some(End::Completed {
                outcome: *outcome,
                cause: cause.clone(),
                ended: ended.clone(),
            }),
            Body::Failed {
                code,
                step,
                message,
                reason,
                checkpoint_id,
                ..
            } => Some(End::Failed {
                code: code.clone(),
                step: *step,
                message: message.clone(),
                reason: reason.clone(),
                checkpoint_id: checkpoint_id.clone(),
            }),
            _ => None,
        }
    }
}

impl State {
    /// Action record `r`, by its index among every record the run wrote.
    pub(crate) fn rec(&self, r: usize) -> &Value {
        &self.records[r - self.records_base]
    }

    pub(crate) fn rec_mut(&mut self, r: usize) -> &mut Value {
        &mut self.records[r - self.records_base]
    }

    /// How many action records the run wrote, taken ones included: the
    /// index of the next.
    pub(crate) fn records_written(&self) -> usize {
        self.records_base + self.records.len()
    }

    /// The run's deferrals, as the terminal action reports them.
    pub(crate) fn deferred_report(&self) -> Vec<Value> {
        self.deferrals
            .iter()
            .map(|d| {
                json!({
                    "frame": d.frame,
                    "step": d.path.last(),
                    "store_as": d.store_as,
                    "reason": d.reason,
                    "action_id": d.record.map(|r| self.rec(r)["action_id"].clone()),
                })
            })
            .collect()
    }

    /// The terminal action, once the run has ended: its head as stored,
    /// with the root workflow's stores, the records not taken and the
    /// deferrals of the state (§5.19.1).
    pub(crate) fn terminal_action(&self) -> Option<Action> {
        let t = self.finished.as_ref()?;
        let body = match &t.end {
            End::Completed {
                outcome,
                cause,
                ended,
            } => Body::Completed {
                outcome: *outcome,
                cause: cause.clone(),
                ended: ended.clone(),
                outputs: Value::Object(self.frames[0].stores.clone()),
                action_records: self.records.clone(),
                deferred: self.deferred_report(),
            },
            End::Failed {
                code,
                step,
                message,
                reason,
                checkpoint_id,
            } => Body::Failed {
                code: code.clone(),
                step: *step,
                message: message.clone(),
                reason: reason.clone(),
                checkpoint_id: checkpoint_id.clone(),
                action_records: self.records.clone(),
                deferred: self.deferred_report(),
            },
        };
        Some(Action {
            run_id: self.run_id.clone(),
            id: t.id,
            frame: t.frame.clone(),
            body,
        })
    }
}

/// One deferred step (§5.14).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub(crate) struct Deferral {
    /// The workflows of the frames, root first, as on actions.
    pub frame: Vec<String>,
    /// The step each of those frames was at: the last is the deferred
    /// step, the others the invoke steps that led to it. A recovery loop
    /// drops the deferrals under the steps it runs again.
    pub path: Vec<usize>,
    pub store_as: Option<String>,
    pub reason: String,
    /// The action record it left (`planned`), if any.
    pub record: Option<usize>,
}
pub struct Run {
    program: Program,
    state: State,
}

/// A run's state, serialized for storage: the canonical JSON of the state,
/// its SHA-256 and, when a key was given, its HMAC-SHA-256.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Snapshot {
    pub state: String,
    pub sha256: String,
    pub hmac: Option<String>,
}

/// Check `given` against the workflow's declared inputs: every required one
/// present, nothing undeclared.
pub(crate) fn check_inputs(
    workflow: &program::Workflow,
    given: &Map<String, Value>,
) -> Result<(), String> {
    let declared = workflow
        .raw
        .get("inputs")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for name in given.keys() {
        if !declared.contains_key(name) {
            return Err(format!(
                "workflow '{}' has no input '{name}'",
                workflow.name
            ));
        }
    }
    for (name, spec) in &declared {
        if spec.get("required") == Some(&Value::Bool(true)) && !given.contains_key(name) {
            return Err(format!("workflow '{}' needs input '{name}'", workflow.name));
        }
    }
    Ok(())
}

impl Run {
    /// Validate the catalog and start `workflow`. Any validation error
    /// refuses the start: an invalid workflow is never run.
    pub fn start(
        ctx: &Context,
        catalog: &Value,
        workflow: &str,
        inputs: Map<String, Value>,
        options: StartOptions,
    ) -> Result<Run, StartError> {
        Self::start_set(
            ctx,
            catalog,
            &SetOptions::default(),
            workflow,
            inputs,
            options,
        )
    }

    /// [`Run::start`] with the other catalogs of the catalog's set and agent
    /// manifests (`set`): `workflow` is one of the primary catalog's. A set
    /// or a manifest that is refused refuses the start
    /// (`StartError::Program`).
    pub fn start_set(
        ctx: &Context,
        catalog: &Value,
        set: &SetOptions,
        workflow: &str,
        inputs: Map<String, Value>,
        options: StartOptions,
    ) -> Result<Run, StartError> {
        if let Some(h) = options
            .header
            .as_deref()
            .filter(|h| crate::validate::semantics::parse_version(h).is_none())
        {
            return Err(StartError::Header(h.to_string()));
        }
        grounding_error(ctx, &options.grounding)
            .map_or(Ok(()), |e| Err(StartError::Grounding(e)))?;
        destination::check_policies(&options.destinations).map_err(StartError::Policy)?;
        let program = Self::prepare(
            ctx,
            catalog,
            set,
            workflow,
            options.header.as_deref(),
            &options.profiles,
        )?;
        check_inputs(&program.workflows[workflow], &inputs).map_err(StartError::Inputs)?;
        ijson(&Value::Object(inputs.clone())).map_err(StartError::Inputs)?;
        if let Some(identity) = &options.actor_identity {
            ijson(identity).map_err(StartError::Identity)?;
            identity_error(identity, program.workflows[workflow].targets_1_2)
                .map_or(Ok(()), |e| Err(StartError::Identity(e)))?;
        }
        let state = State {
            version: SNAPSHOT_VERSION,
            run_id: options.run_id,
            root: workflow.to_string(),
            attendance: options.attendance,
            catalog_digest: program.digest.clone(),
            now: options.now_ms.min(MAX_TIME),
            next_id: 1,
            frames: vec![Frame::new(workflow, inputs)],
            pending: None,
            finished: None,
            checkpoints: Vec::new(),
            used_decisions: BTreeSet::new(),
            records: Vec::new(),
            trace: Vec::new(),
            deferrals: Vec::new(),
            actor_identity: options.actor_identity,
            header: options.header,
            records_mode: options.records,
            profiles: options.profiles,
            grounding: options.grounding,
            destinations: options.destinations,
            resumed: false,
            trace_base: 0,
            records_base: 0,
            records_taken_sha256: String::new(),
            trace_taken_sha256: String::new(),
        };
        let mut run = Run { program, state };
        run.machine()
            .trace("run_started", None, json!({"workflow": workflow}));
        run.machine().drive();
        Ok(run)
    }

    /// Validate the catalog as a validator reading its file would: with its
    /// header's version (§11.5) and the applied profiles (§5.21).
    fn prepare(
        ctx: &Context,
        catalog: &Value,
        set: &SetOptions,
        workflow: &str,
        header: Option<&str>,
        profiles: &[Value],
    ) -> Result<Program, StartError> {
        let agents =
            crate::agents::Agents::load(&set.agents, &ctx.ontology).map_err(StartError::Program)?;
        let others: Vec<crate::catalogs::Member<'_>> = set
            .catalogs
            .iter()
            .map(|(doc, h)| (doc, h.as_deref()))
            .collect();
        let catalog_set = crate::catalogs::CatalogSet {
            primary: catalog,
            header,
            others: &others,
        };
        let (report, policy) = validate::validate_profiled(ctx, catalog_set, &agents, profiles)
            .map_err(|e| StartError::Program(e.to_string()))?;
        let errors: Vec<Diagnostic> = report
            .diagnostics
            .into_iter()
            .filter(Diagnostic::is_error)
            .collect();
        if !errors.is_empty() {
            return Err(StartError::Invalid(errors));
        }
        Program::build_set(ctx, catalog_set, &agents, workflow, policy).map_err(StartError::Program)
    }

    fn machine(&mut self) -> Machine<'_> {
        Machine {
            program: &self.program,
            st: &mut self.state,
        }
    }

    /// The pending action, or the terminal one once the run has finished
    /// (§5.19.2 **next**). It changes nothing.
    pub fn next(&self) -> Action {
        self.state
            .terminal_action()
            .or_else(|| self.state.pending.as_ref().map(|p| p.action.clone()))
            .expect("a run always has a pending or a terminal action")
    }

    /// The run's identifier (§5.19.2).
    pub fn run_id(&self) -> &str {
        &self.state.run_id
    }

    pub fn is_finished(&self) -> bool {
        self.state.finished.is_some()
    }

    /// Answer the pending action `id`. A response that does not answer it
    /// is refused and leaves the run unchanged.
    pub fn submit(&mut self, id: u64, response: Response, now_ms: u64) -> Result<(), SubmitError> {
        self.machine().submit(id, response, now_ms)
    }

    /// Tell the run the time (§5.19.3): ends a `Sleep` that is due, and
    /// times out a pending action whose deadline has passed. True when it
    /// changed the run: a new action is pending, or the run ended.
    pub fn tick(&mut self, now_ms: u64) -> bool {
        self.machine().tick(now_ms)
    }

    /// The earliest time at which a tick changes the run, or none
    /// (§5.19.3): `until` for a pending `Sleep`, one millisecond after the
    /// deadline (or `expires_at`) of an action that has one, and none for
    /// any other action, for an ended run, or when that time would be after
    /// the maximum time. Liveness is the host's to watch: it is never a
    /// wake-up time.
    pub fn wake_at(&self) -> Option<u64> {
        if self.state.finished.is_some() {
            return None;
        }
        let pending = self.state.pending.as_ref()?;
        match &pending.action.body {
            Body::Sleep { until } => Some(*until),
            _ => pending
                .deadline
                .and_then(|d| d.checked_add(1))
                .filter(|t| *t <= MAX_TIME),
        }
    }

    /// Cancel the run (§5.19.5): it ends at once with a `Failed` action of
    /// code R408 whose message is `reason`, and no retry, failure mode,
    /// recovery loop, handler or rollback runs. A run that ended
    /// `deferred` can be cancelled; one that ended otherwise cannot.
    pub fn cancel(&mut self, reason: &str, now_ms: u64) -> Result<(), CancelError> {
        self.machine().cancel(reason, now_ms)
    }

    /// The trace not taken yet (informative; §6.4: not an audit record).
    pub fn trace(&self) -> &[Value] {
        &self.state.trace
    }

    /// The `seq` the run's next trace event gets: the events taken
    /// (§5.19.4) and those it holds, counted.
    pub fn trace_seq(&self) -> u64 {
        self.state.trace_base + self.state.trace.len() as u64
    }

    /// The run's action records not taken yet (§5.19.4).
    pub fn action_records(&self) -> &[Value] {
        &self.state.records
    }

    /// Take the trace out of the run's state (§5.19.4): it is returned and
    /// removed, `seq` goes on where it left off, and the state's chain head
    /// over taken trace events covers it.
    pub fn take_trace(&mut self) -> Vec<Value> {
        let taken = std::mem::take(&mut self.state.trace);
        for event in &taken {
            self.state.trace_taken_sha256 = canonical::chain(&self.state.trace_taken_sha256, event);
        }
        self.state.trace_base += taken.len() as u64;
        taken
    }

    /// Take the settled action records out of the run's state (§5.19.4):
    /// the longest prefix of records that are neither `planned` nor
    /// `approved` and that no step, deferral or queued action refers to.
    /// Record indices and `action_id`s stay as they were, and the state's
    /// chain head over taken records covers them.
    pub fn take_records(&mut self) -> Vec<Value> {
        // Once the run has ended, no step is in progress: the record of the
        // step it ended at is settled like any other.
        let finished = self.state.finished.is_some();
        let referenced = referenced_records(&self.state, !finished);
        let base = self.state.records_base;
        let k = self
            .state
            .records
            .iter()
            .enumerate()
            .take_while(|(i, r)| {
                !matches!(r["status"].as_str(), Some("planned" | "approved"))
                    && !referenced.contains(&(base + i))
            })
            .count();
        let taken: Vec<Value> = self.state.records.drain(..k).collect();
        for record in &taken {
            self.state.records_taken_sha256 =
                canonical::chain(&self.state.records_taken_sha256, record);
        }
        self.state.records_base += k;
        if finished {
            let base = self.state.records_base;
            for f in &mut self.state.frames {
                if f.cur.record.is_some_and(|r| r < base) {
                    f.cur.record = None;
                }
            }
        }
        taken
    }

    /// The chain heads over the records and the trace events taken so far
    /// (records, trace): empty while nothing was taken (§5.19.4).
    pub fn taken_heads(&self) -> (&str, &str) {
        (
            &self.state.records_taken_sha256,
            &self.state.trace_taken_sha256,
        )
    }

    /// The run's record (§5.19.8), once the run has ended: an action record
    /// derived from its terminal action, so that every run, failed and
    /// cancelled ones included, leaves one. None while the run goes on.
    pub fn run_record(&self) -> Option<Value> {
        let st = &self.state;
        let action = st.terminal_action()?;
        let mut record = json!({
            "action_id": st.run_id,
            "run_id": st.run_id,
            "frame": action.frame,
        });
        let mut details = json!({"kind": action.body.kind()});
        let status = match &action.body {
            Body::Completed {
                outcome,
                cause,
                ended,
                ..
            } => {
                details["outcome"] = json!(outcome);
                details["cause"] = json!(cause);
                if let Some(e) = ended {
                    details["ended"] = e.clone();
                }
                if *outcome == Outcome::Deferred {
                    "planned"
                } else {
                    "executed"
                }
            }
            Body::Failed {
                code,
                step,
                message,
                reason,
                checkpoint_id,
                ..
            } => {
                if let Some(s) = step {
                    record["step"] = json!(s);
                }
                record["code"] = json!(code);
                if let Some(r) = reason {
                    record["reason_code"] = json!(r);
                }
                if let Some(c) = checkpoint_id {
                    record["checkpoint_id"] = json!(c);
                }
                details["message"] = json!(message);
                if code == "R408" {
                    "cancelled"
                } else {
                    "failed"
                }
            }
            _ => unreachable!("a terminal action is Completed or Failed"),
        };
        record["timestamp"] = json!(machine::iso(st.now));
        record["actor"] = json!("agent");
        if let Some(identity) = &st.actor_identity {
            record["actor"] = identity["kind"].clone();
            record["actor_identity"] = identity.clone();
        }
        record["intent"] = json!(format!("run {}", st.root));
        record["status"] = json!(status);
        details["deferred"] = json!(st.deferred_report());
        details["records"] = json!(st.records_written());
        record["details"] = details;
        Some(record)
    }

    /// The run's state as canonical JSON with its SHA-256, and an
    /// HMAC-SHA-256 under `key` when given.
    pub fn snapshot(&self, key: Option<&[u8]>) -> Snapshot {
        let value = serde_json::to_value(&self.state).expect("run state serializes");
        let state = canonical::canonical(&value);
        Snapshot {
            sha256: canonical::sha256_hex(&state),
            hmac: key.map(|k| canonical::hmac_hex(k, &state)),
            state,
        }
    }

    /// Continue from a snapshot taken against `catalog` (§5.19.4). What each
    /// check proves: the digest, that the state was not corrupted; the HMAC,
    /// when a key is given, who wrote it (a digest anyone who can change the
    /// state can recompute); `check_state`, that this executor could have
    /// produced it. The catalog must be the one the run started with.
    pub fn restore(
        ctx: &Context,
        catalog: &Value,
        snapshot: &Snapshot,
        key: Option<&[u8]>,
    ) -> Result<Run, RestoreError> {
        Self::restore_with(ctx, catalog, snapshot, key, RestoreOptions::default())
    }

    /// [`Run::restore`], for the actor `options` names (§5.17): a run keeps
    /// its actor while it continues, so a principal other than the run's is
    /// refused, and so is any actor for a run started without one.
    pub fn restore_with(
        ctx: &Context,
        catalog: &Value,
        snapshot: &Snapshot,
        key: Option<&[u8]>,
        options: RestoreOptions,
    ) -> Result<Run, RestoreError> {
        Self::restore_set(ctx, catalog, &SetOptions::default(), snapshot, key, options)
    }

    /// [`Run::restore_with`] for a run started with [`Run::start_set`]:
    /// `set` must be the catalogs and manifests it started with.
    pub fn restore_set(
        ctx: &Context,
        catalog: &Value,
        set: &SetOptions,
        snapshot: &Snapshot,
        key: Option<&[u8]>,
        options: RestoreOptions,
    ) -> Result<Run, RestoreError> {
        if let Some(actor) = &options.actor_identity {
            ijson(actor).map_err(RestoreError::Actor)?;
            // Checked again once the root workflow's version is known.
            if let Some(e) = identity_error(actor, false) {
                return Err(RestoreError::Actor(e));
            }
        }
        if !canonical::same_digest(&canonical::sha256_hex(&snapshot.state), &snapshot.sha256) {
            return Err(RestoreError::Digest);
        }
        match key {
            Some(k) => {
                let expected = canonical::hmac_hex(k, &snapshot.state);
                if !snapshot
                    .hmac
                    .as_deref()
                    .is_some_and(|h| canonical::same_digest(h, &expected))
                {
                    return Err(RestoreError::Hmac);
                }
            }
            // A signed snapshot is only trusted with its key.
            None if snapshot.hmac.is_some() => return Err(RestoreError::Hmac),
            None => {}
        }
        let mut value: Value = serde_json::from_str(&snapshot.state)
            .map_err(|e| RestoreError::Malformed(e.to_string()))?;
        // Version 1 (before Standard 1.2) stored the whole terminal action;
        // it must equal the one derived from the state, checked below.
        let mut stored_terminal: Option<Action> = None;
        let v1 = value.get("version").and_then(Value::as_u64) == Some(1);
        match value.get("version").and_then(Value::as_u64) {
            Some(1) => {
                if let Some(finished) = value.get_mut("finished").filter(|f| !f.is_null()) {
                    let action: Action = serde_json::from_value(finished.clone())
                        .map_err(|e| RestoreError::Malformed(e.to_string()))?;
                    let Some(end) = End::of(&action.body) else {
                        return Err(RestoreError::Malformed(
                            "the terminal action is not terminal".into(),
                        ));
                    };
                    *finished = serde_json::to_value(Terminal {
                        id: action.id,
                        frame: action.frame.clone(),
                        end,
                    })
                    .expect("a terminal head serializes");
                    stored_terminal = Some(action);
                }
                value["version"] = json!(SNAPSHOT_VERSION);
            }
            Some(v) if v != u64::from(SNAPSHOT_VERSION) => return Err(RestoreError::Version(v)),
            _ => {}
        }
        let mut state: State =
            serde_json::from_value(value).map_err(|e| RestoreError::Malformed(e.to_string()))?;
        if let Some(p) = state.pending.as_mut().filter(|_| v1) {
            // A version-1 pending action carried no run_id.
            p.action.run_id = state.run_id.clone();
        }
        fill_idempotency_key(&mut state);
        destination::check_policies(&state.destinations)
            .map_err(|e| RestoreError::Malformed(format!("destination policy: {e}")))?;
        let program = Self::prepare(
            ctx,
            catalog,
            set,
            &state.root,
            state.header.as_deref(),
            &state.profiles,
        )
        .map_err(RestoreError::Start)?;
        if program.digest != state.catalog_digest {
            return Err(RestoreError::Catalog);
        }
        check_state(&program, &state).map_err(RestoreError::Malformed)?;
        if let Some(e) = grounding_error(ctx, &state.grounding) {
            return Err(RestoreError::Malformed(e));
        }
        if let Some(mut stored) = stored_terminal {
            stored.run_id = state.run_id.clone();
            if state.terminal_action().as_ref() != Some(&stored) {
                return Err(RestoreError::Malformed(
                    "the stored terminal action differs from the run's state".into(),
                ));
            }
        }
        if let Some(actor) = &options.actor_identity {
            if let Some(e) = identity_error(actor, program.workflows[&state.root].targets_1_2) {
                return Err(RestoreError::Actor(e));
            }
            let principal = |v: &Value| {
                v.get("principal")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            };
            match state.actor_identity.as_ref().and_then(principal) {
                None => {
                    return Err(RestoreError::Actor(
                        "the run was started without an actor".into(),
                    ));
                }
                Some(p) if Some(&p) != principal(actor).as_ref() => {
                    return Err(RestoreError::Actor(format!(
                        "the run's actor is '{p}', not '{}'; a run keeps its actor while it continues (§5.17)",
                        principal(actor).unwrap_or_default()
                    )));
                }
                Some(_) => {}
            }
        }
        Ok(Run { program, state })
    }

    /// Resume a run that ended `deferred` (§5.14.1): it continues, as the
    /// same run, with the steps it deferred. A host resumes one saved state
    /// once.
    pub fn resume(&mut self, options: ResumeOptions) -> Result<(), ResumeError> {
        match self.state.finished.as_ref().map(|t| &t.end) {
            Some(End::Completed {
                outcome: Outcome::Deferred,
                ..
            }) => {}
            Some(End::Completed { outcome, .. }) => {
                let outcome = serde_json::to_value(outcome).unwrap_or(Value::Null);
                return Err(ResumeError::NotDeferred(format!(
                    "this run ended {}",
                    outcome.as_str().unwrap_or("otherwise")
                )));
            }
            Some(End::Failed { code, .. }) => {
                return Err(ResumeError::NotDeferred(format!(
                    "this run failed with {code}"
                )));
            }
            None => {
                return Err(ResumeError::NotDeferred("this run has not finished".into()));
            }
        }
        if let Some(actor) = &options.actor_identity {
            ijson(actor).map_err(ResumeError::Identity)?;
            let v12 = self.program.workflows[&self.state.root].targets_1_2;
            if let Some(e) = identity_error(actor, v12) {
                return Err(ResumeError::Identity(e));
            }
        }
        if let Some(m) = not_kept(&self.program, &self.state) {
            return Err(ResumeError::NotKept(m));
        }
        self.machine().resume(options);
        Ok(())
    }
}

/// What a deferred end's state does not keep that resuming needs, if
/// anything (§5.14.1): which steps ran ahead of a frame's deferrals, and the
/// nested run of each deferred `invoke` step that has deferrals under it.
fn not_kept(program: &Program, st: &State) -> Option<String> {
    fn walk(program: &Program, st: &State, f: &Frame, prefix: &mut Vec<usize>) -> Option<String> {
        if !f.deferred.is_empty() && f.ahead.is_none() {
            return Some(format!(
                "which steps of '{}' ran after its first deferral",
                f.workflow
            ));
        }
        let listed = f.deferred.iter().chain(f.resume.iter().flatten());
        for &s in listed {
            let wf = &program.workflows[&f.workflow];
            if wf.steps.get(s).is_none_or(|x| x.capability != "invoke") {
                continue;
            }
            prefix.push(s);
            let under = st
                .deferrals
                .iter()
                .any(|d| d.path.len() > prefix.len() && d.path[..prefix.len()] == prefix[..]);
            let found = match f.parked.get(&s) {
                Some(child) => walk(program, st, child, prefix),
                None if under => Some(format!("the nested run of step {s} of '{}'", f.workflow)),
                None => None,
            };
            prefix.pop();
            if found.is_some() {
                return found;
            }
        }
        None
    }
    walk(program, st, &st.frames[0], &mut Vec::new())
}

/// The indices of the records a deferral or a queued action refers to and,
/// with `current`, the record of each frame's current step, in every frame,
/// running or kept under a deferred `invoke` step: these stay in the state
/// (`take_records`).
fn referenced_records(st: &State, current: bool) -> BTreeSet<usize> {
    fn walk(f: &Frame, current: bool, out: &mut BTreeSet<usize>) {
        if current {
            out.extend(f.cur.record);
        }
        out.extend(f.queued.map(|q| q.record));
        for child in f.parked.values() {
            walk(child, current, out);
        }
    }
    let mut out: BTreeSet<usize> = st.deferrals.iter().filter_map(|d| d.record).collect();
    for f in &st.frames {
        walk(f, current, &mut out);
    }
    out
}

/// A restored state must be one this executor could have produced: the
/// digest only proves the snapshot was not corrupted, not who made it.
fn check_state(program: &Program, st: &State) -> Result<(), String> {
    if st.frames.is_empty() {
        return Err("the state has no frames".into());
    }
    if st.frames.len() > MAX_FRAMES {
        return Err(format!("more than {MAX_FRAMES} nested runs"));
    }
    if st.pending.is_some() == st.finished.is_some() {
        return Err("exactly one of a pending and a terminal action must be set".into());
    }
    if st.frames[0].workflow != st.root {
        return Err("the first frame does not run the root workflow".into());
    }
    if st.now > MAX_TIME || st.next_id > MAX_TIME || st.trace_base > MAX_TIME {
        return Err("a time or action id is out of range".into());
    }
    if st.records_base > MAX_TIME as usize {
        return Err("the count of taken records is out of range".into());
    }
    // A chain head is empty exactly while nothing was taken (§5.19.4).
    let head_ok = |h: &str, taken: bool| {
        if taken {
            h.len() == 64 && h.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        } else {
            h.is_empty()
        }
    };
    if !head_ok(&st.records_taken_sha256, st.records_base > 0)
        || !head_ok(&st.trace_taken_sha256, st.trace_base > 0)
    {
        return Err("a chain head over taken items is malformed".into());
    }
    if st
        .pending
        .as_ref()
        .is_some_and(|p| p.action.run_id != st.run_id)
    {
        return Err("the pending action is for another run".into());
    }
    let v12 = program.workflows[&st.root].targets_1_2;
    if let Some(e) = st
        .actor_identity
        .as_ref()
        .and_then(|a| identity_error(a, v12))
    {
        return Err(format!("actor_identity: {e}"));
    }
    if st
        .header
        .as_deref()
        .is_some_and(|h| crate::validate::semantics::parse_version(h).is_none())
    {
        return Err("the catalog header's version is not a version".into());
    }
    let bad_reason = |r: &Option<String>| r.as_deref().is_some_and(|t| !machine::is_reason(t));
    if st
        .frames
        .iter()
        .any(|f| bad_reason(&f.cur.error.as_ref().and_then(|e| e.reason.clone())))
        || st
            .finished
            .as_ref()
            .is_some_and(|t| matches!(&t.end, End::Failed { reason, .. } if bad_reason(reason)))
    {
        return Err("a failure's reason is not a reason (§5.19.7)".into());
    }
    // Every record a step, a deferral or a queued action refers to is one
    // the state still holds: only settled, unreferenced ones are taken.
    let kept = |r: usize| r >= st.records_base && r < st.records_written();
    for (i, f) in st.frames.iter().enumerate() {
        check_frame(program, st, f, i)?;
    }
    // A frame below the top waits on its invoke step for the nested run.
    for f in &st.frames[..st.frames.len() - 1] {
        let wf = &program.workflows[&f.workflow];
        let invoking = f.stage == Stage::Execute
            && wf
                .steps
                .get(f.step)
                .is_some_and(|s| s.capability == "invoke");
        if !invoking {
            return Err(format!(
                "'{}' has a nested run but is not at an invoke step",
                f.workflow
            ));
        }
    }
    for d in &st.deferrals {
        let well_formed = !d.frame.is_empty()
            && d.frame.len() == d.path.len()
            && d.frame.iter().zip(&d.path).all(|(w, &i)| {
                program
                    .workflows
                    .get(w)
                    .is_some_and(|wf| i < wf.steps.len())
            })
            && d.record.is_none_or(kept);
        if !well_formed {
            return Err("a deferral refers to a missing workflow, step or record".into());
        }
    }
    if !st
        .records
        .iter()
        .all(|r| r.get("status").is_some_and(Value::is_string))
    {
        return Err("an action record is not an object with a status".into());
    }
    if let Some(p) = &st.pending {
        if p.action.body.is_terminal() || p.action.id >= st.next_id {
            return Err("the pending action is not a pending action".into());
        }
        // The purpose must be one the action can have, and point at what
        // exists: responses are dispatched on the pair.
        let top = st.frames.last().expect("checked non-empty above");
        let wf = &program.workflows[&top.workflow];
        let modes = wf.steps.get(top.step).map_or(0, |s| s.failure_modes.len());
        let fits = match (&p.action.body, &p.purpose) {
            (Body::InvokeCapability { .. }, Purpose::Capability)
            | (Body::AwaitEvent { .. }, Purpose::Event)
            | (Body::CreateCheckpoint { .. }, Purpose::Checkpoint)
            | (Body::Rollback { .. }, Purpose::GateRollback { .. })
            | (Body::RequestApproval { .. }, Purpose::Approval { .. })
            | (Body::RecheckSource { .. }, Purpose::Recheck) => true,
            (Body::CreateCheckpoint { .. }, Purpose::FailureCheckpoint { mode })
            | (Body::Rollback { .. }, Purpose::FailureRollback { mode }) => *mode < modes,
            (Body::Sleep { .. }, Purpose::Sleep) => {
                matches!(top.stage, Stage::Backoff { .. } | Stage::Delay { .. })
                    && top.step < wf.steps.len()
            }
            _ => false,
        };
        if !fits {
            return Err("the pending action's purpose does not fit it".into());
        }
        let step = match &p.action.body {
            Body::InvokeCapability { step, .. }
            | Body::CreateCheckpoint { step }
            | Body::Rollback { step, .. }
            | Body::RequestApproval { step, .. }
            | Body::RecheckSource { step, .. }
            | Body::AwaitEvent { step, .. } => Some(*step),
            _ => None,
        };
        if step.is_some_and(|s| s != top.step || s >= wf.steps.len()) {
            return Err("the pending action is for another step".into());
        }
    }
    Ok(())
}

/// The checks of one frame, a running one or (recursively) a nested run
/// parked under a deferred `invoke` step (§5.14.1); `depth` is the number of
/// frames above it, parked or running.
fn check_frame(program: &Program, st: &State, f: &Frame, depth: usize) -> Result<(), String> {
    let Some(wf) = program.workflows.get(&f.workflow) else {
        return Err(format!("unknown workflow '{}'", f.workflow));
    };
    let limit = if f.stage == Stage::Begin && f.escalation.is_none() {
        wf.steps.len()
    } else {
        wf.steps.len().saturating_sub(1)
    };
    if f.step > limit || (f.stage != Stage::Begin && wf.steps.is_empty()) {
        return Err(format!(
            "step {} is out of range in '{}'",
            f.step, f.workflow
        ));
    }
    let kept = |r: usize| r >= st.records_base && r < st.records_written();
    if f.cur.record.is_some_and(|r| !kept(r)) || f.queued.is_some_and(|q| !kept(q.record)) {
        return Err("a step refers to a missing action record".into());
    }
    let waiting_delegate = |i: usize| {
        wf.steps.get(i).is_some_and(|s| {
            s.capability == "delegate" && s.raw.get("wait").is_some_and(Value::is_object)
        })
    };
    if !f.replaces.iter().all(|r| waiting_delegate(r.step))
        || !f.replaces.windows(2).all(|w| w[0].step < w[1].step)
    {
        return Err("replaced delegations must name waiting delegate steps, in order".into());
    }
    // Deferred steps come before the current one, except while a handler
    // runs: it may be listed before the steps it escalates from.
    let ordered = f.deferred.windows(2).all(|w| w[0] < w[1]);
    let in_range = f
        .deferred
        .iter()
        .all(|&d| d < wf.steps.len() && (f.escalation.is_some() || d <= f.step));
    let listed = |k: &usize| f.deferred.contains(k) || f.resume.iter().flatten().any(|r| r == k);
    let caps_known = f.nested_caps.keys().all(listed);
    if !ordered || !in_range || !caps_known {
        return Err(format!(
            "the deferred steps of '{}' are out of range or out of order",
            f.workflow
        ));
    }
    // A resumption's list (§5.14.1): steps in step order, none deferred,
    // and a handler only last, while its escalation waits for it.
    if let Some(list) = &f.resume {
        let handler_last = f.pending_escalation.is_some();
        let normal = if handler_last {
            &list[..list.len().saturating_sub(1)]
        } else {
            &list[..]
        };
        let fits = list
            .iter()
            .all(|&k| k < wf.steps.len() && !f.deferred.contains(&k))
            && normal.windows(2).all(|w| w[0] < w[1])
            && normal.iter().all(|&k| !wf.steps[k].handler)
            && (!handler_last || list.last().is_some_and(|&h| wf.steps[h].handler));
        if !fits {
            return Err(format!(
                "the resumption list of '{}' is out of range or out of order",
                f.workflow
            ));
        }
    }
    if f.queued.is_some_and(|q| q.step >= wf.steps.len()) {
        return Err(format!(
            "the queued action of '{}' names a step out of range",
            f.workflow
        ));
    }
    if f.pending_escalation.is_some() && (f.escalation.is_some() || f.resume.is_none()) {
        return Err("a pending escalation needs a resumption and no escalation".into());
    }
    if f.ahead.as_ref().is_some_and(|a| {
        a.iter()
            .any(|&k| k >= wf.steps.len() || f.deferred.contains(&k))
    }) {
        return Err(format!(
            "the steps that ran ahead in '{}' are out of range",
            f.workflow
        ));
    }
    for (&k, child) in &f.parked {
        let invoke = wf.steps.get(k).is_some_and(|s| s.capability == "invoke");
        if !invoke || !listed(&k) {
            return Err(format!(
                "a nested run is kept under step {k} of '{}', which is not a deferred invoke step",
                f.workflow
            ));
        }
        let waiting = !child.deferred.is_empty() || child.resume.is_some();
        if child.escalation.is_some() || !waiting || child.stage != Stage::Begin {
            return Err(format!(
                "the nested run kept under step {k} of '{}' did not end deferred",
                f.workflow
            ));
        }
        if depth + 2 > MAX_FRAMES {
            return Err(format!("more than {MAX_FRAMES} nested runs"));
        }
        check_frame(program, st, child, depth + 1)?;
    }
    Ok(())
}

impl Frame {
    pub(crate) fn new(workflow: &str, inputs: Map<String, Value>) -> Frame {
        Frame {
            workflow: workflow.to_string(),
            inputs,
            stores: Map::new(),
            ran_inputs: Map::new(),
            recovery: None,
            loops: Map::new(),
            step: 0,
            stage: Stage::Begin,
            cur: StepState::default(),
            escalation: None,
            ended: None,
            deferred: Vec::new(),
            nested_caps: BTreeMap::new(),
            always_ask: BTreeSet::new(),
            marked: false,
            replaces: Vec::new(),
            resume: None,
            parked: BTreeMap::new(),
            pending_escalation: None,
            queued: None,
            ahead: None,
        }
    }
}

/// What is wrong with a delegation's attested identity
/// (`effective.identity`, `identity@1`, §5.17), if anything: it must be an
/// `agent_identity`, and its `model_family` and `role` must agree with the
/// ones `effective` attests beside it. When the delegating workflow targets
/// 1.2 or later (`v12`), its `model_id` must agree too; below 1.2 the
/// executor does not read `model_id`, as 1.1 did not.
pub(crate) fn delegate_identity_error(delegation: &Value, v12: bool) -> Option<String> {
    let effective = delegation.get("effective")?;
    let identity = effective.get("identity").filter(|v| !v.is_null())?;
    if let Some(e) = identity_error(identity, v12) {
        return Some(format!("effective.identity: {e}"));
    }
    let keys: &[&str] = if v12 {
        &["model_family", "model_id", "role"]
    } else {
        &["model_family", "role"]
    };
    for &key in keys {
        if let (Some(a), Some(b)) = (identity.get(key), effective.get(key))
            && a != b
        {
            return Some(format!(
                "effective.identity.{key} {a} contradicts effective.{key} {b}"
            ));
        }
    }
    None
}

/// The principal a delegation's host attested (`effective.identity`).
pub(crate) fn delegate_principal(delegation: &Value) -> Option<String> {
    delegation
        .get("effective")?
        .get("identity")?
        .get("principal")?
        .as_str()
        .map(str::to_string)
}

/// The first grounding policy whose shape is wrong or that requires a
/// capability the ontology does not define (§5.20): a host's policy is
/// refused, never applied to nothing. `grounding[i].<why>`.
fn grounding_error(ctx: &Context, policies: &[grounding::Policy]) -> Option<String> {
    policies.iter().enumerate().find_map(|(i, p)| {
        grounding::Policy::new(p.require.clone(), p.kinds.clone(), p.attested)
            .and_then(|p| p.check_ids(&ctx.ontology))
            .err()
            .map(|e| format!("grounding[{i}].{e}"))
    })
}

/// A pending `InvokeCapability` read from a state that predates idempotency
/// keys gets `<run_id>:<id>`, its own id (§5.19.4), and so does the step it
/// is for, so that the later attempts of its pass reuse the key and every
/// `InvokeCapability` the executor delivers carries one (§4.4.2).
fn fill_idempotency_key(state: &mut State) {
    let Some(p) = state.pending.as_mut() else {
        return;
    };
    let Body::InvokeCapability {
        idempotency_key: key @ None,
        ..
    } = &mut p.action.body
    else {
        return;
    };
    let filled = format!("{}:{}", state.run_id, p.action.id);
    *key = Some(filled.clone());
    if let Some(f) = state.frames.last_mut() {
        f.cur.idempotency_key = Some(filled);
    }
}

/// Why `items`, a `RolledBack`'s `not_covered`, is malformed, if it is
/// (§4.4.1, §5.19.1): each an object with a string `item`, a `reason` that
/// is `transmitted`, `delegated`, `outside_scope` or an `x-` reason, an
/// optional string `detail`, and nothing else.
pub(crate) fn not_covered_ok(items: &[Value]) -> Result<(), String> {
    for (i, item) in items.iter().enumerate() {
        let Some(m) = item.as_object() else {
            return Err(format!("not_covered[{i}] is not an object"));
        };
        if !m.get("item").is_some_and(Value::is_string) {
            return Err(format!("not_covered[{i}].item is not a string"));
        }
        let reason = m.get("reason").and_then(Value::as_str).unwrap_or_default();
        let x_reason = grounding::vendor(reason) && reason.len() <= 2 + 1 + 61;
        if !(matches!(reason, "transmitted" | "delegated" | "outside_scope") || x_reason) {
            return Err(format!(
                "not_covered[{i}].reason must be transmitted, delegated, outside_scope or an x- reason; a change the checkpoint captured that the host did not restore makes the answer an Error"
            ));
        }
        if m.get("detail").is_some_and(|d| !d.is_string()) {
            return Err(format!("not_covered[{i}].detail is not a string"));
        }
        if let Some(k) = m
            .keys()
            .find(|k| !matches!(k.as_str(), "item" | "reason" | "detail"))
        {
            return Err(format!("not_covered[{i}] has an unknown member '{k}'"));
        }
    }
    Ok(())
}

/// Why `v` is not an `agent_identity` (`schemas/agent_identity_schema.yaml`),
/// if it is not: an object with a string `principal`, a `kind`, string
/// optional fields, and `authenticated_by` and `trust_class` from their
/// vocabularies. Unknown fields are allowed. `v12`: the workflow the
/// identity is reported to targets 1.2 or later, whose `agent_identity`
/// (1.1.0) types `model_id`; below 1.2 (1.0.0) `model_id` is an unknown
/// field, allowed with any value.
pub(crate) fn identity_error(v: &Value, v12: bool) -> Option<String> {
    use crate::validate::identity::{TRUST_CLASSES, known_mechanism};
    let Value::Object(m) = v else {
        return Some("an identity must be an object".into());
    };
    if !m.get("principal").is_some_and(Value::is_string) {
        return Some("an identity needs a string principal".into());
    }
    if !matches!(
        m.get("kind").and_then(Value::as_str),
        Some("agent" | "human" | "service")
    ) {
        return Some("an identity's kind must be agent, human or service".into());
    }
    for key in [
        "role",
        "model_family",
        "model_id",
        "owner",
        "authenticated_by",
        "trust_class",
    ] {
        if (v12 || key != "model_id") && m.get(key).is_some_and(|x| !x.is_string()) {
            return Some(format!("an identity's {key} must be a string"));
        }
    }
    if let Some(a) = m.get("authenticated_by").and_then(Value::as_str)
        && !known_mechanism(a)
    {
        return Some(format!("'{a}' is not an authenticated_by value"));
    }
    if let Some(c) = m.get("trust_class").and_then(Value::as_str)
        && !TRUST_CLASSES.contains(&c)
    {
        return Some(format!("'{c}' is not a trust class"));
    }
    None
}
