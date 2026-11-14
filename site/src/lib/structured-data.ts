// The home page's JSON-LD (schema.org): the web site, its publisher, the
// standard as a written work, and the Claude Code plugin as software. Names,
// versions, counts, the license and the keywords come from the repository's
// files; the publisher's name and addresses are the only values written here.
// There is no email address, phone number or postal address: contact is
// through the repository's issues.
import { loadCounts } from '../data/counts';
import { loadOntology } from '../data/ontology';
import { loadVersions } from '../data/versions';
import { homeDescription } from './home';
import { SITE_ORIGIN } from './origin';
import { GITHUB_BASE, readRepoFile } from './repo';

export const PUBLISHER = {
  name: 'Synapti',
  url: 'https://synapti.ai',
  github: 'https://github.com/synaptiai',
} as const;

interface PluginJson {
  name: string;
  description: string;
  license: string;
  keywords: string[];
}

function pluginJson(): PluginJson {
  const p = JSON.parse(readRepoFile('.claude-plugin/plugin.json')) as Partial<PluginJson>;
  if (typeof p.description !== 'string' || typeof p.license !== 'string' || !Array.isArray(p.keywords)) {
    throw new Error('structured-data: plugin.json lacks a description, license or keywords');
  }
  return p as PluginJson;
}

/** Keywords: the plugin's keywords, then the layer names, without repeats. */
export function keywords(): string[] {
  const words = ['agent capability standard', 'grounded agency', 'AI agents', 'capability ontology', 'workflow validation'];
  words.push(...pluginJson().keywords, ...loadOntology().layers.map((l) => l.id.toLowerCase()));
  return [...new Set(words)];
}

export function homeGraph(): Record<string, unknown> {
  const v = loadVersions();
  const c = loadCounts();
  const plugin = pluginJson();
  const license = `https://spdx.org/licenses/${plugin.license}.html`;
  const org = `${SITE_ORIGIN}/#publisher`;
  const std = v.standard.current;
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${SITE_ORIGIN}/#website`,
        url: `${SITE_ORIGIN}/`,
        name: 'Agent Capability Standard',
        description: homeDescription(),
        inLanguage: 'en',
        publisher: { '@id': org },
      },
      {
        '@type': 'Organization',
        '@id': org,
        name: PUBLISHER.name,
        url: PUBLISHER.url,
        sameAs: [PUBLISHER.github],
        contactPoint: {
          '@type': 'ContactPoint',
          contactType: 'technical support',
          url: `${GITHUB_BASE}/issues`,
          availableLanguage: 'en',
        },
        knowsAbout: keywords(),
      },
      {
        '@type': 'CreativeWork',
        '@id': `${SITE_ORIGIN}/#standard`,
        name: 'Agent Capability Standard',
        alternateName: 'Grounded Agency',
        description: homeDescription(),
        url: `${SITE_ORIGIN}/spec/${std.version}/`,
        version: std.version,
        creativeWorkStatus: std.status,
        ...(std.date ? { datePublished: std.date } : {}),
        license,
        keywords: keywords().join(', '),
        isAccessibleForFree: true,
        inLanguage: 'en',
        publisher: { '@id': org },
        sameAs: [GITHUB_BASE],
        about: { '@type': 'Thing', name: `${c.capabilityCount} agent capabilities in ${c.layerCount} layers` },
      },
      {
        '@type': 'SoftwareApplication',
        '@id': `${SITE_ORIGIN}/#plugin`,
        name: 'Agent Capability Standard plugin for Claude Code',
        description: plugin.description,
        url: `${SITE_ORIGIN}/`,
        applicationCategory: 'DeveloperApplication',
        softwareVersion: v.plugin,
        license,
        keywords: keywords().join(', '),
        isAccessibleForFree: true,
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
        publisher: { '@id': org },
        // Its listing in the skills.sh directory (checked to exist on 2026-11-14).
        sameAs: [GITHUB_BASE, `https://skills.sh/${GITHUB_BASE.replace('https://github.com/', '')}`],
        isBasedOn: { '@id': `${SITE_ORIGIN}/#standard` },
      },
    ],
  };
}

/** The graph as script text: JSON with `<` escaped, so no string in it can close the script element. */
export function homeJsonLd(): string {
  return JSON.stringify(homeGraph()).replace(/</g, '\\u003c');
}
