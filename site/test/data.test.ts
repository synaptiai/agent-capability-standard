// Each expected value names its source. None is copied from the loaders' output.
// Values that change with routine content or release work (counts, versions,
// catalog order) are read at test time through ./independent. Literals stay
// for inline fixtures, for facts the Standard fixes (edge types, the requires
// edges, diagnostic codes), for files that do not change once released (a
// versioned Standard), and for a few named items whose change would be a real
// change to check (debug_code_change bindings, skill names, citation author).
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
import {
  catalogFiles,
  claudeLayerTable,
  diagnosticRowsPerSection,
  profileFiles,
  profileWorkflowIds,
  repoText,
  skillsReadme,
  standardFileVersions,
  stepLineCount,
  topLevelKeys,
} from './independent';

const layerTable = claudeLayerTable();
const capabilityTotal = layerTable.reduce((n, l) => n + l.count, 0);
const catalogs = catalogFiles();
const coreIds = topLevelKeys(repoText(catalogs.core));
const domainIdsByFile = catalogs.domain.map((f) => topLevelKeys(repoText(f)));
const allCatalogIds = new Set([...coreIds, ...domainIdsByFile.flat()]);
const stepTotal = [catalogs.core, ...catalogs.domain].reduce((n, f) => n + stepLineCount(repoText(f)), 0);
const ontologyText = repoText('schemas/capability_ontology.yaml');
// `grep -c '^- from:' schemas/capability_ontology.yaml`
const edgeLines = (ontologyText.match(/^- from:/gm) ?? []).length;
const ontologyVersion = /^meta:\n(?:[ ].*\n)*?[ ]{2}version:\s*['"]?([^'"\s]+)/m.exec(ontologyText)?.[1];
const undefinedProfileIds = profileFiles().flatMap((f) =>
  profileWorkflowIds(repoText(`schemas/profiles/${f}`))
    .filter((id) => !allCatalogIds.has(id))
    .map((id) => [f.replace(/\.yaml$/, '').replace(/_/g, '-'), id] as const),
);
const readme = skillsReadme();

describe('ontology', () => {
  const o = loadOntology();

  it('has the layers, sizes and capabilities of the CLAUDE.md layer table', () => {
    // CLAUDE.md "Layer Architecture" table (36 capabilities in 9 layers at 9945a39).
    expect(o.capabilities).toHaveLength(capabilityTotal);
    expect(o.layers.map((l) => [l.id, l.capabilities])).toEqual(layerTable.map((r) => [r.id, r.capabilities]));
  });

  it('has 7 edge types (Standard §4.3) and one edge per `- from:` line', () => {
    expect(edgeLines).toBeGreaterThan(0);
    expect(o.edges).toHaveLength(edgeLines);
    expect(o.edgeTypes.map((t) => t.id)).toEqual([
      'requires',
      'soft_requires',
      'enables',
      'precedes',
      'conflicts_with',
      'alternative_to',
      'specializes',
    ]);
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

  it('reads meta.version', () => {
    // The `version:` line under `meta:` (2.1.0 at 9945a39).
    expect(ontologyVersion).toMatch(/^\d+\.\d+\.\d+$/);
    expect(o.version).toBe(ontologyVersion);
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

  it('reads every top-level workflow of the core and domain catalogs', () => {
    // Top-level keys by a line scan (12 core and 16 domain at 9945a39, plan "Context").
    const domainTotal = domainIdsByFile.reduce((n, ids) => n + ids.length, 0);
    expect(w.core).toHaveLength(coreIds.length);
    expect(w.domain).toHaveLength(domainTotal);
    expect(w.all).toHaveLength(coreIds.length + domainTotal);
  });

  it('keeps the core catalog in file order', () => {
    expect(w.core.map((x) => x.id)).toEqual(coreIds);
  });

  it('reads each domain file in file order and nothing from examples/', () => {
    expect(w.domainSources).toEqual(catalogs.domain);
    catalogs.domain.forEach((src, i) => {
      expect(w.domain.filter((x) => x.source === src).map((x) => x.id)).toEqual(domainIdsByFile[i]);
    });
    // examples/digital_twin_sync_loop.workflow_catalog.yaml repeats this id.
    expect(w.byId.get('digital_twin_sync_loop')!.source).toBe('schemas/workflow_catalog.yaml');
    expect(w.all.some((x) => x.source.startsWith('examples/'))).toBe(false);
  });

  it('has one step per `- capability:` line of the catalogs', () => {
    // 277 at 9945a39 (design.md "review" section 2).
    expect(stepTotal).toBeGreaterThan(0);
    expect(w.all.reduce((n, x) => n + x.steps.length, 0)).toBe(stepTotal);
  });

  it('turns ids into slugs and records the catalog header version', () => {
    const d = w.byId.get('debug_code_change')!;
    expect(d.slug).toBe('debug-code-change');
    // First line of schemas/workflow_catalog.yaml ("# Standard version: 1.1.0" at 9945a39).
    const header = repoText('schemas/workflow_catalog.yaml').split('\n')[0]!;
    expect(header).toMatch(/^# Standard version: \d+\.\d+\.\d+$/);
    expect(d.standardVersion).toBe(header.split(': ')[1]);
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

  it('has one domain per profile file, keyed by the domain field (design.md "review" resolution 24)', () => {
    // File names with '_' read as '-' (seven domains at 9945a39).
    expect(p.map((d) => d.key)).toEqual(profileFiles().map((f) => f.replace(/\.yaml$/, '').replace(/_/g, '-')));
    const da = p.find((d) => d.key === 'data-analysis')!;
    expect(da.profileFile).toBe('schemas/profiles/data_analysis.yaml');
    expect(da.readme).toBe('docs/domains/data-analysis/README.md');
  });

  it('marks the workflow ids no catalog defines', () => {
    // design.md "pipeline" section 0, "Profiles": 12 at 9945a39, in audio, multimodal and vision.
    const undefinedIds = p.flatMap((d) => d.workflows.filter((x) => !x.defined).map((x) => [d.key, x.id]));
    expect(undefinedIds).toEqual(undefinedProfileIds);
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

  it('has the skills skills/README.md counts and names', () => {
    // The README's "Total" line (36 + 6 = 42 at 9945a39) and its Composed Skills table.
    expect(readme.atomic).toBe(capabilityTotal);
    expect(s).toHaveLength(readme.total);
    expect(s.filter((x) => x.kind === 'capability')).toHaveLength(readme.atomic);
    const composed = s.filter((x) => x.kind === 'composed');
    expect(composed).toHaveLength(readme.composed);
    expect(composed.map((x) => x.name).sort()).toEqual([...readme.composedNames].sort());
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

  it('has the codes of the current Standard §9.2-§9.7, each section with its §9.1 severity', () => {
    // Table rows counted per section of the newest spec/STANDARD-v*.md
    // (9, 6, 4, 6, 5 and 16, so 46 codes, in 1.1.0).
    const rows = diagnosticRowsPerSection(repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`));
    const perSection = Object.fromEntries(Object.keys(rows).map((n) => [n, d.filter((x) => x.section === n).length]));
    expect(perSection).toEqual(rows);
    expect(d).toHaveLength(Object.values(rows).reduce((a, b) => a + b, 0));
    // §9.1: only the §9.7 codes are warnings.
    expect(d.filter((x) => x.severity === 'warning').map((x) => x.section)).toEqual(Array(rows['9.7']).fill('9.7'));
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
    expect(rs).toHaveLength(d.length);
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
  it('reads CITATION.cff', () => {
    // The file's own `version:` and `date-released:` lines (1.1.0 and 2026-10-28 at 9945a39).
    const cff = repoText('CITATION.cff');
    const version = /^version:\s*"([^"]+)"/m.exec(cff)?.[1];
    const released = /^date-released:\s*"(\d{4}-\d{2}-\d{2})"/m.exec(cff)?.[1];
    expect(version).toBeDefined();
    expect(released).toBeDefined();
    const c = loadCitation();
    expect(c).toMatchObject({
      title: 'Agent Capability Ontology + Workflow DSL',
      version,
      date_released: released,
      authors: [{ given: 'Daniel', family: 'Bentes' }],
      license: 'Apache-2.0',
    });
    expect(c.bibtex).toContain('author={Bentes, Daniel}');
    expect(c.bibtex).toContain(`year={${released!.slice(0, 4)}}`);
  });

  it('rejects an unquoted date', () => {
    const doc = { title: 't', version: '1', 'date-released': new Date(), license: 'x', message: 'm', authors: [{ 'given-names': 'a', 'family-names': 'b' }] };
    expect(() => buildCitation(doc, 'u')).toThrow(/date-released/);
  });

  it('reads every version from its own file', () => {
    const v = loadVersions();
    // The Standard versions come from the spec/ file names, newest first (1.1.0, then 1.0.0, at 9945a39).
    const files = standardFileVersions();
    expect([v.standard.current, ...v.standard.previous].map((x) => x.version)).toEqual(files);
    for (const s of [v.standard.current, ...v.standard.previous]) {
      // The status is the first clause of the file's Status line ("Candidate Standard" in both).
      const text = repoText(s.source);
      const statusLine = /^\*\*Status:\*\* (.+)$/m.exec(text)![1]!;
      expect(s.status).not.toBe('');
      expect(statusLine.startsWith(s.status)).toBe(true);
      expect(s.status).not.toMatch(/[—–;]/);
      expect(s.date).toBe(/^\*\*Date:\*\* (\S+)$/m.exec(text)?.[1] ?? null);
    }
    expect(v.ontology).toBe(ontologyVersion);
    // plugin.json "version" and pyproject.toml [project] version change with each release; check their form.
    const plugin = JSON.parse(repoText('.claude-plugin/plugin.json')) as { version: string };
    expect(v.plugin).toBe(plugin.version);
    expect(v.plugin).toMatch(/^\d+\.\d+\.\d+$/);
    expect(v.pythonPackage).toMatch(/^\d+\.\d+\.\d+$/);
    expect(repoText('pyproject.toml')).toContain(`version = "${v.pythonPackage}"`);
    expect(v.commit).toMatch(/^[0-9a-f]{40}$/);
  });

  it('computes the counts from the sources the other tests read', () => {
    // At 9945a39: 36 capabilities, 9 layers, 99 edges, 7 edge types, 28 workflows
    // (12 core, 16 domain), 277 steps, 7 profiles, 12 undefined profile workflows,
    // 46 diagnostic codes, 42 skills, 6 composed.
    expect(loadCounts()).toMatchObject({
      capabilityCount: capabilityTotal,
      layerCount: layerTable.length,
      edgeCount: edgeLines,
      edgeTypeCount: 7,
      workflowCount: coreIds.length + domainIdsByFile.reduce((n, ids) => n + ids.length, 0),
      coreWorkflowCount: coreIds.length,
      domainWorkflowCount: domainIdsByFile.reduce((n, ids) => n + ids.length, 0),
      stepCount: stepTotal,
      profileCount: profileFiles().length,
      undefinedProfileWorkflowCount: undefinedProfileIds.length,
      diagnosticCount: Object.values(diagnosticRowsPerSection(repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`))).reduce((a, b) => a + b, 0),
      skillCount: readme.total,
      composedSkillCount: readme.composed,
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
