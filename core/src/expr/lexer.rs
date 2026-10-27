//! Byte-oriented lexer. Outside string literals only ASCII is accepted, so
//! Unicode whitespace, full-width operators and smart quotes are errors.

use super::ast::RefAt;
use super::{MAX_LEN, SyntaxError};
use crate::{refs, types};

#[derive(Debug, Clone, PartialEq)]
pub enum Tok {
    Ref(Box<RefAt>),
    Null,
    True,
    False,
    Num(f64),
    Str(String),
    LParen,
    RParen,
    LBrack,
    RBrack,
    LBrace,
    RBrace,
    Comma,
    Colon,
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
    In,
    And,
    Or,
    Not,
    Eof,
}

pub struct Lexer<'a> {
    src: &'a str,
    s: &'a [u8],
    i: usize,
}

fn is_ws(b: u8) -> bool {
    matches!(b, b' ' | b'\t' | b'\n' | b'\r')
}

fn is_word(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

impl<'a> Lexer<'a> {
    pub fn new(src: &'a str) -> Self {
        Lexer {
            src,
            s: src.as_bytes(),
            i: 0,
        }
    }

    fn err<T>(&self, pos: usize, msg: impl Into<String>) -> Result<T, SyntaxError> {
        Err(SyntaxError {
            pos,
            msg: msg.into(),
            annotation: false,
        })
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.i).copied()
    }

    /// Consume `n` bytes and return `t`.
    fn take(&mut self, n: usize, t: Tok) -> Tok {
        self.i += n;
        t
    }

    fn skip_ws(&mut self) {
        while self.peek().is_some_and(is_ws) {
            self.i += 1;
        }
    }

    pub fn tokenize(mut self) -> Result<Vec<(Tok, usize)>, SyntaxError> {
        if self.src.len() > MAX_LEN {
            return self.err(MAX_LEN, format!("expression longer than {MAX_LEN} bytes"));
        }
        let mut out = Vec::new();
        loop {
            self.skip_ws();
            let start = self.i;
            let Some(b) = self.peek() else {
                out.push((Tok::Eof, start));
                return Ok(out);
            };
            let two = self.s.get(self.i + 1).copied();
            let tok = match (b, two) {
                (b'$', _) => self.lex_ref()?,
                (b'"', _) => Tok::Str(self.lex_string()?),
                (b'-' | b'0'..=b'9', _) => self.lex_number()?,
                (b'=', Some(b'=')) => self.take(2, Tok::Eq),
                (b'!', Some(b'=')) => self.take(2, Tok::Ne),
                (b'<', Some(b'=')) => self.take(2, Tok::Le),
                (b'>', Some(b'=')) => self.take(2, Tok::Ge),
                (b'&', Some(b'&')) => self.take(2, Tok::And),
                (b'|', Some(b'|')) => self.take(2, Tok::Or),
                (b'<', _) => self.take(1, Tok::Lt),
                (b'>', _) => self.take(1, Tok::Gt),
                (b'!', _) => self.take(1, Tok::Not),
                (b'(', _) => self.take(1, Tok::LParen),
                (b')', _) => self.take(1, Tok::RParen),
                (b'[', _) => self.take(1, Tok::LBrack),
                (b']', _) => self.take(1, Tok::RBrack),
                (b'{', _) => self.take(1, Tok::LBrace),
                (b'}', _) => self.take(1, Tok::RBrace),
                (b',', _) => self.take(1, Tok::Comma),
                (b':', _) => self.take(1, Tok::Colon),
                (b'=', _) => return self.err(start, "unexpected '='; equality is '=='"),
                (b'&', _) => return self.err(start, "unexpected '&'; logical and is '&&'"),
                (b'|', _) => return self.err(start, "unexpected '|'; logical or is '||'"),
                (b'\'', _) => {
                    return self.err(start, "strings use double quotes, not single quotes");
                }
                (b, _) if b.is_ascii_alphabetic() || b == b'_' => {
                    while self.peek().is_some_and(is_word) {
                        self.i += 1;
                    }
                    match &self.src[start..self.i] {
                        "null" => Tok::Null,
                        "true" => Tok::True,
                        "false" => Tok::False,
                        "in" => Tok::In,
                        w => {
                            let hint = match w {
                                "True" | "TRUE" => " (literals are lower-case: true)",
                                "False" | "FALSE" => " (literals are lower-case: false)",
                                "None" | "nil" | "NULL" | "Null" | "undefined" => " (use null)",
                                "and" | "AND" => " (use &&)",
                                "or" | "OR" => " (use ||)",
                                "not" | "NOT" => " (use !; for 'not in', write !(x in y))",
                                _ => {
                                    " (bare identifiers are not allowed; reference values with ${...} and quote strings)"
                                }
                            };
                            return self.err(start, format!("unknown identifier '{w}'{hint}"));
                        }
                    }
                }
                _ => {
                    let ch = self.src[start..].chars().next().unwrap_or('\u{fffd}');
                    return self.err(
                        start,
                        format!("unexpected character {ch:?} (U+{:04X})", ch as u32),
                    );
                }
            };
            out.push((tok, start));
        }
    }

    /// RFC 8259 number grammar; the value is the nearest binary64 and must be
    /// finite. Integer literals must also lie within ±2^53.
    fn lex_number(&mut self) -> Result<Tok, SyntaxError> {
        let start = self.i;
        if self.peek() == Some(b'-') {
            self.i += 1;
        }
        match self.peek() {
            Some(b'0') => {
                self.i += 1;
                if self.peek().is_some_and(|b| b.is_ascii_digit()) {
                    return self.err(start, "leading zeros are not allowed in numbers");
                }
            }
            Some(b'1'..=b'9') => {
                while self.peek().is_some_and(|b| b.is_ascii_digit()) {
                    self.i += 1;
                }
            }
            _ => {
                return self.err(
                    start,
                    "'-' must be followed by a digit (there is no unary minus operator)",
                );
            }
        }
        let mut integral = true;
        if self.peek() == Some(b'.') {
            integral = false;
            self.i += 1;
            if !self.peek().is_some_and(|b| b.is_ascii_digit()) {
                return self.err(start, "a digit is required after the decimal point");
            }
            while self.peek().is_some_and(|b| b.is_ascii_digit()) {
                self.i += 1;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            integral = false;
            self.i += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.i += 1;
            }
            if !self.peek().is_some_and(|b| b.is_ascii_digit()) {
                return self.err(start, "a digit is required in the exponent");
            }
            while self.peek().is_some_and(|b| b.is_ascii_digit()) {
                self.i += 1;
            }
        }
        if self.peek().is_some_and(|b| is_word(b) || b == b'.') {
            return self.err(self.i, "invalid character after number");
        }
        let text = &self.src[start..self.i];
        // `str::parse::<f64>` is correctly rounded (round half to even).
        let v: f64 = text.parse().map_err(|_| SyntaxError {
            pos: start,
            msg: format!("bad number '{text}'"),
            annotation: false,
        })?;
        if !v.is_finite() {
            return self.err(
                start,
                format!("number {text} is outside the binary64 range"),
            );
        }
        // Judge integer literals by their digits: parsing has already rounded
        // 2^53 + 1 down to 2^53.
        let digits = text.trim_start_matches('-');
        if integral && !digits.parse::<u64>().is_ok_and(|n| n <= 1u64 << 53) {
            return self.err(
                start,
                format!("integer literal {text} is beyond ±2^53 and cannot be compared exactly"),
            );
        }
        Ok(Tok::Num(v))
    }

    /// Double-quoted string with escapes `\" \\ \b \f \n \r \t \uXXXX`
    /// (no surrogate code points). Raw control characters are not allowed.
    fn lex_string(&mut self) -> Result<String, SyntaxError> {
        let start = self.i;
        self.i += 1; // opening quote
        let mut out = String::new();
        loop {
            let Some(b) = self.peek() else {
                return self.err(start, "unterminated string literal");
            };
            match b {
                b'"' => {
                    self.i += 1;
                    return Ok(out);
                }
                b'\\' => {
                    let esc = self.i;
                    self.i += 1;
                    let Some(e) = self.peek() else {
                        return self.err(start, "unterminated string literal");
                    };
                    self.i += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            // CEL forbids surrogate code points in escapes; an
                            // astral character is written as itself.
                            let cp = self.hex4(esc)?;
                            match char::from_u32(cp) {
                                Some(c) => out.push(c),
                                None => {
                                    return self.err(
                                        esc,
                                        "\\u escape names a surrogate code point; write the character itself",
                                    );
                                }
                            }
                        }
                        _ => return self.err(esc, format!("invalid escape \\{}", e as char)),
                    }
                }
                0x00..=0x1F => {
                    return self.err(
                        self.i,
                        "raw control character in string literal; use an escape",
                    );
                }
                _ => {
                    let ch = self.src[self.i..].chars().next().unwrap_or('\u{fffd}');
                    out.push(ch);
                    self.i += ch.len_utf8();
                }
            }
        }
    }

    fn hex4(&mut self, pos: usize) -> Result<u32, SyntaxError> {
        let h = self.s.get(self.i..self.i + 4).ok_or(SyntaxError {
            pos,
            msg: "truncated \\u escape".into(),
            annotation: false,
        })?;
        let mut v = 0u32;
        for &c in h {
            let d = (c as char).to_digit(16).ok_or(SyntaxError {
                pos,
                msg: "invalid hex digit in \\u escape".into(),
                annotation: false,
            })?;
            v = v * 16 + d;
        }
        self.i += 4;
        Ok(v)
    }

    /// `${...}`: the body uses the same grammar as binding references.
    fn lex_ref(&mut self) -> Result<Tok, SyntaxError> {
        let pos = self.i;
        if self.s.get(self.i + 1) != Some(&b'{') {
            return self.err(pos, "'$' must start a reference '${...}'");
        }
        let body_start = self.i + 2;
        let Some(close) = self.src[body_start..].find('}') else {
            return self.err(pos, "unterminated reference: expected '}'");
        };
        let body = &self.src[body_start..body_start + close];
        let r = refs::parse_ref(body).map_err(|msg| SyntaxError {
            pos,
            msg,
            annotation: false,
        })?;
        let ann = match &r.annotation {
            None => None,
            Some(text) => Some(types::parse_annotation(text).map_err(|msg| SyntaxError {
                pos,
                msg,
                annotation: true,
            })?),
        };
        self.i = body_start + close + 1;
        Ok(Tok::Ref(Box::new(RefAt { r, ann, pos })))
    }
}
