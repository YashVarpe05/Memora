import { registerPlugin } from '@capacitor/core';

import type { DiscoveredFile, FileDiscovery, PermissionState, ScanOptions } from '@memora/core';
import { DEFAULT_SCAN } from '@memora/core';

/**
 * UNVERIFIED ON DEVICE. No APK has been built and no phone has run this.
 *
 * TO CHECK ON A REAL PHONE:
 *  - whether requestPermission's Settings round-trip ends in 'granted' (there is no
 *    callback; the app just resumes, so checkPermission is called again on resume)
 *  - whether MediaStore returns PDFs from Downloads/ and not only gallery images
 *  - how long a scan of a real gallery takes
 *  - whether reading by content:// URI works on the target API level
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

  async read(path: string): Promise<Uint8Array> {
    const { data } = await Native.read({ path });
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
}
