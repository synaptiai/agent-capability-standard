import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { manifestMaxima } from '@synaptiai/acs-core';
import { declaredAgents, deriveAgentManifest, ManifestDerivationError, taskRefusal } from '../src/acs/agents.js';
import { groundedTool } from '../src/acs/grounded.js';
import { lintDelegationTargets } from '../src/acs/lint.js';

const acs = (record: Record<string, unknown>) => ({ annotations: { acs: record } });

describe('agent manifests of Standard Agents agents (STANDARD 1.2.0 §5.15.1)', () => {
  it('derives a manifest from the offered tools and the subagents', () => {
    const child = deriveAgentManifest({ name: 'db-writer', tools: { write_row: acs({ capability: 'mutate' }) } });
    expect(child).toEqual({ agent: 'db-writer', standard: '1.2', ontology: '2.2', capabilities: ['mutate'] });
    const parent = deriveAgentManifest(
      {
        name: 'steward',
        tools: {
          read: acs({ capability: 'retrieve', additional_capabilities: ['search'] }),
          done: acs({ control: true }),
        },
        subagents: ['db-writer'],
      },
      { 'db-writer': child },
    );
    expect(parent.capabilities).toEqual(['delegate', 'mutate', 'retrieve', 'search']);
    expect(manifestMaxima(parent)?.requires_approval).toBe(true);
  });

  it('refuses an unannotated tool and a subagent without a manifest', () => {
    const derive = () =>
      deriveAgentManifest({ name: 'a', tools: { shell: {}, read: acs({ capability: 'retrieve' }) }, subagents: ['b'] });
    expect(derive).toThrow(ManifestDerivationError);
    try {
      derive();
    } catch (e) {
      expect((e as ManifestDerivationError).unannotated).toEqual(['shell']);
      expect((e as ManifestDerivationError).missingChildren).toEqual(['b']);
    }
    // An unannotated control-only tool is no gap: control: true is its annotation.
    expect(() => deriveAgentManifest({ name: 'a', tools: { done: acs({ control: true }) } })).not.toThrow();
  });

  const thrown = (derive: () => unknown): ManifestDerivationError => {
    try {
      derive();
    } catch (e) {
      expect(e).toBeInstanceOf(ManifestDerivationError);
      return e as ManifestDerivationError;
    }
    throw new Error('derivation did not throw');
  };

  it('follows what a composite invokes, and refuses an invoked tool it is not given', () => {
    const args = z.object({});
    const dbWrite = groundedTool({
      name: 'db_write',
      capability: 'mutate',
      description: 'write a row',
      args,
      execute: async () => ({ success: true, evidence_anchors: [] }),
    });
    const deploy = groundedTool({
      name: 'deploy',
      capability: 'execute',
      invokes: { db_write: dbWrite } as never,
      description: 'deploy',
      args,
      execute: async () => ({ result: true, evidence_anchors: [] }) as never,
    });
    // The composite's annotation copies its joined flags; a manifest cannot
    // carry them, so the invoked tool must be given for its capability.
    const error = thrown(() => deriveAgentManifest({ name: 'deployer', tools: { deploy } }));
    expect(error.unresolvedInvokes).toEqual(['db_write']);
    expect(error.message).toContain('invoked tools not given: db_write');
    // Given as a helper the prompts do not offer, its capability counts, so
    // a delegation to the agent needs a checkpoint.
    const manifest = deriveAgentManifest({ name: 'deployer', tools: { deploy }, invoked: { db_write: dbWrite } });
    expect(manifest.capabilities).toEqual(['execute', 'mutate']);
    expect(manifestMaxima(manifest)).toEqual({
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
    });
    // Offered too, it is followed once; transitively, a helper's own invokes.
    const chain = deriveAgentManifest({
      name: 'chain',
      tools: { top: acs({ capability: 'invoke', invokes: ['mid'] }) },
      invoked: { mid: acs({ capability: 'retrieve', invokes: ['low'] }), low: acs({ capability: 'send' }) },
    });
    expect(chain.capabilities).toEqual(['invoke', 'retrieve', 'send']);
    expect(thrown(() => deriveAgentManifest({ name: 'a', tools: { top: acs({ capability: 'invoke', invokes: ['mid'] }) }, invoked: { mid: {} } })).unannotated).toEqual(['mid']);
  });

  it('refuses a tool whose declared flags exceed its capabilities', () => {
    const migrate = acs({ capability: 'execute', flags: { risk: 'high', mutation: true, requires_checkpoint: true } });
    const error = thrown(() => deriveAgentManifest({ name: 'migrator', tools: { run_migration: migrate } }));
    expect(error.raisedFlags).toEqual(['run_migration']);
    // Flags no stricter than the ontology's (or weaker, which are ignored) are no gap.
    const same = deriveAgentManifest({
      name: 'ok',
      tools: { run: acs({ capability: 'execute', flags: { risk: 'medium', requires_approval: true } }) },
    });
    expect(same.capabilities).toEqual(['execute']);
    expect(() =>
      deriveAgentManifest({ name: 'ok', tools: { w: acs({ capability: 'mutate', flags: { risk: 'low' } }) } }),
    ).not.toThrow();
    // A grounded tool's declared flags are in its annotation too.
    const stricter = groundedTool({
      name: 'search_all',
      capability: 'search',
      flags: { requires_approval: true },
      description: 'search',
      args: z.object({}),
      execute: async () => ({ results: [], evidence_anchors: [] }) as never,
    });
    expect(thrown(() => deriveAgentManifest({ name: 's', tools: { search_all: stricter } })).raisedFlags).toEqual([
      'search_all',
    ]);
  });

  it('refuses a task that does not fit', () => {
    const manifest = {
      agent: 'db-writer',
      standard: '1.2',
      ontology: '2.2',
      capabilities: ['mutate'],
      task: { table: { type: 'string', required: true } },
    };
    expect(taskRefusal(manifest, { table: 't' })).toBeNull();
    expect(taskRefusal(manifest, { colour: 'x' })).toBe("'db-writer' missing task inputs: table; undeclared task inputs: colour");
  });

  it('reads declared agents and lints them against relationships', () => {
    const workflow = { agents: ['reviewer-a', 'ghost'] };
    expect(declaredAgents(workflow)).toEqual(['reviewer-a', 'ghost']);
    expect(declaredAgents({})).toBeNull();
    expect(lintDelegationTargets('w', workflow, ['reviewer-a'])).toEqual([
      {
        code: 'V107',
        name: 'UNRESOLVED_TARGET',
        severity: 'error',
        message: "the workflow lists agent 'ghost', but the agent that runs it has no relationship to it",
        location: { workflow: 'w', field: 'agents[1]', path: '/w/agents/1' },
      },
    ]);
    expect(lintDelegationTargets('a/b', { agents: ['x'] }, [])[0]?.location).toMatchObject({ path: '/a~1b/agents/0' });
  });
});
