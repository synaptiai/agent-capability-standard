//! Reference core of the Agent Capability Standard.
//!
//! The workflow validator and executor live here so that every consumer — the
//! `acs` CLI, `tools/validate_workflows.py`, and the `grounded_agency` Python
//! package — runs one implementation. See `tasks/design-114.md`.

pub mod diag;
pub mod yaml;

#[cfg(feature = "python")]
mod python;
