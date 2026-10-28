//! The step algorithm (design-114 §16.3) over the run state.

use serde_json::{Map, Value, json};

use super::canonical;
use super::program::{GateAction, Program, Step, Workflow};
use super::quorum;
use super::{
    Action, Attendance, Body, Checkpoint, Deferral, Frame, MAX_FRAMES, MAX_TIME, Outcome, Pending,
    Purpose, Replacement, Response, Stage, State, StepError, StepState, SubmitError, check_inputs,
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
    if let [m] = found.as_slice() {
        if m.start == 0 && m.end == s.len() {
            if let Ok(r) = &m.parsed {
                return read(r);
            }
        }
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

/// What an approval request asked for.
struct Asked<'s> {
    digest: &'s str,
    expires_at: Option<u64>,
    min: u64,
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
            "seq": self.st.trace.len(),
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
        let step = self.frame_ref().step;
        let purpose = self
            .step_ref()
            .raw
            .get("purpose")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let n = self.st.records.len();
        let mut record = json!({
            "action_id": format!("{}/{}/{step}/{n}", self.st.run_id, self.names().join("/")),
            "timestamp": iso(self.st.now),
            "actor": "agent",
            "intent": purpose,
            "status": status,
        });
        if let Some(identity) = &self.st.actor_identity {
            record["actor"] = identity["kind"].clone();
            record["actor_identity"] = identity.clone();
        }
        if self.always_ask() {
            record["always_ask"] = json!(true);
        }
        if let Some(a) = approval {
            record["approval"] = a;
        }
        self.st.records.push(record);
        n
    }

    /// A record for an action that did not go ahead, with the reason.
    fn record_refused(&mut self, status: &str, approval: Option<Value>, reason: &str) {
        let r = self.record(status, approval);
        self.st.records[r]["reason"] = json!(reason);
        self.frame().cur.record = Some(r);
    }

    fn set_record_status(&mut self, status: &str) {
        if let Some(r) = self.frame_ref().cur.record {
            self.st.records[r]["status"] = json!(status);
        }
    }

    /// An approved action that then failed. A record that is already
    /// rejected, expired or executed keeps its status.
    fn record_failed(&mut self) {
        if let Some(r) = self.frame_ref().cur.record {
            if self.st.records[r]["status"] == "approved" {
                self.st.records[r]["status"] = json!("failed");
            }
        }
    }

    // ---- actions ----

    fn emit(&mut self, body: Body, purpose: Purpose, deadline: Option<u64>) -> Flow {
        let action = Action {
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

    fn finish(&mut self, body: Body) -> Flow {
        let action = Action {
            id: self.st.next_id,
            frame: self.names(),
            body,
        };
        self.st.next_id += 1;
        self.st.pending = None;
        self.st.finished = Some(action);
        Flow::Wait
    }

    /// End the whole run from any frame (replanning ends every frame).
    fn finish_run(&mut self, outcome: Outcome) -> Flow {
        self.trace("run_finished", None, json!({"outcome": outcome}));
        let outputs = Value::Object(self.st.frames[0].stores.clone());
        let records = self.st.records.clone();
        let deferred = self.deferred_report();
        self.finish(Body::Completed {
            outcome,
            cause: None,
            ended: None,
            outputs,
            action_records: records,
            deferred,
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
        let message = message.into();
        self.trace_step("step_failed", json!({"code": code, "message": message}));
        self.frame().cur.error = Some(StepError {
            code: code.to_string(),
            message,
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

    /// After a step: the next one, or the end of an escalation.
    fn next_step(&mut self) -> Flow {
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
        if self.frame_ref().escalation.is_some() {
            return self.next_step();
        }
        self.end_frame(Ok((Outcome::Completed, None)))
    }

    fn fail_run(&mut self, code: &str, message: &str) -> Flow {
        let step = self.st.frames.last().map(|f| f.step);
        self.trace(
            "run_failed",
            step,
            json!({"code": code, "message": message}),
        );
        let records = self.st.records.clone();
        let deferred = self.deferred_report();
        self.finish(Body::Failed {
            code: code.to_string(),
            step,
            message: message.to_string(),
            action_records: records,
            deferred,
        })
    }

    /// The top frame ends: the run ends, or the parent's invoke step gets
    /// the result.
    fn end_frame(&mut self, end: Result<(Outcome, Option<String>), (String, String)>) -> Flow {
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
                    let outputs = Value::Object(self.st.frames[0].stores.clone());
                    let records = self.st.records.clone();
                    let deferred = self.deferred_report();
                    let ended = self.st.frames[0].ended.clone();
                    self.finish(Body::Completed {
                        outcome,
                        cause,
                        ended,
                        outputs,
                        action_records: records,
                        deferred,
                    })
                }
                Err((code, message)) => self.fail_run(&code, &message),
            };
        }
        let child = self.st.frames.pop().expect("checked above");
        if child.marked || !child.always_ask.is_empty() {
            self.frame().cur.always_ask = true;
        }
        let result = match &end {
            Ok((o, _)) => json!(o),
            Err((c, _)) => json!(c),
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
                self.frame().cur.output = Some(json!({
                    "result": Value::Object(child.stores),
                    "steps_executed": steps,
                    "evidence_anchors": [],
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
                if let Some(r) = self.frame_ref().cur.record {
                    if self.st.records[r]["status"] == "approved" {
                        self.st.records[r]["status"] = json!("executed");
                        self.st.records[r]["reason"] =
                            json!("its nested run deferred steps, which are queued separately");
                    }
                }
                let wf = &self.program.workflows[&child.workflow];
                let mut caps: Vec<String> = child
                    .deferred
                    .iter()
                    .map(|&d| wf.steps[d].capability.clone())
                    .chain(child.nested_caps.into_values().flatten())
                    .collect();
                caps.sort_unstable();
                caps.dedup();
                let step = self.frame_ref().step;
                self.frame().nested_caps.insert(step, caps);
                self.defer_step(&format!(
                    "invoked workflow '{}' deferred steps",
                    child.workflow
                ))
            }
            Ok((outcome, _)) => self.finish_run(outcome),
            Err((code, message)) => self.exec_error(
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
        let escalating = self.frame_ref().escalation.is_some();
        let (index, count) = (self.frame_ref().step, self.workflow().steps.len());
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
        self.set_stage(Stage::Approval)
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
            return self.end_frame(Err((
                "F503".to_string(),
                "there is no checkpoint to roll back to".to_string(),
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
        // A standing mandate needs no one present: it is asked even in an
        // unattended run, and the plan applies only if none covers the step.
        let mandate = !marked
            && spec
                .get("approver")
                .and_then(|a| a.get("kind"))
                .and_then(Value::as_str)
                == Some("standing_mandate");
        if self.st.attendance == Attendance::Unattended && !mandate {
            let why = if marked {
                "the run is unattended and the step uses an item from an always-ask trust class"
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
        if marked {
            if let Value::Object(a) = &mut approver {
                a.insert("kind".into(), json!("human"));
                a.remove("mandate_ref");
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
                );
                self.skip_step(&format!("approval needed, but {why}"))
            }
            "defer_to_queue" => {
                let r = self.record("planned", approval);
                self.st.records[r]["reason"] =
                    json!(format!("{why} (when_unattended: defer_to_queue)"));
                self.frame().cur.record = Some(r);
                self.defer_step(why)
            }
            _ => {
                let why = format!("approval is needed, but {why}");
                self.record_refused("rejected", approval, &why);
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
        let record = match self.frame_ref().cur.record {
            // The queued action (when_unattended: defer_to_queue).
            Some(r) if self.st.records[r]["status"] == "planned" => Some(r),
            // An invoke that ran: its nested run's records are the queue.
            Some(_) => None,
            None if self.step_ref().requires_approval => {
                let r = self.record("planned", None);
                self.st.records[r]["reason"] = json!(why);
                Some(r)
            }
            None => None,
        };
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

    /// A wait or delay ended: checkpoints taken before it describe a world
    /// that may have changed, so they authorise nothing after it (W608).
    fn invalidate_checkpoints(&mut self) {
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
            self.trace_step(
                "checkpoints_invalidated",
                json!({"checkpoint_ids": invalidated}),
            );
        }
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
        deferred()
            .map(|d| &d.capability)
            .chain(f.nested_caps.values().flatten())
            .find(|c| step.after.contains(c))
            .map(|c| {
                format!(
                    "the ontology orders {} after {c}, which was deferred",
                    step.capability
                )
            })
    }

    /// A recovery loop to `target` runs its steps again: they are no longer
    /// deferred, here or in the nested runs under them, and the actions
    /// they queued are superseded.
    fn undefer_from(&mut self, target: usize) {
        let f = self.frame();
        f.deferred.retain(|&d| d < target);
        f.nested_caps.retain(|&k, _| k < target);
        let depth = self.st.frames.len() - 1;
        let prefix: Vec<usize> = self.st.frames[..depth].iter().map(|f| f.step).collect();
        self.supersede(
            |d| d.path.len() > depth && d.path[..depth] == prefix[..] && d.path[depth] >= target,
            "superseded: a recovery loop ran the step again",
        );
    }

    /// An invoke step starts its nested run (again, after a retry): what an
    /// earlier attempt deferred under it is superseded.
    fn undefer_nested(&mut self) {
        let path: Vec<usize> = self.st.frames.iter().map(|f| f.step).collect();
        let step = self.frame_ref().step;
        self.frame().nested_caps.remove(&step);
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
            if self.st.records[r]["status"] == "planned" {
                self.st.records[r]["status"] = json!("rejected");
                self.st.records[r]["reason"] = json!(reason);
            }
        }
    }
    /// The run's deferrals, as the terminal action reports them.
    fn deferred_report(&self) -> Vec<Value> {
        self.st
            .deferrals
            .iter()
            .map(|d| {
                json!({
                    "frame": d.frame,
                    "step": d.path.last(),
                    "store_as": d.store_as,
                    "reason": d.reason,
                    "action_id": d.record.map(|r| self.st.records[r]["action_id"].clone()),
                })
            })
            .collect()
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
        } = asked;
        let spec = self.approval_spec();
        let now = self.st.now;
        let distinct: std::collections::BTreeSet<&String> = approvers.iter().collect();
        // A person was asked instead of the mandate (§5.17).
        let mandate_ref = if self.always_ask() {
            Value::Null
        } else {
            spec.get("approver")
                .and_then(|a| a.get("mandate_ref"))
                .cloned()
                .unwrap_or(Value::Null)
        };
        let sub = |decision: &str| {
            json!({
                "digest": expected,
                "decision": decision,
                "approvers": distinct.iter().collect::<Vec<_>>(),
                "mode": spec.get("mode").and_then(Value::as_str).unwrap_or("in_session"),
                "mandate_ref": mandate_ref,
                "decided_at": iso(now),
                "expires_at": expires_at.map(iso),
            })
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
            if self.st.attendance == Attendance::Unattended {
                return self.unattended(Some(record), "no standing mandate covers the action");
            }
            let why = "the approver was unavailable";
            self.record_refused("rejected", Some(record), why);
            return self.step_error("F502", why);
        }
        let reused = !self.st.used_decisions.insert(decision_id.clone());
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
        } else if (distinct.len() as u64) < min {
            Some((
                "rejected",
                format!("{} distinct approver(s), {min} needed", distinct.len()),
            ))
        } else {
            None
        };
        self.trace_step(
            "approval_decided",
            json!({"decision_id": decision_id, "decision": decision, "valid": problem.is_none()}),
        );
        if let Some((status, reason)) = problem {
            let sub = sub(status);
            self.record_refused(status, Some(sub), &reason);
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
                self.step_error("F502", "the approved source changed before acting")
            }
            _ => {
                self.set_record_status("expired");
                if let Some(r) = self.frame_ref().cur.record {
                    self.st.records[r]["reason"] =
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
            if wf.extension("delegation@1") {
                if let Err(e) = accept_from_input(&self.frame_ref().cur.inputs) {
                    return self.step_error("R402", e);
                }
            }
            if wf.extension("identity@1") {
                if let Err(e) = identity_inputs(&self.frame_ref().cur.inputs) {
                    return self.step_error("R402", e);
                }
            }
        }
        // A correlate key that resolves to null would match every event
        // without that key: fail before acting (delegating) or waiting.
        if wf.extension("wait@1") {
            if let Some(Value::Object(c)) = step.raw.get("wait").and_then(|w| w.get("correlate")) {
                let bindings = FrameBindings(self.frame_ref());
                if let Some(k) = c
                    .iter()
                    .find(|(_, v)| resolve(v, &bindings).is_null())
                    .map(|(k, _)| k)
                {
                    return self.step_error(
                        "R402",
                        format!("wait.correlate.{k} resolved to null, so it would match events that lack it"),
                    );
                }
            }
        }
        // A delegate that waits delegates first (an InvokeCapability below),
        // then waits for its delegate's result.
        let delegating = step.capability == "delegate" && self.frame_ref().cur.delegated.is_none();
        if wf.extension("wait@1") && !delegating {
            if let Some(Value::Object(wait)) = step.raw.get("wait") {
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
                        liveness: wait.get("liveness").cloned(),
                        deadline,
                    },
                    Purpose::Event,
                    deadline,
                );
            }
        }
        if step.capability == "invoke" {
            return self.invoke(step);
        }
        if step.capability == "constrain" && wf.extension("quorum@1") {
            if let Some(Value::Object(q)) = step.raw.get("quorum") {
                let result = quorum::evaluate(q, self.frame_ref());
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
        }
        let inputs = self.frame_ref().cur.inputs.clone();
        let attempt = self.frame_ref().cur.attempt;
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
        self.undefer_nested();
        let mut frame = Frame::new(&target, child_inputs);
        frame.marked = self.always_ask();
        self.st.frames.push(frame);
        Flow::Continue
    }

    /// An execution error: retried while attempts remain (R401, R402,
    /// R406), then on to the failure modes.
    fn exec_error(&mut self, code: &str, message: impl Into<String>) -> Flow {
        let message = message.into();
        let (attempt, retry) = {
            let s = self.step_ref();
            (
                self.frame_ref().cur.attempt,
                s.retry.as_ref().map(|r| (r.max, r.backoff.clone())),
            )
        };
        if matches!(code, "R401" | "R402" | "R406") {
            if let Some((max, backoff)) = retry {
                if attempt <= max {
                    let wait_ms: u64 = match backoff.as_str() {
                        "linear" => 1000u64.saturating_mul(u64::from(attempt)),
                        "exponential" => {
                            1000u64.saturating_mul(1u64 << attempt.saturating_sub(1).min(32))
                        }
                        _ => 0,
                    };
                    self.trace_step(
                        "retry",
                        json!({"code": code, "message": message, "attempt": attempt, "backoff_ms": wait_ms}),
                    );
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
            }
        }
        self.step_error(code, message)
    }

    fn output(&mut self, value: Value) -> Flow {
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
        if step.capability == "delegate"
            && self.frame_ref().cur.delegated.is_none()
            && self.program.workflows[&self.frame_ref().workflow].extension("wait@1")
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
            self.trace_step("delegated", json!({"task_id": value.get("task_id")}));
            let f = self.frame();
            f.replaces.retain(|r| r.step != step.index);
            f.cur.delegated = Some(value);
            return self.set_stage(Stage::Execute);
        }
        if step.capability == "checkpoint" {
            let id = value
                .get("checkpoint_id")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| self.derived_checkpoint_id());
            self.add_checkpoint(id);
        }
        self.frame().cur.output = Some(value);
        self.set_stage(Stage::After)
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
        let f = self.frame_ref();
        f.marked
            || !f.always_ask.is_empty()
                && self
                    .step_ref()
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
        let identity = identity
            .filter(|_| self.program.workflows[&self.frame_ref().workflow].extension("identity@1"));
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
        self.invalidate_checkpoints();
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
        self.set_record_status("executed");
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
            Some(e) => {
                self.record_failed();
                self.end_frame(Err((e.code, e.message)))
            }
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
        let (code, message) = match &self.frame_ref().cur.error {
            Some(e) => (e.code.clone(), e.message.clone()),
            None => (
                "R402".to_string(),
                format!(
                    "failure mode {f} fired: {}",
                    step.raw["failure_modes"][f]["condition"]
                ),
            ),
        };
        if self.frame_ref().cur.error.is_some() {
            self.record_failed();
        }
        if fm.action == "escalate" {
            return match fm.goto {
                Some(h) => self.escalate(h, &code),
                None => self.end_frame(Err((code, message))),
            };
        }
        let Some(target) = fm.goto else {
            return self.end_frame(Err((code, message)));
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
                None => self.end_frame(Err((
                    "R404".to_string(),
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
            return self.end_frame(Err((
                "R402".to_string(),
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
        let cleared: Vec<String> = wf.steps[target..]
            .iter()
            .filter_map(|s| s.store_as.clone())
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
                Response::RolledBack | Response::Error { .. }
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
            Response::Output { value } | Response::Current { value } => vec![value],
            Response::Event { event, .. } => vec![event],
            _ => Vec::new(),
        };
        for v in values {
            super::ijson(v).map_err(SubmitError::Malformed)?;
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
            (Purpose::Capability, Response::Output { value }) => {
                self.output(value);
            }
            (
                purpose @ (Purpose::Capability | Purpose::Event),
                Response::Error { code, message },
            ) => {
                // A timeout keeps its code; so does lost liveness on a wait.
                // Anything else a host reports is a failed step.
                let keep = code == "R401" || (code == "R406" && matches!(purpose, Purpose::Event));
                let code = if keep { code } else { "R402".to_string() };
                self.exec_error(&code, message);
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
            (Purpose::Checkpoint, Response::Error { message, .. }) => {
                self.step_error("F501", format!("could not take a checkpoint: {message}"));
            }
            (Purpose::FailureCheckpoint { mode }, Response::Checkpoint { checkpoint_id }) => {
                self.add_checkpoint(checkpoint_id);
                self.recover(mode);
            }
            (Purpose::FailureCheckpoint { .. }, Response::Error { message, .. }) => {
                self.end_frame(Err((
                    "F501".to_string(),
                    format!("could not take a checkpoint: {message}"),
                )));
            }
            (Purpose::GateRollback { message }, Response::RolledBack) => {
                self.trace_step("rolled_back", json!({}));
                self.step_error("R403", message);
            }
            (Purpose::FailureRollback { mode }, Response::RolledBack) => {
                self.trace_step("rolled_back", json!({}));
                self.recover(mode);
            }
            (
                Purpose::GateRollback { .. } | Purpose::FailureRollback { .. },
                Response::Error { message, .. },
            ) => {
                self.end_frame(Err((
                    "F503".to_string(),
                    format!("rollback failed: {message}"),
                )));
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
                },
            ) => {
                let asked = Asked {
                    digest: &digest,
                    expires_at,
                    min,
                };
                self.decide(decision_id, &decision, &approvers, &given, asked);
            }
            (Purpose::Recheck, Response::Current { value }) => {
                self.rechecked(value);
            }
            (Purpose::Recheck, Response::Error { message, .. }) => {
                self.step_error(
                    "F502",
                    format!("could not recheck the approved source: {message}"),
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

    pub(crate) fn tick(&mut self, now: u64) {
        if self.st.finished.is_some() {
            return;
        }
        self.st.now = self.st.now.max(now.min(MAX_TIME));
        let Some(pending) = self.st.pending.clone() else {
            return;
        };
        match (&pending.action.body, &pending.purpose) {
            (Body::Sleep { until }, _) if self.st.now >= *until => {
                self.st.pending = None;
                if matches!(self.frame_ref().stage, Stage::Delay { .. }) {
                    // The world may have changed while the step waited.
                    self.invalidate_checkpoints();
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
                let mandate_ref = if self.always_ask() {
                    None
                } else {
                    spec.get("approver").and_then(|a| a.get("mandate_ref"))
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
            _ => return,
        }
        self.drive();
    }
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
