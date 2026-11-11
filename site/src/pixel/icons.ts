// The favicon (SVG and PNG) and the static social image, drawn from the mark
// with the colours in tokens.css.
import tokensCss from '../styles/tokens.css?raw';
import { parseTokens, resolveColor } from '../../scripts/check-contrast.mjs';
import { parseGrid, toRects, type Paint } from './grid';
import { LETTERS } from './glyphs';
import { Raster, encodePng, type Rgb } from './png';
import { MARK_GRID } from './svg';

type Theme = 'light' | 'dark';

const TOKENS = parseTokens(tokensCss);
if (TOKENS.problems.length > 0) throw new Error(`icons: tokens.css: ${TOKENS.problems.join('; ')}`);

function rgb(theme: Theme, expr: string): Rgb {
  const [r, g, b] = resolveColor(expr, TOKENS[theme]).map(Math.round) as [number, number, number];
  return [r, g, b];
}

const hex = (c: Rgb) => `#${c.map((x) => x.toString(16).padStart(2, '0')).join('')}`;

/** The colours a grid paint takes in a theme, plus the page and frame colours. */
export function iconColours(theme: Theme): Record<Paint, Rgb> & { page: Rgb; frame: Rgb } {
  return {
    fg: rgb(theme, 'var(--ink)'),
    fg2: rgb(theme, 'color-mix(in srgb, var(--ink) 35%, var(--bg))'),
    accent: rgb(theme, 'var(--accent)'),
    bg: rgb(theme, 'var(--bg)'),
    page: rgb(theme, 'var(--bg)'),
    frame: rgb(theme, 'var(--line)'),
  };
}

/** Favicon size: the mark at 2px a cell, a 2px gap and a 2px frame on each side. */
export const FAVICON_SIZE = MARK_GRID.w * 2 + 8;

export function faviconSvg(): string {
  const rects = toRects(MARK_GRID);
  const css = (theme: Theme) => {
    const c = iconColours(theme);
    return `.p{fill:${hex(c.page)}}.l{fill:${hex(c.frame)}}.fg{fill:${hex(c.fg)}}.fg2{fill:${hex(c.fg2)}}.accent{fill:${hex(c.accent)}}.bg{fill:${hex(c.bg)}}`;
  };
  const s = FAVICON_SIZE;
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${s} ${s}" width="${s}" height="${s}" shape-rendering="crispEdges">`,
    `<style>${css('light')}@media (prefers-color-scheme: dark){${css('dark')}}</style>`,
    `<rect class="l" width="${s}" height="${s}"/>`,
    `<rect class="p" x="2" y="2" width="${s - 4}" height="${s - 4}"/>`,
    `<g transform="translate(4 4) scale(2)">`,
    rects.map((r) => `<rect class="${r.paint}" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}"/>`).join(''),
    `</g></svg>`,
  ].join('');
}

function drawGrid(raster: Raster, rows: readonly string[], id: string, x: number, y: number, scale: number, colours: Record<Paint, Rgb>): void {
  for (const r of toRects(parseGrid(id, rows))) {
    raster.fill(x + r.x * scale, y + r.y * scale, r.w * scale, r.h * scale, colours[r.paint]);
  }
}

export function faviconPng(): Buffer {
  const c = iconColours('light');
  const s = FAVICON_SIZE;
  const raster = new Raster(s, s, c.frame);
  raster.fill(2, 2, s - 4, s - 4, c.page);
  drawGrid(raster, MARK_GRID.rows, 'mark', 4, 4, 2, c);
  return encodePng(raster);
}

export const OG_WIDTH = 1200;
export const OG_HEIGHT = 630;

/** The social image: always dark, a dot grid, a frame, the mark and "ACS" in pixel letters. */
export function ogPng(): Buffer {
  const c = iconColours('dark');
  const dot = rgb('dark', 'color-mix(in srgb, var(--ink) 6%, var(--bg))');
  const raster = new Raster(OG_WIDTH, OG_HEIGHT, c.page);
  for (let y = 12; y < OG_HEIGHT; y += 12) for (let x = 12; x < OG_WIDTH; x += 12) raster.fill(x, y, 2, 2, dot);
  const inset = 24;
  const t = 4;
  raster.fill(inset, inset, OG_WIDTH - 2 * inset, t, c.frame);
  raster.fill(inset, OG_HEIGHT - inset - t, OG_WIDTH - 2 * inset, t, c.frame);
  raster.fill(inset, inset, t, OG_HEIGHT - 2 * inset, c.frame);
  raster.fill(OG_WIDTH - inset - t, inset, t, OG_HEIGHT - 2 * inset, c.frame);

  const scale = 16;
  const markW = MARK_GRID.w * scale;
  const markH = MARK_GRID.h * scale;
  const word = ['A', 'C', 'S'];
  const letterW = 5 * scale;
  const letterH = 7 * scale;
  const gap = scale;
  const total = markW + 4 * scale + word.length * letterW + (word.length - 1) * gap;
  const x0 = Math.round((OG_WIDTH - total) / 2);
  const y0 = Math.round((OG_HEIGHT - markH) / 2);
  drawGrid(raster, MARK_GRID.rows, 'mark', x0, y0, scale, c);
  let x = x0 + markW + 4 * scale;
  for (const ch of word) {
    drawGrid(raster, LETTERS[ch]!, `letter ${ch}`, x, y0 + (markH - letterH) / 2, scale, c);
    x += letterW + gap;
  }
  return encodePng(raster);
}

/** The page background of a theme, for the browser chrome colour. */
export function pageColour(theme: Theme): string {
  return hex(rgb(theme, 'var(--bg)'));
}
