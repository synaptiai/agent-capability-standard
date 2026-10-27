//! Durations (STANDARD v1.1 §5.10.1): `<digits>(ms|s|m|h|d)` or an ISO-8601
//! day-time duration `P[nD][T[nH][nM][n[.n]S]]`.

use std::time::Duration;

/// The longest duration accepted, in nanoseconds: `u64::MAX` milliseconds
/// (about 584 million years), the same bound for both forms.
const MAX_NANOS: u128 = u64::MAX as u128 * 1_000_000;

/// Parse a duration. ISO-8601 years, calendar months and weeks are not
/// accepted (their length varies); fractions are allowed on seconds only.
pub fn parse(text: &str) -> Result<Duration, String> {
    let fail = |why: &str| {
        Err(format!(
            "'{text}' is not a duration ({why}); use e.g. '30s', '5m', '2h', '1d' or 'PT1H30M'"
        ))
    };
    if let Some(iso) = text.strip_prefix('P') {
        return match iso_nanos(iso) {
            None => fail("not an ISO-8601 day-time duration"),
            Some(Some(n)) if n <= MAX_NANOS => Ok(Duration::new(
                (n / 1_000_000_000) as u64,
                (n % 1_000_000_000) as u32,
            )),
            Some(_) => fail("too large"),
        };
    }
    let digits = text.bytes().take_while(u8::is_ascii_digit).count();
    if digits == 0 {
        return fail("no leading number");
    }
    let (number, unit) = text.split_at(digits);
    let Ok(n) = number.parse::<u64>() else {
        return fail("too large");
    };
    let millis_per = match unit {
        "ms" => 1,
        "s" => 1_000,
        "m" => 60_000,
        "h" => 3_600_000,
        "d" => 86_400_000,
        _ => return fail("unit must be ms, s, m, h or d"),
    };
    match n.checked_mul(millis_per) {
        Some(ms) => Ok(Duration::from_millis(ms)),
        None => fail("too large"),
    }
}

/// `[nD][T[nH][nM][n[.n]S]]` after the `P`, with at least one component and,
/// after a `T`, at least one time component. Total nanoseconds: `None` when
/// malformed, `Some(None)` when the total overflows.
fn iso_nanos(s: &str) -> Option<Option<u128>> {
    let (date, time) = match s.split_once('T') {
        Some((d, t)) => (d, Some(t)),
        None => (s, None),
    };
    // Syntax decides validity; arithmetic overflow only makes it too large.
    let mut total: Option<u128> = Some(0);
    let mut add = |n: Option<u128>, scale: u128| {
        total = total
            .zip(n)
            .and_then(|(t, n)| n.checked_mul(scale).and_then(|v| t.checked_add(v)));
    };
    let mut components = 0;
    if !date.is_empty() {
        let days = date.strip_suffix('D')?;
        add(whole(days)?, 86_400 * 1_000_000_000);
        components += 1;
    }
    if let Some(mut t) = time {
        let before = components;
        for (unit, scale) in [('H', 3_600u128), ('M', 60)] {
            if let Some(i) = t.find(unit) {
                add(whole(&t[..i])?, scale * 1_000_000_000);
                t = &t[i + 1..];
                components += 1;
            }
        }
        if let Some(secs) = t.strip_suffix('S') {
            let (int, frac) = match secs.split_once('.') {
                Some((i, f)) => (i, f),
                None => (secs, ""),
            };
            add(whole(int)?, 1_000_000_000);
            if secs.contains('.') {
                if frac.is_empty() || frac.len() > 9 || !frac.bytes().all(|b| b.is_ascii_digit()) {
                    return None;
                }
                add(format!("{frac:0<9}").parse().ok(), 1);
            }
            components += 1;
        } else if !t.is_empty() {
            return None;
        }
        if components == before {
            return None; // `T` with nothing after it
        }
    }
    if components == 0 {
        return None;
    }
    Some(total)
}

/// A run of ASCII digits (at least one): `Some(None)` when it does not fit
/// in a `u128`, which the caller reports as too large.
fn whole(s: &str) -> Option<Option<u128>> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    Some(s.parse().ok())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ms(text: &str) -> u128 {
        parse(text).unwrap().as_millis()
    }

    #[test]
    fn short_forms() {
        assert_eq!(ms("250ms"), 250);
        assert_eq!(ms("30s"), 30_000);
        assert_eq!(ms("5m"), 300_000);
        assert_eq!(ms("2h"), 7_200_000);
        assert_eq!(ms("1d"), 86_400_000);
        assert_eq!(ms("0s"), 0);
    }

    #[test]
    fn iso_forms() {
        assert_eq!(ms("PT1H30M"), 5_400_000);
        assert_eq!(ms("P1D"), 86_400_000);
        assert_eq!(ms("P1DT2H"), 93_600_000);
        assert_eq!(ms("PT0.5S"), 500);
        assert_eq!(ms("PT1M0.25S"), 60_250);
        assert_eq!(parse("PT0.000000001S").unwrap().as_nanos(), 1);
    }

    #[test]
    fn rejects() {
        for bad in [
            "",
            "5",
            "m",
            "5 m",
            "5min",
            "-5s",
            "+5s",
            "1.5h",
            "5M",
            "P",
            "PT",
            "P1W",
            "P1Y",
            "P1M",
            "PT1H2",
            "PTS",
            "PT.5S",
            "PT1.S",
            "PT1.0000000001S",
            "pt1h",
            "P1DT",
            "PT1M1H",
            "18446744073709551616ms",
            "213503982334601d",
        ] {
            assert!(parse(bad).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn overflow_is_too_large_not_wrapped() {
        for big in [
            "PT664613997892457936451903530140172289S",
            "P10000000000000000000000000D",
            "PT99999999999999999999999999999999999999H",
            "PT99999999999999999999999999999999999999M",
            "P213503982334601D",
            "213503982334601d",
            "999999999999999999999999999999999999999999s",
        ] {
            let err = parse(big).unwrap_err();
            assert!(err.contains("too large"), "{big}: {err}");
        }
        // Both forms share one bound: u64::MAX milliseconds, just over
        // 213,503,982,334 days.
        assert!(parse("P213503982334D").is_ok());
        assert!(parse("213503982334d").is_ok());
        assert!(parse("P213503982335D").unwrap_err().contains("too large"));
        assert!(parse("213503982335d").unwrap_err().contains("too large"));
    }
}
