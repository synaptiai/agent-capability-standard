// The "Copy page as Markdown" button. Runs in the browser too.
//
// The clipboard write is started during the click, with the fetch passed in
// as a promise (ClipboardItem), because Safari refuses a clipboard write made
// after awaiting a network request. Where ClipboardItem is missing, the text
// is fetched first and written with writeText.

export interface CopyDeps {
  fetch: (url: string) => Promise<{ ok: boolean; status: number; text(): Promise<string> }>;
  clipboard: {
    write?: (items: unknown[]) => Promise<void>;
    writeText: (text: string) => Promise<void>;
  };
  /** ClipboardItem, when the browser has it. */
  makeItem?: (data: Record<string, Promise<Blob>>) => unknown;
}

export const COPY_MESSAGES = {
  copied: 'Copied',
  fetchFailed: 'Could not load the Markdown. Use View as Markdown instead.',
  blocked: 'The browser did not allow copying. Use View as Markdown instead.',
} as const;

/** Copy the Markdown at `url`; returns the message to show. */
export async function copyMarkdown(url: string, deps: CopyDeps): Promise<string> {
  const text = deps.fetch(url).then((res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.text();
  });
  // Settle here too, so a failed fetch is never an unhandled rejection.
  const fetched = text.then(
    () => true,
    () => false,
  );
  try {
    if (deps.makeItem && deps.clipboard.write) {
      const blob = text.then((t) => new Blob([t], { type: 'text/plain' }));
      blob.catch(() => {}); // handled through `fetched` below
      const item = deps.makeItem({ 'text/plain': blob });
      await deps.clipboard.write([item]);
    } else {
      await deps.clipboard.writeText(await text);
    }
    return COPY_MESSAGES.copied;
  } catch {
    return (await fetched) ? COPY_MESSAGES.blocked : COPY_MESSAGES.fetchFailed;
  }
}
