// Helpers for the prose, RFC and skill templates (visual spec 3.10): the page
// hero band takes the rendered H1 out of the Markdown HTML, and the RFC
// lifecycle track (F-R2) is computed from the RFC's status and the statuses
// spec/GOVERNANCE.md lists.
import { SECTIONS, type Section } from './routes';
import { statusStyle } from './status';

/** The first <h1> of rendered HTML and the HTML without it; h1 is null when there is none. */
export function splitH1(html: string): { h1: string | null; rest: string } {
  const m = /<h1\b[^>]*>[\s\S]*?<\/h1>/.exec(html);
  if (!m) return { h1: null, rest: html };
  return { h1: m[0], rest: html.slice(0, m.index) + html.slice(m.index + m[0].length) };
}

/** The hero's section glyph and eyebrow word. */
export function sectionHero(section: Section): { glyph: string; label: string } {
  const s = SECTIONS.find((x) => x.id === section);
  if (!s) throw new Error(`prose-page: unknown section ${section}`);
  return { glyph: `section:${section}`, label: s.label };
}

export interface LifecycleState {
  status: string;
  /** The glyph of the state (an alias in glyphs-prose.ts). */
  glyph: string;
  current: boolean;
}

export interface Lifecycle {
  /** The first state every RFC starts in. */
  start: LifecycleState;
  /** The states an RFC ends in, in the order GOVERNANCE.md lists them. */
  outcomes: LifecycleState[];
  /** The state the RFC is in, as GOVERNANCE.md names it. */
  current: string;
}

/**
 * F-R2: the first status GOVERNANCE.md lists is where an RFC starts, and the
 * others are where it can end. The current state is the one whose badge
 * style the RFC's own status line has ("Draft Proposal" is a draft). Throws
 * when the status matches none of them.
 */
export function rfcLifecycle(status: string, allowed: readonly string[], where: string): Lifecycle {
  if (allowed.length < 2) throw new Error(`${where}: GOVERNANCE.md lists ${allowed.length} RFC status(es); the lifecycle needs a start and an outcome`);
  const style = statusStyle(status);
  const hit = allowed.find((a) => statusStyle(a) === style);
  if (!hit) throw new Error(`${where}: status "${status}" is none of ${allowed.join(', ')}`);
  const state = (s: string): LifecycleState => ({ status: s, glyph: `lifecycle:${statusStyle(s)}`, current: s === hit });
  return { start: state(allowed[0]!), outcomes: allowed.slice(1).map(state), current: hit };
}

/** The track's accessible sentence, which the Markdown copy repeats. */
export function lifecycleSentence(l: Lifecycle, date: string | null): string {
  const outs = l.outcomes.map((o) => o.status);
  const ends = outs.length === 1 ? outs[0] : `${outs.slice(0, -1).join(', ')} or ${outs.at(-1)}`;
  return `An RFC starts as ${l.start.status} and ends as ${ends}; this one is ${l.current}${date ? `, dated ${date}` : ''}.`;
}
