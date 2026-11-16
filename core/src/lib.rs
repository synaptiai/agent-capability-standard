//! Reference core of the Agent Capability Standard.
//!
//! The workflow validator and the executor live here so that every consumer
//! — `tools/validate_workflows.py` and the `grounded_agency` Python package —
//! runs one implementation. See `tasks/design-114.md`.

pub mod agents;
pub mod catalogs;
pub mod cron;
pub mod destination;
pub mod diag;
pub mod duration;
pub mod exec;
pub mod expr;
pub mod grounding;
pub mod names;
pub mod ontology;
pub mod profile;
pub mod refs;
pub mod schema;
pub mod trigger;
pub mod types;
pub mod validate;
pub mod yaml;

#[cfg(feature = "python")]
mod python;
#[cfg(feature = "wasm")]
pub mod wasm;
