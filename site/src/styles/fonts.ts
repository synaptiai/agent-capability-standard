// The self-hosted fonts (Fontsource, SIL Open Font License), latin subset.
// Pixel fonts use font-display: optional so headings never re-flow late, and
// are preloaded so a first visit gets them rather than the fallback; body and
// mono fonts use swap. Characters outside the subset fall back to
// the next font in each stack.
import atkinson400 from '@fontsource/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-400-normal.woff2?url';
import atkinson400i from '@fontsource/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-400-italic.woff2?url';
import atkinson700 from '@fontsource/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-700-normal.woff2?url';
import atkinson700i from '@fontsource/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-700-italic.woff2?url';
import mono400 from '@fontsource/atkinson-hyperlegible-mono/files/atkinson-hyperlegible-mono-latin-400-normal.woff2?url';
import mono700 from '@fontsource/atkinson-hyperlegible-mono/files/atkinson-hyperlegible-mono-latin-700-normal.woff2?url';
import jersey400 from '@fontsource/jersey-10/files/jersey-10-latin-400-normal.woff2?url';
import silkscreen400 from '@fontsource/silkscreen/files/silkscreen-latin-400-normal.woff2?url';

interface Face {
  family: string;
  weight: number;
  style: 'normal' | 'italic';
  display: 'swap' | 'optional';
  url: string;
  preload?: boolean;
}

const FACES: Face[] = [
  { family: 'Jersey 10', weight: 400, style: 'normal', display: 'optional', url: jersey400, preload: true },
  { family: 'Silkscreen', weight: 400, style: 'normal', display: 'optional', url: silkscreen400, preload: true },
  { family: 'Atkinson Hyperlegible Next', weight: 400, style: 'normal', display: 'swap', url: atkinson400, preload: true },
  { family: 'Atkinson Hyperlegible Next', weight: 400, style: 'italic', display: 'swap', url: atkinson400i },
  { family: 'Atkinson Hyperlegible Next', weight: 700, style: 'normal', display: 'swap', url: atkinson700 },
  { family: 'Atkinson Hyperlegible Next', weight: 700, style: 'italic', display: 'swap', url: atkinson700i },
  { family: 'Atkinson Hyperlegible Mono', weight: 400, style: 'normal', display: 'swap', url: mono400 },
  { family: 'Atkinson Hyperlegible Mono', weight: 700, style: 'normal', display: 'swap', url: mono700 },
];

export const FONT_FACE_CSS: string = FACES.map(
  (f) =>
    `@font-face{font-family:'${f.family}';font-style:${f.style};font-weight:${f.weight};font-display:${f.display};src:url(${f.url}) format('woff2')}`,
).join('');

export const FONT_PRELOADS: readonly string[] = FACES.filter((f) => f.preload).map((f) => f.url);

/** Font credits for the footer and the licence file. */
export const FONT_CREDITS: readonly string[] = [...new Set(FACES.map((f) => f.family))];
