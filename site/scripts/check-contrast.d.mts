// Types for check-contrast.mjs, for the tests.
export type Rgb = [number, number, number];
export interface Pair {
  kind: 'text' | 'edge';
  label: string;
  fg?: string;
  bg?: string;
  anyOf?: { fg: string; bg: string }[];
}
export const TEXT_MIN: number;
export const EDGE_MIN: number;
export function ruleDeclarations(css: string, selector: string): Record<string, string> | null;
export function parseTokens(css: string): { light: Record<string, string>; dark: Record<string, string>; problems: string[] };
export function resolveColor(expr: string, tokens: Record<string, string>): Rgb;
export function contrast(a: Rgb, b: Rgb): number;
export function pairs(tokens: Record<string, string>): Pair[];
export function pairRatio(pair: Pair, tokens: Record<string, string>): number;
export function checkContrast(css: string): { checked: number; failures: string[]; problems: string[] };
export const FIGURE_COLOUR_EXCEPTIONS: Readonly<Record<string, string>>;
