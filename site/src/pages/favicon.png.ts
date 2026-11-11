// The favicon as PNG, drawn from the mark in the light theme.
import { faviconPng } from '../pixel/icons';

export function GET(): Response {
  return new Response(new Uint8Array(faviconPng()), { headers: { 'Content-Type': 'image/png' } });
}
