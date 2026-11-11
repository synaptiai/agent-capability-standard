// Each expected value names its source. None is copied from the loaders' output.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildCitation, loadCitation } from '../src/data/citation';
import { loadCounts } from '../src/data/counts';
import { crossCheck, loadDiagnostics, parseDiagRs, parseSpecDiagnostics } from '../src/data/diagnostics';
import { buildOntology, loadOntology } from '../src/data/ontology';
import { buildProfile, loadProfiles } from '../src/data/profiles';
import { loadSkills, parseFrontmatter } from '../src/data/skills';
import { loadVersions, olderVersionNote } from '../src/data/versions';
import { readRepoFile } from '../src/lib/repo';
import { loadWorkflows, parseCatalog, referenceRoots } from '../src/data/workflows';

describe('ontology', () => {
  const o = loadOntology();

  it('has 36 capabilities in 9 layers with the layer sizes CLAUDE.md lists', () => {
    // CLAUDE.md "Layer Architecture" table.
    expect(o.capabilities).toHaveLength(36);
    expect(o.layers.map((l) => [l.id, l.capabilities.length])).toEqual([
      ['PERCEIVE', 4],
      ['UNDERSTAND', 6],
      ['REASON', 4],
      ['MODEL', 5],
      ['SYNTHESIZE', 3],
      ['EXECUTE', 3],
      ['VERIFY', 5],
      ['REMEMBER', 2],
      ['COORDINATE', 4],
    ]);
    expect(o.layers[0]!.capabilities).toEqual(['retrieve', 'search', 'observe', 'receive']);
  });

  it('has 7 edge types (Standard §4.3) and 99 edges', () => {
    // 99: `grep -c '^- from:' schemas/capability_ontology.yaml`, run 2026-11-11.
    expect(o.edgeTypes.map((t) => t.id)).toEqual([
      'requires',
      'soft_requires',
      'enables',
      'precedes',
      'conflicts_with',
      'alternative_to',
      'specializes',
    ]);
    expect(o.edges).toHaveLength(99);
  });

  it('has requires edges only from checkpoint to mutate, send and rollback (Standard §4.4)', () => {
    const req = o.edgeTypes.find((t) => t.id === 'requires')!.edges;
    expect(req).toEqual([
      { from: 'checkpoint', to: 'mutate' },
      { from: 'checkpoint', to: 'send' },
      { from: 'checkpoint', to: 'rollback' },
    ]);
    expect(o.byId.get('rollback')!.edgesIn.requires).toEqual(['checkpoint']);
  });

  it('sets missing flags to false', () => {
    // The execute node has no requires_checkpoint or mutation_overridable key.
    const execute = o.byId.get('execute')!;
    expect(execute.requires_checkpoint).toBe(false);
    expect(execute.mutation_overridable).toBe(false);
    expect(execute.requires_approval).toBe(true);
    // Only audit sets mutation_overridable (CLAUDE.md "Safety Model").
    expect(o.capabilities.filter((c) => c.mutation_overridable).map((c) => c.id)).toEqual(['audit']);
  });

  it('reads meta.version 2.1.0', () => {
    expect(o.version).toBe('2.1.0');
  });

  it('rejects a layer list that disagrees with its nodes', () => {
    const doc = {
      meta: { name: 'x', version: '1', description: 'x' },
      layers: { L: { description: 'd', cognitive_mapping: 'm', capabilities: ['a', 'b'] } },
      nodes: [{ id: 'a', layer: 'L', description: 'd', risk: 'low', input_schema: {}, output_schema: {} }],
      edge_types: {},
      edges: [],
    };
    expect(() => buildOntology(doc)).toThrow(/layer L lists/);
  });
});

describe('workflows', () => {
  const w = loadWorkflows();

  it('has 28 workflows: 12 core and 16 domain (plan, "Context")', () => {
    expect(w.all).toHaveLength(28);
    expect(w.core).toHaveLength(12);
    expect(w.domain).toHaveLength(16);
  });

  it('keeps the core catalog in file order', () => {
    // Top-level keys of schemas/workflow_catalog.yaml, in order.
    expect(w.core.map((x) => x.id)).toEqual([
      'monitor_and_replan',
      'clarify_intent',
      'debug_code_change',
      'world_model_build',
      'capability_gap_analysis',
      'digital_twin_sync_loop',
      'digital_twin_bootstrap',
      'rag_pipeline',
      'security_assessment',
      'multi_agent_orchestration',
      'data_quality_pipeline',
      'model_deployment',
    ]);
  });

  it('reads four workflows from each domain file and nothing from examples/', () => {
    // design.md "ia-home" section 3: four workflows per domain file.
    expect(w.domainSources).toEqual([
      'schemas/workflows/data_analysis_workflows.yaml',
      'schemas/workflows/healthcare_workflows.yaml',
      'schemas/workflows/manufacturing_workflows.yaml',
      'schemas/workflows/personal_assistant_workflows.yaml',
    ]);
    for (const src of w.domainSources) expect(w.domain.filter((x) => x.source === src)).toHaveLength(4);
    // examples/digital_twin_sync_loop.workflow_catalog.yaml repeats this id.
    expect(w.byId.get('digital_twin_sync_loop')!.source).toBe('schemas/workflow_catalog.yaml');
    expect(w.all.some((x) => x.source.startsWith('examples/'))).toBe(false);
  });

  it('has 277 steps (design.md "review" section 2)', () => {
    expect(w.all.reduce((n, x) => n + x.steps.length, 0)).toBe(277);
  });

  it('turns ids into slugs and records the catalog header version', () => {
    const d = w.byId.get('debug_code_change')!;
    expect(d.slug).toBe('debug-code-change');
    // First line of schemas/workflow_catalog.yaml: "# Standard version: 1.1.0".
    expect(d.standardVersion).toBe('1.1.0');
  });

  it('records which workflows invoke which (workflow_catalog.yaml, digital_twin_bootstrap steps)', () => {
    expect(w.byId.get('world_model_build')!.invokedBy).toEqual(['digital_twin_bootstrap']);
    expect(w.byId.get('digital_twin_sync_loop')!.invokedBy).toEqual(['digital_twin_bootstrap']);
  });

  it('lists the earlier outputs a step reads', () => {
    // debug_code_change rollback binds ${checkpoint_out...} and its gate reads ${verify_out...};
    // execute reads ${bug...} (an input) and ${plan_out...} in its gate.
    const steps = w.byId.get('debug_code_change')!.steps;
    expect(steps.find((s) => s.capability === 'rollback')!.consumes).toEqual(['checkpoint_out', 'verify_out']);
    expect(steps.find((s) => s.capability === 'execute')!.consumes).toEqual(['plan_out']);
  });

  it('takes the domain from the workflow and the profile path', () => {
    const d = w.domain.find((x) => x.id === 'data_pipeline_validation')!;
    // schemas/workflows/data_analysis_workflows.yaml, data_pipeline_validation.
    expect(d.domain).toBe('data-analysis');
    expect(d.profile).toBe('schemas/profiles/data_analysis.yaml');
  });

  it('skips x- vendor keys at the top of a catalog (Standard §5.1)', () => {
    const text = [
      'x-vendor: {anything: 1}',
      'w:',
      '  goal: g',
      '  risk: low',
      '  steps:',
      '  - capability: observe',
      '    store_as: a',
      '    input_bindings: {target: "${inp}"}',
      '  - capability: explain',
      '    input_bindings: {data: "${a.x}", more: ["${inp}"]}',
    ].join('\n');
    const out = parseCatalog('t.yaml', text, 'core', loadOntology());
    expect(out.map((x) => x.id)).toEqual(['w']);
    expect(out[0]!.steps[1]!.consumes).toEqual(['a']);
  });

  it('rejects an unknown capability', () => {
    const text = 'w:\n  goal: g\n  risk: low\n  steps:\n  - capability: teleport\n';
    expect(() => parseCatalog('t.yaml', text, 'core', loadOntology())).toThrow(/unknown capability teleport/);
  });

  it('finds the root of every reference', () => {
    expect([...referenceRoots({ a: '${x.y} and ${ z }', b: ['${w}'] })]).toEqual(['x', 'z', 'w']);
  });

  it('reads a hyphen as part of a root (Standard 1.1.0 §5.3: [A-Za-z_][A-Za-z0-9_-]*)', () => {
    expect([...referenceRoots('${plan-result.x}')]).toEqual(['plan-result']);
    // Both `plan` and `plan-result` are stored; the step reads only the second.
    const text = [
      'w:',
      '  goal: g',
      '  risk: low',
      '  steps:',
      '  - capability: plan',
      '    store_as: plan',
      '  - capability: plan',
      '    store_as: plan-result',
      '  - capability: explain',
      '    input_bindings: {data: "${plan-result.x}"}',
    ].join('\n');
    expect(parseCatalog('t.yaml', text, 'core', loadOntology())[0]!.steps[2]!.consumes).toEqual(['plan-result']);
  });
});

describe('profiles', () => {
  const p = loadProfiles();

  it('has the seven domains keyed by the domain field (design.md "review" resolution 24)', () => {
    expect(p.map((d) => d.key)).toEqual([
      'audio',
      'data-analysis',
      'healthcare',
      'manufacturing',
      'multimodal',
      'personal-assistant',
      'vision',
    ]);
    const da = p.find((d) => d.key === 'data-analysis')!;
    expect(da.profileFile).toBe('schemas/profiles/data_analysis.yaml');
    expect(da.readme).toBe('docs/domains/data-analysis/README.md');
  });

  it('marks the 12 workflow ids no catalog defines, all in audio, multimodal and vision', () => {
    // design.md "pipeline" section 0, "Profiles".
    const undefinedIds = p.flatMap((d) => d.workflows.filter((x) => !x.defined).map((x) => [d.key, x.id]));
    expect(undefinedIds).toHaveLength(12);
    expect(new Set(undefinedIds.map(([k]) => k))).toEqual(new Set(['audio', 'multimodal', 'vision']));
    // schemas/profiles/vision.yaml workflows list.
    expect(p.find((d) => d.key === 'vision')!.workflows.map((x) => x.id)).toContain('object_detection_pipeline');
  });

  it('rejects a domain field that does not match the file name', () => {
    expect(() =>
      buildProfile('schemas/profiles/data_analysis.yaml', { domain: 'data_analysis', version: '1' }, new Set()),
    ).toThrow(/expected data-analysis/);
  });
});

describe('skills', () => {
  const s = loadSkills();

  it('has 42 skills: 36 capability skills and 6 composed (skills/README.md after Phase 1)', () => {
    expect(s).toHaveLength(42);
    expect(s.filter((x) => x.kind === 'capability')).toHaveLength(36);
    expect(s.filter((x) => x.kind === 'composed').map((x) => x.dir)).toEqual([
      'capability-gap-analysis',
      'debug-workflow',
      'digital-twin-bootstrap',
      'digital-twin-sync-loop',
      'discover-capabilities',
      'perspective-validation',
    ]);
  });

  it('shows the frontmatter name and joins composed skills to workflows', () => {
    // skills/capability-gap-analysis/SKILL.md frontmatter "name: gap-analysis-workflow";
    // skills/debug-workflow/SKILL.md line 14 says it runs debug_code_change.
    const gap = s.find((x) => x.dir === 'capability-gap-analysis')!;
    expect(gap.name).toBe('gap-analysis-workflow');
    expect(gap.workflow).toBe('capability_gap_analysis');
    expect(s.find((x) => x.dir === 'digital-twin-sync-loop')!.name).toBe('digital-twin-sync-workflow');
    expect(s.find((x) => x.dir === 'debug-workflow')!.workflow).toBe('debug_code_change');
    expect(s.find((x) => x.dir === 'perspective-validation')!.workflow).toBeUndefined();
  });

  it('requires frontmatter', () => {
    expect(() => parseFrontmatter('# no frontmatter\n', 'x')).toThrow(/no frontmatter/);
  });
});

describe('diagnostics', () => {
  const d = loadDiagnostics();

  it('has the 46 codes of Standard §9.2-§9.7, each section with its §9.1 severity', () => {
    expect(d).toHaveLength(46);
    const perSection = Object.fromEntries(
      ['9.2', '9.3', '9.4', '9.5', '9.6', '9.7'].map((n) => [n, d.filter((x) => x.section === n).length]),
    );
    // Rows counted in each §9 table of spec/STANDARD-v1.1.0.md.
    expect(perSection).toEqual({ '9.2': 9, '9.3': 6, '9.4': 4, '9.5': 6, '9.6': 5, '9.7': 16 });
    expect(d.filter((x) => x.severity === 'warning').map((x) => x.section)).toEqual(Array(16).fill('9.7'));
  });

  it('reads code, name, category and anchors from the tables', () => {
    expect(d[0]).toMatchObject({
      code: 'V101',
      name: 'UNKNOWN_CAPABILITY',
      severity: 'error',
      category: 'Validation Errors',
      sectionAnchor: '92-validation-errors',
      anchor: 'v101',
      descriptionMd: 'Capability ID not found in ontology',
    });
    expect(d.find((x) => x.code === 'W602')).toMatchObject({ name: 'SAFETY_FLAG_DOWNGRADE', severity: 'warning' });
    expect(d.find((x) => x.code === 'F505')!.severity).toBe('error');
  });

  it('lists B205 once although Appendix C repeats it', () => {
    expect(d.filter((x) => x.code === 'B205')).toHaveLength(1);
  });

  it('agrees with core/src/diag.rs', () => {
    const rs = parseDiagRs(readFileSync('../core/src/diag.rs', 'utf8'));
    expect(rs).toHaveLength(46);
    expect(() => crossCheck(d, rs)).not.toThrow();
  });

  it('fails when the spec and diag.rs disagree on severity', () => {
    const rs = parseDiagRs(readFileSync('../core/src/diag.rs', 'utf8')).map((r) =>
      r.code === 'W601' ? { ...r, severity: 'error' as const } : r,
    );
    expect(() => crossCheck(d, rs)).toThrow(/W601/);
  });

  it('fails when a section heading disagrees with the §9.1 severity', () => {
    const text = [
      '### 9.1 Categories and Severity',
      '| Validation | V1xx | error | x |',
      '### 9.2 Warnings',
      '| V101 | A_NAME | first |',
      '### 9.8 Diagnostic Format',
    ].join('\n');
    expect(() => parseSpecDiagnostics(text)).toThrow(/V101 has severity error/);
  });

  it('stops at §9.8', () => {
    const text = [
      '### 9.1 Categories and Severity',
      '| Validation | V1xx | error | x |',
      '### 9.2 Validation Errors',
      '| V101 | A_NAME | first |',
      '### 9.8 Diagnostic Format',
      '| V102 | LATER | not a diagnostic row |',
    ].join('\n');
    expect(parseSpecDiagnostics(text).map((x) => x.code)).toEqual(['V101']);
  });
});

describe('citation, versions and counts', () => {
  it('reads CITATION.cff (set in Phase 1: version 1.1.0, released 2026-10-28)', () => {
    const c = loadCitation();
    expect(c).toMatchObject({
      title: 'Agent Capability Ontology + Workflow DSL',
      version: '1.1.0',
      date_released: '2026-10-28',
      authors: [{ given: 'Daniel', family: 'Bentes' }],
      license: 'Apache-2.0',
    });
    expect(c.bibtex).toContain('author={Bentes, Daniel}');
    expect(c.bibtex).toContain('year={2026}');
  });

  it('rejects an unquoted date', () => {
    const doc = { title: 't', version: '1', 'date-released': new Date(), license: 'x', message: 'm', authors: [{ 'given-names': 'a', 'family-names': 'b' }] };
    expect(() => buildCitation(doc, 'u')).toThrow(/date-released/);
  });

  it('reads every version from its own file', () => {
    const v = loadVersions();
    // spec/STANDARD-v1.1.0.md and -v1.0.0.md header lines; plugin.json; pyproject.toml.
    expect(v.standard.current).toMatchObject({ version: '1.1.0', status: 'Candidate Standard', date: '2026-10-28' });
    expect(v.standard.previous.map((x) => [x.version, x.status])).toEqual([['1.0.0', 'Candidate Standard']]);
    expect(v.ontology).toBe('2.1.0');
    expect(v.plugin).toBe('2.0.0');
    expect(v.pythonPackage).toBe('0.1.0');
    expect(v.commit).toMatch(/^[0-9a-f]{40}$/);
  });

  it('computes the counts the plan states', () => {
    // plan "Context": 36 capabilities, 9 layers, 99 edges, 28 workflows (12 core, 16 domain),
    // 7 profiles, 46 diagnostic codes; skills/README.md: 42 skills, 6 composed.
    expect(loadCounts()).toMatchObject({
      capabilityCount: 36,
      layerCount: 9,
      edgeCount: 99,
      edgeTypeCount: 7,
      workflowCount: 28,
      coreWorkflowCount: 12,
      domainWorkflowCount: 16,
      stepCount: 277,
      profileCount: 7,
      undefinedProfileWorkflowCount: 12,
      diagnosticCount: 46,
      skillCount: 42,
      composedSkillCount: 6,
    });
  });
});

describe('the note on an older Standard version', () => {
  // A made-up 1.2.0 that supersedes 1.1.0 only and has an appendix for 1.1.0 only.
  const v120 = [
    '# Standard',
    '',
    '**Version:** 1.2.0',
    '**Status:** Candidate Standard',
    '**Supersedes:** [STANDARD-v1.1.0](STANDARD-v1.1.0.md) (still supported)',
    '',
    '## Appendix C: Changes from 1.0.0 to 1.1.0',
    '',
    '## Appendix D: Changes from 1.1.0',
    '',
  ].join('\n');

  it('states support and links the appendix only where the current text does', () => {
    expect(olderVersionNote('1.1.0', v120)).toEqual({
      stillSupported: true,
      changes: { label: 'Appendix D', anchor: 'appendix-d-changes-from-110' },
    });
    expect(olderVersionNote('1.0.0', v120)).toEqual({ stillSupported: false, changes: null });
  });

  it('reads the real 1.1.0 text for 1.0.0', () => {
    // spec/STANDARD-v1.1.0.md: "**Supersedes:** [STANDARD-v1.0.0](STANDARD-v1.0.0.md) (still supported; ...)"
    // and "## Appendix C: Changes from 1.0.0", whose id the spike's done-check names.
    expect(olderVersionNote('1.0.0', readRepoFile('spec/STANDARD-v1.1.0.md'))).toEqual({
      stillSupported: true,
      changes: { label: 'Appendix C', anchor: 'appendix-c-changes-from-100' },
    });
  });
});
