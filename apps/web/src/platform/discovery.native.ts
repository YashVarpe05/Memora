import { registerPlugin } from '@capacitor/core';

import type { DiscoveredFile, FileDiscovery, PermissionState, ScanOptions } from '@memora/core';
import { DEFAULT_SCAN } from '@memora/core';

/**
 * PARTLY VERIFIED ON DEVICE 2026-09-03 — Galaxy S23 FE, Android 16 (SDK 36).
 *
 * Answered against the real MediaStore, by query rather than by reasoning:
 *  - DATE_MODIFIED is in SECONDS (measured 1716896518, ten digits). The interface is
 *    epoch milliseconds, so the plugin divides going in and multiplies coming out.
 *  - MediaStore.Files DOES return files outside the media collections: 832 PDFs, 132 of
 *    them in Download/ and 2 in Documents/DigiLocker/Issued/.
 *
 * STILL UNVERIFIED: the MANAGE_EXTERNAL_STORAGE Settings round-trip, reading bytes by
 * content:// URI, and end-to-end upload timing.
 */

interface NativeScanPage {
  files: DiscoveredFile[];
  done: boolean;
}

interface FileDiscoveryNative {
  isSupported(): Promise<{ supported: boolean }>;
  requestPermission(): Promise<{ state: PermissionState }>;
  checkPermission(): Promise<{ state: PermissionState }>;
  scan(options: {
    limit: number;
    offset: number;
    since: number;
    maxBytes: number;
  }): Promise<NativeScanPage>;
  count(options: { since: number; maxBytes: number }): Promise<{ total: number }>;
  read(options: { path: string }): Promise<{ data: string }>;
}

const Native = registerPlugin<FileDiscoveryNative>('FileDiscovery');

/** Page size for one bridge call. Capacitor returns one JSON payload per call. */
const PAGE = 100;

export class AndroidFileDiscovery implements FileDiscovery {
  async isSupported(): Promise<boolean> {
    return (await Native.isSupported()).supported;
  }

  async requestPermission(): Promise<PermissionState> {
    return (await Native.requestPermission()).state;
  }

  /** Called after the app resumes from the Settings page, where there is no callback. */
  async checkPermission(): Promise<PermissionState> {
    return (await Native.checkPermission()).state;
  }

  scan(options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    return this.#paged(0, options);
  }

  since(marker: number, options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    return this.#paged(marker, options);
  }

  /** Repeated bridge calls become the async iterable the interface promises. */
  async *#paged(since: number, options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    const limit = options?.limit ?? DEFAULT_SCAN.limit;
    const maxBytes = options?.maxBytes ?? DEFAULT_SCAN.maxBytes;
    let offset = 0;
    let yielded = 0;

    while (yielded < limit) {
      const page = await Native.scan({
        limit: Math.min(PAGE, limit - yielded),
        offset,
        since,
        maxBytes,
      });
      for (const file of page.files) {
        yield file;
        yielded += 1;
      }
      offset += page.files.length;
      if (page.done || page.files.length === 0) return;
    }
  }

  /** The denominator for progress. Same selection as scan(), computed in SQL. */
  async count(options?: ScanOptions): Promise<number> {
    const { total } = await Native.count({
      since: 0,
      maxBytes: options?.maxBytes ?? DEFAULT_SCAN.maxBytes,
    });
    return total;
  }

  async read(path: string): Promise<Uint8Array> {
    const { data } = await Native.read({ path });
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
}
