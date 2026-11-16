import { describe, expect, it } from 'vitest';
import { manifestMaxima } from '@synaptiai/acs-core';
import { declaredAgents, deriveAgentManifest, ManifestDerivationError, taskRefusal } from '../src/acs/agents.js';
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
