// /.well-known/agent-skills/<name>/SKILL.md: each skill's SKILL.md, byte for
// byte as committed, so the digest in the index is the digest of this file.
import type { APIRoute, GetStaticPaths } from 'astro';
import { loadSkills, type Skill } from '../../../../lib/agent-skills';

export const getStaticPaths = (() => loadSkills().map((skill) => ({ params: { name: skill.entry.name }, props: { skill } }))) satisfies GetStaticPaths;

export const GET: APIRoute = ({ props }) => {
  const { bytes } = (props as { skill: Skill }).skill;
  return new Response(new Uint8Array(bytes), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
};
