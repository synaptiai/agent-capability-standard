//! Syntax tree of a condition expression.

use serde_json::Value;

use crate::refs::Ref;
use crate::types::Type;

/// A reference, its parsed type annotation, and the byte offset of its `$`.
#[derive(Debug, Clone, PartialEq)]
pub struct RefAt {
    pub r: Ref,
    pub ann: Option<Type>,
    pub pos: usize,
}

impl RefAt {
    /// The reference as written inside `${...}`, without its annotation:
    /// two operands name the same value exactly when their keys are equal.
    pub fn key(&self) -> String {
        let path: String = self.r.path.iter().map(ToString::to_string).collect();
        format!("{}{path}", self.r.root)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Expr {
    Lit(Value, usize),
    Ref(Box<RefAt>),
    Not(Box<Expr>, usize),
    Cmp(CmpOp, Box<Expr>, Box<Expr>, usize),
    /// n-ary; kept flat so tree depth does not grow with the operand count.
    And(Vec<Expr>),
    Or(Vec<Expr>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    /// Membership: an element of a list, or a key of a map.
    In,
}

impl CmpOp {
    pub fn is_ordering(self) -> bool {
        matches!(self, CmpOp::Lt | CmpOp::Le | CmpOp::Gt | CmpOp::Ge)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            CmpOp::Eq => "==",
            CmpOp::Ne => "!=",
            CmpOp::Lt => "<",
            CmpOp::Le => "<=",
            CmpOp::Gt => ">",
            CmpOp::Ge => ">=",
            CmpOp::In => "in",
        }
    }
}

impl Expr {
    /// Byte offset where the expression starts.
    pub fn pos(&self) -> usize {
        match self {
            Expr::Lit(_, p) | Expr::Not(_, p) | Expr::Cmp(_, _, _, p) => *p,
            Expr::Ref(r) => r.pos,
            Expr::And(v) | Expr::Or(v) => v.first().map_or(0, Expr::pos),
        }
    }

    /// Every reference in the expression, left to right.
    pub fn refs(&self) -> Vec<&RefAt> {
        let mut out = Vec::new();
        let mut stack = vec![self];
        while let Some(e) = stack.pop() {
            match e {
                Expr::Lit(..) => {}
                Expr::Ref(r) => out.push(r.as_ref()),
                Expr::Not(x, _) => stack.push(x),
                Expr::Cmp(_, l, r, _) => {
                    stack.push(r);
                    stack.push(l);
                }
                Expr::And(xs) | Expr::Or(xs) => stack.extend(xs.iter().rev()),
            }
        }
        out
    }
}
