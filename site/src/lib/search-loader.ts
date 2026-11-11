// Loading the Pagefind index in the browser. Runs in the browser too.

/**
 * A loader that imports `url` once and shares the attempt between callers.
 * After a failure (offline, a flaky connection, a blocker), the next call
 * tries again, with a query added so a browser that keeps a failed module
 * import does not hand back the same failure.
 */
export function retryingLoader<T>(url: string, importer: (url: string) => Promise<T>): () => Promise<T | null> {
  let loading: Promise<T | null> | null = null;
  let failures = 0;
  return () => {
    loading ??= importer(failures === 0 ? url : `${url}?retry=${failures}`).catch(() => {
      failures++;
      loading = null;
      return null;
    });
    return loading;
  };
}

/** What the search dialog says when the index could not load. */
export function loadFailedMessage(dev: boolean): string {
  return dev
    ? 'Search works on the built site only. Run npm run build, then npm run preview.'
    : 'Search could not load. Check your connection and try again.';
}
