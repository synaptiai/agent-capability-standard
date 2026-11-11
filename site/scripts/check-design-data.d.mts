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
