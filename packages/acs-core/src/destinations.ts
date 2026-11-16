/**
 * Destination policies (Agent Capability Standard 1.2.0, section 4.4.2):
 * which destinations a `send` may reach. A policy is a list of patterns; a
 * destination is allowed by a policy when one of its patterns matches it,
 * and by the policies in force when every one of them allows it.
 *
 * A pattern is an exact destination; a prefix ending in `*` whose last
 * character before the `*` is one of `/ : @ . ? #` (and which, when it
 * starts an authority with `//`, finishes it with `/`, `?` or `#`); or a
 * suffix starting with `*@` or `*.`, where what the `*` covers holds only
 * ASCII letters, digits, `.`, `-`, `_` and `+`. Strings compare by code
 * point, with no case folding or Unicode normalisation: `===`,
 * `startsWith` and `endsWith` on JavaScript strings agree with code-point
 * equality. The same grammar as the core's `destination.rs`; both are held
 * to `tests/conformance/destinations/match.json`.
 */

/** Characters a prefix pattern may end with before its `*`. */
const PREFIX_ENDS = new Set(['/', ':', '@', '.', '?', '#']);

/** What the `*` of a suffix pattern may cover. */
const NAME_PART = /^[A-Za-z0-9._+-]+$/;

/** A checked pattern. */
export type DestinationPattern =
  | { readonly kind: 'exact'; readonly text: string }
  | { readonly kind: 'prefix'; readonly text: string }
  | { readonly kind: 'suffix'; readonly text: string };

/** The pattern `p` checked: the pattern, or the problem with it. */
export function parsePattern(p: string): DestinationPattern | string {
  if (p.length === 0) return 'a pattern is not empty';
  const stars = p.split('*').length - 1;
  if (stars === 0) return { kind: 'exact', text: p };
  if (stars > 1) {
    return `'${p}' has more than one '*'; a pattern is exact, a prefix ending in '*' or a suffix starting with '*'`;
  }
  if (p.endsWith('*')) {
    const prefix = p.slice(0, -1);
    if (prefix.length === 0) {
      return "'*' alone allows every destination; name a prefix such as https:* or https://hooks.example.com/*";
    }
    const last = [...prefix].pop() as string;
    if (!PREFIX_ENDS.has(last)) {
      return `the prefix of '${p}' must end with one of / : @ . ? # before its '*', as in https://hooks.example.com/*`;
    }
    const authority = prefix.indexOf('//');
    if (authority >= 0 && !/[/?#]/.test(prefix.slice(authority + 2))) {
      return `the prefix of '${p}' starts an authority it does not finish: put '/', '?' or '#' after the host, as in https://hooks.example.com/*`;
    }
    return { kind: 'prefix', text: prefix };
  }
  if (p.startsWith('*')) {
    const suffix = p.slice(1);
    if ([...suffix].length < 2 || !(suffix.startsWith('@') || suffix.startsWith('.'))) {
      return `the suffix of '${p}' must start with '@' or '.' and name something after it, as in *@example.com or *.example.com`;
    }
    return { kind: 'suffix', text: suffix };
  }
  return `'${p}' has a '*' in the middle; a pattern is exact, a prefix ending in '*' or a suffix starting with '*'`;
}

/** The problem with pattern `p`, or null when it is a pattern. */
export function checkPattern(p: string): string | null {
  const parsed = parsePattern(p);
  return typeof parsed === 'string' ? parsed : null;
}

/** The first problem of any policy, as "policy i, pattern j: ...", or null. */
export function checkPolicies(policies: readonly (readonly string[])[]): string | null {
  for (const [i, policy] of policies.entries()) {
    for (const [j, p] of policy.entries()) {
      const problem = checkPattern(p);
      if (problem !== null) return `policy ${i}, pattern ${j}: ${problem}`;
    }
  }
  return null;
}

/** Whether `pattern` matches `destination`; an invalid pattern matches
 * nothing (it fails closed). */
export function matches(pattern: string, destination: string): boolean {
  const p = parsePattern(pattern);
  if (typeof p === 'string') return false;
  switch (p.kind) {
    case 'exact':
      return destination === p.text;
    case 'prefix':
      return destination.startsWith(p.text);
    case 'suffix':
      return (
        destination.length > p.text.length &&
        destination.endsWith(p.text) &&
        NAME_PART.test(destination.slice(0, destination.length - p.text.length))
      );
  }
}

/** Whether every policy allows `destination` (none in force: allowed; an
 * empty policy allows none). */
export function allowed(policies: readonly (readonly string[])[], destination: string): boolean {
  return policies.every((policy) => policy.some((p) => matches(p, destination)));
}
