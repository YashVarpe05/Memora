import type { DiscoveredFile, FileDiscovery, PermissionState, ScanOptions } from '@memora/core';

/**
 * Web: not supported, and that is the point.
 *
 * Browsers cannot enumerate device storage — no gallery, no Downloads folder, no
 * background scanning. This implementation exists so the boundary is visible in code and
 * the PWA keeps building, not as a stub waiting to be filled in. It cannot be filled in.
 */
export class WebFileDiscovery implements FileDiscovery {
  async isSupported(): Promise<boolean> {
    return false;
  }

  async requestPermission(): Promise<PermissionState> {
    return 'denied';
  }

  async *scan(_options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    // Intentionally empty. A browser has nothing to enumerate.
  }

  async *since(_marker: number, _options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    // Intentionally empty.
  }

  async count(_options?: ScanOptions): Promise<number> {
    return 0;
  }

  async read(_path: string): Promise<Uint8Array> {
    throw new Error('File discovery is not available in a browser. Install the app.');
  }
}
