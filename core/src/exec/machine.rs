//! The step algorithm (design-114 §16.3) over the run state.

use serde_json::{Map, Value, json};

use super::canonical;
use super::program::{GateAction, Program, Step, Workflow};
use super::quorum;
use super::{
    Action, Attendance, Body, CancelError, Checkpoint, Deferral, End, Frame, MAX_FRAMES, MAX_TIME,
    Outcome, Pending, Purpose, Queued, RecordMode, Replacement, Response, ResumeOptions, Stage,
    State, StepError, StepState, SubmitError, Terminal, check_inputs,
};
use crate::duration;
use crate::expr::ast::RefAt;
use crate::expr::eval::{self, Bindings};
use crate::refs;

/// A safety net against an executor bug looping without host interaction;
/// every real loop is bounded by step counts and `max_loops`.
const MAX_TRANSITIONS: u32 = 1_000_000;

/// How one transition left the machine.
enum Flow {
    /// Keep going without the host.
    Continue,
    /// An action is pending, or the run finished.
    Wait,
}

/// The values a frame's references read: step outputs, then inputs, then
/// `_recovery`.
struct FrameBindings<'a>(&'a Frame);

impl Bindings for FrameBindings<'_> {
    fn get(&self, root: &str) -> Option<&Value> {
        let f = self.0;
        if root == "_recovery" {
            return f.recovery.as_ref();
        }
        f.stores.get(root).or_else(|| f.inputs.get(root))
    }
}

/// Resolve the references in a binding value: a string that is exactly one
/// reference takes the referenced value; references inside a longer string
/// are interpolated (strings as they are, other values as compact JSON).
pub(crate) fn resolve(value: &Value, b: &dyn Bindings) -> Value {
    match value {
        Value::String(s) => resolve_str(s, b),
        Value::Array(a) => Value::Array(a.iter().map(|v| resolve(v, b)).collect()),
        Value::Object(m) => {
            Value::Object(m.iter().map(|(k, v)| (k.clone(), resolve(v, b))).collect())
        }
        other => other.clone(),
    }
}

fn resolve_str(s: &str, b: &dyn Bindings) -> Value {
    let found = refs::find_refs(s);
    if found.is_empty() {
        return Value::String(s.to_string());
    }
    let read = |r: &refs::Ref| {
        let at = RefAt {
            r: r.clone(),
            ann: None,
            pos: 0,
        };
        eval::resolve(&at, b).into_owned()
    };
    if let [m] = found.as_slice()
        && m.start == 0
        && m.end == s.len()
        && let Ok(r) = &m.parsed
    {
        return read(r);
    }
    let mut out = String::new();
    let mut last = 0;
    for m in &found {
        out.push_str(&s[last..m.start]);
        match &m.parsed {
            Ok(r) => match read(r) {
                Value::String(t) => out.push_str(&t),
                other => out.push_str(&other.to_string()),
            },
            Err(_) => out.push_str(&s[m.start..m.end]),
        }
        last = m.end;
    }
    out.push_str(&s[last..]);
    Value::String(out)
}

/// `ms` since the Unix epoch as an RFC 3339 UTC timestamp.
pub(crate) fn iso(ms: u64) -> String {
    let secs = ms / 1000;
    let days = i64::try_from(secs / 86_400).unwrap_or(i64::MAX / 2);
    let rem = secs % 86_400;
    // Civil date from days since 1970-01-01 (Howard Hinnant's algorithm).
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}.{:03}Z",
        rem / 3600,
        rem % 3600 / 60,
        rem % 60,
        ms % 1000
    )
}

/// `now + d`, capped at [`MAX_TIME`] so every time stays an exact JSON
/// number.
fn later(now: u64, d: std::time::Duration) -> u64 {
    now.saturating_add(u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
        .min(MAX_TIME)
}

/// The reasons §5.19.7 defines. A host may also send a vendor reason
/// (`x-…`, [`is_reason`]).
pub(crate) const REASONS: &[&str] = &[
    "unsupported_capability",
    "unsupported_domain",
    "not_recorded",
    "outcome_unknown",
    "key_conflict",
    "destination_not_allowed",
    "unsupported_scope",
    "unsupported_ttl",
    "over_capacity",
    "secret_in_data",
    "below_minimum_confidence",
    "invalid_confidence",
];

/// Whether `t` is a reason (§5.19.7): one of [`REASONS`], or `x-`, then a
/// lowercase letter or a digit, then at most 61 lowercase letters, digits,
/// `_`, `.` or `-`.
pub(crate) fn is_reason(t: &str) -> bool {
    REASONS.contains(&t) || (crate::grounding::vendor(t) && t.len() <= 2 + 1 + 61)
}

/// The reason a failure came with (§5.19.7): a token, or a value a host gave
/// that is not one, which is ignored and only traced.
#[derive(Debug, Clone, Default, PartialEq)]
pub(crate) struct Reason {
    pub token: Option<String>,
    pub ignored: Option<Value>,
}

impl Reason {
    /// A reason the executor raises itself.
    pub(crate) fn of(token: &str) -> Reason {
        debug_assert!(is_reason(token), "{token} is not a reason");
        Reason {
            token: Some(token.to_string()),
            ignored: None,
        }
    }

    /// The `reason` member of a host's `Error` response.
    fn from_response(v: Option<Value>) -> Reason {
        match v {
            None => Reason::default(),
            Some(Value::String(t)) if is_reason(&t) => Reason {
                token: Some(t),
                ignored: None,
            },
            Some(other) => Reason {
                token: None,
                ignored: Some(other),
            },
        }
    }

    /// Add the reason to a trace event's detail: `reason`, or
    /// `reason_ignored` for a value outside the grammar. Nothing without one.
    fn annotate(&self, detail: &mut Value) {
        if let Some(t) = &self.token {
            detail["reason"] = json!(t);
        }
        if let Some(v) = &self.ignored {
            detail["reason_ignored"] = v.clone();
        }
    }
}

/// How a run, or a nested run, failed.
pub(crate) struct Fail {
    pub code: String,
    pub message: String,
    /// The reason the failure came with (§5.19.7).
    pub reason: Option<String>,
}

impl Fail {
    /// A failure the executor makes, with no reason.
    fn new(code: impl Into<String>, message: impl Into<String>) -> Fail {
        Fail {
            code: code.into(),
            message: message.into(),
            reason: None,
        }
    }
}

/// What an approval request asked for.
struct Asked<'s> {
    digest: &'s str,
    expires_at: Option<u64>,
    min: u64,
    /// The approver as the request named it (§5.14): a person asked in
    /// place of a mandate has no `mandate_ref`.
    approver: &'s Value,
    /// `identity@1`: the identities the decision attested (§5.17), checked
    /// by `submit`; `None` when it carried none or the workflow does not
    /// declare the extension.
    identities: Option<Vec<Value>>,
}

pub(crate) struct Machine<'a> {
    pub program: &'a Program,
    pub st: &'a mut State,
}

impl<'a> Machine<'a> {
    // ---- frames and steps ----

    fn frame(&mut self) -> &mut Frame {
        self.st
            .frames
            .last_mut()
            .expect("a running run has a frame")
    }

    fn frame_ref(&self) -> &Frame {
        self.st.frames.last().expect("a running run has a frame")
    }

    fn workflow(&self) -> &'a Workflow {
        let program: &'a Program = self.program;
        &program.workflows[&self.frame_ref().workflow]
    }

    fn step_ref(&self) -> &'a Step {
        let f = self.frame_ref();
        &self.workflow().steps[f.step]
    }

    fn names(&self) -> Vec<String> {
        self.st.frames.iter().map(|f| f.workflow.clone()).collect()
    }

    // ---- trace and records ----

    pub(crate) fn trace(&mut self, kind: &str, step: Option<usize>, detail: Value) {
        let event = json!({
            // Taken events count (§5.19.4): `seq` goes on where it left off.
            "seq": self.st.trace_base + self.st.trace.len() as u64,
            "at": self.st.now,
            "kind": kind,
            "frame": self.names(),
            "step": step,
            "detail": detail,
        });
        self.st.trace.push(event);
    }

    fn trace_step(&mut self, kind: &str, detail: Value) {
        let step = self.frame_ref().step;
        self.trace(kind, Some(step), detail);
    }

    fn record(&mut self, status: &str, approval: Option<Value>) -> usize {
        // A queued step a resumption re-entered continues its queued
        // action: the record its deferral left is updated in place, with
        // every decision and refusal of the step until it goes on or
        // carries the action out, a re-ask and a retry included (§5.14.1).
        if let Some(r) = self.queued_record() {
            let always_ask = self.always_ask();
            self.stamp(r);
            // check_state keeps every record an object.
            let Some(record) = self.st.rec_mut(r).as_object_mut() else {
                return r;
            };
            record.insert("status".into(), json!(status));
            if always_ask {
                record.insert("always_ask".into(), json!(true));
            } else {
                record.remove("always_ask");
            }
            match approval {
                Some(a) => record.insert("approval".into(), a),
                None => record.remove("approval"),
            };
            record.remove("reason");
            record.remove("reason_code");
            record.remove("code");
            // The checkpoint of this pass, not of an earlier one (§6.4).
            match self.frame_ref().cur.checkpoint_id.clone() {
                Some(c) => self.st.rec_mut(r)["checkpoint_id"] = json!(c),
                None => {
                    if let Some(record) = self.st.rec_mut(r).as_object_mut() {
                        record.remove("checkpoint_id");
                    }
                }
            }
            // Likewise the pass's idempotency key (§4.4.2).
            match self.frame_ref().cur.idempotency_key.clone() {
                Some(k) => self.st.rec_mut(r)["idempotency_key"] = json!(k),
                None => {
                    if let Some(record) = self.st.rec_mut(r).as_object_mut() {
                        record.remove("idempotency_key");
                    }
                }
            }
            return r;
        }
        let top = self.st.frames.len() - 1;
        self.push_record(top, status, approval)
    }

    /// Write a new action record for the current step of frame `i` (§6.4):
    /// its correlation members, the run's actor, the step's `purpose` as
    /// its intent and the checkpoint the step used. Returns its index.
    fn push_record(&mut self, i: usize, status: &str, approval: Option<Value>) -> usize {
        let f = &self.st.frames[i];
        let step = &self.program.workflows[&f.workflow].steps[f.step];
        let purpose = step
            .raw
            .get("purpose")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let frame: Vec<String> = self.st.frames[..=i]
            .iter()
            .map(|f| f.workflow.clone())
            .collect();
        let n = self.st.records_written();
        let mut record = json!({
            "action_id": format!("{}/{}/{}/{n}", self.st.run_id, frame.join("/"), f.step),
            "run_id": self.st.run_id,
            "frame": frame,
            "step": f.step,
            "capability": step.capability,
            "timestamp": iso(self.st.now),
            "actor": "agent",
            "intent": purpose,
            "status": status,
        });
        if let Some(identity) = &self.st.actor_identity {
            record["actor"] = identity["kind"].clone();
            record["actor_identity"] = identity.clone();
        }
        if self.always_ask_at(i) {
            record["always_ask"] = json!(true);
        }
        // An applied profile required a person for the step (§5.21.3).
        if step.person {
            record["person_required"] = json!(true);
        }
        if let Some(c) = &f.cur.checkpoint_id {
            record["checkpoint_id"] = json!(c);
        }
        // Once the step has called its capability, its pass's key (§6.4).
        if let Some(k) = &f.cur.idempotency_key {
            record["idempotency_key"] = json!(k);
        }
        if let Some(a) = approval {
            record["approval"] = a;
        }
        self.st.records.push(record);
        n
    }

    /// In record mode `actions` (§6.4): a record of its own for a
    /// failure-mode checkpoint or a rollback of the current step, with the
    /// step's correlation members and `purpose`; it is not the step's record.
    fn side_record(
        &mut self,
        capability: &str,
        status: &str,
        checkpoint_id: Option<String>,
        code: Option<&str>,
    ) {
        if self.st.records_mode != RecordMode::Actions {
            return;
        }
        let top = self.st.frames.len() - 1;
        let r = self.push_record(top, status, None);
        let record = self.st.rec_mut(r);
        record["capability"] = json!(capability);
        // The step's pass key is not this action's (§4.4.2).
        if let Some(m) = record.as_object_mut() {
            m.remove("idempotency_key");
        }
        match checkpoint_id {
            Some(c) => record["checkpoint_id"] = json!(c),
            None => {
                if let Some(m) = record.as_object_mut() {
                    m.remove("checkpoint_id");
                }
            }
        }
        if let Some(code) = code {
            record["code"] = json!(code);
        }
    }

    /// Record `r` is written again now: it takes the time and the actor of
    /// then (§5.14.1, §5.17).
    fn stamp(&mut self, r: usize) {
        let now = iso(self.st.now);
        let actor = self.st.actor_identity.clone();
        let Some(record) = self.st.rec_mut(r).as_object_mut() else {
            return;
        };
        record.insert("timestamp".into(), json!(now));
        record.insert("actor".into(), json!("agent"));
        record.remove("actor_identity");
        if let Some(identity) = actor {
            record.insert("actor".into(), identity["kind"].clone());
            record.insert("actor_identity".into(), identity);
        }
    }

    /// A record for an action that did not go ahead, with the reason and,
    /// when the step fails for it, the code (§6.4).
    fn record_refused(
        &mut self,
        status: &str,
        approval: Option<Value>,
        reason: &str,
        code: Option<&str>,
    ) {
        let r = self.record(status, approval);
        self.st.rec_mut(r)["reason"] = json!(reason);
        if let Some(code) = code {
            self.st.rec_mut(r)["code"] = json!(code);
        }
        self.frame().cur.record = Some(r);
    }

    fn set_record_status(&mut self, status: &str) {
        if let Some(r) = self.frame_ref().cur.record {
            self.st.rec_mut(r)["status"] = json!(status);
        }
    }

    /// An approved action that then failed. A record that is already
    /// rejected, expired or executed keeps its status.
    fn record_failed(&mut self) {
        let error = self.frame_ref().cur.error.clone();
        if let Some(r) = self.frame_ref().cur.record
            && self.st.rec(r)["status"] == "approved"
        {
            let record = self.st.rec_mut(r);
            record["status"] = json!("failed");
            // The code and the reason the step failed with (§5.19.7, §6.4).
            if let Some(e) = error {
                record["code"] = json!(e.code);
                if let Some(reason) = e.reason {
                    record["reason_code"] = json!(reason);
                }
            }
        }
    }

    // ---- actions ----

    fn emit(&mut self, body: Body, purpose: Purpose, deadline: Option<u64>) -> Flow {
        // The step starts its pass with its first checkpoint, call or wait
        // (§5.19.5).
        if matches!(
            (&body, &purpose),
            (Body::CreateCheckpoint { .. }, Purpose::Checkpoint)
                | (Body::InvokeCapability { .. }, _)
                | (Body::AwaitEvent { .. }, _)
        ) {
            self.frame().cur.started = true;
        }
        let action = Action {
            run_id: self.st.run_id.clone(),
            id: self.st.next_id,
            frame: self.names(),
            body,
        };
        self.st.next_id += 1;
        self.st.pending = Some(Pending {
            action,
            purpose,
            deadline,
        });
        Flow::Wait
    }

    /// The run ends: its terminal action's head is stored, and `next()`
    /// derives the records, outputs and deferrals from the state.
    fn finish(&mut self, end: End) -> Flow {
        let terminal = Terminal {
            id: self.st.next_id,
            frame: self.names(),
            end,
        };
        self.st.next_id += 1;
        self.st.pending = None;
        self.st.finished = Some(terminal);
        Flow::Wait
    }

    /// End the whole run from any frame (replanning ends every frame).
    fn finish_run(&mut self, outcome: Outcome) -> Flow {
        self.trace("run_finished", None, json!({"outcome": outcome}));
        self.finish(End::Completed {
            outcome,
            cause: None,
            ended: None,
        })
    }

    // ---- the loop ----

    pub(crate) fn drive(&mut self) {
        let mut fuel = MAX_TRANSITIONS;
        while self.st.finished.is_none() && self.st.pending.is_none() {
            fuel -= 1;
            if fuel == 0 {
                self.fail_run("R402", "the executor exceeded its transition budget");
                return;
            }
            match self.transition() {
                Flow::Continue | Flow::Wait => {}
            }
        }
    }

    fn transition(&mut self) -> Flow {
        match self.frame_ref().stage.clone() {
            Stage::Begin => self.begin(),
            Stage::Delay { until } => self.emit(Body::Sleep { until }, Purpose::Sleep, None),
            Stage::Ready => self.ready(),
            Stage::Checkpoint => self.checkpoint(),
            Stage::Approval => self.approval(),
            Stage::Recheck => self.recheck(),
            Stage::Execute => self.execute(),
            Stage::Backoff { until } => self.emit(Body::Sleep { until }, Purpose::Sleep, None),
            Stage::After => self.after(),
            Stage::Failure => self.failure(),
        }
    }

    fn set_stage(&mut self, stage: Stage) -> Flow {
        self.frame().stage = stage;
        Flow::Continue
    }

    // ---- step outcomes ----

    /// The step failed before or while executing: on to its failure modes.
    fn step_error(&mut self, code: &str, message: impl Into<String>) -> Flow {
        self.step_error_with(code, message, Reason::default())
    }

    /// [`Machine::step_error`] with the reason the failure came with
    /// (§5.19.7): the step keeps it, and the trace shows it.
    fn step_error_with(&mut self, code: &str, message: impl Into<String>, reason: Reason) -> Flow {
        let message = message.into();
        let mut detail = json!({"code": code, "message": message});
        reason.annotate(&mut detail);
        self.trace_step("step_failed", detail);
        // Record mode `actions` (§6.4): a step that fails after it started
        // has a `failed` record of the pass; an approved one keeps its own,
        // which says why.
        if self.st.records_mode == RecordMode::Actions {
            let cur = &self.frame_ref().cur;
            match cur.record {
                None if cur.started => {
                    let r = self.record("failed", None);
                    self.frame().cur.record = Some(r);
                    let record = self.st.rec_mut(r);
                    record["code"] = json!(code);
                    if let Some(t) = &reason.token {
                        record["reason_code"] = json!(t);
                    }
                }
                Some(r) if self.st.rec(r)["status"] == "approved" => {
                    let record = self.st.rec_mut(r);
                    record["code"] = json!(code);
                    if let Some(t) = &reason.token {
                        record["reason_code"] = json!(t);
                    }
                }
                _ => {}
            }
        }
        self.frame().cur.error = Some(StepError {
            code: code.to_string(),
            message,
            reason: reason.token,
        });
        self.set_stage(Stage::Failure)
    }

    fn skip_step(&mut self, why: &str) -> Flow {
        self.trace_step("step_skipped", json!({"reason": why}));
        if let Some(store) = self.step_ref().store_as.clone() {
            let f = self.frame();
            f.stores.remove(&store);
            f.ran_inputs.remove(&store);
        }
        self.next_step()
    }

    /// After a step: the next one, or the end of an escalation. During a
    /// resumption, the next step of its list (§5.14.1).
    fn next_step(&mut self) -> Flow {
        // The step goes on: the queued action it continued closes. A loop
        // that runs a later step again keeps that step's.
        if self.queued_record().is_some() {
            self.settle_queued();
        }
        if let Some(list) = self.frame_ref().resume.clone() {
            if let Some(&next) = list.first() {
                let f = self.frame();
                f.step = next;
                f.stage = Stage::Begin;
                return Flow::Continue;
            }
            self.frame().resume = None;
            if self.frame_ref().escalation.is_none() {
                // The list is done: every later step ran before the deferral
                // (or a gate ended the run), and its output stands.
                let len = self.workflow().steps.len();
                let f = self.frame();
                f.step = len;
                f.stage = Stage::Begin;
                return Flow::Continue;
            }
        }
        if let Some(cause) = self.frame_ref().escalation.clone() {
            // A handler that was deferred (or whose nested run deferred
            // steps) did not finish handling: the run is deferred, not
            // escalated, and keeps the cause.
            let f = self.frame_ref();
            let outcome = if f.deferred.contains(&f.step) {
                Outcome::Deferred
            } else {
                Outcome::Escalated
            };
            return self.end_frame(Ok((outcome, Some(cause))));
        }
        let f = self.frame();
        f.step += 1;
        f.stage = Stage::Begin;
        Flow::Continue
    }

    /// A gate with `action: end` fired: this run ends as it would after its
    /// last step (completed, or escalated or deferred), and no later step
    /// runs.
    fn end_run(&mut self, message: Value) -> Flow {
        let step = self.frame_ref().step;
        self.trace_step("run_ended", json!({"message": message}));
        self.frame().ended = Some(json!({"step": step, "message": message}));
        // During a resumption, the queued steps after it, and a deferred
        // handler, will not run: their queued actions are superseded.
        if let Some(left) = self.frame().resume.take() {
            self.supersede_queued(
                &left,
                "superseded: a gate ended the resumed run before the step",
            );
        }
        self.frame().pending_escalation = None;
        if self.frame_ref().escalation.is_some() {
            return self.next_step();
        }
        self.end_frame(Ok((Outcome::Completed, None)))
    }

    fn fail_run(&mut self, code: &str, message: &str) -> Flow {
        self.fail_run_with(Fail::new(code, message))
    }

    /// End the run with `fail`; the `Failed` action carries its reason.
    fn fail_run_with(&mut self, fail: Fail) -> Flow {
        let step = self.st.frames.last().map(|f| f.step);
        let mut detail = json!({"code": fail.code, "message": fail.message});
        if let Some(r) = &fail.reason {
            detail["reason"] = json!(r);
        }
        self.trace("run_failed", step, detail);
        self.finish(End::Failed {
            code: fail.code,
            step,
            message: fail.message,
            reason: fail.reason,
            checkpoint_id: None,
        })
    }

    /// The top frame ends: the run ends, or the parent's invoke step gets
    /// the result.
    fn end_frame(&mut self, end: Result<(Outcome, Option<String>), Fail>) -> Flow {
        // The frame fails while its step has failed (a failure mode's
        // rollback or checkpoint failed too, or there was no checkpoint to
        // roll back to): an approved record of the step is failed (§6.4).
        if end.is_err() && self.frame_ref().cur.error.is_some() {
            self.record_failed();
        }
        self.settle_queued();
        // A run that completed with deferred steps ends deferred.
        let end = match end {
            Ok((Outcome::Completed, cause)) if !self.frame_ref().deferred.is_empty() => {
                Ok((Outcome::Deferred, cause))
            }
            other => other,
        };
        if self.st.frames.len() == 1 {
            return match end {
                Ok((outcome, cause)) => {
                    self.trace(
                        "run_finished",
                        None,
                        json!({"outcome": outcome, "cause": cause}),
                    );
                    let ended = self.st.frames[0].ended.clone();
                    self.finish(End::Completed {
                        outcome,
                        cause,
                        ended,
                    })
                }
                Err(fail) => self.fail_run_with(fail),
            };
        }
        let child = self.st.frames.pop().expect("checked above");
        if child.marked || !child.always_ask.is_empty() {
            self.frame().cur.always_ask = true;
        }
        let result = match &end {
            Ok((o, _)) => json!(o),
            Err(f) => json!(f.code),
        };
        self.trace_step(
            "invoke_returned",
            json!({"workflow": child.workflow, "result": result, "ended": child.ended}),
        );
        match end {
            Ok((Outcome::Completed, _)) => {
                // In step order, which survives a snapshot (object keys
                // are sorted there).
                let steps: Vec<Value> = self.program.workflows[&child.workflow]
                    .steps
                    .iter()
                    .filter_map(|s| s.store_as.as_deref())
                    .filter(|s| child.stores.contains_key(*s))
                    .map(|s| json!(s))
                    .collect();
                // With grounding@1, the invoking workflow's step carries the
                // anchors of its nested run's stored outputs (§5.20); else
                // none, as in 1.1.
                let anchors = if self.program.workflows[&self.frame_ref().workflow]
                    .extension("grounding@1")
                {
                    nested_anchors(&self.program.workflows[&child.workflow], &child.stores)
                } else {
                    Vec::new()
                };
                self.frame().cur.output = Some(json!({
                    "result": Value::Object(child.stores),
                    "steps_executed": steps,
                    "evidence_anchors": anchors,
                }));
                self.set_stage(Stage::After)
            }
            Ok((Outcome::Escalated, cause)) => self.exec_error(
                "R402",
                format!(
                    "invoked workflow '{}' escalated ({})",
                    child.workflow,
                    cause.unwrap_or_default()
                ),
            ),
            // The nested run escalated, but its handler was deferred: an
            // escalated nested run, as above.
            Ok((Outcome::Deferred, Some(cause))) => self.exec_error(
                "R402",
                format!(
                    "invoked workflow '{}' escalated ({cause}) and its handler was deferred",
                    child.workflow
                ),
            ),
            // The nested run deferred some of its steps: so is the invoke
            // step, and whatever depends on it. The invocation itself ran,
            // so its record (if approved) is executed; the nested run's own
            // records are the queued actions.
            Ok((Outcome::Deferred, None)) => {
                if let Some(r) = self.frame_ref().cur.record
                    && self.st.rec(r)["status"] == "approved"
                {
                    self.st.rec_mut(r)["status"] = json!("executed");
                    self.st.rec_mut(r)["reason"] =
                        json!("its nested run deferred steps, which are queued separately");
                }
                let wf = &self.program.workflows[&child.workflow];
                let mut caps: Vec<String> = child
                    .deferred
                    .iter()
                    .map(|&d| wf.steps[d].capability.clone())
                    .chain(
                        child
                            .deferred
                            .iter()
                            .filter_map(|d| child.nested_caps.get(d))
                            .flatten()
                            .cloned(),
                    )
                    .collect();
                caps.sort_unstable();
                caps.dedup();
                let step = self.frame_ref().step;
                let why = format!("invoked workflow '{}' deferred steps", child.workflow);
                // Kept, at rest, so that a resumption continues it (§5.14.1).
                let mut child = child;
                child.stage = Stage::Begin;
                child.step = wf.steps.len();
                child.cur = StepState::default();
                let f = self.frame();
                f.nested_caps.insert(step, caps);
                f.parked.insert(step, child);
                self.defer_step(&why)
            }
            Ok((outcome, _)) => self.finish_run(outcome),
            Err(Fail { code, message, .. }) => self.exec_error(
                "R402",
                format!(
                    "invoked workflow '{}' failed with {code}: {message}",
                    child.workflow
                ),
            ),
        }
    }

    // ---- stages ----

    fn begin(&mut self) -> Flow {
        let index = self.frame_ref().step;
        // A resumption runs its list in order (§5.14.1): this step leaves
        // it. A deferred handler reached so takes up the escalation it was
        // deferred under, before the handler check below reads it.
        if self.frame_ref().resume.as_ref().and_then(|l| l.first()) == Some(&index) {
            let handler = self.step_ref().handler;
            let f = self.frame();
            if let Some(list) = f.resume.as_mut() {
                list.remove(0);
            }
            if handler && let Some(cause) = f.pending_escalation.take() {
                f.escalation = Some(cause);
            }
        }
        let escalating = self.frame_ref().escalation.is_some();
        let count = self.workflow().steps.len();
        if !escalating {
            if index >= count {
                return self.end_frame(Ok((Outcome::Completed, None)));
            }
            if self.step_ref().handler {
                let f = self.frame();
                f.step += 1;
                return Flow::Continue;
            }
        }
        let f = self.frame();
        // A recovery loop back to a waiting delegate replaces its delegation
        // when that step next delegates, as a retry does. The entry stays
        // pending until the delegation is made: a pass that skips or defers
        // the step keeps it for the next.
        let replaces = f
            .replaces
            .iter()
            .find(|r| r.step == index)
            .map(|r| r.task_id.clone());
        f.cur = StepState {
            replaces,
            ..StepState::default()
        };
        // A step that begins while a deferral of its own is listed is one a
        // resumption re-enters: it continues that queued action (§5.14.1).
        // A recovery loop that runs it again keeps the action (`queued`).
        let path: Vec<usize> = self.st.frames.iter().map(|f| f.step).collect();
        if let Some(pos) = self.st.deferrals.iter().position(|d| d.path == path) {
            let d = self.st.deferrals.remove(pos);
            if let Some(record) = d.record {
                self.frame().queued = Some(Queued {
                    step: index,
                    record,
                });
            }
        }
        let capability = self.step_ref().capability.clone();
        self.trace_step("step_started", json!({"capability": capability}));
        let program = self.program;
        let wf = &program.workflows[&self.frame_ref().workflow];
        let step = &wf.steps[index];
        // Before its condition: a step that depends on a deferred step waits
        // for it, rather than running on a missing value or an unchanged
        // world.
        if let Some(why) = self.deferred_cause(step) {
            return self.defer_step(&why);
        }
        // Not deferred: while a step of its frame is, it runs ahead (§5.14).
        let f = self.frame();
        if !f.deferred.is_empty()
            && let Some(ahead) = &mut f.ahead
        {
            ahead.insert(index);
        }
        // A deferred invoke step whose nested run ended deferred continues
        // it (the resumption reopened it); its condition, gates and inputs
        // were settled when the invocation started.
        if let Some(child) = self.frame().parked.remove(&index) {
            let f = self.frame();
            f.nested_caps.remove(&index);
            f.stage = Stage::Execute;
            // Its nested run goes on: the step has started (§5.19.5).
            f.cur.started = true;
            self.trace_step("invoke_resumed", json!({"workflow": child.workflow}));
            self.st.frames.push(child);
            return Flow::Continue;
        }
        if let Some(c) = &step.condition {
            let ok = match eval::eval_condition(c, &FrameBindings(self.frame_ref())) {
                Ok(b) => b,
                Err(e) => {
                    self.trace_step(
                        "expression_error",
                        json!({"site": "condition", "code": "R405", "message": e.msg}),
                    );
                    false
                }
            };
            if !ok {
                if !step.skip_if_false {
                    return self
                        .step_error("R403", "the condition is false and skip_if_false is false");
                }
                return self.skip_step("condition is false");
            }
        }
        for (g, gate) in step.gates.iter().enumerate().filter(|(_, g)| !g.after) {
            if !self.gate_fires(g, gate) {
                continue;
            }
            if gate.action == GateAction::End {
                return self.end_run(json!(gate.message));
            }
            let message = gate
                .message
                .clone()
                .unwrap_or_else(|| format!("gates[{g}] fired"));
            match gate.action {
                GateAction::Stop => return self.step_error("R403", message),
                GateAction::Skip => return self.skip_step("a gate skipped the step"),
                GateAction::Rollback => return self.rollback(Purpose::GateRollback { message }),
                GateAction::End | GateAction::Warn => {}
            }
        }
        // A delay (§5.13) waits before anything else the step does.
        if let Some(d) = step.delay {
            let until = later(self.st.now, d);
            self.trace_step("delay_started", json!({"until": until}));
            return self.set_stage(Stage::Delay { until });
        }
        self.set_stage(Stage::Ready)
    }

    /// The step goes on: resolve its inputs, then ask for approval.
    fn ready(&mut self) -> Flow {
        let program = self.program;
        let step = &program.workflows[&self.frame_ref().workflow].steps[self.frame_ref().step];
        let bindings = step.raw.get("input_bindings").cloned().unwrap_or(json!({}));
        let inputs = resolve(&bindings, &FrameBindings(self.frame_ref()));
        // Resolving can nest a stored value deeper than any value a host
        // may send; such inputs could not be snapshotted or sent.
        if let Err(e) = super::ijson(&inputs) {
            return self.step_error("R402", format!("the step's resolved inputs: {e}"));
        }
        self.frame().cur.inputs = inputs;
        if step.capability == "send"
            && let Some(message) = self.destination_refusal()
        {
            // Before approval and the checkpoint: no one is asked and no
            // checkpoint is used for a send that may not go (§4.4.2). An
            // executor refusal, not retried.
            return self.step_error_with("F504", message, Reason::of("destination_not_allowed"));
        }
        self.set_stage(Stage::Approval)
    }

    /// Why the current `send` step's destination may not go, if a
    /// destination policy is in force and does not allow it (§4.4.2). The
    /// policies in force are the host's, then each applied profile's
    /// (§5.21.3). The message does not repeat the destination, which can
    /// hold a credential (§6.7); the step's inputs hold it.
    fn destination_refusal(&self) -> Option<String> {
        let mut policies = self.st.destinations.clone();
        policies.extend(self.program.policy.destinations());
        if policies.is_empty() {
            return None;
        }
        match self
            .frame_ref()
            .cur
            .inputs
            .get("destination")
            .and_then(Value::as_str)
        {
            Some(d) if crate::destination::allowed(&policies, d) => None,
            Some(_) => Some(format!(
                "the step's destination is not one the {} destination {} in force {} (§4.4.2)",
                policies.len(),
                if policies.len() == 1 { "policy" } else { "policies" },
                if policies.len() == 1 { "allows" } else { "all allow" },
            )),
            None => Some(
                "the step's destination is not a string, so no destination policy in force can allow it (§4.4.2)"
                    .to_string(),
            ),
        }
    }

    /// Evaluate a gate; an evaluation error fires it (fail-safe).
    fn gate_fires(&mut self, g: usize, gate: &super::program::Gate) -> bool {
        let fired = match eval::eval_condition(&gate.when, &FrameBindings(self.frame_ref())) {
            Ok(b) => b,
            Err(e) => {
                self.trace_step(
                    "expression_error",
                    json!({"site": format!("gates[{g}].when"), "code": "R405", "message": e.msg}),
                );
                // Fail-safe: an error fires a gate, except `end`, which
                // would report the run a success.
                gate.action != GateAction::End
            }
        };
        if fired {
            let action = match gate.action {
                GateAction::Stop => "stop",
                GateAction::Rollback => "rollback",
                GateAction::Skip => "skip",
                GateAction::Warn => "warn",
                GateAction::End => "end",
            };
            self.trace_step(
                "gate_fired",
                json!({"gate": g, "action": action, "message": gate.message}),
            );
        }
        fired
    }

    /// Roll back to the latest checkpoint; with none, the run fails (F503).
    fn rollback(&mut self, purpose: Purpose) -> Flow {
        let Some(cp) = self.st.checkpoints.last().map(|c| c.id.clone()) else {
            return self.end_frame(Err(Fail::new(
                "F503",
                "there is no checkpoint to roll back to",
            )));
        };
        let step = self.frame_ref().step;
        self.emit(
            Body::Rollback {
                step,
                checkpoint_id: cp,
            },
            purpose,
            None,
        )
    }

    /// Consumed only once the step is about to execute: a step that is
    /// skipped, deferred or refused approval leaves the checkpoint valid.
    fn checkpoint(&mut self) -> Flow {
        if !self.step_ref().requires_checkpoint {
            return self.set_stage(Stage::Execute);
        }
        if let Some(cp) = self.st.checkpoints.iter_mut().rev().find(|c| c.valid) {
            cp.valid = false;
            let id = cp.id.clone();
            self.trace_step("checkpoint_consumed", json!({"checkpoint_id": id}));
            // The step's records name the checkpoint it uses (§6.4).
            if let Some(r) = self.frame_ref().cur.record {
                self.st.rec_mut(r)["checkpoint_id"] = json!(id);
            }
            self.frame().cur.checkpoint_id = Some(id);
            return self.set_stage(Stage::Execute);
        }
        let step = self.frame_ref().step;
        self.emit(Body::CreateCheckpoint { step }, Purpose::Checkpoint, None)
    }

    fn approval_spec(&self) -> Map<String, Value> {
        self.step_ref()
            .raw
            .get("approval")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default()
    }

    fn approval(&mut self) -> Flow {
        if !self.step_ref().requires_approval {
            return self.set_stage(Stage::Checkpoint);
        }
        let spec = self.approval_spec();
        // A step that uses an item from an always-ask trust class (§5.17)
        // is asked of a person: no mandate covers it.
        let marked = self.always_ask();
        if marked && !self.frame_ref().cur.always_ask {
            self.frame().cur.always_ask = true;
            self.trace_step("always_ask", json!({}));
        }
        // A step an applied profile requires a person for (§5.21.3) is
        // asked as an always-ask step is, but marks nothing: only the
        // request and the decision change.
        if self.step_ref().person && !self.frame_ref().cur.person {
            self.frame().cur.person = true;
            let profiles = self.step_ref().raised_by.clone();
            self.trace_step("person_required", json!({"profiles": profiles}));
        }
        let required = marked || self.step_ref().person;
        // So is a queued step that an attended resumption re-enters
        // (§5.14.1); every request for a re-entered queued step names it
        // while the step continues it (a re-ask and a retry included).
        let queued = self.queued_record();
        let person = required || (queued.is_some() && self.st.attendance == Attendance::Attended);
        let queued_action_id =
            queued.and_then(|r| self.st.rec(r)["action_id"].as_str().map(str::to_string));
        // A standing mandate needs no one present: it is asked even in an
        // unattended run, and the plan applies only if none covers the step.
        let mandate = !person
            && spec
                .get("approver")
                .and_then(|a| a.get("kind"))
                .and_then(Value::as_str)
                == Some("standing_mandate");
        if self.st.attendance == Attendance::Unattended && !mandate {
            let why = if marked {
                "the run is unattended and the step uses an item from an always-ask trust class"
            } else if required {
                "the run is unattended and an applied profile requires a person for this step"
            } else {
                "the run is unattended"
            };
            return self.unattended(None, why);
        }
        let bindings = FrameBindings(self.frame_ref());
        let mut shown = match spec.get("shows") {
            Some(Value::Array(list)) => {
                Value::Array(list.iter().map(|v| resolve(v, &bindings)).collect())
            }
            _ => json!([self.frame_ref().cur.inputs]),
        };
        // Asked again after a recheck saw the source change: show the
        // change, so the approver (and the digest) see what is new.
        if let (Value::Array(items), Some(previous), Some(current)) = (
            &mut shown,
            self.frame_ref().cur.previous.clone(),
            self.frame_ref().cur.rebaseline.clone(),
        ) {
            items.push(json!({"recheck": {"previous": previous, "current": current}}));
        }
        let baseline = spec
            .get("recheck")
            .and_then(|r| r.get("source"))
            .map(|s| resolve(s, &bindings));
        let digest = canonical::digest(&shown);
        let expires_at = spec
            .get("expires")
            .and_then(Value::as_str)
            .and_then(|e| duration::parse(e).ok())
            .map(|d| later(self.st.now, d));
        let mut approver = spec
            .get("approver")
            .cloned()
            .unwrap_or_else(|| json!({"kind": "human"}));
        if person && let Value::Object(a) = &mut approver {
            a.insert("kind".into(), json!("human"));
            a.remove("mandate_ref");
            if required {
                a.insert("always_ask".into(), json!(true));
            }
        }
        // More approvers than any count can reach: the cap keeps the state
        // exactly representable (I-JSON) without changing the outcome.
        let min = approver
            .get("min_approvers")
            .and_then(|m| m.as_u64().or_else(|| m.as_f64().map(|f| f as u64)))
            .unwrap_or(1)
            .min(1 << 53);
        let mode = spec
            .get("mode")
            .and_then(Value::as_str)
            .unwrap_or("in_session")
            .to_string();
        let f = self.frame();
        f.cur.baseline = f.cur.rebaseline.take().or(baseline);
        let step = f.step;
        self.trace_step("approval_requested", json!({"digest": digest}));
        self.emit(
            Body::RequestApproval {
                step,
                approver,
                mode,
                shown,
                digest: digest.clone(),
                expires_at,
                queued_action_id,
            },
            Purpose::Approval {
                digest,
                expires_at,
                min,
            },
            expires_at,
        )
    }

    /// An unattended run that cannot be approved follows the step's
    /// `when_unattended`: `fail` (F502, the default), `skip`, or
    /// `defer_to_queue` (a `planned` record; the step and the steps that read
    /// it are deferred, and the run ends `deferred`).
    fn unattended(&mut self, approval: Option<Value>, why: &str) -> Flow {
        let plan = self
            .approval_spec()
            .get("when_unattended")
            .and_then(Value::as_str)
            .unwrap_or("fail")
            .to_string();
        self.trace_step(
            "approval_unattended",
            json!({"when_unattended": plan, "reason": why}),
        );
        match plan.as_str() {
            "skip" => {
                self.record_refused(
                    "rejected",
                    approval,
                    &format!("{why} (when_unattended: skip); the step was skipped"),
                    None,
                );
                self.skip_step(&format!("approval needed, but {why}"))
            }
            "defer_to_queue" => {
                let r = self.record("planned", approval);
                self.st.rec_mut(r)["reason"] =
                    json!(format!("{why} (when_unattended: defer_to_queue)"));
                self.frame().cur.record = Some(r);
                self.defer_step(why)
            }
            _ => {
                let why = format!("approval is needed, but {why}");
                self.record_refused("rejected", approval, &why, Some("F502"));
                self.step_error("F502", why)
            }
        }
    }

    /// Defer the current step (§5.14): it does not run now, and later steps
    /// that depend on it are deferred too (`deferred_cause`). The queued
    /// action is its `planned` record; a dependent step that requires
    /// approval gets one too.
    fn defer_step(&mut self, why: &str) -> Flow {
        self.trace_step("step_deferred", json!({"reason": why}));
        let step = self.frame_ref().step;
        // From a frame's first deferral on, the steps that run ahead of it
        // are tracked, so that a resumption knows them (§5.14.1).
        let f = self.frame();
        if f.deferred.is_empty() {
            f.ahead = Some(Default::default());
        }
        if let Some(ahead) = &mut f.ahead {
            ahead.remove(&step);
        }
        let record = match self.frame_ref().cur.record {
            // The queued action (when_unattended: defer_to_queue).
            Some(r) if self.st.rec(r)["status"] == "planned" => Some(r),
            // An invoke that ran: its nested run's records are the queue.
            Some(_) => None,
            None if self.step_ref().requires_approval => {
                let r = self.record("planned", None);
                self.st.rec_mut(r)["reason"] = json!(why);
                Some(r)
            }
            None => None,
        };
        // A queued step deferred again keeps its record `planned`, under
        // its deferral; it no longer continues it now.
        if self.queued_record().is_some() {
            self.frame().queued = None;
        }
        let store_as = self.step_ref().store_as.clone();
        if let Some(store) = &store_as {
            let f = self.frame();
            f.stores.remove(store);
            f.ran_inputs.remove(store);
        }
        // Kept in list order: a handler may come before the steps it
        // escalates from.
        let deferred = &mut self.frame().deferred;
        if let Err(at) = deferred.binary_search(&step) {
            deferred.insert(at, step);
        }
        self.st.deferrals.push(Deferral {
            frame: self.names(),
            path: self.st.frames.iter().map(|f| f.step).collect(),
            store_as,
            reason: why.to_string(),
            record,
        });
        self.next_step()
    }

    /// A wait or delay ended, or the run resumed: checkpoints taken before
    /// it describe a world that may have changed, so they authorise nothing
    /// after it (W608, §5.14.1). Traced at `step`; returns the ids.
    fn invalidate_checkpoints(&mut self, step: Option<usize>) -> Vec<String> {
        let invalidated: Vec<String> = self
            .st
            .checkpoints
            .iter_mut()
            .filter(|c| c.valid)
            .map(|c| {
                c.valid = false;
                c.id.clone()
            })
            .collect();
        if !invalidated.is_empty() {
            self.trace(
                "checkpoints_invalidated",
                step,
                json!({"checkpoint_ids": invalidated}),
            );
        }
        invalidated
    }

    /// Why `step` must wait for a deferred step of this frame, if it must:
    /// it reads a deferred step's store; or (unless it is a handler, the
    /// escalation path) it may act on the world, or the ontology orders its
    /// capability after a deferred one (`precedes`, as `verify` after
    /// `mutate`).
    fn deferred_cause(&self, step: &Step) -> Option<String> {
        let f = self.frame_ref();
        if f.deferred.is_empty() {
            return None;
        }
        let wf = &self.program.workflows[&f.workflow];
        let deferred = || f.deferred.iter().map(|&d| &wf.steps[d]);
        if let Some(store) = deferred()
            .filter_map(|d| d.store_as.as_deref())
            .find(|s| step.reads.iter().any(|r| r == s))
        {
            return Some(format!("it reads '{store}', which was deferred"));
        }
        // A handler is the escalation path; `after_deferral: run` is the
        // author saying the step does not depend on what was deferred.
        if step.handler || step.after_deferral_runs {
            return None;
        }
        if step.acts {
            return Some("it may act on the world, after a deferred step".to_string());
        }
        // The capabilities nested runs deferred count for the deferred
        // invoke steps only: during a resumption, an entry of a queued
        // invoke step stays until its nested run continues.
        deferred()
            .map(|d| &d.capability)
            .chain(
                f.deferred
                    .iter()
                    .filter_map(|d| f.nested_caps.get(d))
                    .flatten(),
            )
            .find(|c| step.after.contains(c))
            .map(|c| {
                format!(
                    "the ontology orders {} after {c}, which was deferred",
                    step.capability
                )
            })
    }

    /// The steps a recovery loop to `target` runs again, in step order.
    /// During a resumption, those from `target` to the step that loops,
    /// after which the resumption goes on with its list; a handler among
    /// them does not run, so a deferred one keeps its place last in the
    /// list, its kept nested run and its queued actions (§5.14.1). Else
    /// every step from `target` on.
    fn rerun(&self, target: usize) -> Vec<usize> {
        let f = self.frame_ref();
        let steps = &self.workflow().steps;
        if f.resume.is_some() && f.escalation.is_none() {
            (target..=f.step).filter(|&k| !steps[k].handler).collect()
        } else {
            (target..steps.len()).collect()
        }
    }

    /// A recovery loop to `target` runs its steps again (`rerun`): they are
    /// no longer deferred, here or in the nested runs under them, and the
    /// actions they queued are superseded. During a resumption they run
    /// first, and then the steps left in its list, a deferred handler
    /// last: the queued steps after the loop keep their queued actions, and
    /// a step after it that ran ahead keeps its output.
    fn undefer_from(&mut self, target: usize) {
        let rerun = self.rerun(target);
        let f = self.frame();
        if let Some(list) = f.resume.as_mut()
            && f.escalation.is_none()
        {
            list.splice(0..0, rerun.iter().copied());
        }
        f.deferred.retain(|d| !rerun.contains(d));
        f.nested_caps.retain(|k, _| !rerun.contains(k));
        f.parked.retain(|k, _| !rerun.contains(k));
        if f.deferred.is_empty() {
            f.ahead = None;
        } else if let Some(ahead) = &mut f.ahead {
            ahead.retain(|k| !rerun.contains(k));
        }
        let depth = self.st.frames.len() - 1;
        let prefix: Vec<usize> = self.st.frames[..depth].iter().map(|f| f.step).collect();
        self.supersede(
            |d| {
                d.path.len() > depth
                    && d.path[..depth] == prefix[..]
                    && rerun.contains(&d.path[depth])
            },
            "superseded: a recovery loop ran the step again",
        );
    }

    /// An invoke step starts its nested run (again, after a retry): what an
    /// earlier attempt deferred under it is superseded.
    fn undefer_nested(&mut self) {
        let path: Vec<usize> = self.st.frames.iter().map(|f| f.step).collect();
        let step = self.frame_ref().step;
        self.frame().nested_caps.remove(&step);
        self.frame().parked.remove(&step);
        self.supersede(
            |d| d.path.len() > path.len() && d.path[..path.len()] == path[..],
            "superseded: the invoke step ran its workflow again",
        );
    }

    /// Drop the deferrals `gone` selects; their queued actions are
    /// superseded (`rejected`, with the reason).
    fn supersede(&mut self, gone: impl Fn(&Deferral) -> bool, reason: &str) {
        let (dropped, kept): (Vec<Deferral>, Vec<Deferral>) =
            std::mem::take(&mut self.st.deferrals)
                .into_iter()
                .partition(|d| gone(d));
        self.st.deferrals = kept;
        for r in dropped.iter().filter_map(|d| d.record) {
            if self.st.rec(r)["status"] == "planned" {
                self.reject_queued(r, reason);
            }
        }
    }

    /// Queued action `r` is superseded. A resumed run writes the record
    /// again, with the time and the actor of then (§5.14.1, §5.17); a run
    /// that was not resumed leaves them, as 1.1 does.
    fn reject_queued(&mut self, r: usize, reason: &str) {
        if self.st.resumed {
            self.stamp(r);
        }
        self.st.rec_mut(r)["status"] = json!("rejected");
        self.st.rec_mut(r)["reason"] = json!(reason);
    }

    /// Supersede the deferrals of `steps` of the current frame, nested ones
    /// included, and drop their kept nested runs: a resumption will not
    /// re-enter them (§5.14.1). Steps of the list that only run again have
    /// no deferral and are unaffected.
    fn supersede_queued(&mut self, steps: &[usize], reason: &str) {
        let depth = self.st.frames.len() - 1;
        let prefix: Vec<usize> = self.st.frames[..depth].iter().map(|f| f.step).collect();
        self.supersede(
            |d| {
                d.path.len() > depth
                    && d.path[..depth] == prefix[..]
                    && steps.contains(&d.path[depth])
            },
            reason,
        );
        let f = self.frame();
        f.parked.retain(|k, _| !steps.contains(k));
        f.nested_caps.retain(|k, _| !steps.contains(k));
    }

    /// The record of the queued action the current step continues, if it
    /// continues one (§5.14.1).
    fn queued_record(&self) -> Option<usize> {
        let f = self.frame_ref();
        f.queued.filter(|q| q.step == f.step).map(|q| q.record)
    }

    /// The re-entered queued step went on, or the run left it: its queued
    /// action closes. One whose step never reached its approval (skipped,
    /// failed or ended first) is superseded.
    fn settle_queued(&mut self) {
        if let Some(q) = self.frame().queued.take()
            && self.st.rec(q.record)["status"] == "planned"
        {
            self.reject_queued(
                q.record,
                "superseded: the step did not reach its approval when its run resumed",
            );
        }
    }

    fn decide(
        &mut self,
        decision_id: String,
        decision: &str,
        approvers: &[String],
        given: &str,
        asked: Asked<'_>,
    ) -> Flow {
        let Asked {
            digest: expected,
            expires_at,
            min,
            approver,
            identities,
        } = asked;
        let spec = self.approval_spec();
        let now = self.st.now;
        // Who counts toward min_approvers (§5.14, §5.17): with attested
        // identities, the principals whose identities meet the request;
        // else the distinct strings of `approvers`, as the host vouches.
        let wf = self.workflow();
        let v12 = wf.targets_1_2;
        let requires = v12
            && (approver.get("sender_check").is_some()
                || approver.get("accept_trust_classes").is_some());
        let counting = match identities {
            Some(list) => {
                let mut by_principal: std::collections::BTreeMap<String, Value> =
                    std::collections::BTreeMap::new();
                for id in list {
                    let p = id["principal"].as_str().unwrap_or_default().to_string();
                    by_principal.entry(p).or_insert(id);
                }
                let mut counted = Vec::new();
                let mut refused = Vec::new();
                for (p, id) in by_principal {
                    match meets(approver, &id, v12) {
                        Ok(()) => counted.push((p, id)),
                        Err(why) => refused.push(format!("{p} ({why})")),
                    }
                }
                Counting {
                    approvers: counted.iter().map(|(p, _)| p.clone()).collect(),
                    identities: Some(counted.into_iter().map(|(_, id)| id).collect()),
                    note: (!refused.is_empty())
                        .then(|| format!("not counted: {}", refused.join(", "))),
                    attested: true,
                }
            }
            None if requires => Counting {
                approvers: Vec::new(),
                identities: None,
                note: Some(
                    "the approver requires attested identities (sender_check, accept_trust_classes), and the decision carries none"
                        .into(),
                ),
                attested: true,
            },
            None => Counting {
                approvers: approvers
                    .iter()
                    .collect::<std::collections::BTreeSet<_>>()
                    .into_iter()
                    .cloned()
                    .collect(),
                identities: None,
                note: None,
                attested: false,
            },
        };
        // A person asked in place of a mandate (§5.17, §5.14.1) names none.
        let mandate_ref = approver.get("mandate_ref").cloned().unwrap_or(Value::Null);
        let sub = |decision: &str| {
            let mut sub = json!({
                "digest": expected,
                "decision": decision,
                "approvers": counting.approvers,
                "mode": spec.get("mode").and_then(Value::as_str).unwrap_or("in_session"),
                "mandate_ref": mandate_ref,
                "decided_at": iso(now),
                "expires_at": expires_at.map(iso),
                // The host's identifier of the decision (§5.19.1, §6.4).
                "decision_id": decision_id,
            });
            if let Some(ids) = &counting.identities {
                sub["approver_identities"] = json!(ids);
            }
            sub
        };
        if decision == "unavailable" {
            // No one could decide: in an unattended run, the plan applies;
            // in an attended one, the step cannot go ahead.
            // Single use like any decision; no one approved, so no
            // approvers are recorded, whatever the host sent.
            self.trace_step(
                "approval_decided",
                json!({"decision_id": decision_id, "decision": decision, "valid": false}),
            );
            self.st.used_decisions.insert(decision_id.clone());
            let mut record = sub("unavailable");
            record["approvers"] = json!([]);
            if let Value::Object(m) = &mut record {
                m.remove("approver_identities");
            }
            if self.st.attendance == Attendance::Unattended {
                return self.unattended(Some(record), "no standing mandate covers the action");
            }
            let why = "the approver was unavailable";
            self.record_refused("rejected", Some(record), why, Some("F502"));
            return self.step_error("F502", why);
        }
        let reused = !self.st.used_decisions.insert(decision_id.clone());
        let counted = counting.approvers.len() as u64;
        // (status, reason) for a decision that does not let the step run.
        let problem: Option<(&str, String)> = if reused {
            Some((
                "rejected",
                format!("decision '{decision_id}' was already used"),
            ))
        } else if decision == "rejected" {
            Some(("rejected", "approval was rejected".to_string()))
        } else if decision != "approved" {
            Some(("rejected", format!("'{decision}' is not a decision")))
        } else if expires_at.is_some_and(|e| now > e) {
            Some(("expired", "the approval expired".to_string()))
        } else if !canonical::same_digest(given, expected) {
            Some((
                "rejected",
                "the decision approves different values than were shown".to_string(),
            ))
        } else if counted < min {
            let mut why = if counting.attested {
                format!("{counted} counted approver(s), {min} needed")
            } else {
                format!("{counted} distinct approver(s), {min} needed")
            };
            if let Some(note) = &counting.note {
                why.push_str("; ");
                why.push_str(note);
            }
            Some(("rejected", why))
        } else {
            None
        };
        self.trace_step(
            "approval_decided",
            json!({"decision_id": decision_id, "decision": decision, "valid": problem.is_none()}),
        );
        if let Some((status, reason)) = problem {
            let sub = sub(status);
            self.record_refused(status, Some(sub), &reason, Some("F502"));
            return self.step_error("F502", reason);
        }
        let r = self.record("approved", Some(sub("approved")));
        self.frame().cur.record = Some(r);
        self.set_stage(Stage::Recheck)
    }

    fn recheck(&mut self) -> Flow {
        let spec = self.approval_spec();
        let Some(recheck) = spec.get("recheck").and_then(Value::as_object) else {
            return self.set_stage(Stage::Checkpoint);
        };
        let source = recheck
            .get("source")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let compare = recheck
            .get("compare")
            .and_then(Value::as_str)
            .unwrap_or("digest")
            .to_string();
        let step = self.frame_ref().step;
        self.emit(
            Body::RecheckSource {
                step,
                source,
                compare,
            },
            Purpose::Recheck,
            None,
        )
    }

    fn rechecked(&mut self, current: Value) -> Flow {
        let spec = self.approval_spec();
        let recheck = spec.get("recheck").cloned().unwrap_or(json!({}));
        let compare = recheck
            .get("compare")
            .and_then(Value::as_str)
            .unwrap_or("digest");
        let baseline = self.frame_ref().cur.baseline.clone().unwrap_or(Value::Null);
        let same = if compare == "version" {
            eval::deep_eq(
                baseline.get("version").unwrap_or(&Value::Null),
                current.get("version").unwrap_or(&Value::Null),
            )
        } else {
            canonical::digest(&baseline) == canonical::digest(&current)
        };
        self.trace_step("recheck", json!({"changed": !same}));
        if same {
            return self.set_stage(Stage::Checkpoint);
        }
        match recheck
            .get("on_change")
            .and_then(Value::as_str)
            .unwrap_or("reask")
        {
            "replan" => {
                self.set_record_status("expired");
                self.finish_run(Outcome::ReplanRequired)
            }
            "stop" => {
                self.set_record_status("expired");
                if let Some(r) = self.frame_ref().cur.record {
                    self.st.rec_mut(r)["code"] = json!("F502");
                }
                self.step_error("F502", "the approved source changed before acting")
            }
            _ => {
                self.set_record_status("expired");
                if let Some(r) = self.frame_ref().cur.record {
                    self.st.rec_mut(r)["reason"] =
                        json!("the approved source changed; asked again");
                }
                let f = self.frame();
                f.cur.previous = Some(baseline);
                f.cur.rebaseline = Some(current);
                f.cur.record = None;
                self.set_stage(Stage::Approval)
            }
        }
    }

    fn execute(&mut self) -> Flow {
        if self.frame_ref().cur.attempt == 0 {
            self.frame().cur.attempt = 1;
        }
        let program = self.program;
        let wf = &program.workflows[&self.frame_ref().workflow];
        let step = &wf.steps[self.frame_ref().step];
        let now = self.st.now;
        // A waiting delegate keeps the deadline its delegation started
        // under: one timeout bounds the delegation and the wait.
        let deadline = match self.frame_ref().cur.deadline {
            Some(d) if step.capability == "delegate" => Some(d),
            _ => step.timeout.map(|t| later(now, t)),
        };
        if step.capability == "delegate"
            && wf.extension("wait@1")
            && step.raw.get("wait").is_some_and(Value::is_object)
        {
            self.frame().cur.deadline = deadline;
        }
        let index = step.index;
        if matches!(
            step.capability.as_str(),
            "receive" | "synchronize" | "delegate"
        ) {
            if wf.extension("delegation@1")
                && let Err(e) = accept_from_input(&self.frame_ref().cur.inputs)
            {
                return self.step_error("R402", e);
            }
            if wf.extension("identity@1")
                && let Err(e) = identity_inputs(&self.frame_ref().cur.inputs)
            {
                return self.step_error("R402", e);
            }
        }
        // A correlate key that resolves to null would match every event
        // without that key: fail before acting (delegating) or waiting.
        if wf.extension("wait@1")
            && let Some(Value::Object(c)) = step.raw.get("wait").and_then(|w| w.get("correlate"))
        {
            let bindings = FrameBindings(self.frame_ref());
            if let Some(k) = c
                .iter()
                .find(|(_, v)| resolve(v, &bindings).is_null())
                .map(|(k, _)| k)
            {
                return self.step_error(
                    "R402",
                    format!(
                        "wait.correlate.{k} resolved to null, so it would match events that lack it"
                    ),
                );
            }
        }
        // A delegate that waits delegates first (an InvokeCapability below),
        // then waits for its delegate's result.
        let delegating = step.capability == "delegate" && self.frame_ref().cur.delegated.is_none();
        if wf.extension("wait@1")
            && !delegating
            && let Some(Value::Object(wait)) = step.raw.get("wait")
        {
            let bindings = FrameBindings(self.frame_ref());
            let mut correlate: Map<String, Value> = wait
                .get("correlate")
                .and_then(Value::as_object)
                .map(|c| {
                    c.iter()
                        .map(|(k, v)| (k.clone(), resolve(v, &bindings)))
                        .collect()
                })
                .unwrap_or_default();
            // The result must be for this delegation.
            if let Some(task) = self
                .frame_ref()
                .cur
                .delegated
                .as_ref()
                .and_then(|d| d.get("task_id"))
                .filter(|t| !t.is_null())
            {
                correlate.insert("task_id".to_string(), task.clone());
            }
            let inputs = &self.frame_ref().cur.inputs;
            let accept_from = string_list(inputs, "accept_from");
            let sender_check = string_list(inputs, "sender_check");
            let accept_trust_classes = string_list(inputs, "accept_trust_classes");
            let delegate_principal = if wf.extension("identity@1") {
                self.frame_ref()
                    .cur
                    .delegated
                    .as_ref()
                    .and_then(super::delegate_principal)
            } else {
                None
            };
            return self.emit(
                Body::AwaitEvent {
                    step: index,
                    event_type: wait
                        .get("event_type")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    source_kind: wait
                        .get("source_kind")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    correlate,
                    accept_from,
                    sender_check,
                    accept_trust_classes,
                    delegate_principal,
                    liveness: wait.get("liveness").cloned(),
                    deadline,
                },
                Purpose::Event,
                deadline,
            );
        }
        if step.capability == "invoke" {
            return self.invoke(step);
        }
        if step.capability == "constrain"
            && wf.extension("quorum@1")
            && let Some(Value::Object(q)) = step.raw.get("quorum")
        {
            let identities =
                self.program.workflows[&self.frame_ref().workflow].extension("identity@1");
            // The executor runs the quorum itself: the step starts here.
            self.frame().cur.started = true;
            let result = quorum::evaluate(q, self.frame_ref(), identities);
            self.trace_step("quorum", json!({"tally": result.output["tally"]}));
            self.frame().cur.output = Some(result.output);
            if !result.compliant {
                // The output stays readable by failure modes.
                if let Some(store) = &step.store_as {
                    let out = self.frame_ref().cur.output.clone().unwrap_or_default();
                    self.frame().stores.insert(store.clone(), out);
                }
                return self.step_error("F504", result.message);
            }
            return self.set_stage(Stage::After);
        }
        let inputs = self.frame_ref().cur.inputs.clone();
        let attempt = self.frame_ref().cur.attempt;
        // The pass's idempotency key (§4.4.2): the id of its first
        // InvokeCapability, kept by every later attempt of the pass (a
        // retry keeps `cur`; `begin` starts a new pass with a new one). A
        // delegation that replaces another is a new one, with its own key.
        let next = self.st.next_id;
        let run_id = self.st.run_id.clone();
        let cur = &mut self.frame().cur;
        if cur.idempotency_key.is_none() || cur.replaces.is_some() {
            cur.idempotency_key = Some(format!("{run_id}:{next}"));
        }
        let key = cur.idempotency_key.clone();
        // The record of the pass carries the key once the step calls its
        // capability (§6.4).
        if let Some(r) = cur.record {
            self.st.rec_mut(r)["idempotency_key"] = json!(key);
        }
        self.emit(
            Body::InvokeCapability {
                step: index,
                capability: step.capability.clone(),
                store_as: step.store_as.clone(),
                domain: step
                    .raw
                    .get("domain")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                inputs,
                deadline,
                attempt,
                idempotency_key: key,
                replaces: self.frame_ref().cur.replaces.clone(),
            },
            Purpose::Capability,
            deadline,
        )
    }

    fn invoke(&mut self, step: &Step) -> Flow {
        let inputs = &self.frame_ref().cur.inputs;
        let target = step
            .raw
            .get("workflow_id")
            .and_then(Value::as_str)
            .or_else(|| inputs.get("workflow").and_then(Value::as_str))
            .map(str::to_string);
        let Some(target) = target else {
            // The executor's own refusals are not retried: a retry would
            // meet the same refusal without the host ever being asked.
            return self.step_error("R402", "the invoke step names no workflow");
        };
        let Some(child) = self.program.workflows.get(&target) else {
            return self.step_error("R402", format!("workflow '{target}' is not in the catalog"));
        };
        if self.st.frames.len() >= MAX_FRAMES {
            return self.step_error(
                "R402",
                format!("invoking '{target}' would nest more than {MAX_FRAMES} runs"),
            );
        }
        let child_inputs = inputs
            .get("input")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        if let Err(e) = check_inputs(child, &child_inputs) {
            return self.step_error("R402", e);
        }
        self.trace_step("invoke_started", json!({"workflow": target}));
        // Its nested run starts: so has the step (§5.19.5).
        self.frame().cur.started = true;
        self.undefer_nested();
        let mut frame = Frame::new(&target, child_inputs);
        frame.marked = self.always_ask();
        self.st.frames.push(frame);
        Flow::Continue
    }

    /// An execution error: retried while attempts remain (R401, R402,
    /// R406), then on to the failure modes.
    fn exec_error(&mut self, code: &str, message: impl Into<String>) -> Flow {
        self.exec_error_with(code, message, Reason::default())
    }

    /// [`Machine::exec_error`] with the reason the error came with
    /// (§5.19.7): the retry trace shows it, and the step keeps it when it
    /// fails.
    fn exec_error_with(&mut self, code: &str, message: impl Into<String>, reason: Reason) -> Flow {
        let message = message.into();
        let (attempt, retry) = {
            let s = self.step_ref();
            (
                self.frame_ref().cur.attempt,
                s.retry.as_ref().map(|r| (r.max, r.backoff.clone())),
            )
        };
        if matches!(code, "R401" | "R402" | "R406")
            && let Some((max, backoff)) = retry
            && attempt <= max
        {
            let wait_ms: u64 = match backoff.as_str() {
                "linear" => 1000u64.saturating_mul(u64::from(attempt)),
                "exponential" => 1000u64.saturating_mul(1u64 << attempt.saturating_sub(1).min(32)),
                _ => 0,
            };
            let mut detail = json!({
                "code": code,
                "message": message,
                "attempt": attempt,
                "backoff_ms": wait_ms,
            });
            reason.annotate(&mut detail);
            self.trace_step("retry", detail);
            // A delegate that waits is delegated again: a delegate
            // that went silent is replaced, not waited on again.
            let cur = &mut self.frame().cur;
            if let Some(d) = cur.delegated.take() {
                cur.replaces = d.get("task_id").cloned();
            }
            cur.deadline = None;
            if wait_ms == 0 {
                self.frame().cur.attempt = self.frame_ref().cur.attempt.saturating_add(1);
                return self.set_stage(Stage::Execute);
            }
            let until = self.st.now.saturating_add(wait_ms).min(MAX_TIME);
            return self.set_stage(Stage::Backoff { until });
        }
        self.step_error_with(code, message, reason)
    }

    fn output(&mut self, value: Value, seen: Option<&[String]>) -> Flow {
        let step = self.step_ref();
        let missing: Vec<&String> = match &value {
            Value::Object(m) => step
                .required_outputs
                .iter()
                .filter(|k| !m.contains_key(k.as_str()))
                .collect(),
            _ => step.required_outputs.iter().collect(),
        };
        if !value.is_object() || !missing.is_empty() {
            let detail = if value.is_object() {
                format!(
                    "the output lacks {}",
                    missing
                        .iter()
                        .map(|m| format!("'{m}'"))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            } else {
                "the output is not an object".to_string()
            };
            let capability = step.capability.clone();
            return self.exec_error(
                "R402",
                format!("{detail}, which the '{capability}' contract requires"),
            );
        }
        // A memory step that bound a scope gets that scope or fails (§4.5):
        // a host that does not know the input would store or look up
        // elsewhere without saying so. Retried as any R402.
        if matches!(step.capability.as_str(), "persist" | "recall")
            && let Some(bound) = self
                .frame_ref()
                .cur
                .inputs
                .get("scope")
                .filter(|v| !v.is_null())
            && value.get("scope") != Some(bound)
        {
            let message = format!(
                "the step asked for memory scope {bound} and the output's scope is {}",
                value
                    .get("scope")
                    .map_or_else(|| "absent".to_string(), Value::to_string)
            );
            return self.exec_error_with("R402", message, Reason::of("unsupported_scope"));
        }
        let wf = &self.program.workflows[&self.frame_ref().workflow];
        // A delegation's attested identity is read under identity@1 only.
        if step.capability == "delegate"
            && self.frame_ref().cur.delegated.is_none()
            && wf.extension("identity@1")
            && let Some(e) = super::delegate_identity_error(&value)
        {
            return self.exec_error("R402", e);
        }
        if step.capability == "delegate"
            && self.frame_ref().cur.delegated.is_none()
            && wf.extension("wait@1")
            && step.raw.get("wait").is_some_and(Value::is_object)
        {
            if value.get("accepted") != Some(&Value::Bool(true)) {
                return self.exec_error("R402", "the delegation was not accepted");
            }
            // The result is matched to this delegation by its task_id.
            if !value.get("task_id").is_some_and(Value::is_string) {
                return self.exec_error(
                    "R402",
                    "a delegation the step waits on needs a task_id to match its result",
                );
            }
            // The accepted delegation's output becomes the step's output
            // once the result arrives (with `result` added): its
            // confidence is checked now (§5.21.3).
            if let Some(flow) = self.confidence_failure(&value) {
                return flow;
            }
            let mut traced = json!({"task_id": value.get("task_id")});
            if wf.extension("identity@1")
                && let Some(p) = super::delegate_principal(&value)
            {
                traced["principal"] = json!(p);
            }
            self.trace_step("delegated", traced);
            let f = self.frame();
            f.replaces.retain(|r| r.step != step.index);
            f.cur.delegated = Some(value);
            return self.set_stage(Stage::Execute);
        }
        // `require_record` (§6.4): an audit step that did not write its
        // record fails, retried as any R402.
        if step.capability == "audit"
            && self.frame_ref().cur.inputs.get("require_record") == Some(&Value::Bool(true))
            && value.get("recorded") != Some(&Value::Bool(true))
        {
            return self.exec_error_with(
                "R402",
                "the audit step did not write its record (recorded is not true)",
                Reason::of("not_recorded"),
            );
        }
        // Grounding (§5.20), after the checks of required fields (R402) and
        // before the after-gates. A delegate that waits returned above: its
        // acceptance is not its claim.
        if let Err(message) = self.grounding_check(&value, seen) {
            return self.step_error("F505", message);
        }
        // An applied profile's minimum confidence (§5.21.3), after the
        // required fields and the grounding check, before the after-gates.
        if let Some(flow) = self.confidence_failure(&value) {
            return flow;
        }
        if step.capability == "checkpoint" {
            let id = value
                .get("checkpoint_id")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| self.derived_checkpoint_id());
            self.frame().cur.checkpoint_id = Some(id.clone());
            self.add_checkpoint(id);
        }
        self.frame().cur.output = Some(value);
        self.set_stage(Stage::After)
    }

    /// The step's failure when `value`, an output the host returned for
    /// it, fails the applied profiles' minimum confidence (§5.21.3): F504
    /// with `below_minimum_confidence` or `invalid_confidence`.
    fn confidence_failure(&mut self, value: &Value) -> Option<Flow> {
        let min = self.program.policy.minimum_confidence()?;
        let fault = crate::profile::check_confidence(value, min)?;
        Some(self.step_error_with("F504", fault.message(min), Reason::of(fault.reason())))
    }

    /// §5.20's check of a host's output for the current step: under every
    /// policy that requires its capability (the frame workflow's own, then
    /// the host's, then the applied profiles' (§5.21.3); the last two apply
    /// in every frame), each on its own. With none, nothing is checked or
    /// traced, as in 1.1. On success the trace gets one `grounding` event,
    /// from the last policy checked.
    fn grounding_check(&mut self, output: &Value, seen: Option<&[String]>) -> Result<(), String> {
        let step = self.step_ref();
        let wf = &self.program.workflows[&self.frame_ref().workflow];
        let policies: Vec<&crate::grounding::Policy> = wf
            .grounding
            .iter()
            .chain(&self.st.grounding)
            .chain(&self.program.grounding)
            .filter(|p| p.requires(&step.capability))
            .collect();
        let Some(last) = policies.len().checked_sub(1) else {
            return Ok(());
        };
        let mut detail = Value::Null;
        for (i, policy) in policies.iter().enumerate() {
            let checked = crate::grounding::check(output, policy, &step.bound, seen)?;
            if i == last {
                detail = json!({
                    "status": checked.status,
                    "counted": checked.counted,
                    "legacy": checked.legacy,
                    "unattested": checked.unattested,
                    "policies": policies.len(),
                });
            }
        }
        self.trace_step("grounding", detail);
        Ok(())
    }

    fn derived_checkpoint_id(&self) -> String {
        format!(
            "{}:{}:{}:{}",
            self.st.run_id,
            self.frame_ref().workflow,
            self.frame_ref().step,
            self.st.checkpoints.len()
        )
    }

    /// Whether the current step reads (in its bindings, condition or gates)
    /// a store or input marked always-ask (§5.17).
    fn always_ask(&self) -> bool {
        self.always_ask_at(self.st.frames.len() - 1)
    }

    /// [`Machine::always_ask`] for the current step of frame `i`.
    fn always_ask_at(&self, i: usize) -> bool {
        let f = &self.st.frames[i];
        f.marked
            || !f.always_ask.is_empty()
                && self.program.workflows[&f.workflow].steps[f.step]
                    .reads
                    .iter()
                    .any(|r| f.always_ask.contains(r))
    }

    /// Whether a `receive` or `synchronize` output holds an item whose
    /// sender's trust class the step's `always_ask_trust_classes` lists.
    fn asks_always(&self, out: &Value) -> bool {
        let Some(classes) = string_list(&self.frame_ref().cur.inputs, "always_ask_trust_classes")
        else {
            return false;
        };
        // An item with no identity, or no trust class, counts as always-ask.
        let asks = |identity: &Value| {
            identity["trust_class"]
                .as_str()
                .is_none_or(|c| classes.iter().any(|x| x == c))
        };
        match self.step_ref().capability.as_str() {
            "receive" => out["data"]
                .as_array()
                .is_some_and(|items| items.iter().any(|i| asks(&i["sender_identity"]))),
            "synchronize" => asks(&out["sender_identity"]),
            "delegate" => out
                .get("result")
                .is_some_and(|r| asks(&r["sender_identity"])),
            _ => false,
        }
    }

    fn add_checkpoint(&mut self, id: String) {
        self.trace_step("checkpoint_created", json!({"checkpoint_id": id}));
        self.st.checkpoints.push(Checkpoint { id, valid: true });
    }

    fn event(
        &mut self,
        pending: Pending,
        event: Value,
        principal: Option<String>,
        identity: Option<Value>,
    ) -> Flow {
        let step = self.step_ref();
        let Body::AwaitEvent {
            event_type,
            source_kind,
            correlate,
            accept_from,
            sender_check,
            accept_trust_classes,
            ..
        } = &pending.action.body
        else {
            return self.fail_run("R402", "an event answered an action that awaits none");
        };
        // Without identity@1 the run is as before: no identity is kept.
        let identities = self.program.workflows[&self.frame_ref().workflow].extension("identity@1");
        let identity = identity.filter(|_| identities);
        // A waiting delegate's binding comes from its delegation, not from
        // the action, which only tells the host.
        let delegate_principal = identities
            .then(|| {
                self.frame_ref()
                    .cur
                    .delegated
                    .as_ref()
                    .and_then(super::delegate_principal)
            })
            .flatten();
        // An identity names its principal; the response may give it once.
        let principal = principal.or_else(|| {
            identity
                .as_ref()
                .and_then(|i| i["principal"].as_str())
                .map(str::to_string)
        });
        let field = |k: &str| -> Value {
            event
                .get("canonical")
                .and_then(|c| c.get(k))
                .or_else(|| event.get(k))
                .cloned()
                .unwrap_or(Value::Null)
        };
        let reason = if event.get("event_type").and_then(Value::as_str) != Some(event_type) {
            Some("event_type".to_string())
        } else if source_kind.as_ref().is_some_and(|k| {
            event
                .get("source")
                .and_then(|s| s.get("kind"))
                .and_then(Value::as_str)
                != Some(k.as_str())
        }) {
            Some("source_kind".to_string())
        } else if let Some(k) = {
            // In key order: a snapshot stores the keys sorted (canonical
            // JSON), so a restored run would otherwise report a different
            // key than the live run, which keeps the author's order.
            let mut keys: Vec<&String> = correlate.keys().collect();
            keys.sort();
            keys.into_iter()
                .find(|k| !eval::deep_eq(&field(k), &correlate[k.as_str()]))
        } {
            Some(format!("correlate.{k}"))
        } else if accept_from
            .as_ref()
            .is_some_and(|a| !principal.as_ref().is_some_and(|p| a.contains(p)))
        {
            Some("accept_from".to_string())
        } else if delegate_principal
            .as_ref()
            .is_some_and(|d| principal.as_ref() != Some(d))
        {
            // A waiting delegate keeps only what the party its host
            // attested sends (§5.17).
            Some("delegate_identity".to_string())
        } else if !listed(sender_check, &identity, "authenticated_by") {
            Some("sender_check".to_string())
        } else if !listed(accept_trust_classes, &identity, "trust_class") {
            Some("accept_trust_classes".to_string())
        } else {
            None
        };
        if let Some(reason) = reason {
            // Not ours: keep waiting on the same action. Drops are counted
            // per reason and traced once each, so a noisy source cannot
            // grow the trace without bound.
            let counts = &mut self.frame().cur.dropped;
            let n = counts.get(&reason).and_then(Value::as_u64).unwrap_or(0);
            counts.insert(reason.clone(), json!(n.saturating_add(1)));
            if n == 0 {
                self.trace_step("event_dropped", json!({"reason": reason}));
            }
            self.st.pending = Some(pending);
            return Flow::Wait;
        }
        let at = self.frame_ref().step;
        self.invalidate_checkpoints(Some(at));
        let mut item = event.clone();
        if let Value::Object(m) = &mut item {
            if let Some(p) = &principal {
                m.insert("sender".into(), json!(p));
            }
            if let Some(i) = &identity {
                m.insert("sender_identity".into(), i.clone());
            }
        }
        let anchors = event.get("anchors").cloned().unwrap_or(json!([]));
        let output = if let Some(delegated) = self.frame_ref().cur.delegated.clone() {
            let mut out = delegated;
            out["result"] = item;
            out
        } else if step.capability == "synchronize" {
            let mut out = json!({
                "synchronized": true,
                "agreed_state": event.get("canonical").cloned().unwrap_or(json!({})),
                "participants": self.frame_ref().cur.inputs.get("agents").cloned().unwrap_or(json!([])),
                "evidence_anchors": anchors,
            });
            if let Some(p) = &principal {
                out["sender"] = json!(p);
            }
            if let Some(i) = &identity {
                out["sender_identity"] = i.clone();
            }
            out
        } else {
            json!({
                "data": [item],
                "source": event.get("source").and_then(|s| s.get("kind")).cloned().unwrap_or(Value::Null),
                "timestamp": event.get("timestamp").cloned().unwrap_or(Value::Null),
                "evidence_anchors": anchors,
            })
        };
        let dropped = Value::Object(self.frame_ref().cur.dropped.clone());
        self.trace_step(
            "event_received",
            json!({"event_type": event_type, "dropped": dropped}),
        );
        self.frame().cur.output = Some(output);
        self.set_stage(Stage::After)
    }

    fn after(&mut self) -> Flow {
        let program = self.program;
        let step = &program.workflows[&self.frame_ref().workflow].steps[self.frame_ref().step];
        if let (Some(store), Some(out)) = (&step.store_as, self.frame_ref().cur.output.clone()) {
            // The mark follows the data (§5.17): an output holding an item
            // from an always-ask class, or computed from one, is marked.
            if self.always_ask() || self.frame_ref().cur.always_ask || self.asks_always(&out) {
                self.frame().always_ask.insert(store.clone());
            }
            // The inputs the step ran with: a quorum judges its reviewers
            // by these, not by re-resolving their bindings later.
            let inputs = self.frame_ref().cur.inputs.clone();
            let f = self.frame();
            f.stores.insert(store.clone(), out);
            f.ran_inputs.insert(store.clone(), inputs);
        }
        // Record mode `actions` (§6.4): one record for each pass of each
        // step that runs; an approved step's record is that record.
        if self.st.records_mode == RecordMode::Actions && self.frame_ref().cur.record.is_none() {
            let r = self.record("executed", None);
            self.frame().cur.record = Some(r);
        }
        self.set_record_status("executed");
        // The queued action the step continued is carried out: it closes,
        // so a recovery loop that runs the step again asks for a new action
        // (§5.14.1).
        if self.frame_ref().cur.record.is_some()
            && self.frame_ref().cur.record == self.queued_record()
        {
            self.frame().queued = None;
        }
        self.trace_step("step_completed", json!({}));
        for (g, gate) in step.gates.iter().enumerate().filter(|(_, g)| g.after) {
            if !self.gate_fires(g, gate) {
                continue;
            }
            let message = gate
                .message
                .clone()
                .unwrap_or_else(|| format!("gates[{g}] fired"));
            match gate.action {
                GateAction::Stop => return self.step_error("R403", message),
                GateAction::Rollback => return self.rollback(Purpose::GateRollback { message }),
                // A failure mode whose `when` holds still wins: the run
                // ends once they are checked.
                GateAction::End => {
                    self.frame().cur.ending = Some(json!(gate.message));
                    break;
                }
                GateAction::Skip | GateAction::Warn => {}
            }
        }
        self.set_stage(Stage::Failure)
    }

    fn failure(&mut self) -> Flow {
        let program = self.program;
        let step = &program.workflows[&self.frame_ref().workflow].steps[self.frame_ref().step];
        let error = self.frame_ref().cur.error.clone();
        for (f, fm) in step.failure_modes.iter().enumerate() {
            let by_code = error
                .as_ref()
                .is_some_and(|e| fm.on_error.contains(&e.code));
            let by_when = !by_code
                && fm.when.as_ref().is_some_and(|w| {
                    match eval::eval_condition(w, &FrameBindings(self.frame_ref())) {
                        Ok(b) => b,
                        Err(e) => {
                            self.trace_step(
                                "expression_error",
                                json!({"site": format!("failure_modes[{f}].when"), "code": "R405", "message": e.msg}),
                            );
                            false
                        }
                    }
                });
            if by_code || by_when {
                self.trace_step(
                    "failure_mode_fired",
                    json!({"failure_mode": f, "action": fm.action}),
                );
                return match fm.action.as_str() {
                    "rollback" => self.rollback(Purpose::FailureRollback { mode: f }),
                    "pause_and_checkpoint" => {
                        let index = step.index;
                        self.emit(
                            Body::CreateCheckpoint { step: index },
                            Purpose::FailureCheckpoint { mode: f },
                            None,
                        )
                    }
                    _ => self.recover(f),
                };
            }
        }
        match error {
            // end_frame fails the step's approved record.
            Some(e) => self.end_frame(Err(Fail {
                code: e.code,
                message: e.message,
                reason: e.reason,
            })),
            None => match self.frame().cur.ending.take() {
                Some(message) => self.end_run(message),
                None => self.next_step(),
            },
        }
    }

    /// The recovery of fired failure mode `f`: loop, escalate, or end.
    fn recover(&mut self, f: usize) -> Flow {
        let program = self.program;
        let wf = &program.workflows[&self.frame_ref().workflow];
        let step = &wf.steps[self.frame_ref().step];
        let fm = &step.failure_modes[f];
        let (code, message, reason) = match &self.frame_ref().cur.error {
            Some(e) => (e.code.clone(), e.message.clone(), e.reason.clone()),
            None => (
                "R402".to_string(),
                format!(
                    "failure mode {f} fired: {}",
                    step.raw["failure_modes"][f]["condition"]
                ),
                None,
            ),
        };
        let failed = |code: String, message: String| Fail {
            code,
            message,
            reason: reason.clone(),
        };
        if self.frame_ref().cur.error.is_some() {
            self.record_failed();
        }
        // An escalation or the end of the run closes the step's queued
        // action (`escalate`, `end_frame`); a loop runs the step again, which
        // keeps it.
        if fm.action == "escalate" {
            return match fm.goto {
                Some(h) => self.escalate(h, &code),
                None => self.end_frame(Err(failed(code, message))),
            };
        }
        let Some(target) = fm.goto else {
            return self.end_frame(Err(failed(code, message)));
        };
        let key = format!("{}:{f}", step.index);
        let taken = self
            .frame_ref()
            .loops
            .get(&key)
            .and_then(Value::as_u64)
            .unwrap_or(0);
        if taken >= fm.max_loops {
            self.trace_step(
                "recovery_exhausted",
                json!({"failure_mode": f, "loops": taken}),
            );
            return match fm.on_exhausted {
                Some(h) => self.escalate(h, "R404"),
                None => self.end_frame(Err(Fail::new(
                    "R404",
                    format!("recovery loop exhausted after {taken} loop(s): {message}"),
                ))),
            };
        }
        let inject = fm
            .recovery
            .as_ref()
            .and_then(|r| r.get("inject_context"))
            .and_then(Value::as_object);
        let injected: Map<String, Value> = inject
            .map(|m| {
                let b = FrameBindings(self.frame_ref());
                m.iter().map(|(k, v)| (k.clone(), resolve(v, &b))).collect()
            })
            .unwrap_or_default();
        // Injected context computed from a marked value is marked (§5.17).
        let marked_injection = inject.is_some_and(|m| {
            let f = self.frame_ref();
            let mut roots = Vec::new();
            for v in m.values() {
                super::program::roots(v, &mut roots);
            }
            f.marked
                || self.frame_ref().cur.always_ask
                || self.always_ask()
                || roots.iter().any(|r| f.always_ask.contains(r))
        });
        if marked_injection {
            self.frame().always_ask.insert("_recovery".to_string());
        }
        if let Err(e) = super::ijson(&Value::Object(injected.clone())) {
            return self.end_frame(Err(Fail::new(
                "R402",
                format!("the context a recovery loop injects: {e}"),
            )));
        }
        // A loop runs again every waiting delegate from its target to this
        // step, and each replaces its delegation (§5.13). This step's is the
        // one it holds or, when a retry's re-delegation failed, the one that
        // retry was replacing; an earlier step's is in its output, or still
        // pending from an earlier loop when the step did not run since.
        if target <= step.index && wf.extension("wait@1") {
            for s in &wf.steps[target..=step.index] {
                if s.capability != "delegate" || !s.raw.get("wait").is_some_and(Value::is_object) {
                    continue;
                }
                let f = self.frame_ref();
                let task = if s.index == step.index {
                    f.cur
                        .delegated
                        .as_ref()
                        .and_then(|d| d.get("task_id"))
                        .cloned()
                        .or_else(|| f.cur.replaces.clone())
                } else {
                    s.store_as
                        .as_ref()
                        .and_then(|k| f.stores.get(k))
                        .and_then(|v| v.get("task_id"))
                        .cloned()
                };
                if let Some(task_id) = task {
                    let pending = &mut self.frame().replaces;
                    pending.retain(|r| r.step != s.index);
                    pending.push(Replacement {
                        step: s.index,
                        task_id,
                    });
                    pending.sort_by_key(|r| r.step);
                }
            }
        }
        let cleared: Vec<String> = self
            .rerun(target)
            .into_iter()
            .filter_map(|k| wf.steps[k].store_as.clone())
            .collect();
        self.undefer_from(target);
        let frame = self.frame();
        frame.loops.insert(key, json!(taken + 1));
        let mut recovery = match frame.recovery.take() {
            Some(Value::Object(m)) => m,
            _ => Map::new(),
        };
        recovery.extend(injected);
        frame.recovery = Some(Value::Object(recovery));
        for s in &cleared {
            frame.stores.remove(s);
            frame.ran_inputs.remove(s);
        }
        frame.step = target;
        frame.stage = Stage::Begin;
        self.trace(
            "loop",
            Some(step.index),
            json!({"failure_mode": f, "to": target, "loop": taken + 1}),
        );
        Flow::Continue
    }

    fn escalate(&mut self, handler: usize, cause: &str) -> Flow {
        self.trace_step("escalated", json!({"handler": handler, "cause": cause}));
        self.settle_queued();
        // During a resumption (§5.14.1): this escalation takes precedence
        // over a deferred handler's, whose queued actions are superseded;
        // the queued steps not yet re-entered stay deferred, and the steps
        // listed only to run again keep their outputs from before.
        if let Some(left) = self.frame().resume.take() {
            let mut left = left;
            if self.frame().pending_escalation.take().is_some()
                && let Some(h) = left.pop()
            {
                self.supersede_queued(&[h], "superseded: another escalation took precedence");
            }
            let depth = self.st.frames.len() - 1;
            let prefix: Vec<usize> = self.st.frames[..depth].iter().map(|f| f.step).collect();
            let queued: Vec<bool> = left
                .iter()
                .map(|&k| {
                    self.st.deferrals.iter().any(|d| {
                        d.path.len() == depth + 1
                            && d.path[..depth] == prefix[..]
                            && d.path[depth] == k
                    })
                })
                .collect();
            let f = self.frame();
            for (k, q) in left.into_iter().zip(queued) {
                if q {
                    if let Err(at) = f.deferred.binary_search(&k) {
                        f.deferred.insert(at, k);
                    }
                } else {
                    f.ahead.get_or_insert_with(Default::default).insert(k);
                }
            }
            if f.deferred.is_empty() {
                f.ahead = None;
            } else if f.ahead.is_none() {
                f.ahead = Some(Default::default());
            }
        }
        let f = self.frame();
        f.escalation = Some(cause.to_string());
        f.step = handler;
        f.stage = Stage::Begin;
        Flow::Continue
    }

    // ---- host interaction ----

    pub(crate) fn submit(
        &mut self,
        id: u64,
        response: Response,
        now: u64,
    ) -> Result<(), SubmitError> {
        if self.st.finished.is_some() {
            return Err(SubmitError::Finished);
        }
        let pending = self
            .st
            .pending
            .clone()
            .expect("an unfinished run has a pending action");
        if pending.action.id != id {
            return Err(SubmitError::WrongAction {
                pending: pending.action.id,
                got: id,
            });
        }
        let ok = matches!(
            (&pending.action.body, &response),
            (
                Body::InvokeCapability { .. },
                Response::Output { .. } | Response::Error { .. }
            ) | (
                Body::CreateCheckpoint { .. },
                Response::Checkpoint { .. } | Response::Error { .. }
            ) | (
                Body::Rollback { .. },
                Response::RolledBack { .. } | Response::Error { .. }
            ) | (Body::RequestApproval { .. }, Response::Decision { .. })
                | (
                    Body::RecheckSource { .. },
                    Response::Current { .. } | Response::Error { .. }
                )
                | (
                    Body::AwaitEvent { .. },
                    Response::Event { .. } | Response::LivenessLost | Response::Error { .. }
                )
        );
        if !ok {
            return Err(SubmitError::Unexpected {
                action: pending.action.body.kind(),
                response: response.kind(),
            });
        }
        let values: Vec<&Value> = match &response {
            Response::Output { value, .. } | Response::Current { value } => vec![value],
            Response::Event { event, .. } => vec![event],
            _ => Vec::new(),
        };
        for v in values {
            super::ijson(v).map_err(SubmitError::Malformed)?;
        }
        if let Response::RolledBack {
            not_covered: Some(items),
        } = &response
        {
            super::ijson(&Value::Array(items.clone())).map_err(SubmitError::Malformed)?;
            super::not_covered_ok(items).map_err(SubmitError::Malformed)?;
        }
        let identity_declared =
            self.program.workflows[&self.frame_ref().workflow].extension("identity@1");
        if let (
            true,
            Response::Event {
                principal,
                identity: Some(identity),
                ..
            },
        ) = (identity_declared, &response)
        {
            super::ijson(identity).map_err(SubmitError::Malformed)?;
            if let Some(e) = super::identity_error(identity) {
                return Err(SubmitError::Malformed(e));
            }
            if principal
                .as_ref()
                .is_some_and(|p| identity["principal"].as_str() != Some(p))
            {
                return Err(SubmitError::Malformed(
                    "the event's principal is not its identity's principal".into(),
                ));
            }
        }
        if let (
            true,
            Response::Decision {
                approvers,
                approver_identities: Some(list),
                ..
            },
        ) = (identity_declared, &response)
            && !list.is_null()
        {
            approver_identities_error(approvers, list).map_or(Ok(()), |e| {
                Err(SubmitError::Malformed(format!("approver_identities: {e}")))
            })?;
        }
        self.st.now = self.st.now.max(now.min(MAX_TIME));
        self.st.pending = None;
        let late = pending.deadline.is_some_and(|d| self.st.now > d);
        self.respond(pending, response, late);
        self.drive();
        Ok(())
    }

    fn respond(&mut self, pending: Pending, response: Response, late: bool) {
        match (pending.purpose.clone(), response) {
            (Purpose::Capability | Purpose::Event, _) if late => {
                self.exec_error("R401", "the result arrived after the step's timeout");
            }
            (
                Purpose::Capability,
                Response::Output {
                    value,
                    evidence_seen,
                },
            ) => {
                self.output(value, evidence_seen.as_deref());
            }
            (
                purpose @ (Purpose::Capability | Purpose::Event),
                Response::Error {
                    code,
                    message,
                    reason,
                },
            ) => {
                // A timeout keeps its code; so does lost liveness on a wait.
                // Anything else a host reports is a failed step.
                let keep = code == "R401" || (code == "R406" && matches!(purpose, Purpose::Event));
                let code = if keep { code } else { "R402".to_string() };
                self.exec_error_with(&code, message, Reason::from_response(reason));
            }
            (
                Purpose::Event,
                Response::Event {
                    event,
                    principal,
                    identity,
                },
            ) => {
                self.event(pending, event, principal, identity);
            }
            (Purpose::Event, Response::LivenessLost) => {
                self.exec_error("R406", "the event source stopped answering (liveness)");
            }
            (Purpose::Checkpoint, Response::Checkpoint { checkpoint_id }) => {
                self.add_checkpoint(checkpoint_id);
            }
            (
                Purpose::Checkpoint,
                Response::Error {
                    message, reason, ..
                },
            ) => {
                self.step_error_with(
                    "F501",
                    format!("could not take a checkpoint: {message}"),
                    Reason::from_response(reason),
                );
            }
            (Purpose::FailureCheckpoint { mode }, Response::Checkpoint { checkpoint_id }) => {
                self.side_record("checkpoint", "executed", Some(checkpoint_id.clone()), None);
                self.add_checkpoint(checkpoint_id);
                self.recover(mode);
            }
            (
                Purpose::FailureCheckpoint { .. },
                Response::Error {
                    message, reason, ..
                },
            ) => {
                let reason = Reason::from_response(reason).token;
                self.side_record("checkpoint", "failed", None, Some("F501"));
                self.side_reason(reason.as_deref());
                self.end_frame(Err(Fail {
                    code: "F501".to_string(),
                    message: format!("could not take a checkpoint: {message}"),
                    reason,
                }));
            }
            (Purpose::GateRollback { message }, Response::RolledBack { not_covered }) => {
                self.rolled_back_ok(&pending, not_covered);
                self.step_error("R403", message);
            }
            (Purpose::FailureRollback { mode }, Response::RolledBack { not_covered }) => {
                self.rolled_back_ok(&pending, not_covered);
                self.recover(mode);
            }
            (
                Purpose::GateRollback { .. } | Purpose::FailureRollback { .. },
                Response::Error {
                    message, reason, ..
                },
            ) => {
                let reason = Reason::from_response(reason).token;
                self.side_record("rollback", "failed", rolled_back(&pending), Some("F503"));
                self.side_reason(reason.as_deref());
                self.end_frame(Err(Fail {
                    code: "F503".to_string(),
                    message: format!("rollback failed: {message}"),
                    reason,
                }));
            }
            (
                Purpose::Approval {
                    digest,
                    expires_at,
                    min,
                },
                Response::Decision {
                    decision_id,
                    decision,
                    approvers,
                    digest: given,
                    approver_identities,
                },
            ) => {
                let approver = match &pending.action.body {
                    Body::RequestApproval { approver, .. } => approver.clone(),
                    _ => json!({"kind": "human"}),
                };
                // Read under identity@1 only; `submit` checked them.
                let identities = approver_identities
                    .filter(|_| self.workflow().extension("identity@1"))
                    .and_then(|v| v.as_array().cloned());
                let asked = Asked {
                    digest: &digest,
                    expires_at,
                    min,
                    approver: &approver,
                    identities,
                };
                self.decide(decision_id, &decision, &approvers, &given, asked);
            }
            (Purpose::Recheck, Response::Current { value }) => {
                self.rechecked(value);
            }
            (
                Purpose::Recheck,
                Response::Error {
                    message, reason, ..
                },
            ) => {
                self.step_error_with(
                    "F502",
                    format!("could not recheck the approved source: {message}"),
                    Reason::from_response(reason),
                );
            }
            // check_state and submit rule this out; a run never panics.
            (purpose, response) => {
                self.fail_run(
                    "R402",
                    &format!("a {} response does not fit {purpose:?}", response.kind()),
                );
            }
        }
    }

    /// Resume a run that ended `deferred` (§5.14.1); `Run::resume` checked
    /// that it did, and that its state keeps what this needs.
    pub(crate) fn resume(&mut self, o: ResumeOptions) {
        let principal = |v: &Option<Value>| {
            v.as_ref()
                .and_then(|i| i.get("principal"))
                .cloned()
                .unwrap_or(Value::Null)
        };
        let previous = principal(&self.st.actor_identity);
        if o.actor_identity.is_some() {
            self.st.actor_identity = o.actor_identity;
        }
        self.st.attendance = o.attendance;
        self.st.now = self.st.now.max(o.now_ms.min(MAX_TIME));
        self.st.finished = None;
        self.st.resumed = true;
        // The queued actions of a nested run that failed under a step that
        // was not deferred are never carried out.
        let orphans: Vec<Vec<usize>> = self
            .st
            .deferrals
            .iter()
            .filter(|d| orphaned(&self.st.frames[0], &d.path))
            .map(|d| d.path.clone())
            .collect();
        self.supersede(
            |d| orphans.contains(&d.path),
            "superseded: the nested run it was queued in failed",
        );
        let actor = principal(&self.st.actor_identity);
        let attendance = self.st.attendance;
        self.trace(
            "run_resumed",
            None,
            json!({"attendance": attendance, "actor": actor, "previous_actor": previous}),
        );
        let invalidated = self.invalidate_checkpoints(None);
        reopen(self.program, &mut self.st.frames[0], &invalidated);
        self.drive();
    }

    /// True when the tick changed the run: a new action is pending, or the
    /// run ended (§5.19.2 **tick**).
    pub(crate) fn tick(&mut self, now: u64) -> bool {
        if self.st.finished.is_some() {
            return false;
        }
        self.st.now = self.st.now.max(now.min(MAX_TIME));
        let Some(pending) = self.st.pending.clone() else {
            return false;
        };
        match (&pending.action.body, &pending.purpose) {
            (Body::Sleep { until }, _) if self.st.now >= *until => {
                self.st.pending = None;
                if matches!(self.frame_ref().stage, Stage::Delay { .. }) {
                    // The world may have changed while the step waited.
                    let step = self.frame_ref().step;
                    self.invalidate_checkpoints(Some(step));
                    self.trace_step("delay_finished", json!({}));
                    self.set_stage(Stage::Ready);
                } else {
                    self.frame().cur.attempt = self.frame_ref().cur.attempt.saturating_add(1);
                    self.set_stage(Stage::Execute);
                }
            }
            (_, Purpose::Approval { .. }) if pending.deadline.is_some_and(|d| self.st.now > d) => {
                self.st.pending = None;
                let digest = match &pending.purpose {
                    Purpose::Approval { digest, .. } => digest.clone(),
                    _ => String::new(),
                };
                let spec = self.approval_spec();
                // As the request named it: a person asked in place of a
                // mandate names none (§5.17, §5.14.1).
                let mandate_ref = match &pending.action.body {
                    Body::RequestApproval { approver, .. } => approver.get("mandate_ref").cloned(),
                    _ => None,
                };
                let sub = json!({
                    "digest": digest,
                    "decision": "expired",
                    "approvers": [],
                    "mode": spec.get("mode").and_then(Value::as_str).unwrap_or("in_session"),
                    "mandate_ref": mandate_ref,
                    "decided_at": iso(self.st.now),
                    "expires_at": pending.deadline.map(iso),
                });
                self.record_refused(
                    "expired",
                    Some(sub),
                    "no decision before the approval expired",
                    Some("F502"),
                );
                self.trace_step("approval_expired", json!({}));
                self.step_error("F502", "no decision before the approval expired");
            }
            (_, Purpose::Capability | Purpose::Event)
                if pending.deadline.is_some_and(|d| self.st.now > d) =>
            {
                self.st.pending = None;
                self.exec_error("R401", "the step timed out");
            }
            _ => return false,
        }
        self.drive();
        true
    }

    /// Cancel the run (§5.19.5): it ends with `Failed` R408 and no retry,
    /// failure mode, recovery loop, handler or rollback. Approved and queued
    /// records become `cancelled`; in record mode `actions`, so does a new
    /// record of every step, in every frame, that started its pass and has
    /// no record of it, and of a pending failure-mode checkpoint or rollback.
    pub(crate) fn cancel(&mut self, reason: &str, now: u64) -> Result<(), CancelError> {
        if let Some(t) = &self.st.finished
            && !matches!(
                t.end,
                End::Completed {
                    outcome: Outcome::Deferred,
                    ..
                }
            )
        {
            return Err(CancelError::Ended(t.end.describe()));
        }
        self.st.now = self.st.now.max(now.min(MAX_TIME));
        let pending = self.st.pending.take();
        let was_finished = self.st.finished.take().is_some();
        let cancel = |record: &mut Value| {
            record["status"] = json!("cancelled");
            record["code"] = json!("R408");
            record["reason"] = json!(reason);
        };
        // Approved actions may or may not have been carried out; queued ones
        // will not be. A resumed run writes a queued record again with the
        // time and actor of now, as when it supersedes one (§5.14.1).
        let base = self.st.records_base;
        let open: Vec<(usize, bool)> = self
            .st
            .records
            .iter()
            .enumerate()
            .filter_map(|(i, r)| match r["status"].as_str() {
                Some("approved") => Some((base + i, false)),
                Some("planned") => Some((base + i, true)),
                _ => None,
            })
            .collect();
        for (r, queued) in open {
            if queued && self.st.resumed {
                self.stamp(r);
            }
            cancel(self.st.rec_mut(r));
        }
        if !was_finished && self.st.records_mode == RecordMode::Actions {
            // By the step's state, root first: a step that started its pass
            // and has no record of it may have taken effect.
            for i in 0..self.st.frames.len() {
                let cur = &self.st.frames[i].cur;
                if cur.started && cur.record.is_none() {
                    let r = self.push_record(i, "cancelled", None);
                    cancel(self.st.rec_mut(r));
                    self.st.frames[i].cur.record = Some(r);
                }
            }
            // A pending failure-mode checkpoint or rollback has its own.
            let side = match pending.as_ref().map(|p| (&p.action.body, &p.purpose)) {
                Some((Body::CreateCheckpoint { .. }, Purpose::FailureCheckpoint { .. })) => {
                    Some(("checkpoint", None))
                }
                Some((Body::Rollback { checkpoint_id, .. }, _)) => {
                    Some(("rollback", Some(checkpoint_id.clone())))
                }
                _ => None,
            };
            if let Some((capability, checkpoint_id)) = side {
                self.side_record(capability, "cancelled", checkpoint_id, Some("R408"));
                if let Some(last) = self.st.records.last_mut() {
                    last["reason"] = json!(reason);
                }
            }
        }
        let checkpoint_id = self.st.checkpoints.last().map(|c| c.id.clone());
        let step = (!was_finished).then(|| self.frame_ref().step);
        self.trace("run_cancelled", step, json!({"reason": reason}));
        // A cancelled run cannot be resumed: nothing is kept for it.
        for f in &mut self.st.frames {
            f.parked.clear();
            f.resume = None;
            f.pending_escalation = None;
            f.queued = None;
            let deferred = f.deferred.clone();
            f.nested_caps.retain(|k, _| deferred.contains(k));
        }
        self.finish(End::Failed {
            code: "R408".into(),
            step,
            message: reason.into(),
            reason: None,
            checkpoint_id,
        });
        Ok(())
    }

    /// The host restored the checkpoint of the executor's own rollback
    /// (§4.4.1): its record (record mode `actions`) and the `rolled_back`
    /// trace event carry what the checkpoint never covered, when the host
    /// listed any.
    fn rolled_back_ok(&mut self, pending: &Pending, not_covered: Option<Vec<Value>>) {
        let written = self.st.records_written();
        self.side_record("rollback", "executed", rolled_back(pending), None);
        let detail = match not_covered {
            Some(nc) => {
                if self.st.records_written() > written {
                    let r = written;
                    self.st.rec_mut(r)["details"] = json!({"not_covered": nc});
                }
                json!({"not_covered": nc})
            }
            None => json!({}),
        };
        self.trace_step("rolled_back", detail);
    }

    /// The reason a failure-mode checkpoint or rollback failed with, on the
    /// record `side_record` just wrote (§6.4).
    fn side_reason(&mut self, reason: Option<&str>) {
        if let (RecordMode::Actions, Some(t)) = (self.st.records_mode, reason)
            && let Some(last) = self.st.records.last_mut()
        {
            last["reason_code"] = json!(t);
        }
    }
}

/// The evidence anchors of the outputs a nested run stored, in the order of
/// its workflow's steps: each `ref` once, and no `acs:` anchor, which names
/// a value of the nested run (§5.20).
fn nested_anchors(wf: &Workflow, stores: &Map<String, Value>) -> Vec<Value> {
    let mut refs: Vec<&str> = Vec::new();
    let mut out = Vec::new();
    let outputs = wf
        .steps
        .iter()
        .filter_map(|s| s.store_as.as_deref())
        .filter_map(|s| stores.get(s));
    for output in outputs {
        let items = output
            .get("evidence_anchors")
            .and_then(Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or_default();
        for item in items {
            let Some(r) = item.get("ref").and_then(Value::as_str) else {
                continue;
            };
            if crate::grounding::is_anchor(item) && !r.starts_with("acs:") && !refs.contains(&r) {
                refs.push(r);
                out.push(item.clone());
            }
        }
    }
    out
}

/// The checkpoint a pending `Rollback` restores.
fn rolled_back(pending: &Pending) -> Option<String> {
    match &pending.action.body {
        Body::Rollback { checkpoint_id, .. } => Some(checkpoint_id.clone()),
        _ => None,
    }
}

/// Whether a deferral's queued action can no longer be carried out: its
/// path runs through a step that is not deferred in its frame (the nested
/// run it was queued in failed), or a nested run that was not kept. A step
/// still listed by an earlier resumption of a nested run that was never
/// continued counts as deferred.
fn orphaned(top: &Frame, path: &[usize]) -> bool {
    let mut f = top;
    for (j, k) in path.iter().enumerate() {
        if !f.deferred.contains(k) && !f.resume.iter().flatten().any(|r| r == k) {
            return true;
        }
        if j + 1 < path.len() {
            match f.parked.get(k) {
                Some(child) => f = child,
                None => return true,
            }
        }
    }
    false
}

/// Reopen a frame that ended deferred (§5.14.1 item 2): its resumption list
/// is, in step order, the deferred steps; the steps that ran ahead of them
/// and that a later listed step reads; and the checkpoint steps whose
/// checkpoint the resumption invalidated and that a later listed step that
/// requires a checkpoint reads. A deferred handler goes last. Its kept
/// nested runs are reopened too. A frame reopened before whose nested run
/// was not continued (its invoke step was deferred again) keeps its list:
/// nothing it reads has changed since.
fn reopen(program: &Program, f: &mut Frame, invalidated: &[String]) {
    if f.resume.is_some() {
        return;
    }
    let wf = &program.workflows[&f.workflow];
    let deferred = std::mem::take(&mut f.deferred);
    let ahead = f.ahead.take().unwrap_or_default();
    let handler = f.escalation.take().map(|cause| {
        f.pending_escalation = Some(cause);
        f.step
    });
    let mut list: std::collections::BTreeSet<usize> = deferred
        .iter()
        .copied()
        .filter(|&s| Some(s) != handler)
        .collect();
    let reads = |s: usize, store: &str| wf.steps[s].reads.iter().any(|r| r == store);
    // Descending, so that every later reader is settled first.
    for c in (0..wf.steps.len()).rev() {
        let step = &wf.steps[c];
        if list.contains(&c) || step.handler {
            continue;
        }
        let Some(store) = step.store_as.as_deref() else {
            continue;
        };
        let later: Vec<usize> = list.range(c + 1..).copied().chain(handler).collect();
        let ran_ahead = ahead.contains(&c)
            && !step.after_deferral_runs
            && later.iter().any(|&s| reads(s, store));
        let stale_checkpoint = step.capability == "checkpoint"
            && f.stores
                .get(store)
                .and_then(|o| o.get("checkpoint_id"))
                .and_then(Value::as_str)
                .is_some_and(|id| invalidated.iter().any(|i| i == id))
            && later
                .iter()
                .any(|&s| wf.steps[s].requires_checkpoint && reads(s, store));
        if ran_ahead || stale_checkpoint {
            list.insert(c);
        }
    }
    let mut queue: Vec<usize> = list.into_iter().collect();
    queue.extend(handler);
    for child in f.parked.values_mut() {
        reopen(program, child, invalidated);
    }
    f.step = queue.first().copied().unwrap_or(wf.steps.len());
    f.stage = Stage::Begin;
    f.cur = StepState::default();
    f.resume = Some(queue);
}

/// What is wrong with a decision's `approver_identities` (§5.17), if
/// anything: a list of `agent_identity`, one per principal (an identical
/// repeat is one), whose principals are exactly `approvers` when that is
/// not empty.
fn approver_identities_error(approvers: &[String], list: &Value) -> Option<String> {
    let Some(items) = list.as_array() else {
        return Some("must be a list".into());
    };
    let mut seen: std::collections::BTreeMap<&str, &Value> = std::collections::BTreeMap::new();
    for (i, id) in items.iter().enumerate() {
        if let Err(e) = super::ijson(id) {
            return Some(format!("[{i}]: {e}"));
        }
        if let Some(e) = super::identity_error(id) {
            return Some(format!("[{i}]: {e}"));
        }
        let p = id["principal"].as_str().unwrap_or_default();
        match seen.get(p) {
            Some(other) if *other != id => {
                return Some(format!("two different identities for '{p}'"));
            }
            _ => {
                seen.insert(p, id);
            }
        }
    }
    let principals: std::collections::BTreeSet<&str> = seen.keys().copied().collect();
    let named: std::collections::BTreeSet<&str> = approvers.iter().map(String::as_str).collect();
    if !approvers.is_empty() && principals != named {
        return Some("the decision's approvers are not its identities' principals".into());
    }
    None
}

/// Who an approval decision counts (§5.14, §5.17).
struct Counting {
    /// The approvers that count: principals with identities, else the
    /// distinct strings of `approvers`, in order.
    approvers: Vec<String>,
    /// With identities: those of the approvers that count.
    identities: Option<Vec<Value>>,
    /// Who did not count, and why.
    note: Option<String>,
    /// Counted by attested identity (or required to be, and none came).
    attested: bool,
}

/// Whether an attested approver identity meets the request (§5.17): a
/// `human` approver's identity has kind `human`; a requested `role` is its
/// role; and, in a workflow that targets 1.2, its `authenticated_by` and
/// `trust_class` are among the approver's `sender_check` and
/// `accept_trust_classes`. In an earlier target those two are not read.
fn meets(approver: &Value, id: &Value, v12: bool) -> Result<(), String> {
    if approver["kind"] == "human" && id["kind"] != "human" {
        return Err(format!(
            "kind {} is not 'human'",
            id.get("kind").unwrap_or(&Value::Null)
        ));
    }
    if let Some(role) = approver.get("role").and_then(Value::as_str)
        && id["role"].as_str() != Some(role)
    {
        return Err(match id["role"].as_str() {
            Some(r) => format!("role '{r}' is not '{role}'"),
            None => format!("no role, '{role}' requested"),
        });
    }
    if v12 {
        for (key, field) in [
            ("sender_check", "authenticated_by"),
            ("accept_trust_classes", "trust_class"),
        ] {
            let Some(allowed) = approver.get(key).and_then(Value::as_array) else {
                continue;
            };
            let v = id[field].as_str();
            if !v.is_some_and(|v| allowed.iter().any(|a| a == v)) {
                return Err(match v {
                    Some(v) => format!("{field} '{v}' is not in {key}"),
                    None => format!("no {field}, which {key} requires"),
                });
            }
        }
    }
    Ok(())
}

/// Whether `identity`'s `field` is one of `allowed` (`sender_check`,
/// `accept_trust_classes`): true when nothing is required, false when the
/// identity or the field is missing.
fn listed(allowed: &Option<Vec<String>>, identity: &Option<Value>, field: &str) -> bool {
    let Some(allowed) = allowed else {
        return true;
    };
    identity
        .as_ref()
        .and_then(|i| i[field].as_str())
        .is_some_and(|v| allowed.iter().any(|a| a == v))
}

/// The `identity@1` inputs a step resolved, checked as the validator checks
/// literals: a bound value that is not a list of known values (say, a
/// reference that resolved to null) would silently turn a check off, so it
/// fails the step instead.
fn identity_inputs(inputs: &Value) -> Result<(), String> {
    use crate::validate::identity::{TRUST_CLASSES, known_mechanism};
    for key in [
        "sender_check",
        "accept_trust_classes",
        "always_ask_trust_classes",
    ] {
        let Some(value) = inputs.get(key) else {
            continue;
        };
        let Some(items) = value.as_array() else {
            return Err(format!(
                "{key} must be a list, got {}",
                crate::yaml::kind_of(value)
            ));
        };
        if items.is_empty() && key != "always_ask_trust_classes" {
            return Err(format!("{key} is empty, so it would accept no sender"));
        }
        for item in items {
            let known = item.as_str().is_some_and(|s| {
                if key == "sender_check" {
                    known_mechanism(s)
                } else {
                    TRUST_CLASSES.contains(&s)
                }
            });
            if !known {
                return Err(format!(
                    "{key} holds {item}, which is not one of its values"
                ));
            }
        }
    }
    Ok(())
}

/// A bound list of strings (`accept_from`, `sender_check`, ...), if any.
/// `accept_from`, when bound, must be a non-empty list of principals when
/// the step runs: anything else would drop every sender.
fn accept_from_input(inputs: &Value) -> Result<(), String> {
    let Some(value) = inputs.get("accept_from") else {
        return Ok(());
    };
    match value.as_array() {
        Some(items) if items.is_empty() => {
            Err("accept_from is empty, so it would accept no sender".into())
        }
        Some(items) => match items.iter().find(|i| !i.is_string()) {
            Some(bad) => Err(format!("accept_from holds {bad}, which is not a principal")),
            None => Ok(()),
        },
        None => Err(format!(
            "accept_from must be a list, got {}",
            crate::yaml::kind_of(value)
        )),
    }
}

fn string_list(inputs: &Value, key: &str) -> Option<Vec<String>> {
    inputs.get(key).and_then(Value::as_array).map(|a| {
        a.iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timestamps() {
        assert_eq!(iso(0), "1970-01-01T00:00:00.000Z");
        assert_eq!(iso(951_782_400_123), "2000-02-29T00:00:00.123Z");
        assert_eq!(iso(1_798_761_599_999), "2026-12-31T23:59:59.999Z");
    }

    #[test]
    fn binding_resolution() {
        let mut m = Map::new();
        m.insert("a".into(), json!({"n": 3, "s": "x", "l": [1, 2]}));
        assert_eq!(resolve(&json!("${a.n}"), &m), json!(3));
        assert_eq!(resolve(&json!("n=${a.n} s=${a.s}"), &m), json!("n=3 s=x"));
        assert_eq!(
            resolve(&json!(["${a.l[1]}", {"k": "${nope}"}]), &m),
            json!([2, {"k": null}])
        );
        assert_eq!(resolve(&json!("${a.n: number}"), &m), json!(3));
    }
}
