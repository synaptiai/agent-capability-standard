// Markdown copies of the generated reference pages: edge types, diagnostics,
// schemas, the RFC overview and the citation page.
import { CITATION_SOURCE, loadCitation } from '../data/citation';
import { DIAG_RS, loadDiagnostics } from '../data/diagnostics';
import { loadOntology, ONTOLOGY_SOURCE } from '../data/ontology';
import { currentStandard } from '../lib/generated';
import { githubBlobUrl, readRepoFile } from '../lib/repo';
import { allowedRfcStatuses, rfcRows } from '../lib/rfcs';
import { kebab } from '../lib/routes';
import { schemaGroups, schemaListing } from '../lib/views';
import { blocks, cell, code, fence, figure, generatedLine, markdownCopy, mdLink, mdUrl, table } from './md';
import { RFC_FIG_TITLE, rfcLanes, rfcLanesCaption, SHELF_MIN_ROWS, schemaShelves, shelfCaption, shelfTitle } from '../lib/index-figures';
import { edgeTypesFigureBlocks } from './edges-spec';
import type { Twin } from './types';

export function edgeTypesTwin(source: string, title: string, description: string | null): Twin {
  const o = loadOntology();
  const capLink = (id: string) => mdLink(code(id), `/capabilities/${kebab(id)}/`);
  const markdown = blocks(
    markdownCopy(source, readRepoFile(source), { sourceNote: true }),
    '## Edge types in the ontology',
    `${generatedLine([ONTOLOGY_SOURCE])} Ontology version ${o.version}. It has ${o.edgeTypes.length} edge types and ${o.edges.length} edges, counted as the ontology declares them, so a symmetric pair declared in both directions appears twice.`,
    table(
      ['Type', 'Description', 'Semantics', 'Transitive', 'Symmetric', 'Edges'],
      o.edgeTypes.map((t) => [code(t.id), cell(t.description), cell(t.semantics), t.transitive ? 'Yes' : 'No', t.symmetric ? 'Yes' : 'No', String(t.edges.length)]),
    ),
    '## All edges',
    ...o.edgeTypes.map((t) =>
      blocks(
        `### ${code(t.id)} (${t.edges.length})`,
        t.edges.length === 0 ? 'The ontology has no edges of this type.' : t.edges.map((e) => `- ${capLink(e.from)} to ${capLink(e.to)}`).join('\n'),
      ),
    ),
    ...edgeTypesFigureBlocks(),
  );
  return { title, description, markdown };
}

export function diagnosticsTwin(): Twin {
  const diagnostics = loadDiagnostics();
  const std = currentStandard();
  const errors = diagnostics.filter((d) => d.severity === 'error').length;
  const description = `The ${diagnostics.length} diagnostic codes of Standard ${std.version}: what each one means, its category and whether it is an error or a warning.`;
  const markdown = blocks(
    '# Diagnostics',
    `A validator or runtime reports a problem as a diagnostic code. Standard ${std.version} defines ${diagnostics.length} codes: ${errors} errors and ${diagnostics.length - errors} warnings. A workflow is valid when it has no errors; a warning marks a workflow that is accepted but suspect. Each code's severity is fixed.`,
    generatedLine([std.source, DIAG_RS]),
    table(
      ['Code', 'Name', 'Category', 'Severity', 'Description', 'Section'],
      diagnostics.map((d) => [
        d.code,
        code(d.name),
        d.category,
        d.severity,
        cell(d.descriptionMd),
        `[§${d.section}](${mdUrl(`${std.url}#${d.sectionAnchor}`)})`,
      ]),
    ),
  );
  return { title: 'Diagnostics', description, markdown };
}

export function schemasTwin(): Twin {
  const std = currentStandard();
  const entries = schemaListing(readRepoFile(std.source));
  const description = 'The schema files of the Agent Capability Standard, grouped by what the Standard requires of them, with a link to each file.';
  const markdown = blocks(
    '# Schemas',
    `These are the schema files in the repository, each linked to GitHub. Section 6.1 of the ${mdLink('Standard', `${std.url}`)} says what each required schema must hold. Workflow catalogs are listed under ${mdLink('Workflows', '/workflows/')} and domain profiles under ${mdLink('Domains', '/domains/')}.`,
    generatedLine([std.source]),
    ...(() => {
      const groups = schemaGroups(std.version);
      const shelves = schemaShelves(entries, groups);
      const maxLines = Math.max(...shelves.flatMap((sh) => sh.tiles.map((t) => t.lines)));
      return shelves.map((sh) => {
        const g = groups.find((x) => x.key === sh.key)!;
        const rows = table(
          ['File', 'What it holds', 'Lines'],
          sh.tiles.map((t) => [
            `[${code(t.entry.source)}](${githubBlobUrl(t.entry.source)})${sh.key === 'required' ? ' (required)' : ''}`,
            cell([t.entry.purpose ? `${t.entry.purpose}.` : '', t.entry.description].filter(Boolean).join(' ')),
            String(t.lines),
          ]),
        );
        return blocks(`## ${g.label}`, g.intro, sh.tiles.length >= SHELF_MIN_ROWS ? figure(shelfTitle(sh), shelfCaption(sh, maxLines), rows) : rows);
      });
    })(),
  );
  return { title: 'Schemas', description, markdown };
}

export async function rfcsIndexTwin(): Promise<Twin> {
  const allowed = allowedRfcStatuses();
  const rows = await rfcRows();
  const rfcs = rows.filter((r) => r.numbered);
  const proposals = rows.filter((r) => !r.numbered);
  const description = 'Requests for comments that propose changes to the Agent Capability Standard, with the status, target version and date of each.';
  const markdown = blocks(
    '# RFCs',
    `An RFC proposes a change to the standard. Its status is ${allowed.slice(0, -1).join(', ')} or ${allowed.at(-1)}. How an RFC is decided is described under ${mdLink('Decision-making', '/community/governance/#decision-making')} on the Governance page.`,
    (() => {
      const lanes = rfcLanes(rows);
      return figure(
        RFC_FIG_TITLE,
        rfcLanesCaption(lanes),
        lanes
          .map((l) => `- ${l.target ?? 'No target'}${l.version ? (l.url ? ' (published)' : ' (not yet published)') : ''}: ${l.rfcs.map((r) => `${mdLink(r.label, r.url)} (${r.status})`).join(', ')}`)
          .join('\n'),
      );
    })(),
    table(
      ['RFC', 'Title', 'Status', 'Target', 'Date'],
      rfcs.map((r) => [mdLink(r.label, r.url), cell(r.title), r.status, r.target ? cell(r.target) : '', r.date ?? '']),
    ),
    proposals.length > 0 && '## Proposals',
    proposals.length > 0 &&
      proposals.map((r) => `- ${mdLink(r.title, r.url)}: ${r.status}${r.date ? `, dated ${r.date}` : ''}`).join('\n'),
  );
  return { title: 'RFCs', description, markdown };
}

export function citationTwin(): Twin {
  const c = loadCitation();
  const authors = c.authors.map((a) => `${a.given} ${a.family}`).join(', ');
  const description = `How to cite ${c.title}, version ${c.version}, with the citation file and a BibTeX entry.`;
  const markdown = blocks(
    '# Cite this standard',
    c.message,
    generatedLine([CITATION_SOURCE]),
    [
      `- Title: ${c.title}`,
      `- Version: ${c.version}`,
      `- Released: ${c.date_released}`,
      `- ${c.authors.length === 1 ? 'Author' : 'Authors'}: ${authors}`,
      `- Licence: ${c.license}`,
    ].join('\n'),
    '## BibTeX',
    fence('bibtex', c.bibtex),
    '## Citation file',
    fence('yaml', readRepoFile(CITATION_SOURCE).trimEnd()),
  );
  return { title: 'Cite this standard', description, markdown };
}
