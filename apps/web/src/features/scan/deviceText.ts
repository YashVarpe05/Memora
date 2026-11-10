import type { DiscoveredFile, TextExtractor } from '@memora/core';
import { maskIdentifiers } from '@memora/core';
import type { components } from '@memora/core/types/api';
import { apiFetch } from '@/platform/api';

type Indexed = components['schemas']['UploadResponse'];

/**
 * Read a file on the device and send only its masked text. Resolves `null` when the device
 * cannot read this type, so the caller can fall back to uploading the file. Throws when it
 * can read the type but indexing failed: a failed read must never turn into an upload.
 */
export async function indexOnDevice(
  extractor: TextExtractor,
  file: DiscoveredFile,
): Promise<Indexed | null> {
  const extracted = await extractor.extract(file.path, file.mimeType);
  if (!extracted) return null;
  const pages = extracted.pages.map(page => ({
    number: page.number,
    text: maskIdentifiers(page.text).text,
  }));
  const response = await apiFetch('/api/index/text-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content_hash: extracted.contentHash,
      filename: file.name,
      device_path: file.path,
      mime_type: file.mimeType,
      byte_size: extracted.byteSize,
      pages,
    }),
  });
  if (response.status === 401) throw new Error('Device connection expired. Reconnect to continue.');
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Indexing failed (${response.status}).`);
  }
  return await response.json() as Indexed;
}
