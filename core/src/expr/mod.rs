//! Condition expressions (design-114 §7): `condition`, `gates[].when` and
//! `failure_modes[].when`.
//!
//! The grammar is ACS-owned and CEL-compatible: with every `${...}` replaced
//! by an opaque variable, each valid expression is a valid CEL expression
//! with the same result wherever CEL returns a value. Evaluation is bounded
//! by construction — no functions, iteration or arithmetic — and by the
//! length and depth limits below.

pub mod ast;
pub mod check;
pub mod eval;
mod lexer;
mod parser;

pub use parser::parse;

/// Maximum expression length in UTF-8 bytes.
pub const MAX_LEN: usize = 4096;
/// Maximum nesting of `(`, `!`, `[` and `{`.
pub const MAX_DEPTH: usize = 32;

/// What a [`SyntaxError`] is about, which decides its code: a malformed
/// expression is V108, a malformed `${...}` reference B201 (as in a
/// binding), and an annotation that names no type B205.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyntaxKind {
    Expression,
    Reference,
    Annotation,
}

impl SyntaxKind {
    /// The diagnostic code a validator reports for this kind of error.
    pub fn code(self) -> crate::diag::Code {
        use crate::diag::Code;
        match self {
            SyntaxKind::Expression => Code::InvalidExpression,
            SyntaxKind::Reference => Code::InvalidBindingPath,
            SyntaxKind::Annotation => Code::InvalidAnnotation,
        }
    }
}

/// A syntax or limit error, at a byte offset.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SyntaxError {
    pub pos: usize,
    pub msg: String,
    pub kind: SyntaxKind,
}
