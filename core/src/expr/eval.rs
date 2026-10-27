//! Deterministic evaluation (design-114 §7): a pure function of the
//! expression and the values bound to its reference roots.

use std::borrow::Cow;
use std::cmp::Ordering;

use serde_json::Value;

use super::ast::{CmpOp, Expr, RefAt};
use crate::refs::Seg;
use crate::yaml::kind_of;

/// A runtime evaluation error (R405).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvalError {
    pub pos: usize,
    pub msg: String,
}

/// Values for reference roots. A root with no value resolves to `null`.
pub trait Bindings {
    fn get(&self, root: &str) -> Option<&Value>;
}

impl Bindings for serde_json::Map<String, Value> {
    fn get(&self, root: &str) -> Option<&Value> {
        serde_json::Map::get(self, root)
    }
}

static NULL: Value = Value::Null;

/// Resolve a reference. Total: a missing root or key, an index out of range,
/// or a segment applied to the wrong kind of value yields `null`. A slice
/// clamps to the array's bounds.
pub fn resolve<'a>(r: &RefAt, b: &'a dyn Bindings) -> Cow<'a, Value> {
    let mut cur: Cow<'a, Value> = Cow::Borrowed(b.get(&r.r.root).unwrap_or(&NULL));
    for seg in &r.r.path {
        cur = match (seg, cur) {
            (Seg::Field(k), Cow::Borrowed(Value::Object(m))) => {
                Cow::Borrowed(m.get(k).unwrap_or(&NULL))
            }
            (Seg::Field(k), Cow::Owned(Value::Object(mut m))) => {
                Cow::Owned(m.remove(k).unwrap_or(Value::Null))
            }
            (Seg::Index(i), Cow::Borrowed(Value::Array(a))) => {
                Cow::Borrowed(a.get(*i).unwrap_or(&NULL))
            }
            (Seg::Index(i), Cow::Owned(Value::Array(mut a))) => Cow::Owned(if *i < a.len() {
                a.swap_remove(*i)
            } else {
                Value::Null
            }),
            (Seg::Slice(s, e), c) => match &*c {
                Value::Array(a) => {
                    let n = a.len();
                    let s = s.unwrap_or(0).min(n);
                    let e = e.unwrap_or(n).min(n);
                    Cow::Owned(Value::Array(if s < e {
                        a[s..e].to_vec()
                    } else {
                        Vec::new()
                    }))
                }
                _ => Cow::Borrowed(&NULL),
            },
            _ => Cow::Borrowed(&NULL),
        };
    }
    cur
}

/// Deep structural equality, iterative so deep values cannot exhaust the
/// stack. Numbers compare by binary64 value (`1 == 1.0`, `-0 == 0`); values of
/// different kinds are unequal, never an error.
pub fn deep_eq(a: &Value, b: &Value) -> bool {
    let mut stack: Vec<(&Value, &Value)> = vec![(a, b)];
    while let Some((x, y)) = stack.pop() {
        match (x, y) {
            (Value::Null, Value::Null) => {}
            (Value::Bool(p), Value::Bool(q)) if p == q => {}
            (Value::Number(p), Value::Number(q)) if p.as_f64() == q.as_f64() => {}
            (Value::String(p), Value::String(q)) if p == q => {}
            (Value::Array(p), Value::Array(q)) if p.len() == q.len() => {
                stack.extend(p.iter().zip(q.iter()));
            }
            (Value::Object(p), Value::Object(q)) if p.len() == q.len() => {
                for (k, v) in p {
                    match q.get(k) {
                        Some(w) => stack.push((v, w)),
                        None => return false,
                    }
                }
            }
            _ => return false,
        }
    }
    true
}

fn order(a: &Value, b: &Value) -> Option<Ordering> {
    match (a, b) {
        (Value::Number(p), Value::Number(q)) => p.as_f64()?.partial_cmp(&q.as_f64()?),
        // UTF-8 byte order is Unicode code point order.
        (Value::String(p), Value::String(q)) => Some(p.as_str().cmp(q.as_str())),
        // As in CEL: false < true.
        (Value::Bool(p), Value::Bool(q)) => Some(p.cmp(q)),
        _ => None,
    }
}

fn eval_inner<'a>(e: &'a Expr, b: &'a dyn Bindings) -> Result<Cow<'a, Value>, EvalError> {
    Ok(match e {
        Expr::Lit(v, _) => Cow::Borrowed(v),
        Expr::Ref(r) => resolve(r, b),
        Expr::Not(x, pos) => Cow::Owned(Value::Bool(!boolean(x, b, *pos, "!")?)),
        // CEL semantics: the operands are evaluated in any order and a
        // determining operand (false for &&, true for ||) wins over an error
        // in another; otherwise the first error stands.
        Expr::And(xs) => Cow::Owned(Value::Bool(absorb(xs, b, false, "&&")?)),
        Expr::Or(xs) => Cow::Owned(Value::Bool(absorb(xs, b, true, "||")?)),
        Expr::Cmp(op, l, r, pos) => {
            let lv = eval_inner(l, b)?;
            let rv = eval_inner(r, b)?;
            let res = match op {
                CmpOp::Eq => deep_eq(&lv, &rv),
                CmpOp::Ne => !deep_eq(&lv, &rv),
                _ => {
                    let o = order(&lv, &rv).ok_or_else(|| EvalError {
                        pos: *pos,
                        msg: format!(
                            "'{}' needs two numbers, two strings or two booleans, got {} and {}",
                            op.as_str(),
                            kind_of(&lv),
                            kind_of(&rv)
                        ),
                    })?;
                    match op {
                        CmpOp::Lt => o == Ordering::Less,
                        CmpOp::Le => o != Ordering::Greater,
                        CmpOp::Gt => o == Ordering::Greater,
                        _ => o != Ordering::Less,
                    }
                }
            };
            Cow::Owned(Value::Bool(res))
        }
    })
}

/// n-ary `&&` (`decisive = false`) or `||` (`decisive = true`).
fn absorb(xs: &[Expr], b: &dyn Bindings, decisive: bool, op: &str) -> Result<bool, EvalError> {
    let mut first_error = None;
    for x in xs {
        match boolean(x, b, x.pos(), op) {
            Ok(v) if v == decisive => return Ok(decisive),
            Ok(_) => {}
            Err(e) => {
                first_error.get_or_insert(e);
            }
        }
    }
    match first_error {
        Some(e) => Err(e),
        None => Ok(!decisive),
    }
}

fn boolean(e: &Expr, b: &dyn Bindings, pos: usize, op: &str) -> Result<bool, EvalError> {
    match &*eval_inner(e, b)? {
        Value::Bool(x) => Ok(*x),
        other => Err(EvalError {
            pos,
            msg: format!(
                "operand of '{op}' must be boolean, got {} (there is no truthiness)",
                kind_of(other)
            ),
        }),
    }
}

/// Evaluate an expression to its value.
pub fn eval_value(e: &Expr, b: &dyn Bindings) -> Result<Value, EvalError> {
    eval_inner(e, b).map(Cow::into_owned)
}

/// Evaluate a `condition`, `gates[].when` or `failure_modes[].when`: the
/// result must be a boolean.
pub fn eval_condition(e: &Expr, b: &dyn Bindings) -> Result<bool, EvalError> {
    match &*eval_inner(e, b)? {
        Value::Bool(x) => Ok(*x),
        other => Err(EvalError {
            pos: e.pos(),
            msg: format!(
                "condition must evaluate to a boolean, got {}",
                kind_of(other)
            ),
        }),
    }
}
