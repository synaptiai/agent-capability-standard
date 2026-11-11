// The Markdown copy of the home page, from the same content module the page uses.
import { loadOntology, capabilitiesOfLayer } from '../data/ontology';
import { coverage, faq, getStarted, HOME_H1, homeDescription, inlineText, opening, principles, story, WHY, type Card, type HomeLink } from '../lib/home';
import { kebab } from '../lib/routes';
import { blocks, code, fence, mdLink, mdUrl } from './md';
import type { Twin } from './types';

/** A home link as Markdown: site pages go to their copies, other URLs stay. */
function link(l: HomeLink): string {
  return l.url.startsWith('/') ? `[${l.text}](${mdUrl(l.url)})` : `[${l.text}](${l.url})`;
}

function cards(list: (Card & { extra?: HomeLink })[]): string {
  return list.map((c) => `- **${c.title}.** ${c.line} ${link(c.link)}${c.extra ? `, ${link(c.extra)}` : ''}`).join('\n');
}

/** Indent continuation lines so they stay inside a numbered list item. */
function indent(md: string): string {
  return md
    .split('\n')
    .map((l, i) => (l.trim() === '' ? '' : i === 0 && !md.startsWith('-') ? l : `   ${l}`))
    .join('\n');
}

export function homeTwin(): Twin {
  const o = opening();
  const p = principles();
  const s = story();
  const cov = coverage();
  const f = faq();
  const g = getStarted();
  const ontology = loadOntology();
  const summary = inlineText(o.summary);
  const markdown = blocks(
    `# ${HOME_H1}`,
    summary,
    o.versionLine,
    o.links.map(link).join(' | '),
    `${o.install.label}:`,
    fence('sh', o.install.commands.join('\n')),
    '## Design principles',
    `${p.intro} From [section 3 of the Standard](${mdUrl(p.sectionUrl)}).`,
    p.items.map((i, n) => `${n + 1}. **${i.title}.**${i.markdown.startsWith('-') ? '\n\n' : ' '}${indent(i.markdown)}`).join('\n\n'),
    '## Why a standard',
    WHY,
    `## How a workflow is built: ${code(s.workflow.id)}`,
    s.steps.map((st) => `${st.beat}. **${st.title}** ${inlineText(st.text)}`).join('\n'),
    '## The capabilities',
    ...ontology.layers.map(
      (l) => `- ${mdLink(l.id, `/layers/${l.slug}/`)}: ${capabilitiesOfLayer(ontology, l.id).map((c) => mdLink(code(c.id), `/capabilities/${kebab(c.id)}/`)).join(', ')}`,
    ),
    `How the set was derived: ${mdLink('First-principles derivation', '/background/methodology/first-principles-reassessment/')}.`,
    '## What the standard covers',
    '### The standard',
    cards(cov.standard),
    '### Reference data',
    cards(cov.data),
    '### Tools',
    cards(cov.tools),
    '## Questions',
    f.items.map((i) => `### ${i.question}\n\n${inlineText(i.answer)}`).join('\n\n'),
    link(f.more),
    '## Get started',
    'For coding agents. Paste this into Claude Code, Codex, Cursor or another coding agent:',
    fence('text', g.prompt),
    cards(g.cards),
  );
  return { title: 'Agent Capability Standard', description: homeDescription(), markdown };
}
