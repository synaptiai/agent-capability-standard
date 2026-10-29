//! Reference core of the Agent Capability Standard.
//!
//! The workflow validator and the executor live here so that every consumer
//! — `tools/validate_workflows.py` and the `grounded_agency` Python package —
//! runs one implementation. See `tasks/design-114.md`.

pub mod cron;
pub mod diag;
pub mod duration;
pub mod exec;
pub mod expr;
pub mod ontology;
pub mod refs;
pub mod schema;
pub mod types;
pub mod validate;
pub mod yaml;

#[cfg(feature = "python")]
mod python;
