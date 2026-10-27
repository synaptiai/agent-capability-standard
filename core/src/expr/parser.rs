//! Recursive-descent parser (design-114 §7).
//!
//! ```text
//! or_expr  = and_expr { "||" and_expr }
//! and_expr = cmp_expr { "&&" cmp_expr }
//! cmp_expr = unary [ cmp_op unary ]          (non-associative; cmp_op includes `in`)
//! unary    = "!" unary | primary
//! primary  = reference | literal | "(" or_expr ")"
//! ```

use serde_json::{Map, Number, Value};

use super::ast::{CmpOp, Expr};
use super::lexer::{Lexer, Tok};
use super::{MAX_DEPTH, SyntaxError};

/// Parse a condition expression.
pub fn parse(src: &str) -> Result<Expr, SyntaxError> {
    let toks = Lexer::new(src).tokenize()?;
    let mut p = Parser {
        toks,
        i: 0,
        depth: 0,
    };
    let e = p.or_expr()?;
    match p.peek() {
        Tok::Eof => Ok(e),
        _ => Err(p.err("unexpected token after end of expression")),
    }
}

struct Parser {
    toks: Vec<(Tok, usize)>,
    i: usize,
    depth: usize,
}

fn cmp_op(t: &Tok) -> Option<CmpOp> {
    Some(match t {
        Tok::Eq => CmpOp::Eq,
        Tok::Ne => CmpOp::Ne,
        Tok::Lt => CmpOp::Lt,
        Tok::Le => CmpOp::Le,
        Tok::Gt => CmpOp::Gt,
        Tok::Ge => CmpOp::Ge,
        Tok::In => CmpOp::In,
        _ => return None,
    })
}

impl Parser {
    fn peek(&self) -> &Tok {
        &self.toks[self.i].0
    }

    fn pos(&self) -> usize {
        self.toks[self.i].1
    }

    /// Take the current token, moving it out (it is never read again), and
    /// advance. The final `Eof` is never taken.
    fn bump(&mut self) -> Tok {
        if self.i + 1 < self.toks.len() {
            let t = std::mem::replace(&mut self.toks[self.i].0, Tok::Eof);
            self.i += 1;
            t
        } else {
            Tok::Eof
        }
    }

    fn err(&self, msg: impl Into<String>) -> SyntaxError {
        SyntaxError {
            pos: self.pos(),
            msg: msg.into(),
            annotation: false,
        }
    }

    fn enter(&mut self) -> Result<(), SyntaxError> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            return Err(self.err(format!("nesting deeper than {MAX_DEPTH} levels")));
        }
        Ok(())
    }

    fn expect(&mut self, t: Tok, what: &str) -> Result<(), SyntaxError> {
        if *self.peek() == t {
            self.bump();
            Ok(())
        } else {
            Err(self.err(format!("expected {what}")))
        }
    }

    fn or_expr(&mut self) -> Result<Expr, SyntaxError> {
        let mut v = vec![self.and_expr()?];
        while *self.peek() == Tok::Or {
            self.bump();
            v.push(self.and_expr()?);
        }
        Ok(if v.len() == 1 {
            v.remove(0)
        } else {
            Expr::Or(v)
        })
    }

    fn and_expr(&mut self) -> Result<Expr, SyntaxError> {
        let mut v = vec![self.cmp_expr()?];
        while *self.peek() == Tok::And {
            self.bump();
            v.push(self.cmp_expr()?);
        }
        Ok(if v.len() == 1 {
            v.remove(0)
        } else {
            Expr::And(v)
        })
    }

    fn cmp_expr(&mut self) -> Result<Expr, SyntaxError> {
        let l = self.unary()?;
        if let Some(op) = cmp_op(self.peek()) {
            let pos = self.pos();
            self.bump();
            let r = self.unary()?;
            if cmp_op(self.peek()).is_some() {
                return Err(self.err("comparison operators are non-associative; add parentheses"));
            }
            return Ok(Expr::Cmp(op, Box::new(l), Box::new(r), pos));
        }
        Ok(l)
    }

    fn unary(&mut self) -> Result<Expr, SyntaxError> {
        if *self.peek() == Tok::Not {
            let pos = self.pos();
            self.bump();
            self.enter()?;
            let e = self.unary()?;
            self.depth -= 1;
            return Ok(Expr::Not(Box::new(e), pos));
        }
        self.primary()
    }

    fn primary(&mut self) -> Result<Expr, SyntaxError> {
        let pos = self.pos();
        match self.peek() {
            Tok::Ref(_) => match self.bump() {
                Tok::Ref(r) => Ok(Expr::Ref(r)),
                _ => Err(self.err("expected a reference")),
            },
            Tok::LParen => {
                self.bump();
                self.enter()?;
                let e = self.or_expr()?;
                self.depth -= 1;
                self.expect(Tok::RParen, "')'")?;
                Ok(e)
            }
            Tok::Eof => Err(self.err("unexpected end of expression")),
            _ => Ok(Expr::Lit(self.literal()?, pos)),
        }
    }

    /// `literal = null | true | false | number | string | list | map`; list
    /// and map members are literals, never references.
    fn literal(&mut self) -> Result<Value, SyntaxError> {
        if *self.peek() == Tok::Eof {
            return Err(self.err("unexpected end of expression"));
        }
        let at = self.i;
        Ok(match self.bump() {
            Tok::Null => Value::Null,
            Tok::True => Value::Bool(true),
            Tok::False => Value::Bool(false),
            Tok::Num(f) => match Number::from_f64(f) {
                Some(n) => Value::Number(n),
                None => return Err(self.err("non-finite number")),
            },
            Tok::Str(s) => Value::String(s),
            Tok::LBrack => {
                self.enter()?;
                let mut v = Vec::new();
                if *self.peek() != Tok::RBrack {
                    loop {
                        v.push(self.literal()?);
                        if *self.peek() == Tok::Comma {
                            self.bump();
                            continue;
                        }
                        break;
                    }
                }
                self.expect(Tok::RBrack, "',' or ']' (list members must be literals)")?;
                self.depth -= 1;
                Value::Array(v)
            }
            Tok::LBrace => {
                self.enter()?;
                let mut m = Map::new();
                if *self.peek() != Tok::RBrace {
                    loop {
                        if !matches!(self.peek(), Tok::Str(_)) {
                            return Err(self.err("map keys must be double-quoted strings"));
                        }
                        let Tok::Str(k) = self.bump() else {
                            return Err(self.err("map keys must be double-quoted strings"));
                        };
                        self.expect(Tok::Colon, "':'")?;
                        let val = self.literal()?;
                        if m.contains_key(&k) {
                            return Err(self.err(format!("duplicate map key {k:?}")));
                        }
                        m.insert(k, val);
                        if *self.peek() == Tok::Comma {
                            self.bump();
                            continue;
                        }
                        break;
                    }
                }
                self.expect(Tok::RBrace, "',' or '}'")?;
                self.depth -= 1;
                Value::Object(m)
            }
            Tok::Ref(_) => {
                self.i = at;
                return Err(self.err("references are not allowed inside list or map literals"));
            }
            _ => {
                self.i = at;
                return Err(self.err("expected an operand (reference, literal or '(')"));
            }
        })
    }
}
