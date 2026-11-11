// The licences of the self-hosted fonts, served with the site as the SIL
// Open Font License asks.
import atkinsonMono from '@fontsource/atkinson-hyperlegible-mono/LICENSE?raw';
import atkinsonNext from '@fontsource/atkinson-hyperlegible-next/LICENSE?raw';
import jersey from '@fontsource/jersey-10/LICENSE?raw';
import silkscreen from '@fontsource/silkscreen/LICENSE?raw';

const LICENCES: [string, string][] = [
  ['Jersey 10', jersey],
  ['Silkscreen', silkscreen],
  ['Atkinson Hyperlegible Next', atkinsonNext],
  ['Atkinson Hyperlegible Mono', atkinsonMono],
];

export function GET(): Response {
  const text = LICENCES.map(([name, body]) => `${name}\n${'='.repeat(name.length)}\n\n${body.trim()}\n`).join('\n\n');
  return new Response(text, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
