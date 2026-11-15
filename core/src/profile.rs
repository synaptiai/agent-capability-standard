//! Domain profiles applied to a run or a validation (STANDARD v1.2 §5.21).
//!
//! Foundation stub: the shape the validator and the executor call through
//! (`semantics::effective`), with no profile loaded. `Policy::default()`
//! applies no profile, so `raise` raises nothing and every result is the
//! 1.1 one. Workstream S6 fills this module in (loading, `raise`, minimum
//! confidence, grounding, destinations and trust weights); its design is
//! `tasks/standard-1.2/designs/S6.md` part 5.1.

use crate::ontology::Risk;

/// The profiles applied to a run or a validation, loaded and checked.
#[derive(Debug, Clone, Default)]
pub struct Policy {
    _private: (),
}

/// What the applied profiles add to one step's or call's flags (§5.21.3).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Raise {
    pub requires_checkpoint: bool,
    pub requires_approval: bool,
    /// A person must decide (§5.21.3 "A person").
    pub person: bool,
}

impl Policy {
    /// No profile is applied.
    pub fn is_empty(&self) -> bool {
        true
    }

    /// The flags the applied profiles raise for a step of `capability` whose
    /// effective risk before profiles is `risk`. With no profile, nothing.
    pub fn raise(&self, _capability: &str, _risk: Risk) -> Raise {
        Raise::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_empty_policy_raises_nothing() {
        let p = Policy::default();
        assert!(p.is_empty());
        for risk in [Risk::Low, Risk::Medium, Risk::High] {
            assert_eq!(p.raise("mutate", risk), Raise::default());
        }
    }
}
