//! Five-field cron expressions (STANDARD v1.1 §5.10): minute hour
//! day-of-month month day-of-week, with `*`, lists, ranges and `/` steps,
//! month names JAN–DEC and weekday names SUN–SAT (0 and 7 are Sunday). When
//! both day fields are restricted a day matches either (Vixie semantics).

/// A parsed schedule: one bit per allowed value of each field.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cron {
    minutes: u64,
    hours: u32,
    days_of_month: u32,
    months: u16,
    days_of_week: u8,
    dom_restricted: bool,
    dow_restricted: bool,
}

struct Field {
    name: &'static str,
    min: u32,
    max: u32,
    names: &'static [&'static str],
}

const MONTHS: &[&str] = &[
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
];
const WEEKDAYS: &[&str] = &["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

const FIELDS: [Field; 5] = [
    Field {
        name: "minute",
        min: 0,
        max: 59,
        names: &[],
    },
    Field {
        name: "hour",
        min: 0,
        max: 23,
        names: &[],
    },
    Field {
        name: "day of month",
        min: 1,
        max: 31,
        names: &[],
    },
    Field {
        name: "month",
        min: 1,
        max: 12,
        names: MONTHS,
    },
    Field {
        name: "day of week",
        min: 0,
        max: 7,
        names: WEEKDAYS,
    },
];

impl Cron {
    /// Parse `minute hour day-of-month month day-of-week`.
    pub fn parse(text: &str) -> Result<Cron, String> {
        let parts: Vec<&str> = text.split_whitespace().collect();
        if parts.first().is_some_and(|p| p.contains('=')) {
            return Err(format!(
                "'{text}': a CRON_TZ=/TZ= prefix is not allowed; set the schedule's timezone"
            ));
        }
        if parts.len() != 5 {
            return Err(format!(
                "'{text}' has {} fields; a cron expression has 5 (minute hour day-of-month month day-of-week)",
                parts.len()
            ));
        }
        let mut bits = [0u64; 5];
        for (i, (part, field)) in parts.iter().zip(FIELDS.iter()).enumerate() {
            bits[i] = parse_field(part, field).map_err(|e| format!("'{text}': {e}"))?;
        }
        // 7 is Sunday, like 0.
        let mut dow = bits[4];
        if dow & (1 << 7) != 0 {
            dow = (dow & !(1 << 7)) | 1;
        }
        Ok(Cron {
            minutes: bits[0],
            hours: bits[1] as u32,
            days_of_month: bits[2] as u32,
            months: bits[3] as u16,
            days_of_week: dow as u8,
            // As in Vixie cron, a field starting with `*` (including `*/n`)
            // counts as unrestricted for the day-matching rule.
            dom_restricted: !parts[2].starts_with('*'),
            dow_restricted: !parts[4].starts_with('*'),
        })
    }

    /// Whether the schedule fires at this local time. `dow` is 0 (Sunday)
    /// to 6.
    pub fn matches(&self, minute: u32, hour: u32, dom: u32, month: u32, dow: u32) -> bool {
        let bit = |set: u64, v: u32| v < 64 && set & (1 << v) != 0;
        if !bit(self.minutes, minute)
            || !bit(self.hours.into(), hour)
            || !bit(self.months.into(), month)
        {
            return false;
        }
        let dom_ok = bit(self.days_of_month.into(), dom);
        let dow_ok = bit(self.days_of_week.into(), dow);
        match (self.dom_restricted, self.dow_restricted) {
            (true, true) => dom_ok || dow_ok,
            _ => dom_ok && dow_ok,
        }
    }
}

fn parse_field(text: &str, field: &Field) -> Result<u64, String> {
    let mut set = 0u64;
    for item in text.split(',') {
        if item.is_empty() {
            return Err(format!("empty item in the {} field", field.name));
        }
        let (range, step) = match item.split_once('/') {
            Some((r, s)) => {
                let step: u32 = s
                    .parse()
                    .ok()
                    .filter(|&n| n >= 1 && s.bytes().all(|b| b.is_ascii_digit()))
                    .ok_or_else(|| format!("'{item}': step must be a positive number"))?;
                (r, step)
            }
            None => (item, 1),
        };
        let (lo, hi) = if range == "*" {
            (field.min, field.max)
        } else if let Some((a, b)) = range.split_once('-') {
            (value(a, field)?, value(b, field)?)
        } else {
            let v = value(range, field)?;
            // `a/step` runs from a to the field's maximum.
            (v, if item.contains('/') { field.max } else { v })
        };
        if lo > hi {
            return Err(format!(
                "'{item}': range runs backwards in the {} field",
                field.name
            ));
        }
        for v in (lo..=hi).step_by(step as usize) {
            set |= 1 << v;
        }
    }
    Ok(set)
}

fn value(text: &str, field: &Field) -> Result<u32, String> {
    let upper = text.to_ascii_uppercase();
    if let Some(i) = field.names.iter().position(|n| *n == upper) {
        // Month names count from 1 (the field's minimum), weekday names from 0.
        return Ok(i as u32 + field.min);
    }
    let v: u32 = text
        .parse()
        .ok()
        .filter(|_| text.bytes().all(|b| b.is_ascii_digit()))
        .ok_or_else(|| format!("'{text}' is not a valid {}", field.name))?;
    if v < field.min || v > field.max {
        return Err(format!(
            "{v} is outside the {} range {}-{}",
            field.name, field.min, field.max
        ));
    }
    Ok(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_matches() {
        let c = Cron::parse("0 6 * * MON-FRI").unwrap();
        assert!(c.matches(0, 6, 15, 3, 1));
        assert!(!c.matches(0, 6, 15, 3, 0));
        assert!(!c.matches(1, 6, 15, 3, 1));
        let every15 = Cron::parse("*/15 * * * *").unwrap();
        for m in [0, 15, 30, 45] {
            assert!(every15.matches(m, 3, 1, 1, 2));
        }
        assert!(!every15.matches(7, 3, 1, 1, 2));
        let c = Cron::parse("5/20 0 1 jan,Jul *").unwrap();
        assert!(c.matches(45, 0, 1, 7, 4));
        assert!(!c.matches(45, 0, 1, 2, 4));
    }

    #[test]
    fn sunday_is_0_and_7() {
        let seven = Cron::parse("0 0 * * 7").unwrap();
        let zero = Cron::parse("0 0 * * 0").unwrap();
        let named = Cron::parse("0 0 * * sun").unwrap();
        assert_eq!(seven, zero);
        assert_eq!(named, zero);
        assert!(seven.matches(0, 0, 3, 3, 0));
        let range = Cron::parse("0 0 * * 5-7").unwrap();
        assert!(range.matches(0, 0, 3, 3, 0) && range.matches(0, 0, 3, 3, 6));
    }

    #[test]
    fn vixie_day_semantics() {
        // Both restricted: the 13th OR any Friday.
        let c = Cron::parse("0 0 13 * FRI").unwrap();
        assert!(c.matches(0, 0, 13, 1, 2));
        assert!(c.matches(0, 0, 10, 1, 5));
        assert!(!c.matches(0, 0, 10, 1, 2));
        // One restricted: AND with the unrestricted (always true) field.
        let c = Cron::parse("0 0 13 * *").unwrap();
        assert!(c.matches(0, 0, 13, 1, 2) && !c.matches(0, 0, 12, 1, 5));
    }

    #[test]
    fn starred_day_fields_are_unrestricted() {
        // `*/2` in day-of-month is unrestricted (Vixie): AND with Monday.
        let c = Cron::parse("0 0 */2 * MON").unwrap();
        assert!(!c.matches(0, 0, 3, 1, 2), "Tuesday the 3rd");
        assert!(c.matches(0, 0, 3, 1, 1), "Monday the 3rd");
        assert!(!c.matches(0, 0, 4, 1, 1), "Monday the 4th");
    }

    #[test]
    fn huge_steps_do_not_overflow() {
        let c = Cron::parse("59/4294967295 * * * *").unwrap();
        assert!(c.matches(59, 0, 1, 1, 0));
        assert!(!c.matches(58, 0, 1, 1, 0));
        assert!(Cron::parse("*/+5 * * * *").is_err());
        assert!(Cron::parse("*/4294967296 * * * *").is_err());
    }

    #[test]
    fn rejects() {
        for bad in [
            "",
            "* * * *",
            "* * * * * *",
            "60 * * * *",
            "* 24 * * *",
            "* * 0 * *",
            "* * 32 * *",
            "* * * 13 * ",
            "* * * * 8",
            "*/0 * * * *",
            "5-1 * * * *",
            "a * * * *",
            "1,,2 * * * *",
            "-1 * * * *",
            "+1 * * * *",
            "* * * FOO *",
            "CRON_TZ=UTC 0 0 * * *",
            "TZ=UTC 0 0 * * *",
            "1-2-3 * * * *",
        ] {
            assert!(Cron::parse(bad).is_err(), "{bad:?}");
        }
    }
}
