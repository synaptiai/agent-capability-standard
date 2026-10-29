//! Hostile inputs: the expression language must reject or evaluate them in
//! bounded time and memory, without panicking or overflowing the stack.

use std::time::Instant;

use acs_core::expr::eval::{deep_eq, eval_condition, eval_value};
use acs_core::expr::{MAX_DEPTH, MAX_LEN, parse};
use serde_json::{Map, Value, json};

fn rejected(s: &str) -> bool {
    parse(s).is_err()
}

#[test]
fn deep_nesting_is_rejected_without_stack_overflow() {
    for n in [MAX_DEPTH + 1, 1_000, 100_000] {
        for (o, c) in [("(", ")"), ("[", "]"), ("{\"a\":", "}")] {
            assert!(rejected(&format!("{}true{}", o.repeat(n), c.repeat(n))));
        }
        assert!(rejected(&format!("{}true", "!".repeat(n))));
        assert!(rejected(&format!(
            "${{a: {}string{}}} == 1",
            "array<".repeat(n),
            ">".repeat(n)
        )));
    }
    assert!(!rejected(&format!(
        "${{a: {}string{}}} == []",
        "array<".repeat(31),
        ">".repeat(31)
    )));
    assert!(!rejected(&format!(
        "{}true{}",
        "(".repeat(MAX_DEPTH),
        ")".repeat(MAX_DEPTH)
    )));
}

#[test]
fn huge_input_is_rejected_before_lexing() {
    let s = format!("${{a}} == \"{}\"", "x".repeat(10_000_000));
    let t = Instant::now();
    assert!(rejected(&s));
    assert!(t.elapsed().as_millis() < 500);
    // A maximum-length flat chain evaluates without deep recursion.
    let chain = vec!["true"; 600].join("&&");
    assert!(chain.len() <= MAX_LEN);
    assert_eq!(
        eval_condition(&parse(&chain).unwrap(), &Map::new()),
        Ok(true)
    );
}

#[test]
fn non_ascii_outside_strings_is_rejected() {
    for s in [
        "${a}\u{00A0}== 1",
        "${a} \u{FF1D}\u{FF1D} 1",
        "${a}\u{200B} == 1",
        "${v\u{0435}rify_out} == 1",
        "${a} == \u{201C}x\u{201D}",
        "\u{FEFF}${a} == 1",
        "${a} == 1\u{2028}",
        "${a} == NaN",
        "${a} == Infinity",
        "${a} == -Infinity",
    ] {
        assert!(rejected(s), "{s:?} should be rejected");
    }
    // Inside a string literal any scalar value is data.
    assert!(!rejected("${a} == \"abc\u{202E}def\""));
}

#[test]
fn numeric_edges() {
    assert!(rejected(&format!("${{a}} == {}", "9".repeat(400))));
    let tiny = format!("0.{}1 == 0", "0".repeat(400));
    assert_eq!(
        eval_condition(&parse(&tiny).unwrap(), &Map::new()),
        Ok(true)
    );
    for (s, want) in [
        ("-0 == 0", true),
        ("1.7976931348623157e308 > 1e308", true),
        ("5e-324 > 0", true),
        ("2.4e-324 == 0", true),
    ] {
        assert_eq!(
            eval_condition(&parse(s).unwrap(), &Map::new()),
            Ok(want),
            "{s}"
        );
    }
    assert!(rejected("1.7976931348623159e308 > 0"), "rounds to infinity");
    assert!(rejected("9007199254740993 == 0"), "integer beyond 2^53");
}

fn nested(n: usize) -> Value {
    let mut v = json!(1);
    for _ in 0..n {
        v = Value::Array(vec![v]);
    }
    v
}

#[test]
fn deep_runtime_values_do_not_overflow_equality() {
    // serde_json's Drop for Value recurses, so build and drop on a big stack;
    // the equality itself is iterative.
    std::thread::Builder::new()
        .stack_size(512 << 20)
        .spawn(|| {
            let (a, b) = (nested(200_000), nested(200_000));
            assert!(deep_eq(&a, &b));
            let mut m = Map::new();
            m.insert("a".into(), a);
            m.insert("b".into(), b);
            let e = parse("${a} == ${b}").unwrap();
            assert_eq!(eval_condition(&e, &m), Ok(true));
        })
        .unwrap()
        .join()
        .unwrap();
}

#[test]
fn fuzz_no_panics() {
    let atoms = [
        "${a}",
        "${a.b}",
        "${a[0]}",
        "${a[1:]}",
        "${a: number}",
        "null",
        "true",
        "false",
        "0",
        "-1.5e3",
        "\"s\"",
        "\"\\u00e9\"",
        "[]",
        "{}",
        "[1,\"x\"]",
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "&&",
        "||",
        "!",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        ",",
        ":",
        " ",
        "$",
        "\"",
        "\\",
        "-",
        ".",
        "é",
    ];
    let mut x: u64 = 88_172_645_463_325_252;
    let mut rnd = || {
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        x
    };
    let mut b = Map::new();
    b.insert("a".into(), json!({"b": [1, "x", null], "0": true}));
    let (mut ok, mut runtime_errors) = (0, 0);
    for _ in 0..200_000 {
        let n = 1 + rnd() % 12;
        let sep = if rnd() % 2 == 0 { " " } else { "" };
        let s = (0..n)
            .map(|_| atoms[(rnd() % atoms.len() as u64) as usize])
            .collect::<Vec<_>>()
            .join(sep);
        if let Ok(e) = parse(&s) {
            match eval_condition(&e, &b) {
                Ok(_) => ok += 1,
                Err(_) => runtime_errors += 1,
            }
        }
        let bytes: Vec<u8> = (0..(rnd() % 20)).map(|_| (rnd() % 128) as u8).collect();
        if let Ok(s) = String::from_utf8(bytes) {
            let _ = parse(&s).map(|e| eval_value(&e, &b));
        }
    }
    assert!(
        ok > 1000 && runtime_errors > 1000,
        "ok={ok} errors={runtime_errors}"
    );
}
