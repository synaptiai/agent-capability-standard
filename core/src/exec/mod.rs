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
use crate::validate::{Context, validate_catalog};
use machine::Machine;
use program::Program;

/// Nested `invoke` runs, the root included.
pub const MAX_FRAMES: usize = 4;
/// The snapshot format this executor writes and reads.
pub const SNAPSHOT_VERSION: u32 = 1;
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Attendance {
    Attended,
    Unattended,
}

#[derive(Debug, Clone)]
pub struct StartOptions {
    pub attendance: Attendance,
    pub run_id: String,
    pub now_ms: u64,
    /// Who runs the workflow (`agent_identity`, §5.17): every action record
    /// carries it as `actor_identity`.
    pub actor_identity: Option<Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Completed,
    Escalated,
    Deferred,
    ReplanRequired,
}

/// What the host should do next.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Action {
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
    },
    Error {
        code: String,
        #[serde(default)]
        message: String,
    },
    Checkpoint {
        checkpoint_id: String,
    },
    RolledBack,
    Decision {
        decision_id: String,
        decision: String,
        #[serde(default)]
        approvers: Vec<String>,
        digest: String,
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
            Response::RolledBack => "RolledBack",
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

#[derive(Debug, Clone, PartialEq)]
pub enum RestoreError {
    Malformed(String),
    Digest,
    Hmac,
    Catalog,
    Version(u64),
    Start(StartError),
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
    pub finished: Option<Action>,
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
        let program = Self::prepare(ctx, catalog, workflow)?;
        check_inputs(&program.workflows[workflow], &inputs).map_err(StartError::Inputs)?;
        ijson(&Value::Object(inputs.clone())).map_err(StartError::Inputs)?;
        if let Some(identity) = &options.actor_identity {
            ijson(identity).map_err(StartError::Identity)?;
            identity_error(identity).map_or(Ok(()), |e| Err(StartError::Identity(e)))?;
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
        };
        let mut run = Run { program, state };
        run.machine()
            .trace("run_started", None, json!({"workflow": workflow}));
        run.machine().drive();
        Ok(run)
    }

    fn prepare(ctx: &Context, catalog: &Value, workflow: &str) -> Result<Program, StartError> {
        let report = validate_catalog(ctx, catalog, None);
        let errors: Vec<Diagnostic> = report
            .diagnostics
            .into_iter()
            .filter(Diagnostic::is_error)
            .collect();
        if !errors.is_empty() {
            return Err(StartError::Invalid(errors));
        }
        Program::build(ctx, catalog, workflow).map_err(StartError::Program)
    }

    fn machine(&mut self) -> Machine<'_> {
        Machine {
            program: &self.program,
            st: &mut self.state,
        }
    }

    /// The pending action, or the terminal one once the run has finished.
    pub fn next(&self) -> &Action {
        self.state
            .finished
            .as_ref()
            .or(self.state.pending.as_ref().map(|p| &p.action))
            .expect("a run always has a pending or a terminal action")
    }

    pub fn is_finished(&self) -> bool {
        self.state.finished.is_some()
    }

    /// Answer the pending action `id`. A response that does not answer it
    /// is refused and leaves the run unchanged.
    pub fn submit(&mut self, id: u64, response: Response, now_ms: u64) -> Result<(), SubmitError> {
        self.machine().submit(id, response, now_ms)
    }

    /// Tell the run the time: ends a `Sleep` that is due, and times out a
    /// pending action whose deadline has passed.
    pub fn tick(&mut self, now_ms: u64) {
        self.machine().tick(now_ms);
    }

    pub fn trace(&self) -> &[Value] {
        &self.state.trace
    }

    pub fn action_records(&self) -> &[Value] {
        &self.state.records
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

    /// Resume from a snapshot taken against `catalog`. The digest (and the
    /// HMAC, when a key is given) must match, and so must the catalog.
    pub fn restore(
        ctx: &Context,
        catalog: &Value,
        snapshot: &Snapshot,
        key: Option<&[u8]>,
    ) -> Result<Run, RestoreError> {
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
        let value: Value = serde_json::from_str(&snapshot.state)
            .map_err(|e| RestoreError::Malformed(e.to_string()))?;
        if let Some(v) = value.get("version").and_then(Value::as_u64) {
            if v != u64::from(SNAPSHOT_VERSION) {
                return Err(RestoreError::Version(v));
            }
        }
        let state: State =
            serde_json::from_value(value).map_err(|e| RestoreError::Malformed(e.to_string()))?;
        let program = Self::prepare(ctx, catalog, &state.root).map_err(RestoreError::Start)?;
        if program.digest != state.catalog_digest {
            return Err(RestoreError::Catalog);
        }
        check_state(&program, &state).map_err(RestoreError::Malformed)?;
        Ok(Run { program, state })
    }
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
    if st.now > MAX_TIME || st.next_id > MAX_TIME {
        return Err("a time or action id is out of range".into());
    }
    if let Some(e) = st.actor_identity.as_ref().and_then(identity_error) {
        return Err(format!("actor_identity: {e}"));
    }
    for f in &st.frames {
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
        if f.cur.record.is_some_and(|r| r >= st.records.len()) {
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
        // Deferred steps come before the current one, except while a
        // handler runs: it may be listed before the steps it escalates from.
        let ordered = f.deferred.windows(2).all(|w| w[0] < w[1]);
        let in_range = f
            .deferred
            .iter()
            .all(|&d| d < wf.steps.len() && (f.escalation.is_some() || d <= f.step));
        let caps_known = f.nested_caps.keys().all(|k| f.deferred.contains(k));
        if !ordered || !in_range || !caps_known {
            return Err(format!(
                "the deferred steps of '{}' are out of range or out of order",
                f.workflow
            ));
        }
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
            && d.record.is_none_or(|r| r < st.records.len());
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
    if st.finished.as_ref().is_some_and(|a| !a.body.is_terminal()) {
        return Err("the terminal action is not terminal".into());
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
        }
    }
}

/// Why `v` is not an `agent_identity` (`schemas/agent_identity_schema.yaml`),
/// if it is not: an object with a string `principal`, a `kind`, string
/// optional fields, and `authenticated_by` and `trust_class` from their
/// vocabularies. Unknown fields are allowed.
pub(crate) fn identity_error(v: &Value) -> Option<String> {
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
        "owner",
        "authenticated_by",
        "trust_class",
    ] {
        if m.get(key).is_some_and(|x| !x.is_string()) {
            return Some(format!("an identity's {key} must be a string"));
        }
    }
    if let Some(a) = m.get("authenticated_by").and_then(Value::as_str) {
        if !known_mechanism(a) {
            return Some(format!("'{a}' is not an authenticated_by value"));
        }
    }
    if let Some(c) = m.get("trust_class").and_then(Value::as_str) {
        if !TRUST_CLASSES.contains(&c) {
            return Some(format!("'{c}' is not a trust class"));
        }
    }
    None
}
