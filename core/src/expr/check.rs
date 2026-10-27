//! Static checking of expressions against producer schemas (STANDARD §10.2
//! L3: "validates gate and condition expressions").
//!
//! An expression's type is a set of JSON kinds, or *dynamic* when the schema
//! gives no usable type (`type: any`, missing metadata, unresolved `$ref`).
//! Every reference may be null at runtime (an absent value resolves to null),
//! so possible nulls are tracked separately and only warned about.

use serde_json::Value;

use super::ast::{CmpOp, Expr, RefAt};
use crate::diag::Code;
use crate::refs::Seg;
use crate::schema;
use crate::types::{self, Type};

const K_NULL: u8 = 1;
const K_BOOL: u8 = 2;
const K_INT: u8 = 4;
const K_FRAC: u8 = 8;
const K_NUM: u8 = K_INT | K_FRAC;
const K_STR: u8 = 16;
const K_ARR: u8 = 32;
const K_OBJ: u8 = 64;
const K_ALL: u8 = 127;

/// What the validator knows about a reference root at this point.
pub struct RootInfo<'a> {
    /// The resolved schema of the root, if it has one.
    pub schema: Option<&'a Value>,
    /// False when the root may legitimately be absent at runtime: an optional
    /// input, or a producer step that a condition or skip gate can skip.
    pub always_present: bool,
}

/// Resolves reference roots for the checker.
pub trait Scope {
    /// `None`: the root is neither an earlier store nor a workflow input.
    fn root(&self, name: &str) -> Option<RootInfo<'_>>;
}

/// A finding: code, byte offset in the expression, message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    pub code: Code,
    pub pos: usize,
    pub msg: String,
}

#[derive(Debug, Clone, Copy)]
struct Ty {
    kinds: u8,
    dynamic: bool,
    maybe_null: bool,
    literal_null: bool,
    /// A diagnostic was already reported for this operand (unknown root, bad
    /// path); further checks on it would only repeat the same mistake.
    poisoned: bool,
}

impl Ty {
    fn exact(kinds: u8) -> Ty {
        Ty {
            kinds,
            dynamic: false,
            maybe_null: false,
            literal_null: false,
            poisoned: false,
        }
    }

    fn dynamic(maybe_null: bool) -> Ty {
        Ty {
            kinds: K_ALL,
            dynamic: true,
            maybe_null,
            literal_null: false,
            poisoned: false,
        }
    }

    fn poisoned() -> Ty {
        Ty {
            poisoned: true,
            ..Ty::dynamic(false)
        }
    }
}

fn kinds_str(k: u8) -> String {
    let mut v = Vec::new();
    for (bit, n) in [
        (K_NULL, "null"),
        (K_BOOL, "boolean"),
        (K_STR, "string"),
        (K_ARR, "array"),
        (K_OBJ, "object"),
    ] {
        if k & bit != 0 {
            v.push(n);
        }
    }
    match k & K_NUM {
        K_NUM => v.push("number"),
        K_INT => v.push("integer"),
        K_FRAC => v.push("non-integral number"),
        _ => {}
    }
    v.join("|")
}

fn name_kinds(t: &str) -> Option<u8> {
    Some(match t.trim() {
        "null" => K_NULL,
        "boolean" => K_BOOL,
        "integer" => K_INT,
        "number" => K_NUM,
        "string" => K_STR,
        "array" => K_ARR,
        "object" => K_OBJ,
        _ => return None, // includes the non-standard `any`
    })
}

fn value_kinds(v: &Value) -> u8 {
    match v {
        Value::Null => K_NULL,
        Value::Bool(_) => K_BOOL,
        Value::Number(n) => {
            if n.as_f64().is_some_and(|f| f.fract() == 0.0) {
                K_INT
            } else {
                K_FRAC
            }
        }
        Value::String(_) => K_STR,
        Value::Array(_) => K_ARR,
        Value::Object(_) => K_OBJ,
    }
}

/// Kinds a schema node admits; `None` means dynamic.
fn schema_kinds(s: &Value) -> Option<u8> {
    let o = s.as_object()?;
    match o.get("type") {
        // `string|object` is the ontology's shorthand for a union.
        Some(Value::String(t)) => {
            let mut k = 0;
            for part in t.split('|') {
                k |= name_kinds(part)?;
            }
            return Some(k);
        }
        Some(Value::Array(ts)) => {
            let mut k = 0;
            for t in ts {
                k |= name_kinds(t.as_str()?)?;
            }
            return Some(k);
        }
        Some(_) => return None,
        None => {}
    }
    for key in ["oneOf", "anyOf"] {
        if let Some(Value::Array(bs)) = o.get(key) {
            let mut k = 0;
            for b in bs {
                k |= schema_kinds(b)?;
            }
            return Some(k);
        }
    }
    if let Some(Value::Array(vals)) = o.get("enum") {
        return Some(vals.iter().fold(0, |k, v| k | value_kinds(v)));
    }
    if let Some(c) = o.get("const") {
        return Some(value_kinds(c));
    }
    if o.contains_key("properties") {
        return Some(K_OBJ);
    }
    if o.contains_key("items") {
        return Some(K_ARR);
    }
    None
}

/// Kinds an annotation names; `None` for `any`.
fn type_kinds(t: &Type) -> Option<u8> {
    Some(match t {
        Type::Unknown | Type::Any => return None,
        Type::Null => K_NULL,
        Type::String => K_STR,
        Type::Number => K_NUM,
        Type::Integer => K_INT,
        Type::Boolean => K_BOOL,
        Type::Object | Type::Map(..) => K_OBJ,
        Type::Array(_) => K_ARR,
        Type::Nullable(inner) => K_NULL | type_kinds(inner)?,
        Type::Union(opts) => {
            let mut k = 0;
            for o in opts {
                k |= type_kinds(o)?;
            }
            k
        }
    })
}

/// Type-checks one expression.
pub struct Checker<'s> {
    scope: &'s dyn Scope,
    pub findings: Vec<Finding>,
    /// References proven non-null by an earlier operand of the enclosing
    /// `&&` (`${x} != null && ...`) or `||` (`${x} == null || ...`).
    non_null: Vec<String>,
}

/// `${x} != null` (`negated = false`) or `${x} == null` (`negated = true`):
/// the key of the reference such an operand tests, if it is one.
fn null_test(e: &Expr, negated: bool) -> Option<String> {
    let Expr::Cmp(op, l, r, _) = e else {
        return None;
    };
    let wanted = if negated { CmpOp::Eq } else { CmpOp::Ne };
    if *op != wanted {
        return None;
    }
    match (l.as_ref(), r.as_ref()) {
        (Expr::Ref(x), Expr::Lit(Value::Null, _)) | (Expr::Lit(Value::Null, _), Expr::Ref(x)) => {
            Some(x.key())
        }
        _ => None,
    }
}

impl<'s> Checker<'s> {
    pub fn new(scope: &'s dyn Scope) -> Self {
        Checker {
            scope,
            findings: Vec::new(),
            non_null: Vec::new(),
        }
    }

    fn push(&mut self, code: Code, pos: usize, msg: String) {
        self.findings.push(Finding { code, pos, msg });
    }

    /// Check a condition: the whole expression must be boolean.
    pub fn check_condition(&mut self, e: &Expr) {
        let t = self.ty(e);
        self.require_bool(t, e.pos(), "a condition");
    }

    fn require_bool(&mut self, t: Ty, pos: usize, what: &str) {
        if t.poisoned {
            return;
        }
        if t.dynamic {
            self.push(
                Code::AmbiguousType,
                pos,
                format!("{what} must be boolean but its type is unknown; annotate it ': boolean'"),
            );
        } else if t.kinds & !K_NULL != K_BOOL {
            self.push(
                Code::ExpressionTypeError,
                pos,
                format!(
                    "{what} must be boolean, found {} (there is no truthiness)",
                    kinds_str(t.kinds)
                ),
            );
        } else if t.maybe_null || t.kinds & K_NULL != 0 {
            self.push(
                Code::NullableOperand,
                pos,
                format!(
                    "{what} may be null at runtime, which is an evaluation error (R405); compare explicitly, e.g. '== true'"
                ),
            );
        }
    }

    fn ty(&mut self, e: &Expr) -> Ty {
        match e {
            Expr::Lit(v, _) => Ty {
                literal_null: v.is_null(),
                ..Ty::exact(value_kinds(v))
            },
            Expr::Ref(r) => self.ref_ty(r),
            Expr::Not(x, pos) => {
                let t = self.ty(x);
                self.require_bool(t, *pos, "the operand of '!'");
                Ty::exact(K_BOOL)
            }
            Expr::And(xs) | Expr::Or(xs) => {
                let is_and = matches!(e, Expr::And(_));
                let op = if is_and { "&&" } else { "||" };
                // Later operands only run when earlier ones did not decide
                // the result, so a null test there narrows what follows.
                let mark = self.non_null.len();
                for x in xs {
                    let t = self.ty(x);
                    self.require_bool(t, x.pos(), &format!("an operand of '{op}'"));
                    if let Some(key) = null_test(x, !is_and) {
                        self.non_null.push(key);
                    }
                }
                self.non_null.truncate(mark);
                Ty::exact(K_BOOL)
            }
            Expr::Cmp(op, l, r, pos) => {
                let lt = self.ty(l);
                let rt = self.ty(r);
                if lt.poisoned || rt.poisoned {
                    return Ty::exact(K_BOOL);
                }
                if op.is_ordering() {
                    self.check_ordering(*op, lt, rt, *pos);
                } else if !(lt.literal_null || rt.literal_null || lt.dynamic || rt.dynamic)
                    && lt.kinds & rt.kinds & !K_NULL == 0
                {
                    let always = if *op == CmpOp::Eq { "false" } else { "true" };
                    self.push(
                        Code::ConstantComparison,
                        *pos,
                        format!(
                            "'{}' between {} and {} is always {always} unless both sides are null",
                            op.as_str(),
                            kinds_str(lt.kinds),
                            kinds_str(rt.kinds)
                        ),
                    );
                }
                Ty::exact(K_BOOL)
            }
        }
    }

    fn check_ordering(&mut self, op: CmpOp, l: Ty, r: Ty, pos: usize) {
        let o = op.as_str();
        if l.literal_null || r.literal_null {
            self.push(
                Code::ExpressionTypeError,
                pos,
                format!("'{o}' with null is always an evaluation error; use == or != null"),
            );
            return;
        }
        if l.dynamic || r.dynamic {
            self.push(
                Code::AmbiguousType,
                pos,
                format!(
                    "'{o}' needs a known number, string or boolean type; annotate the reference (e.g. '${{x.y: number}}')"
                ),
            );
            return;
        }
        let (lk, rk) = (l.kinds & !K_NULL, r.kinds & !K_NULL);
        let numbers = lk != 0 && rk != 0 && lk & !K_NUM == 0 && rk & !K_NUM == 0;
        let strings = lk == K_STR && rk == K_STR;
        let booleans = lk == K_BOOL && rk == K_BOOL;
        if !(numbers || strings || booleans) {
            self.push(
                Code::ExpressionTypeError,
                pos,
                format!(
                    "'{o}' needs two numbers, two strings or two booleans, found {} and {}",
                    kinds_str(l.kinds),
                    kinds_str(r.kinds)
                ),
            );
        } else if l.maybe_null || r.maybe_null || (l.kinds | r.kinds) & K_NULL != 0 {
            self.push(
                Code::NullableOperand,
                pos,
                format!(
                    "an operand of '{o}' may be null or absent at runtime, which is an evaluation error (R405); guard it with '!= null &&'"
                ),
            );
        }
    }

    fn ref_ty(&mut self, at: &RefAt) -> Ty {
        let r = &at.r;
        let Some(info) = self.scope.root(&r.root) else {
            self.push(
                Code::MissingProducer,
                at.pos,
                format!(
                    "'{}' is neither an earlier step's store_as nor a workflow input",
                    r.root
                ),
            );
            return Ty::poisoned();
        };
        // A null test on the reference or on any prefix of it narrows: the
        // prefix is present, so only optional segments below it may be null.
        let mut maybe_null = !info.always_present && !self.non_null.contains(&r.root);
        // `None`: nothing is known below this point.
        let mut node = info.schema;
        let mut walked = r.root.clone();
        for seg in &r.path {
            walked.push_str(&seg.to_string());
            let Some(n) = node else {
                // Nothing is known below an untyped node, so every further
                // segment may be absent unless a guard narrowed it.
                maybe_null = !self.non_null.contains(&walked);
                continue;
            };
            let step = match seg {
                Seg::Field(key) => {
                    let required = n
                        .get("required")
                        .and_then(Value::as_array)
                        .is_some_and(|rq| rq.iter().any(|x| x.as_str() == Some(key)));
                    maybe_null |= !required;
                    schema::field(n, key)
                }
                Seg::Index(_) => {
                    maybe_null = true; // the index may be out of range
                    schema::index(n)
                }
                Seg::Slice(..) => {
                    if schema::slice_ok(n) {
                        schema::Step::Node(n)
                    } else {
                        schema::Step::Invalid
                    }
                }
            };
            node = match step {
                schema::Step::Node(child) => Some(child),
                schema::Step::Untyped => None,
                schema::Step::Invalid => {
                    self.push(
                        Code::InvalidBindingPath,
                        at.pos,
                        format!("'{walked}' is not in the producer's schema"),
                    );
                    return Ty::poisoned();
                }
            };
            if self.non_null.contains(&walked) {
                maybe_null = false;
            }
        }
        if self.non_null.contains(&at.key()) {
            maybe_null = false;
        }
        let schema_k = node.and_then(schema_kinds);
        let Some(ann) = &at.ann else {
            return match schema_k {
                Some(k) => Ty {
                    maybe_null,
                    ..Ty::exact(k)
                },
                None => Ty::dynamic(maybe_null),
            };
        };
        // An annotation must agree with the schema exactly as a binding
        // annotation must (§5.4 rule 2).
        if let Some(n) = node {
            let (schema_t, _) = types::schema_type(n);
            if !types::compatible(ann, &schema_t) {
                self.push(
                    Code::TypeMismatch,
                    at.pos,
                    format!("annotation {ann} does not match the schema type {schema_t}"),
                );
            }
        }
        match type_kinds(ann) {
            Some(k) => Ty {
                maybe_null,
                ..Ty::exact(k)
            },
            None => Ty::dynamic(maybe_null),
        }
    }
}
