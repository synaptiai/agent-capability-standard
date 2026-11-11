// The copy button's outcomes. Each case fakes the browser: the fetch result
// and whether the clipboard accepts the write.
import { describe, expect, it } from 'vitest';
import { COPY_MESSAGES, copyMarkdown, type CopyDeps } from '../src/lib/copy-markdown';

const okFetch: CopyDeps['fetch'] = async () => ({ ok: true, status: 200, text: async () => '# Page\n' });
const notFound: CopyDeps['fetch'] = async () => ({ ok: false, status: 404, text: async () => '' });
const offline: CopyDeps['fetch'] = async () => {
  throw new TypeError('Failed to fetch');
};
const blocked = async () => {
  throw new DOMException('denied', 'NotAllowedError');
};

describe('copy page as Markdown', () => {
  it('starts the clipboard write before the fetch settles, when ClipboardItem exists', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const order: string[] = [];
    const written: string[] = [];
    const result = copyMarkdown('/a/index.md', {
      fetch: async () => {
        await gate;
        order.push('fetched');
        return { ok: true, status: 200, text: async () => '# Page\n' };
      },
      clipboard: {
        write: async (items) => {
          order.push('write');
          const data = (items[0] as { data: Record<string, Promise<Blob>> }).data;
          written.push(await (await data['text/plain']!).text());
        },
        writeText: async () => {
          throw new Error('not used');
        },
      },
      makeItem: (data) => ({ data }),
    });
    release();
    expect(await result).toBe(COPY_MESSAGES.copied);
    expect(order).toEqual(['write', 'fetched']);
    expect(written).toEqual(['# Page\n']);
  });

  it('falls back to writeText where ClipboardItem is missing', async () => {
    const written: string[] = [];
    const msg = await copyMarkdown('/a/index.md', { fetch: okFetch, clipboard: { writeText: async (t) => void written.push(t) } });
    expect(msg).toBe(COPY_MESSAGES.copied);
    expect(written).toEqual(['# Page\n']);
  });

  it('tells a failed fetch apart from a blocked clipboard, and points to View as Markdown', async () => {
    for (const fetch of [notFound, offline]) {
      expect(await copyMarkdown('/a/index.md', { fetch, clipboard: { writeText: async () => {} } })).toBe(COPY_MESSAGES.fetchFailed);
      expect(
        await copyMarkdown('/a/index.md', { fetch, clipboard: { write: blocked, writeText: blocked }, makeItem: (d) => d }),
      ).toBe(COPY_MESSAGES.fetchFailed);
    }
    expect(await copyMarkdown('/a/index.md', { fetch: okFetch, clipboard: { writeText: blocked } })).toBe(COPY_MESSAGES.blocked);
    expect(
      await copyMarkdown('/a/index.md', { fetch: okFetch, clipboard: { write: blocked, writeText: blocked }, makeItem: (d) => d }),
    ).toBe(COPY_MESSAGES.blocked);
    for (const m of [COPY_MESSAGES.fetchFailed, COPY_MESSAGES.blocked]) expect(m).toMatch(/View as Markdown/);
  });
});
