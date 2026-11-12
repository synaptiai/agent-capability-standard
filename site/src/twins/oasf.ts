// The text equivalent of F-O1 (visual spec 3.10.14) in the OASF safety
// proposal's Markdown copy: the same rows as the figure, as a table.
import { loadOasfMapping } from '../data/oasf';
import { MAPPING_WORDS, oasfCaption } from '../plugins/rehype-prose-figures';
import { cell, code, figure, table } from './md';

export function oasfMapTwin(): string {
  const m = loadOasfMapping();
  return figure(
    'OASF categories mapped to capabilities',
    oasfCaption(),
    table(
      ['OASF category', 'Mapping', 'Capabilities'],
      m.rows.map((r) => [cell(`${r.code} ${r.name}`), MAPPING_WORDS[r.mappingType], r.capabilities.map(code).join(', ')]),
    ),
  );
}
