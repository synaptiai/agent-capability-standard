/**
 * The document the example agent looks after: a flat JSON object of settings
 * in the thread's file system.
 */
import type { ThreadState } from '@standardagents/spec';
import { sha256Hex, type EvidenceAnchor, type Json } from '@synaptiai/acs-core';

export const SETTINGS_PATH = '/config/settings.json';

export type Settings = Record<string, string>;

type Files = Pick<ThreadState, 'readFile' | 'writeFile'>;

/**
 * An evidence anchor (STANDARD v1.2.0 §6.5) for a file as it was when it was
 * read or written: its `digest` is the SHA-256 of its content.
 */
export function fileAnchor(path: string, sha256: string): EvidenceAnchor {
  return { ref: `file:${path}`, kind: 'file', digest: `sha256:${sha256}` };
}

/**
 * An evidence anchor of kind `record` for a checkpoint taken: the record of
 * the action that grounds a `checkpoint` output (§3.1).
 */
export function checkpointAnchor(id: string): EvidenceAnchor {
  return { ref: `checkpoint:${id}`, kind: 'record' };
}

export async function readText(state: Files, path: string): Promise<string | null> {
  const bytes = await state.readFile(path);
  return bytes === null ? null : new TextDecoder().decode(bytes);
}

/** `text` parsed as JSON, or `text` itself when it is not JSON. */
export function parsedOrText(text: string): Json {
  try {
    return JSON.parse(text) as Json;
  } catch {
    return text;
  }
}

/** The settings document, its exact text and that text's SHA-256. */
export async function readSettings(
  state: Files,
  path: string = SETTINGS_PATH,
): Promise<{ settings: Settings; text: string; sha256: string }> {
  const text = (await readText(state, path)) ?? '{}';
  return { settings: JSON.parse(text) as Settings, text, sha256: await sha256Hex(text) };
}

export async function writeText(state: Files, path: string, text: string): Promise<string> {
  await state.writeFile(path, text, 'application/json');
  return sha256Hex(text);
}
