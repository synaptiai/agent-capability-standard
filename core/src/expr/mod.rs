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

/// A syntax or limit error, at a byte offset. A validator reports it as V108,
/// or as B205 when only a reference's type annotation is malformed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SyntaxError {
    pub pos: usize,
    pub msg: String,
    pub annotation: bool,
}
