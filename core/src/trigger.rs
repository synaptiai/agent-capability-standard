//! Trigger evaluation helpers (STANDARD v1.2 §5.10.2): the fire times of a
//! schedule. The host evaluates triggers; the executor never reads them.
//! This is the one fire-time function every binding of the core shares.

use chrono::{
    DateTime, Datelike, Duration, LocalResult, NaiveDate, NaiveDateTime, Offset, TimeZone,
};
use chrono_tz::Tz;
use serde_json::Value;

use crate::cron::Cron;
use crate::duration;
use crate::exec::MAX_TIME;

/// The longest a search for a `cron` fire time runs, in local days: a
/// leap-day schedule across a non-leap century year (2096 to 2104) needs
/// 2922.
const MAX_DAYS: i64 = 3003;

/// The first fire time strictly after `after_ms`, or None when there is
/// none up to [`MAX_TIME`]. `schedule` is a validated `triggers[].schedule`
/// mapping (`cron` or `every`, optional `timezone`).
///
/// - `every`: the multiples of its interval, counted in whole milliseconds
///   (the interval rounded up) from the Unix epoch; `timezone` does not
///   change them.
/// - `cron`: each matching local minute of `timezone` (UTC when absent), at
///   second 0. A local time maps to an instant as RFC 5545 §3.3.5 says: a
///   time that occurs twice is its first occurrence; one that does not occur
///   is read with the UTC offset in effect before the change. Local times
///   that map to one instant fire once.
pub fn next_fire(schedule: &Value, after_ms: u64) -> Result<Option<u64>, String> {
    let Some(s) = schedule.as_object() else {
        return Err("a schedule is a mapping with 'cron' or 'every'".into());
    };
    let text = |key: &str| -> Result<Option<&str>, String> {
        match s.get(key) {
            None | Some(Value::Null) => Ok(None),
            Some(Value::String(t)) => Ok(Some(t)),
            Some(_) => Err(format!("schedule.{key} must be a string")),
        }
    };
    let (cron, every, timezone) = (text("cron")?, text("every")?, text("timezone")?);
    let tz: Tz = timezone
        .unwrap_or("UTC")
        .parse()
        .map_err(|_| format!("'{}' is not an IANA time zone name", timezone.unwrap_or("")))?;
    match (cron, every) {
        (Some(_), Some(_)) => Err("a schedule has 'cron' or 'every', not both".into()),
        (None, None) => Err("a schedule needs 'cron' or 'every'".into()),
        (None, Some(every)) => {
            let nanos = duration::parse(every)?.as_nanos();
            let ms = u64::try_from(nanos.div_ceil(1_000_000)).unwrap_or(u64::MAX);
            if ms == 0 {
                return Err("every must be longer than zero".into());
            }
            if after_ms >= MAX_TIME {
                return Ok(None);
            }
            Ok((after_ms / ms)
                .checked_add(1)
                .and_then(|n| n.checked_mul(ms))
                .filter(|t| *t <= MAX_TIME))
        }
        (Some(expr), None) => {
            let cron = Cron::parse(expr)?;
            if after_ms >= MAX_TIME {
                return Ok(None);
            }
            Ok(next_cron(&cron, tz, after_ms))
        }
    }
}

/// The first local time of `cron` in `tz` whose instant is after `after_ms`.
fn next_cron(cron: &Cron, tz: Tz, after_ms: u64) -> Option<u64> {
    let after = i64::try_from(after_ms).ok()?;
    let local_today = DateTime::from_timestamp_millis(after)?
        .with_timezone(&tz)
        .date_naive();
    // A local time up to a day before `after`'s local date can still map
    // after it (a whole skipped day, Pacific/Apia 2011): start two days back.
    let start = local_today - Duration::days(2);
    let hours: Vec<u32> = cron.hours().collect();
    let minutes: Vec<u32> = cron.minutes().collect();
    let mut best: Option<i64> = None;
    for offset in 0..MAX_DAYS {
        let day = start + Duration::days(offset);
        // No local time of this day or later maps before its local midnight
        // less a day (offsets stay within ±14 hours): the search is over.
        if let Some(b) = best
            && midnight_as_utc(day) - Duration::hours(24).num_milliseconds() > b
        {
            break;
        }
        let dow = day.weekday().num_days_from_sunday();
        if !cron.matches_day(day.day(), day.month(), dow) {
            continue;
        }
        for &h in &hours {
            for &m in &minutes {
                let Some(local) = day.and_hms_opt(h, m, 0) else {
                    continue;
                };
                let t = instant(tz, local);
                if t > after && best.is_none_or(|b| t < b) {
                    best = Some(t);
                }
            }
        }
    }
    best.and_then(|b| u64::try_from(b).ok())
        .filter(|t| *t <= MAX_TIME)
}

fn midnight_as_utc(day: NaiveDate) -> i64 {
    day.and_hms_opt(0, 0, 0)
        .map_or(i64::MIN, |t| t.and_utc().timestamp_millis())
}

/// The instant of local time `local` in `tz`, by RFC 5545 §3.3.5: the first
/// of two occurrences; for a time a clock change skips, the local time read
/// with the offset in effect before the change.
fn instant(tz: Tz, local: NaiveDateTime) -> i64 {
    match tz.from_local_datetime(&local) {
        LocalResult::Single(t) => t.timestamp_millis(),
        LocalResult::Ambiguous(a, b) => a.timestamp_millis().min(b.timestamp_millis()),
        LocalResult::None => {
            // The latest local minute before the gap that exists: its offset
            // is the one in effect before the change.
            let mut p = local;
            for _ in 0..(48 * 60) {
                p -= Duration::minutes(1);
                let offset = match tz.from_local_datetime(&p) {
                    LocalResult::Single(t) => Some(t.offset().fix()),
                    LocalResult::Ambiguous(a, b) => {
                        let later = if a.timestamp_millis() >= b.timestamp_millis() {
                            a
                        } else {
                            b
                        };
                        Some(later.offset().fix())
                    }
                    LocalResult::None => None,
                };
                if let Some(o) = offset {
                    let seconds = i64::from(o.local_minus_utc());
                    return (local - Duration::seconds(seconds))
                        .and_utc()
                        .timestamp_millis();
                }
            }
            // No zone skips two days; read the time as UTC.
            local.and_utc().timestamp_millis()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ms(rfc3339: &str) -> u64 {
        u64::try_from(
            DateTime::parse_from_rfc3339(rfc3339)
                .unwrap()
                .timestamp_millis(),
        )
        .unwrap()
    }

    /// The fire times after `after`, as RFC 3339 UTC instants.
    fn fires(schedule: Value, after: u64, n: usize) -> Vec<u64> {
        let mut out = Vec::new();
        let mut t = after;
        while out.len() < n {
            match next_fire(&schedule, t).unwrap() {
                Some(next) => {
                    out.push(next);
                    t = next;
                }
                None => break,
            }
        }
        out
    }

    fn cron(expr: &str, tz: &str) -> Value {
        json!({"cron": expr, "timezone": tz})
    }

    #[test]
    fn utc_weekdays() {
        assert_eq!(
            fires(
                cron("0 6 * * MON-FRI", "UTC"),
                ms("2026-11-13T07:00:00Z"),
                2
            ),
            [ms("2026-11-16T06:00:00Z"), ms("2026-11-17T06:00:00Z")]
        );
    }

    #[test]
    fn strictly_after() {
        assert_eq!(
            fires(cron("0 6 * * *", "UTC"), ms("2026-11-16T06:00:00Z"), 1),
            [ms("2026-11-17T06:00:00Z")]
        );
    }

    #[test]
    fn every_is_anchored_at_the_epoch() {
        assert_eq!(
            fires(json!({"every": "15m"}), 1000, 2),
            [900_000, 1_800_000]
        );
        assert_eq!(fires(json!({"every": "7m"}), 0, 2), [420_000, 840_000]);
        // Sub-millisecond intervals round up to a whole millisecond.
        assert_eq!(fires(json!({"every": "PT0.0005S"}), 5, 2), [6, 7]);
        // The time zone does not change an `every` schedule.
        assert_eq!(
            fires(
                json!({"every": "1d", "timezone": "America/New_York"}),
                ms("2026-11-15T12:00:00Z"),
                1
            ),
            [ms("2026-11-16T00:00:00Z")]
        );
    }

    #[test]
    fn step_list_range_and_names() {
        assert_eq!(
            fires(
                cron("5/20 0 1 jan,Jul *", "UTC"),
                ms("2026-01-01T00:30:00Z"),
                2
            ),
            [ms("2026-01-01T00:45:00Z"), ms("2026-07-01T00:05:00Z")]
        );
    }

    #[test]
    fn matches_day_vixie() {
        assert_eq!(
            fires(cron("0 0 13 * FRI", "UTC"), ms("2026-11-15T00:00:00Z"), 3),
            [
                ms("2026-11-20T00:00:00Z"),
                ms("2026-11-27T00:00:00Z"),
                ms("2026-12-04T00:00:00Z")
            ]
        );
    }

    #[test]
    fn leap_day() {
        assert_eq!(
            fires(cron("0 0 29 2 *", "UTC"), ms("2026-03-01T00:00:00Z"), 1),
            [ms("2028-02-29T00:00:00Z")]
        );
        // Across a century year that is not a leap year.
        assert_eq!(
            fires(cron("0 0 29 2 *", "UTC"), ms("2096-03-01T00:00:00Z"), 1),
            [ms("2104-02-29T00:00:00Z")]
        );
    }

    #[test]
    fn instant_gap_uses_offset_before() {
        // 02:30 does not occur in New York on 8 March 2026: -05:00 applies.
        assert_eq!(
            fires(
                cron("30 2 * * *", "America/New_York"),
                ms("2026-03-07T12:00:00Z"),
                2
            ),
            [ms("2026-03-08T07:30:00Z"), ms("2026-03-09T06:30:00Z")]
        );
        // Gap times that collide with later ones fire once each.
        assert_eq!(
            fires(
                cron("*/30 2-3 * * *", "America/New_York"),
                ms("2026-03-08T06:00:00Z"),
                3
            ),
            [
                ms("2026-03-08T07:00:00Z"),
                ms("2026-03-08T07:30:00Z"),
                ms("2026-03-09T06:00:00Z")
            ]
        );
    }

    #[test]
    fn instant_fold_takes_first() {
        assert_eq!(
            fires(
                cron("30 1 * * *", "America/New_York"),
                ms("2026-10-31T12:00:00Z"),
                2
            ),
            [ms("2026-11-01T05:30:00Z"), ms("2026-11-02T06:30:00Z")]
        );
    }

    #[test]
    fn whole_skipped_day_and_half_hour_changes() {
        assert_eq!(
            fires(
                cron("0 12 * * *", "Pacific/Apia"),
                ms("2011-12-28T00:00:00Z"),
                4
            ),
            [
                ms("2011-12-28T22:00:00Z"),
                ms("2011-12-29T22:00:00Z"),
                ms("2011-12-30T22:00:00Z"),
                ms("2011-12-31T22:00:00Z")
            ]
        );
        assert_eq!(
            fires(
                cron("15 2 * * *", "Australia/Lord_Howe"),
                ms("2026-10-03T00:00:00Z"),
                2
            ),
            [ms("2026-10-03T15:45:00Z"), ms("2026-10-04T15:15:00Z")]
        );
        assert_eq!(
            fires(
                cron("0 9 * * *", "Asia/Kolkata"),
                ms("2026-11-15T00:00:00Z"),
                1
            ),
            [ms("2026-11-15T03:30:00Z")]
        );
    }

    #[test]
    fn none_after_the_maximum_time() {
        assert_eq!(
            next_fire(&cron("0 0 1 1 *", "UTC"), MAX_TIME).unwrap(),
            None
        );
        assert_eq!(next_fire(&json!({"every": "1h"}), MAX_TIME).unwrap(), None);
    }

    #[test]
    fn every_zero_is_an_error() {
        assert!(next_fire(&json!({"every": "0s"}), 0).is_err());
    }

    #[test]
    fn bad_timezone_is_an_error() {
        assert!(next_fire(&cron("0 0 * * *", "Mars/Olympus"), 0).is_err());
        assert!(next_fire(&json!({"cron": "0 0 * *"}), 0).is_err());
        assert!(next_fire(&json!({}), 0).is_err());
        assert!(next_fire(&json!({"cron": "0 0 * * *", "every": "1h"}), 0).is_err());
    }
}
