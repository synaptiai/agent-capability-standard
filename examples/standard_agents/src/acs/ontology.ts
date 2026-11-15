/**
 * The ontology, as the binding uses it: the table, types and safety-flag
 * rules come from the TypeScript package `@synaptiai/acs-core`; what is
 * specific to this binding is defined here.
 */
export {
  CAPABILITIES,
  type CapabilityId,
  type CapabilityOutput,
  type DeclaredFlags,
  effectiveFlags,
  isCapability,
  type Layer,
  ONTOLOGY_VERSION,
  prerequisites,
  REQUIRES,
  type Risk,
  type SafetyFlags,
} from '@synaptiai/acs-core';

/**
 * The version of the Agent Capability Standard this binding follows, which
 * its annotations and records cite. The package implements a later one
 * (its `STANDARD_VERSION`); the binding moves to it when it implements it.
 */
export const STANDARD_VERSION = '1.1.0';
