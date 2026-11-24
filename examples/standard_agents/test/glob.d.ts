// Vite's import.meta.glob, which vitest provides: the tests read the
// conformance fixtures in place.
interface ImportMeta {
  glob<T = unknown>(pattern: string, options: { eager: true; import: 'default'; query?: '?raw' }): Record<string, T>;
}
