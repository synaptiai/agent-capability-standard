// One collection holds every Markdown source the site renders. It loads from
// the repository root, its pattern list is the exact set of sources in the
// route table (so untracked drafts and the docs/schemas symlink never get in),
// and each entry's id is its repo path, e.g. 'docs/domains/healthcare/README.md'.
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';
import { markdownSources } from './lib/routes';

const docs = defineCollection({
  loader: glob({
    base: '..',
    pattern: markdownSources(),
    generateId: ({ entry }) => entry,
    retainBody: true,
  }),
  // Only the SKILL.md files have frontmatter. The page never takes its layer
  // from here; the ontology decides that.
  schema: z
    .object({
      name: z.string().optional(),
      description: z.string().optional(),
      'argument-hint': z.string().optional(),
      'allowed-tools': z.string().optional(),
      'disable-model-invocation': z.boolean().optional(),
      'user-invocable': z.boolean().optional(),
      context: z.string().optional(),
      agent: z.string().optional(),
      layer: z.string().optional(),
      hooks: z.unknown().optional(),
    })
    .loose(),
});

export const collections = { docs };
