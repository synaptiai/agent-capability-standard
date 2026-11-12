// The stub that joins a row to the rail in the stacked relationship figures
// (F-C1 on capability pages, F-L2 on layer pages): a 2px run from the rail
// at x = 11 to the row, with chevrons that give the direction. "into" points
// at the rail (towards the item in the middle), "out" at the row, "both" at
// each end, and "either" (and the middle item's own stub) at neither.
import { chevron, run, type FigRect } from './lines';

export const STUB_W = 32;
export const STUB_H = 14;

export function railStub(kind: 'into' | 'out' | 'both' | 'either' | 'centre'): FigRect[] {
  const y = STUB_H / 2;
  const line = run(11, y, STUB_W, y, 'ink-2');
  const left = chevron(12, y, 'left', 'ink-2');
  const right = chevron(STUB_W - 1, y, 'right', 'ink-2');
  if (kind === 'into') return [...line, ...left];
  if (kind === 'out') return [...line, ...right];
  if (kind === 'both') return [...line, ...left, ...right];
  return line;
}
