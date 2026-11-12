// The Markdown copy of every page. A page rendered from one Markdown source
// gets that source with its links pointed at other pages' copies; a generated
// page gets Markdown written from the same data its HTML uses. Every template
// is handled here, so a new template fails the build until it has a copy.
import { loadOntology } from '../data/ontology';
import { loadProfiles } from '../data/profiles';
import { loadVersions } from '../data/versions';
import { loadWorkflows } from '../data/workflows';
import { sourceMeta } from '../lib/listing';
import { readRepoFile } from '../lib/repo';
import type { Route } from '../lib/routes';
import { capabilitiesIndexTwin, capabilityTwin, layerTwin } from './capabilities';
import { domainsIndexTwin, domainTwin } from './domains';
import { homeTwin } from './home';
import { listingTwin } from './listing';
import { blocks, markdownCopy } from './md';
import { specFigureBlocks } from './edges-spec';
import { proseFigureBlocks } from './prose';
import { citationTwin, diagnosticsTwin, edgeTypesTwin, rfcsIndexTwin, schemasTwin } from './reference';
import type { Twin } from './types';
import { workflowsIndexTwin, workflowTwin } from './workflows';

export type { Twin };

const cache = new Map<string, Promise<Twin>>();

/** The Markdown copy of a route's page, built once per build. */
export function twinFor(route: Route): Promise<Twin> {
  let t = cache.get(route.url);
  if (!t) {
    t = buildTwin(route);
    cache.set(route.url, t);
  }
  return t;
}

async function buildTwin(route: Route): Promise<Twin> {
  switch (route.template) {
    case 'prose':
    case 'spec':
    case 'rfc':
    case 'skill':
    case 'raw': {
      const source = route.source!;
      const meta = await sourceMeta(route);
      const title = route.template === 'spec' ? route.title : meta.title;
      const copy = markdownCopy(source, readRepoFile(source), { sourceNote: true, title: meta.title });
      // The current Standard's site-drawn figures add their text equivalents (visual spec 3.9),
      // and so do the prose and RFC figures whose words are not in the source (3.10).
      const figures = route.template === 'spec' && source === loadVersions().standard.current.source ? specFigureBlocks() : await proseFigureBlocks(route);
      return { title, description: meta.description, markdown: figures.length > 0 ? blocks(copy, ...figures) : copy };
    }
    case 'home':
      return homeTwin();
    case 'listing':
      return listingTwin(route);
    case 'capabilities-index':
      return capabilitiesIndexTwin();
    case 'capability': {
      const cap = loadOntology().capabilities.find((c) => route.source === `skills/${c.id}/SKILL.md`);
      if (!cap) throw new Error(`twins: no capability for ${route.url}`);
      return capabilityTwin(cap.id, route.source!);
    }
    case 'layer': {
      const layer = loadOntology().layers.find((l) => `/layers/${l.slug}/` === route.url);
      if (!layer) throw new Error(`twins: no layer for ${route.url}`);
      return layerTwin(layer.id);
    }
    case 'workflows-index':
      return workflowsIndexTwin();
    case 'workflow': {
      const wf = loadWorkflows().all.find((w) => `/workflows/${w.slug}/` === route.url);
      if (!wf) throw new Error(`twins: no workflow for ${route.url}`);
      return workflowTwin(wf.id);
    }
    case 'domains-index': {
      const meta = await sourceMeta(route);
      return domainsIndexTwin(route.source!, meta.description);
    }
    case 'domain': {
      const d = loadProfiles().find((p) => `/domains/${p.key}/` === route.url);
      if (!d) throw new Error(`twins: no profile for ${route.url}`);
      const meta = d.readme ? await sourceMeta({ ...route, source: d.readme }) : null;
      return domainTwin(d.key, d.description || meta?.description || null);
    }
    case 'edge-types': {
      const meta = await sourceMeta(route);
      return edgeTypesTwin(route.source!, meta.title, meta.description);
    }
    case 'diagnostics':
      return diagnosticsTwin();
    case 'schemas':
      return schemasTwin();
    case 'rfcs-index':
      return rfcsIndexTwin();
    case 'citation':
      return citationTwin();
    case 'not-found':
      throw new Error('twins: the 404 page has no Markdown copy');
    default: {
      const never: never = route.template;
      throw new Error(`twins: no Markdown copy for template ${String(never)}`);
    }
  }
}
