/**
 * Step domains (STANDARD v1.2.0 §5.2.4): the domain id grammar and the
 * rule a host selects an implementation by
 * (`tests/conformance/domains/match.json` pins it).
 */

const DOMAIN_ID = /^[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*$/;

/** Whether `value` is a domain id: lowercase segments joined by `.`. */
export function isDomainId(value: string): boolean {
  return DOMAIN_ID.test(value);
}

/** No implementation serves a step's domain: the step fails (R402) with the reason `unsupported_domain` (§5.19.7). */
export class UnsupportedDomainError extends Error {
  readonly reason = 'unsupported_domain';
  constructor(readonly domain: string | null) {
    super(`no implementation serves ${domain === null ? 'a step without a domain' : `domain '${domain}'`}`);
    this.name = 'UnsupportedDomainError';
  }
}

/**
 * The implementation a host selects for a step's `domain` (null: none)
 * among `available` ('' is the implementation for no domain), by exact
 * comparison: the step's domain; else the longest proper prefix ending
 * before a `.`; else ''. Throws `UnsupportedDomainError` when none serves.
 */
export function selectImplementation(domain: string | null, available: Iterable<string>): string {
  const keys = new Set(available);
  if (domain !== null) {
    let candidate = domain;
    for (;;) {
      if (keys.has(candidate)) return candidate;
      const cut = candidate.lastIndexOf('.');
      if (cut < 0) break;
      candidate = candidate.slice(0, cut);
    }
  }
  if (keys.has('')) return '';
  throw new UnsupportedDomainError(domain);
}
