// Word breaks for site search (Pagefind), applied to the built pages.
//
// Pagefind starts a new word at the end of a td, li, p, heading
// or div, but not at the end of a th, caption, dt, dd, summary or figcaption.
// Astro's compressed HTML leaves no whitespace between tags, so a table's
// caption and header cells, or a definition term and its value, are indexed
// as one word ("Inputs of checkpointFieldTypeRequired"). After the build,
// a space goes after each of those closing tags when another tag follows at
// once. Whitespace in those places is not drawn: table layout drops it
// between cells, and dt, dd, summary and figcaption are blocks.
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const UNBROKEN = /<\/(th|caption|dt|dd|summary|figcaption)>(?=<)/g;

/** The page with a space after each closing tag Pagefind does not break words on. */
export function spaceForSearch(html: string): string {
  return html.replace(UNBROKEN, '</$1> ');
}

/** Applies spaceForSearch to every .html file under `dir`; returns how many changed. */
export function spaceBuiltPages(dir: string): number {
  let changed = 0;
  const walk = (d: string) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.html')) {
        const before = readFileSync(p, 'utf8');
        const after = spaceForSearch(before);
        if (after !== before) {
          writeFileSync(p, after);
          changed++;
        }
      }
    }
  };
  walk(dir);
  return changed;
}
