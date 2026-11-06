/**
 * File discovery — enumerating documents already on the device.
 *
 * The one platform capability with no web implementation, and the reason Capacitor is
 * required rather than optional. Browsers sandbox storage deliberately: there is no web
 * API that enumerates a gallery or a Downloads folder, and the File System Access API
 * grants handles to user-picked files rather than device-wide scanning. That is a
 * platform boundary, not a missing feature.
 *
 * The web implementation returns `isSupported() === false`, which keeps the PWA building
 * and puts the boundary in code rather than in a comment.
 */

export type PermissionState = 'granted' | 'denied' | 'prompt';

/** A candidate found on the device. Metadata only — never the bytes. */
export interface DiscoveredFile {
  /** Opaque to the caller. Only the platform layer interprets it. */
  path: string;
  name: string;
  /** Bytes. Used to skip large files before anything is read. */
  size: number;
  /** Epoch ms. Drives newest-first ordering and the incremental high-water mark. */
  modifiedAt: number;
  /** Native change generation, when available. Detects changes within one timestamp tick. */
  revision?: string;
  mimeType: string;
  /** Device-relative folder, e.g. `DCIM/Camera/`. Shown while scanning so the user can
   *  see what is being read, and useful for diagnosing filter rules against reality. */
  folder?: string;
}

export interface ScanOptions {
  /**
   * Stop after this many candidates. The first pass is deliberately partial: a phone
   * holds thousands of photos and indexing all of them is hours of OCR, so the app has
   * to be useful in a minute rather than complete in two hours.
   */
  limit?: number;
  /** Newest first by default — recency dominates what people search for. */
  order?: 'newest' | 'oldest';
  /** Mime prefixes to include, e.g. ['image/', 'application/pdf']. */
  include?: readonly string[];
  /** Skip anything larger. A 4 GB video is excluded without being opened. */
  maxBytes?: number;
}

export interface FileDiscovery {
  /** False on web. Callers branch on this rather than sniffing the platform. */
  isSupported(): Promise<boolean>;

  /**
   * Ask for storage access. Called from a screen that has already explained what will
   * be read and where it goes — a permission dialog with no context is denied, and
   * Android does not ask twice.
   */
  requestPermission(): Promise<PermissionState>;

  /**
   * Enumerate candidates. Async iterable rather than an array, because a device may hold
   * tens of thousands of files and materialising that list wastes memory the scan needs.
   */
  scan(options?: ScanOptions): AsyncIterable<DiscoveredFile>;

  /**
   * Candidates modified after `marker`, so a rescan is not a full rescan. The marker is
   * the highest `modifiedAt` seen in the previous pass, persisted through SecureStorage.
   */
  since(marker: number, options?: ScanOptions): AsyncIterable<DiscoveredFile>;

  /**
   * How many candidates match, before reading any of them.
   *
   * Exists so progress can be `142 of 3,417` rather than a spinner. A spinner during a
   * scan of thousands of files is indistinguishable from a hang, and an examiner
   * watching one cannot tell whether the system is working.
   */
  count(options?: ScanOptions & { since?: number }): Promise<number>;

  /** Read one file's bytes, once it has passed filtering and dedup. */
  read(path: string): Promise<Uint8Array>;
}

/** Sensible defaults for the first pass. Documents, not media libraries. */
export const DEFAULT_SCAN: Required<Pick<ScanOptions, 'limit' | 'order' | 'include' | 'maxBytes'>> =
  {
    limit: 500,
    order: 'newest',
    include: ['image/', 'application/pdf'],
    maxBytes: 25 * 1024 * 1024,
  };
