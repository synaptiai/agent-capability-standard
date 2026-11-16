/**
 * Domain profiles (STANDARD 1.2.0 §5.21) a grounded tool applies, as the
 * reference core computes them: their raised flags and person requirement,
 * their grounding policies and their minimum confidence (§5.21.3).
 *
 * The binding does not load the core itself (it runs on the plain
 * TypeScript entry): the host computes the profiles once with the core's
 * WebAssembly entry, `@synaptiai/acs-core/wasm`, and passes the result to
 * each `groundedTool` as `profiles` (`bindingProfiles`). The binding checks no
 * send's destination yet, so a profile that sets `allowed_destinations` is
 * refused rather than applied without it (§5.21.4).
 */
import type { Json } from '@synaptiai/acs-core';
import type { ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import type { CapabilityId, DeclaredFlags } from './ontology.js';

/** The applied profiles, as `groundedTool`'s `profiles` option takes them. */
export interface BindingProfiles {
  /** The profiles as given: part of every record's `config_sha256` (§5.18.8). */
  readonly documents: readonly Json[];
  /** The effective flags of `capability` under the profiles, with a tool's declared flags (`CoreContext.profileFlags`). */
  flags(capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags;
  /** The rules besides flags (`CoreContext.profilePolicy`). */
  readonly policy: ProfilePolicy;
}

/** What `bindingProfiles` needs of a core context (`CoreContext` from `@synaptiai/acs-core/wasm`). */
export interface ProfileCore {
  profileFlags(profiles: Json[], capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags;
  profilePolicy(profiles: Json[]): ProfilePolicy;
}

/** The problem with applying `policy` in this binding, if any: a rule it does not put in force. */
export function unappliedRule(policy: ProfilePolicy): string | null {
  return policy.destinations.length > 0
    ? 'a profile sets allowed_destinations, a destination policy (§4.4.2) this binding does not check yet: the profiles are refused rather than applied without it (STANDARD 1.2.0 §5.21.4)'
    : null;
}

/**
 * Check `documents` with the core and keep what a grounded tool applies.
 * Throws the core's error (`CoreError`, kind `bad_request`, with the
 * diagnostics of §5.21.2) for a profile with an error, and an `Error` for a
 * profile that sets a rule this binding does not apply.
 */
export function bindingProfiles(core: ProfileCore, documents: readonly Json[]): BindingProfiles {
  const list = Object.freeze([...documents]);
  const policy = core.profilePolicy([...list]);
  const problem = unappliedRule(policy);
  if (problem !== null) throw new Error(problem);
  const flags = new Map<string, ProfileFlags>();
  return Object.freeze({
    documents: list,
    policy,
    flags(capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags {
      const key = JSON.stringify([capability, declared ?? null]);
      let found = flags.get(key);
      if (found === undefined) {
        found = core.profileFlags([...list], capability, declared);
        flags.set(key, found);
      }
      return found;
    },
  });
}

/**
 * The minimum-confidence failure of `output` under `minimum` (§5.21.3), or
 * null: an output with no `confidence` member passes; one that is not a
 * number from 0 to 1 is `invalid_confidence`, one below the minimum
 * `below_minimum_confidence`. The messages are the core's.
 */
export function confidenceFailure(
  output: Record<string, unknown>,
  minimum: number,
): { reason: 'below_minimum_confidence' | 'invalid_confidence'; message: string } | null {
  if (!Object.prototype.hasOwnProperty.call(output, 'confidence')) return null;
  const c = output['confidence'];
  if (typeof c !== 'number' || !(c >= 0 && c <= 1)) {
    const text = (JSON.stringify(c) ?? String(c)).slice(0, 64);
    return {
      reason: 'invalid_confidence',
      message: `the output's confidence ${text} is not a number from 0 to 1, and an applied profile sets a minimum confidence`,
    };
  }
  return c < minimum
    ? {
        reason: 'below_minimum_confidence',
        message: `confidence ${c} is below the minimum confidence ${minimum} of the applied profiles`,
      }
    : null;
}
