/**
 * Domain profiles (STANDARD 1.2.0 §5.21) a grounded tool applies, as the
 * reference core computes them: their raised flags and person requirement,
 * their grounding policies and their minimum confidence (§5.21.3).
 *
 * The binding does not load the core itself (it runs on the plain
 * TypeScript entry): the host computes the profiles once with the core's
 * WebAssembly entry, `@synaptiai/acs-core/wasm`, and passes the result to
 * each `groundedTool` as `profiles` (`bindingProfiles`). Their
 * `allowed_destinations` are destination policies a grounded `send` tool
 * applies beside the layer's (§4.4.2, `configureLayer`).
 */
import { shownValue, type Json } from '@synaptiai/acs-core';
import type { Diagnostic, ProfileFlags, ProfilePolicy, Report } from '@synaptiai/acs-core/wasm';
import type { CapabilityId, DeclaredFlags } from './ontology.js';

/** The applied profiles, as `groundedTool`'s `profiles` option takes them. */
export interface BindingProfiles {
  /** The profiles as given: part of every record's `config_sha256` (§5.18.8). */
  readonly documents: readonly Json[];
  /** The effective flags of `capability` under the profiles, with a tool's declared flags (`CoreContext.profileFlags`). */
  flags(capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags;
  /** The rules besides flags (`CoreContext.profilePolicy`). */
  readonly policy: ProfilePolicy;
  /**
   * The warnings of loading the profiles (§5.21.2: W602, W603, W604), as
   * `bindingProfiles` reported them: a member they name is ignored.
   */
  readonly warnings: readonly Diagnostic[];
}

/** What `bindingProfiles` needs of a core context (`CoreContext` from `@synaptiai/acs-core/wasm`). */
export interface ProfileCore {
  checkProfiles(profiles: Json[]): Report;
  profileFlags(profiles: Json[], capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags;
  profilePolicy(profiles: Json[]): ProfilePolicy;
}

/** How `bindingProfiles` reports a warning of loading the profiles. */
export interface BindingProfilesOptions {
  /** Called once for each warning; defaults to `console.warn`. */
  onWarning?: (warning: Diagnostic) => void;
}

/** A warning as one line: its code, message and suggestion. */
function warningText(d: Diagnostic): string {
  return `bindingProfiles: ${d.code} ${d.severity}: ${d.message}${d.suggestion !== undefined ? ` (${d.suggestion})` : ''}`;
}

/**
 * Check `documents` with the core and keep what a grounded tool applies.
 * Throws the core's error (`CoreError`, kind `bad_request`, with the
 * diagnostics of §5.21.2) for a profile with an error. Reports each
 * warning (a misspelled top-level member is W604, and ignored) to
 * `onWarning`, and keeps them as `warnings` (§5.21.4).
 */
export function bindingProfiles(
  core: ProfileCore,
  documents: readonly Json[],
  options: BindingProfilesOptions = {},
): BindingProfiles {
  const list = Object.freeze([...documents]);
  const policy = core.profilePolicy([...list]);
  const warnings = Object.freeze(core.checkProfiles([...list]).diagnostics.filter((d) => d.severity === 'warning'));
  const report = options.onWarning ?? ((d: Diagnostic) => console.warn(warningText(d)));
  for (const w of warnings) report(w);
  const flags = new Map<string, ProfileFlags>();
  return Object.freeze({
    documents: list,
    policy,
    warnings,
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
    // The host's text is not repeated (§6.7).
    return {
      reason: 'invalid_confidence',
      message: `the output's confidence (${shownValue(c)}) is not a number from 0 to 1, and an applied profile sets a minimum confidence`,
    };
  }
  return c < minimum
    ? {
        reason: 'below_minimum_confidence',
        message: `confidence ${c} is below the minimum confidence ${minimum} of the applied profiles`,
      }
    : null;
}
