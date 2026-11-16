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
  effectiveFlagsOf,
  isCapability,
  type Layer,
  ONTOLOGY_VERSION,
  prerequisites,
  prerequisitesOf,
  REQUIRES,
  type Risk,
  type SafetyFlags,
  /**
   * The version of the Agent Capability Standard this binding follows, which
   * its annotations and records cite: the package's, 1.2.0, whose §5.18 the
   * binding implements as a safety layer (class SL, §10.4).
   */
  STANDARD_VERSION,
} from '@synaptiai/acs-core';
