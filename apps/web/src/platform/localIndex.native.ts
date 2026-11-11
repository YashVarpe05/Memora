import { registerPlugin } from '@capacitor/core';

import type { ExtractedText } from '@memora/core';
import { toSearchResponse, type LocalHit } from './localSearch';
import type { components } from '@memora/core/types/api';

interface LocalIndexNative {
  upsert(options: {
    uri: string; name: string; mimeType: string; size: number; modified: number;
    fingerprint: string; pages: { number: number; text: string }[];
  }): Promise<{ id: number; docType: string | null }>;
  known(): Promise<{ files: Record<string, string> }>;
  stats(): Promise<{ documents: number }>;
  prune(options: { present: string[] }): Promise<{ removed: number }>;
  clear(): Promise<void>;
  search(options: { query: string; limit: number }): Promise<{ results: LocalHit[] }>;
  scheduleBackground(options: { enabled: boolean }): Promise<void>;
}

const Native = registerPlugin<LocalIndexNative>('LocalIndex');

/** Where each result lives, so the viewer can open it. Filled by every search. */
const uris = new Map<string, string>();
export const localUriFor = (memoryId: string): string | null => uris.get(memoryId) ?? null;

export const localIndex = {
  known: async () => (await Native.known()).files,
  documents: async () => (await Native.stats()).documents,
  prune: async (present: string[]) => (await Native.prune({ present })).removed,
  setBackground: (enabled: boolean) => Native.scheduleBackground({ enabled }),
  async upsert(file: { path: string; name: string; mimeType: string; size: number; modifiedAt: number },
    fingerprint: string, extracted: ExtractedText | null) {
    return Native.upsert({
      uri: file.path, name: file.name, mimeType: file.mimeType, size: file.size,
      modified: file.modifiedAt, fingerprint,
      pages: (extracted?.pages ?? []).map(page => ({ number: page.number, text: page.text })),
    });
  },
  async search(query: string, limit = 10): Promise<components['schemas']['SearchResponse']> {
    const { results } = await Native.search({ query, limit });
    for (const hit of results) uris.set(String(hit.id), hit.uri);
    return toSearchResponse(results);
  },
};
