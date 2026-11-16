//! Name grammars of STANDARD v1.2: domain ids (§5.2.4), model families
//! (§5.15), catalog ids, workflow names and qualified workflow ids (§5.1,
//! §5.1.1), and Semantic Versioning 2.0.0 for a catalog's `version`.
//!
//! Hand-written matchers: the crate has no regular-expression dependency.

use crate::refs::is_identifier;

fn lower_digit(b: u8) -> bool {
    b.is_ascii_lowercase() || b.is_ascii_digit()
}

/// A dot-separated id whose every segment is non-empty, starts with a
/// lowercase letter or digit, and continues with bytes `more` accepts.
fn dotted(s: &str, more: impl Fn(u8) -> bool) -> bool {
    !s.is_empty()
        && s.split('.').all(|seg| {
            let b = seg.as_bytes();
            !b.is_empty() && lower_digit(b[0]) && b[1..].iter().all(|&c| more(c))
        })
}

/// A domain id (§5.2.4): one or more segments joined by `.`, each
/// `[a-z0-9][a-z0-9_]*` (`text`, `image.object`, `image.3d`).
pub fn is_domain_id(s: &str) -> bool {
    dotted(s, |c| lower_digit(c) || c == b'_')
}

/// A catalog id (§5.1.1): one or more segments joined by `.`, each
/// `[a-z0-9][a-z0-9_-]*` (`acs.reference`, `acme.twin`).
pub fn is_catalog_id(s: &str) -> bool {
    dotted(s, |c| lower_digit(c) || c == b'_' || c == b'-')
}

/// A model family as written (§5.15): `[a-z][a-z0-9_-]*`.
pub fn is_model_family(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b[0].is_ascii_lowercase()
        && b[1..]
            .iter()
            .all(|&c| lower_digit(c) || c == b'_' || c == b'-')
}

/// The model family a host derives from a model's identifier (§5.15):
///
/// 1. the part of the identifier after its last `/`;
/// 2. of that, the part after the last `.` or `:` that comes before its
///    first ASCII digit or `-` (any `.` or `:` when it has neither);
/// 3. the leading run of ASCII letters of the rest, lowercased.
///
/// `None` when that run is empty: the host attests no family.
pub fn model_family(model_id: &str) -> Option<String> {
    let rest = model_id.rsplit('/').next().unwrap_or(model_id);
    let stop = rest
        .find(|c: char| c.is_ascii_digit() || c == '-')
        .unwrap_or(rest.len());
    let rest = match rest[..stop].rfind(['.', ':']) {
        Some(i) => &rest[i + 1..],
        None => rest,
    };
    let family: String = rest
        .chars()
        .take_while(char::is_ascii_alphabetic)
        .map(|c| c.to_ascii_lowercase())
        .collect();
    (!family.is_empty()).then_some(family)
}

/// A workflow name this Standard calls canonical (§5.1): an identifier
/// (`[A-Za-z_][A-Za-z0-9_-]*`) other than the reserved `catalog`.
pub fn is_workflow_name(s: &str) -> bool {
    is_identifier(s) && s != "catalog"
}

/// Split a qualified workflow id (§5.1.1), `<catalog id>/<workflow name>`:
/// exactly one `/`, a catalog id on its left and an identifier on its right.
pub fn split_qualified(s: &str) -> Option<(&str, &str)> {
    let (id, name) = s.split_once('/')?;
    (is_catalog_id(id) && is_identifier(name)).then_some((id, name))
}

/// Semantic Versioning 2.0.0: `MAJOR.MINOR.PATCH`, numeric identifiers
/// without leading zeros, an optional `-` pre-release and `+` build list.
pub fn is_semver(s: &str) -> bool {
    let numeric = |p: &str| {
        !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()) && (p == "0" || !p.starts_with('0'))
    };
    let ident =
        |p: &str| !p.is_empty() && p.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-');
    let (core_pre, build) = match s.split_once('+') {
        Some((c, b)) => (c, Some(b)),
        None => (s, None),
    };
    let (core, pre) = match core_pre.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (core_pre, None),
    };
    let parts: Vec<&str> = core.split('.').collect();
    if parts.len() != 3 || !parts.iter().all(|p| numeric(p)) {
        return false;
    }
    let pre_ok = pre.is_none_or(|p| {
        p.split('.')
            .all(|id| ident(id) && (!id.bytes().all(|b| b.is_ascii_digit()) || numeric(id)))
    });
    let build_ok = build.is_none_or(|b| b.split('.').all(ident));
    pre_ok && build_ok
}

/// The domain id a non-canonical value most likely means: lowercased, with
/// `-` written `_`, when that is a domain id (the suggestion of W620).
pub fn canonical_domain_hint(s: &str) -> Option<String> {
    let hint = s.to_ascii_lowercase().replace('-', "_");
    (hint != s && is_domain_id(&hint)).then_some(hint)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn domain_ids() {
        for ok in [
            "text",
            "image.object",
            "image.3d",
            "3d.mesh",
            "multimodal.text_to_image",
            "plan_invalidation",
        ] {
            assert!(is_domain_id(ok), "{ok}");
        }
        for bad in [
            "",
            "plan-invalidation",
            "Text.Feature",
            "a..b",
            ".a",
            "a.",
            "_a",
            "a b",
        ] {
            assert!(!is_domain_id(bad), "{bad}");
        }
        assert_eq!(
            canonical_domain_hint("Plan-Invalidation").as_deref(),
            Some("plan_invalidation")
        );
        assert_eq!(canonical_domain_hint("a..b"), None);
    }

    #[test]
    fn catalog_ids_and_qualified_names() {
        assert!(is_catalog_id("acs.reference"));
        assert!(is_catalog_id("acme-co.twin_2"));
        assert!(!is_catalog_id("Bad Id"));
        assert!(!is_catalog_id("a..b"));
        assert_eq!(
            split_qualified("acs.reference/world_model_build"),
            Some(("acs.reference", "world_model_build"))
        );
        assert_eq!(split_qualified("plain"), None);
        assert_eq!(split_qualified("a/b/c"), None);
        assert_eq!(split_qualified("Bad/x"), None);
        assert_eq!(split_qualified("a/9x"), None);
    }

    #[test]
    fn workflow_names() {
        assert!(is_workflow_name("digital_twin_sync_loop"));
        assert!(is_workflow_name("A-b"));
        assert!(!is_workflow_name("catalog"));
        assert!(!is_workflow_name("My Workflow"));
        assert!(!is_workflow_name("9lives"));
    }

    #[test]
    fn model_families() {
        assert!(is_model_family("acme"));
        assert!(is_model_family("family_a"));
        assert!(!is_model_family("Acme"));
        assert!(!is_model_family("9a"));
        assert!(!is_model_family(""));
        for (id, family) in [
            ("acme-large-2", Some("acme")),
            ("us.acme.acme-large-2-20260101-v1:0", Some("acme")),
            ("ft:acme-mini-1:org::abc", Some("acme")),
            ("acme/acme-large-2", Some("acme")),
            ("vendor.zephyrline3-1-70b-v1:0", Some("zephyrline")),
            ("Bolt/BoltChat-7B", Some("boltchat")),
            ("z3-mini", Some("z")),
            ("acme-large-2@20260101", Some("acme")),
            ("3d-model", None),
            ("", None),
        ] {
            assert_eq!(model_family(id).as_deref(), family, "{id}");
        }
    }

    #[test]
    fn semver() {
        for ok in [
            "1.0.0",
            "0.1.0",
            "10.20.30",
            "1.0.0-rc.1+b.2",
            "1.0.0-alpha-1",
        ] {
            assert!(is_semver(ok), "{ok}");
        }
        for bad in [
            "01.0.0", "1.0", "1.0.0-", "1.0.0-01", "1.0.0+", "v1.0.0", "1.0.0.0",
        ] {
            assert!(!is_semver(bad), "{bad}");
        }
    }
}
