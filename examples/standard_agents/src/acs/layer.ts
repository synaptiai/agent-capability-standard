/**
 * The layer-wide configuration every grounded tool reads at call time: the
 * destination policies in force for `send` calls (STANDARD 1.2.0 §4.4.2,
 * §5.18.10).
 *
 * A policy here applies to every tool defined with `groundedTool` whose
 * capabilities include `send`, whether or not the tool was defined with the
 * `destination` option (which only says where its destination is): no `send`
 * tool escapes it by how it was defined. Module-level, like the binding's
 * other per-realm state: call `configureLayer` in the module that defines
 * the agent's tools. Without a call no policy is in force, and a
 * destination is the host's to check, as in 1.1.
 */
import { checkPolicies } from '@synaptiai/acs-core';

export interface LayerConfig {
  /** Destination policies the host puts in force (§4.4.2): each a list of patterns. */
  destinations?: readonly (readonly string[])[];
  /**
   * The applied domain profiles' rules (§5.21), as the core computed them:
   * `CoreContext.profilePolicy(profiles)` from `@synaptiai/acs-core/wasm`,
   * or `bindingProfiles(...).policy`, which checked the profiles. Its
   * `destinations` (each profile's `allowed_destinations`) join the
   * policies in force.
   */
  profilePolicy?: { readonly destinations: readonly (readonly string[])[] };
}

let config: { destinations: readonly (readonly string[])[] } = { destinations: [] };

/**
 * Put the layer's destination policies in force, replacing any earlier
 * configuration. Throws, and changes nothing, when a pattern is not one
 * (§4.4.2: a policy that holds an invalid pattern is refused when loaded).
 */
export function configureLayer(next: LayerConfig): void {
  const destinations = [...(next.destinations ?? []), ...(next.profilePolicy?.destinations ?? [])].map((p) =>
    Object.freeze([...p]),
  );
  const problem = checkPolicies(destinations);
  if (problem !== null) throw new Error(`configureLayer: destination ${problem} (STANDARD 1.2.0 §4.4.2)`);
  config = { destinations: Object.freeze(destinations) };
}

/** The destination policies in force: the host's, then the profiles'. */
export function destinationPolicies(): readonly (readonly string[])[] {
  return config.destinations;
}

/** No policy in force: the configuration a realm starts with (for tests). */
export function resetLayer(): void {
  config = { destinations: [] };
}
