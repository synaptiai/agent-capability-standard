// The Markdown copy of the home page, from the same content module the page uses.
import { loadOntology, capabilitiesOfLayer } from '../data/ontology';
import {
  AGENTS_HEADING,
  AGENTS_LINE,
  CAPABILITIES_DERIVED,
  CAPABILITIES_INTRO,
  coverage,
  faq,
  gallery,
  galleryCaption,
  GALLERY_FIG_TITLE,
  GALLERY_INTRO,
  getStarted,
  HOME_H1,
  homeDescription,
  inlineText,
  opening,
  principles,
  story,
  storyCaption,
  STORY_FIG_TITLE,
  STORY_HEADING,
  storyIntro,
  TABLE_FIG_TITLE,
  tableCaption,
  WHY,
  WORKFLOWS_HEADING,
  type Card,
  type HomeLink,
  type LinkSentence,
} from '../lib/home';
import { kebab } from '../lib/routes';
import { blocks, code, fence, figure, mdLink, mdUrl, table } from './md';
import type { Twin } from './types';

/** A home link as Markdown: site pages go to their copies, other URLs stay. */
function link(l: HomeLink): string {
  return l.url.startsWith('/') ? `[${l.text}](${mdUrl(l.url)})` : `[${l.text}](${l.url})`;
}

function sentence(x: LinkSentence): string {
  return `${x.before}${link({ text: x.link.code ? code(x.link.text) : x.link.text, url: x.link.url })}${x.after}`;
}

function cards(list: (Card & { extra?: HomeLink })[]): string {
  return list
    .map((c) => `- **${c.title}${c.count === undefined ? '' : ` (${c.count})`}.** ${c.line} ${link(c.link)}${c.extra ? `, ${link(c.extra)}` : ''}`)
    .join('\n');
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
    '## Why a standard',
    WHY,
    `## ${STORY_HEADING}`,
    sentence(storyIntro()),
    figure(STORY_FIG_TITLE, storyCaption(), s.steps.map((st) => `${st.beat}. **${st.title}** ${inlineText(st.text)}`).join('\n')),
    '## What the standard covers',
    '### The standard',
    cards(cov.standard),
    '### Reference data',
    cards(cov.data),
    '### Tools',
    cards(cov.tools),
    '## The capabilities',
    `${inlineText(CAPABILITIES_INTRO)} ${link(CAPABILITIES_DERIVED)}.`,
    figure(
      TABLE_FIG_TITLE,
      tableCaption(),
      ontology.layers
        .map(
          (l) => `- ${mdLink(l.id, `/layers/${l.slug}/`)}: ${capabilitiesOfLayer(ontology, l.id).map((c) => mdLink(code(c.id), `/capabilities/${kebab(c.id)}/`)).join(', ')}`,
        )
        .join('\n'),
    ),
    '## Design principles',
    `${p.intro} ${sentence(p.source)}`,
    p.items.map((i, n) => `${n + 1}. **${i.title}.**${i.markdown.startsWith('-') ? '\n\n' : ' '}${indent(i.markdown)}`).join('\n\n'),
    `## ${WORKFLOWS_HEADING}`,
    GALLERY_INTRO,
    figure(
      GALLERY_FIG_TITLE,
      galleryCaption(),
      table(
        ['Workflow', 'Group', 'Steps', 'Checkpoints', 'Steps with gates', 'Risk'],
        gallery().flatMap((g) =>
          g.items.map((i) => [mdLink(code(i.workflow.id), `/workflows/${i.workflow.slug}/`), g.label, String(i.steps), String(i.checkpoints), String(i.gated), i.workflow.risk]),
        ),
      ),
    ),
    '## Get started',
    `### ${AGENTS_HEADING}`,
    AGENTS_LINE,
    fence('text', g.prompt),
    g.cards.map((c, n) => `${n + 1}. **${c.title}.** ${c.line} ${link(c.link)}${c.extra ? `, ${link(c.extra)}` : ''}`).join('\n'),
    '## Questions',
    f.items.map((i) => `### ${i.question}\n\n${inlineText(i.answer)}`).join('\n\n'),
    link(f.more),
  );
  return { title: 'Agent Capability Standard', description: homeDescription(), markdown };
}
