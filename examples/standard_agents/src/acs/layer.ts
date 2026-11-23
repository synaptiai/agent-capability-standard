/**
 * The layer-wide configuration every grounded tool reads: the destination
 * policies in force for `send` calls (STANDARD 1.2.0 §4.4.2, §5.18.10), read
 * at call time, and the domain profiles applied to every call (§5.21),
 * read when a tool is defined.
 *
 * A destination policy here applies to every tool defined with
 * `groundedTool` whose capabilities include `send`, whether or not the tool
 * was defined with the `destination` option (which only says where its
 * destination is): no `send` tool escapes it by how it was defined. Profiles
 * here apply to every tool defined with `groundedTool` (the memory tools
 * included) beside its own `profiles`, so none escapes them by how it was
 * defined; a tool defined before the profiles in force changed refuses its
 * calls (R407), since its flags were computed with the earlier ones.
 * Module-level, like the binding's other per-realm state: call
 * `configureLayer` in the module that defines the agent's tools, before
 * them. Without a call no policy or profile is in force, and a destination
 * is the host's to check, as in 1.1.
 */
import { checkPolicies } from '@synaptiai/acs-core';
import type { BindingProfiles } from './profiles.js';

export interface LayerConfig {
  /** Destination policies the host puts in force (§4.4.2): each a list of patterns. */
  destinations?: readonly (readonly string[])[];
  /**
   * Domain profiles (§5.21) every grounded tool applies, as
   * `bindingProfiles` checked them: their flags, person requirement,
   * grounding policies and minimum confidence (§5.21.3) for every call, and
   * their `allowed_destinations` among the policies in force.
   */
  profiles?: BindingProfiles;
  /**
   * The `allowed_destinations` of applied domain profiles (§5.21), as the
   * core computed them (`CoreContext.profilePolicy(profiles)` from
   * `@synaptiai/acs-core/wasm`): its `destinations` join the policies in
   * force. Only those: a policy that also sets a minimum confidence or
   * grounding policies is refused, since the layer would not put them in
   * force from here (§5.21.4); pass the profiles as `profiles`.
   */
  profilePolicy?: {
    readonly destinations: readonly (readonly string[])[];
    readonly minimum_confidence?: number | null;
    readonly grounding?: readonly unknown[];
  };
}

let config: { destinations: readonly (readonly string[])[]; profiles: BindingProfiles | null } = {
  destinations: [],
  profiles: null,
};

/**
 * Put the layer's destination policies and profiles in force, replacing any
 * earlier configuration. Throws, and changes nothing, when a pattern is not
 * one (§4.4.2: a policy that holds an invalid pattern is refused when
 * loaded), or when `profilePolicy` carries rules besides destinations.
 */
export function configureLayer(next: LayerConfig): void {
  const extra = next.profilePolicy;
  if (extra !== undefined && ((extra.minimum_confidence ?? null) !== null || (extra.grounding ?? []).length > 0)) {
    throw new Error(
      'configureLayer: profilePolicy sets a minimum confidence or grounding policies, which it does not put in force; pass the profiles as profiles (STANDARD 1.2.0 §5.21.4)',
    );
  }
  const destinations = [
    ...(next.destinations ?? []),
    ...(next.profilePolicy?.destinations ?? []),
    ...(next.profiles?.policy.destinations ?? []),
  ].map((p) => Object.freeze([...p]));
  const problem = checkPolicies(destinations);
  if (problem !== null) throw new Error(`configureLayer: destination ${problem} (STANDARD 1.2.0 §4.4.2)`);
  config = { destinations: Object.freeze(destinations), profiles: next.profiles ?? null };
}

/** The destination policies in force: the host's, then the profiles'. */
export function destinationPolicies(): readonly (readonly string[])[] {
  return config.destinations;
}

/** The domain profiles the layer applies to every grounded tool, or null. */
export function layerProfiles(): BindingProfiles | null {
  return config.profiles;
}

/** No policy or profile in force: the configuration a realm starts with (for tests). */
export function resetLayer(): void {
  config = { destinations: [], profiles: null };
}
