// Types for check-design-data.mjs, for the tests.
export function ontologyLayers(yamlText: string): string[];
export function checkLayers(layers: string[], tokensCss: string, glyphNames: string[]): string[];
export function checkGrids(
  sets: { label: string; grids: Record<string, readonly string[]>; size?: [number, number] & { allow?: string[] } }[],
): string[];
export function governanceStatuses(text: string): string[];
export function sourceStatuses(files: { path: string; text: string }[]): Map<string, string>;
export function checkStatuses(values: Map<string, string>, styles: Record<string, string>): string[];
export function findHandTypedCounts(files: { path: string; text: string }[], counts: number[]): string[];
export function withoutFences(text: string): string;
export function neededGlyphKeys(sources: {
  standards: { path: string; text: string }[];
  profiles: { stem: string; doc: unknown }[];
  catalogSchema: unknown;
  edgeTypes: string[];
}): { key: string; from: string }[];
export function checkGlyphKeys(
  needed: { key: string; from: string }[],
  aliases?: Readonly<Record<string, string>>,
  grids?: Readonly<Record<string, readonly string[]>>,
): string[];
export function findHexColours(files: { path: string; text: string }[]): string[];
export function statusGlyphKeys(values: Map<string, string>, styles: Record<string, string>): { key: string; from: string }[];
