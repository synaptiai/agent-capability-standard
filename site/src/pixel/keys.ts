// Glyph keys: which grid draws which concept (visual spec 2.2 and 2.3).
// No imports but glyphs.ts, so the check scripts can load it with plain
// `node`.
import { CHAPTER_ALIASES, CHAPTER_EXEMPT_PREFIX, CONCEPT_GLYPHS, GLYPH_ALIASES, LAYER_GLYPHS, UI_GLYPHS } from './glyphs.ts';

/** Every drawn grid by key: the layer glyphs, the inline glyphs, then the concept glyphs. */
export const ALL_GRIDS: Readonly<Record<string, readonly string[]>> = { ...LAYER_GLYPHS, ...UI_GLYPHS, ...CONCEPT_GLYPHS };

/** The grid key a glyph key draws with, following GLYPH_ALIASES; null when there is none. */
export function resolveGlyphKey(key: string): string | null {
  let k = key;
  const seen = new Set<string>();
  while (k in GLYPH_ALIASES) {
    if (seen.has(k)) throw new Error(`glyph alias cycle at ${k}`);
    seen.add(k);
    k = GLYPH_ALIASES[k]!;
  }
  return k in ALL_GRIDS ? k : null;
}

/** Lower case, runs of anything but letters and digits as one hyphen. */
export function slugKey(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/**
 * The glyph key of a Standard H2: its text without the "N." prefix, slugged,
 * through CHAPTER_ALIASES. Null for an appendix, which gets no glyph.
 * "9. Error Model" -> "chapter:diagnostic-model".
 */
export function chapterKey(h2: string): string | null {
  const title = h2.trim();
  if (title.startsWith(CHAPTER_EXEMPT_PREFIX)) return null;
  const slug = slugKey(title.replace(/^\d+\.\s*/, ''));
  return `chapter:${CHAPTER_ALIASES[slug] ?? slug}`;
}

/** The glyph key of a design principle from its Standard H3: "3.1 Grounded Claims" -> "principle:grounded-claims". */
export function principleKey(h3: string): string {
  return `principle:${slugKey(h3.replace(/^\d+(\.\d+)*\.?\s*/, ''))}`;
}

/** The glyph key of the home page's tool cards, by card title. */
export const TOOL_GLYPHS: Readonly<Record<string, string>> = {
  Validator: 'tool:validator',
  Executor: 'tool:executor',
  'Claude Code plugin': 'tool:plugin',
  'Python SDK adapter': 'tool:sdk',
  'Conformance suite': 'tool:conformance',
};
