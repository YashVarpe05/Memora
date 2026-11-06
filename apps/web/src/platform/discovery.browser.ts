import type { DiscoveredFile, FileDiscovery, PermissionState, ScanOptions } from '@memora/core';
import { readState, writeState } from './indexStore';

interface Entry {
  kind: 'file' | 'directory';
  name: string;
  getFile(): Promise<File>;
  values(): AsyncIterable<Entry>;
  queryPermission(): Promise<PermissionState>;
  requestPermission(): Promise<PermissionState>;
  isSameEntry(other: Entry): Promise<boolean>;
}
type Folder = { id: string; handle: Entry };

/** A browser can read only a folder explicitly selected by its owner. */
export class BrowserFileDiscovery implements FileDiscovery {
  constructor(private store = { readState, writeState }) {}

  private folders: Folder[] = [];
  private files = new Map<string, File>();
  pathPrefixes: string[] = [];
  fallback = false;

  async isSupported() { return true; }
  async checkPermission(): Promise<PermissionState> {
    if (this.fallback) return this.files.size ? 'granted' : 'prompt';
    if (!this.folders.length) return 'prompt';
    for (const folder of this.folders) {
      if (await folder.handle.queryPermission() !== 'granted') return 'prompt';
    }
    return 'granted';
  }
  async requestPermission(): Promise<PermissionState> {
    const picker = (window as unknown as { showDirectoryPicker?: () => Promise<Entry> })
      .showDirectoryPicker;
    if (picker) {
      const handle = await picker();
      const folders = (await this.store.readState<Folder[]>('folders')) ?? [];
      let found: Folder | undefined;
      for (const folder of folders) {
        if (await folder.handle.isSameEntry(handle)) found = folder;
      }
      const selected = found ?? { id: crypto.randomUUID(), handle };
      if (!found) folders.push(selected);
      await this.store.writeState('folders', folders);
      this.fallback = false;
      await this.restore();
      return 'granted';
    }
    // Browser fallback is a snapshot. Selecting the folder again is an explicit rescan.
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;
    input.multiple = true;
    const files = await new Promise<File[]>((resolve) => {
      input.onchange = () => resolve(Array.from(input.files ?? []));
      input.oncancel = () => resolve([]);
      input.click();
    });
    if (!files.length) return 'prompt';
    // Snapshot folders cannot be compared by identity. Never reconcile their absence
    // against another selection, even when their display names happen to match.
    this.fallback = true;
    this.folders = [];
    const prefix = `snapshot/${crypto.randomUUID()}/`;
    this.pathPrefixes = [prefix];
    this.files.clear();
    for (const file of files) this.files.set(prefix + file.webkitRelativePath, file);
    return 'granted';
  }
  async restore(): Promise<boolean> {
    const folders = (await this.store.readState<Folder[]>('folders')) ?? [];
    const permitted: Folder[] = [];
    for (const folder of folders) {
      try {
        if (await folder.handle.queryPermission() === 'granted') permitted.push(folder);
      } catch { /* A revoked handle must not be treated as a deleted folder. */ }
    }
    if (!permitted.length) return false;
    this.folders = permitted;
    this.fallback = false;
    this.pathPrefixes = permitted.map(folder => `browser/${folder.id}/`);
    return true;
  }
  /** Saved folders the browser has not currently granted, e.g. after a browser restart. */
  async pendingFolders(): Promise<number> {
    const folders = (await this.store.readState<Folder[]>('folders')) ?? [];
    let pending = 0;
    for (const folder of folders) {
      try {
        if (await folder.handle.queryPermission() !== 'granted') pending++;
      } catch { pending++; }
    }
    return pending;
  }
  /** Re-grant saved folders without re-picking them. Must run from a user gesture. */
  async reallow(): Promise<boolean> {
    const folders = (await this.store.readState<Folder[]>('folders')) ?? [];
    for (const folder of folders) {
      try { await folder.handle.requestPermission(); } catch { /* Stays pending. */ }
    }
    return this.restore();
  }
  async *scan(options?: ScanOptions): AsyncIterable<DiscoveredFile> {
    if (await this.checkPermission() !== 'granted') {
      throw new Error('Folder access expired. Choose the folder again before rescanning.');
    }
    const files = this.files;
    async function* walk(entry: Entry, prefix: string): AsyncIterable<[string, File]> {
      for await (const child of entry.values()) {
        if (child.kind === 'directory') yield* walk(child, prefix + child.name + '/');
        else yield [prefix + child.name, await child.getFile()];
      }
    }
    const folders = [...this.folders];
    async function* entries(): AsyncIterable<[string, File]> {
      if (!folders.length) { yield* files; return; }
      files.clear();
      for (const folder of folders) yield* walk(folder.handle, `browser/${folder.id}/`);
    }
    let seen = 0;
    for await (const [path, file] of entries()) {
      if (seen >= (options?.limit ?? Number.MAX_SAFE_INTEGER)) return;
      seen++;
      files.set(path, file);
      yield { path, name: file.name, size: file.size, modifiedAt: file.lastModified,
        mimeType: file.type || 'application/octet-stream' };
    }
  }
  async *since(marker: number, options?: ScanOptions) {
    for await (const file of this.scan(options)) if (file.modifiedAt >= marker) yield file;
  }
  async count() { return this.files.size; }
  async read(path: string) {
    const file = this.files.get(path);
    if (!file) throw new Error('Folder access expired. Choose the folder again.');
    return new Uint8Array(await file.arrayBuffer());
  }
}
