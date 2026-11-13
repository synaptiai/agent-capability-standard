// The small figure parts as hast elements, for rehype plugins that add them
// to rendered Markdown (chapter icons on Standard H2s, marks and bars in
// table cells, tiles in list items). A rehype step cannot render an Astro
// component, so these build the same markup as PixelGlyph.astro,
// MiniTile.astro and PixelBar.astro, with the same classes from
// figures.css. Keep the two forms in step; test/figures.test.ts compares them.
//
// - glyphElement(name, { scale = 2, label, layer, className }): an inline
//   <svg> of rects. Decorative (aria-hidden) unless `label` is given.
// - miniTileElement(id, { size = 24, relation, link = true }): a small
//   periodic tile, a link to the capability unless `link` is false.
// - pixelBarElement(value, max, { min = 0, digits = 0, label, hideValue }):
//   a bar with its value printed to the right.
import type { Element, ElementContent } from 'hast';
import { loadOntology } from '../data/ontology';
import { capabilityHref } from '../lib/generated';
import { capabilitySymbol } from '../lib/views';
import { glyph, placedRects } from './svg';

const el = (tagName: string, properties: Element['properties'], children: ElementContent[] = []): Element => ({
  type: 'element',
  tagName,
  properties,
  children,
});
const text = (value: string): ElementContent => ({ type: 'text', value });

export function glyphElement(
  name: string,
  { scale = 2, label, layer, className }: { scale?: number; label?: string; layer?: string; className?: string } = {},
): Element {
  if (!Number.isInteger(scale) || scale < 1) throw new Error(`glyphElement: scale must be a whole number, got ${scale}`);
  const g = glyph(name);
  return el(
    'svg',
    {
      className: ['pg', ...(layer ? ['has-layer', 'pg--layer'] : []), ...(className ? [className] : [])],
      style: layer ? `--layer: var(--layer-${layer}); color: var(--layer)` : undefined,
      viewBox: `0 0 ${g.w} ${g.h}`,
      width: g.w * scale,
      height: g.h * scale,
      shapeRendering: 'crispEdges',
      focusable: 'false',
      role: label ? 'img' : undefined,
      ariaLabel: label,
      ariaHidden: label ? undefined : 'true',
      dataGlyph: name,
    },
    placedRects(g).map((r) => {
      const props: Element['properties'] = { x: String(r.x), y: String(r.y), width: r.w, height: r.h };
      return el('rect', Object.assign(props, r.attrs));
    }),
  );
}

export function miniTileElement(id: string, { size = 24, relation, link = true }: { size?: 24 | 32 | 48; relation?: string; link?: boolean } = {}): Element {
  const cap = loadOntology().capabilities.find((c) => c.id === id);
  if (!cap) throw new Error(`miniTileElement: ${id} is not a capability in the ontology`);
  const name = `${id}, ${cap.layer} layer${relation ? `: ${relation}` : ''}`;
  // As in MiniTile.astro: a linked tile is named by hidden text, not an
  // aria-label that would leave out the visible symbol (WCAG 2.5.3).
  const children: ElementContent[] = [el('span', { className: ['mini-tile__symbol'], ariaHidden: 'true', dataPagefindIgnore: '' }, [text(capabilitySymbol(id))])];
  if (link) children.push(el('span', { className: ['visually-hidden'], dataPagefindIgnore: '' }, [text(name)]));
  if (size >= 32) children.push(glyphElement(cap.layer, { scale: size === 48 ? 2 : 1, className: 'mini-tile__glyph' }));
  return el(
    link ? 'a' : 'span',
    {
      className: ['mini-tile', `mini-tile--${size}`, 'has-layer'],
      href: link ? capabilityHref(id) : undefined,
      role: link ? undefined : 'img',
      ariaLabel: link ? undefined : name,
      style: `--layer: var(--layer-${cap.layer})`,
      dataCapability: id,
      dataLayer: cap.layer,
    },
    children,
  );
}

export function pixelBarElement(
  value: number,
  max: number,
  { min = 0, digits = 0, label, hideValue = false }: { min?: number; digits?: number; label?: string; hideValue?: boolean } = {},
): Element {
  if (!(max > min)) throw new Error(`pixelBarElement: max (${max}) must be above min (${min})`);
  if (value < min || value > max) throw new Error(`pixelBarElement: ${value} is outside ${min} to ${max}`);
  const pct = `${(((value - min) / (max - min)) * 100).toFixed(3)}%`;
  const children: ElementContent[] = [
    el('span', { className: ['pixel-bar__track'], ariaHidden: 'true' }, [el('span', { className: ['pixel-bar__fill'], style: `width: ${pct}` })]),
  ];
  if (!hideValue) children.push(el('span', { className: ['pixel-bar__value'] }, [text(label ?? value.toFixed(digits))]));
  return el('span', { className: ['pixel-bar'], dataValue: value }, children);
}
