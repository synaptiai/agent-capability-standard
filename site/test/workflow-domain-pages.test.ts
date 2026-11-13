// The workflow family map (visual spec 3.4, F-WI2) and the figures domain
// pages and the domains index draw from the domain guides' own blocks.
// Expected values come from line scans of the catalog, profile and README
// files, never from the functions under test.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadProfiles } from '../src/data/profiles';
import { headingProfileKey, parameterAcross } from '../src/lib/domain-index';
import { capabilityUsage, listedCapabilities, usageCheck } from '../src/lib/domain-usage';
import { domainMap, referenceMap } from '../src/lib/workflow-index';
import { catalogFiles, repoText } from './independent';

/** Top-level workflow key of each `workflow_id:` line of a catalog, with the step number it sits in. */
function invocations(text: string): { parent: string; child: string; step: number }[] {
  const out: { parent: string; child: string; step: number }[] = [];
  let parent = '';
  let step = 0;
  let inSteps = false;
  for (const line of text.split('\n')) {
    const top = /^([a-z_][a-z0-9_]*):\s*$/.exec(line);
    if (top) {
      parent = top[1]!;
      step = 0;
      inSteps = false;
      continue;
    }
    if (/^ {2}steps:\s*$/.test(line)) inSteps = true;
    else if (/^ {2}[a-z_]+:/.test(line) && !/^ {2}steps:/.test(line)) inSteps = false;
    if (inSteps && /^\s*- capability:/.test(line)) step += 1;
    const m = /^\s+workflow_id:\s*([a-z_0-9]+)/.exec(line);
    if (m && inSteps) out.push({ parent, child: m[1]!, step });
  }
  return out;
}

describe('workflow family map (F-WI2)', () => {
  it('draws each reference workflow that runs others with the steps that run each child', () => {
    const scanned = invocations(repoText(catalogFiles().core));
    expect(scanned.length).toBeGreaterThan(0);
    const drawn = referenceMap().families.flatMap((f) => f.children.flatMap((c) => c.steps.map((step) => ({ parent: f.parent.id, child: c.workflow.id, step }))));
    const key = (x: { parent: string; child: string; step: number }) => `${x.parent}>${x.child}@${x.step}`;
    expect(drawn.map(key).sort()).toEqual(scanned.map(key).sort());
  });

  it('puts every proposed workflow a profile lists under its domain, and no catalog workflow among them', () => {
    const map = domainMap();
    for (const file of loadProfiles()) {
      const text = repoText(file.profileFile);
      const listed = [...text.matchAll(/^ {2}- ([a-z_0-9]+)\s*$/gm)].map((m) => m[1]!);
      const group = map.groups.find((g) => g.domain === file.key);
      const shown = group ? [...group.defined.map((w) => w.id), ...group.proposed] : [];
      for (const id of listed.filter((x) => file.workflows.some((w) => w.id === x))) expect(shown, `${file.key} ${id}`).toContain(id);
    }
  });
});

describe('domain guide figures', () => {
  it('reads the anchor types of each audio "Capability Usage" example from its fence', () => {
    const text = repoText('docs/domains/audio/README.md');
    const usage = capabilityUsage(text, 'test');
    const section = text.slice(text.indexOf('## Capability Usage'), text.indexOf('## Available Workflows'));
    const fences = [...section.matchAll(/```yaml\n([\s\S]*?)```/g)].map((m) => m[1]!);
    expect(usage.map((u) => u.capability)).toEqual(fences.map((f) => /^([a-z_]+):/.exec(f)![1]));
    usage.forEach((u, i) => {
      const types = [...new Set([...fences[i]!.matchAll(/- type: ([a-z_]+)/g)].map((m) => m[1]!))];
      expect(u.anchors, u.heading).toEqual(types);
    });
  });

  it('checks each required anchor type against the profile file', () => {
    const profile = loadProfiles().find((p) => p.key === 'audio')!;
    const required = /required_anchor_types:\n((?: {4}- .+\n)+)/.exec(repoText(profile.profileFile))![1]!.match(/- ([a-z_]+)/g)!.map((s) => s.slice(2));
    const u = capabilityUsage(repoText('docs/domains/audio/README.md'), 'test')[0]!;
    const c = usageCheck(u, profile.profile);
    expect(c.required.map((r) => r.type)).toEqual(required);
    expect(c.required.filter((r) => r.present).map((r) => r.type)).toEqual(required.filter((t) => u.anchors.includes(t)));
  });

  it('lists a proposed workflow\'s capabilities in the order the guide writes them', () => {
    const text = repoText('docs/domains/audio/README.md');
    const block = text.slice(text.indexOf('### 1. Speech Recognition Pipeline'), text.indexOf('### 2.'));
    const ids = [...block.matchAll(/^- `([a-z_]+)`/gm)].map((m) => m[1]!);
    expect(ids.length).toBeGreaterThan(0);
    expect(listedCapabilities(text, 'speech_recognition_pipeline')).toEqual(ids);
    expect(listedCapabilities(text, 'no_such_workflow')).toBeNull();
  });

  it('matches the "Choosing a Domain" headings to profile keys', () => {
    const keys = loadProfiles().map((p) => p.key);
    const text = repoText('docs/domains/README.md');
    const section = text.slice(text.indexOf('## Choosing a Domain'), text.indexOf('\n## ', text.indexOf('## Choosing a Domain') + 3));
    const heads = [...section.matchAll(/^### (.+)$/gm)].map((m) => m[1]!.trim());
    expect(heads.map((h) => headingProfileKey(h, keys)).every((k) => k !== null)).toBe(true);
    expect(new Set(heads.map((h) => headingProfileKey(h, keys))).size).toBe(heads.length);
  });

  it('collects the domain values of the named capability from every catalog', () => {
    const p = parameterAcross(repoText('docs/domains/README.md'))!;
    expect(p.capability).toBe('detect');
    const files = [catalogFiles().core, ...catalogFiles().domain];
    const scanned = new Set<string>();
    for (const f of files) {
      const lines = repoText(f).split('\n');
      lines.forEach((l, i) => {
        if (!/^\s+- capability: detect\s*$/.test(l)) return;
        for (let j = i + 1; j < lines.length && !/^\s+- capability:/.test(lines[j]!); j++) {
          const m = /^\s+domain: ([a-z_-]+)\s*$/.exec(lines[j]!);
          if (m) {
            scanned.add(m[1]!);
            break;
          }
        }
      });
    }
    expect(new Set(p.rows.flatMap((r) => r.values.map((v) => v.value)))).toEqual(scanned);
  });
});

describe('capabilityUsage warnings', () => {
  afterEach(() => vi.restoreAllMocks());

  it('warns when the README has no Capability Usage section', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(capabilityUsage('# Domain\n\n## Overview\n\nText.\n', 'docs/domains/x/README.md')).toEqual([]);
    expect(warn.mock.calls.map((c) => c[0])).toEqual(['docs/domains/x/README.md: no "## Capability Usage" section; no usage figures']);
  });

  it('names the YAML error of an example fence that does not parse', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const readme = ['# Domain', '', '## Capability Usage', '', '### Detection', '', '```yaml', 'detect: [unclosed', '```', ''].join('\n');
    expect(capabilityUsage(readme, 'fixture')).toEqual([]);
    expect(warn.mock.calls.length).toBe(1);
    expect(warn.mock.calls[0]![0]).toMatch(/^fixture: "Detection" under Capability Usage has no single-capability YAML fence \(its YAML does not parse: .+\); no figure$/);
  });
});
