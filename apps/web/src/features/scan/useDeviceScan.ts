import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { DiscoveredFile, FileDiscovery, TextExtractor } from '@memora/core';
import type { components } from '@memora/core/types/api';
import { AndroidFileDiscovery } from '@/platform/discovery.native';
import { BrowserFileDiscovery } from '@/platform/discovery.browser';
import { AndroidTextExtractor } from '@/platform/textExtraction.native';
import { indexOnDevice } from './deviceText';
import { apiFetch, isNative, pairedServer } from '@/platform/api';
import { readState, writeState } from '@/platform/indexStore';

type Job = components['schemas']['JobResponse'];
type Jobs = components['schemas']['JobsResponse'];
type SavedFile = { fingerprint: string; job: string };
export type ScanMode = 'quick' | 'full';

export function useIndexController() {
  const discovery = useRef<FileDiscovery>(isNative() ? new AndroidFileDiscovery() : new BrowserFileDiscovery());
  // Android only. The browser cannot OCR a folder it was given, so it keeps uploading.
  const extractor = useRef<TextExtractor | null>(isNative() ? new AndroidTextExtractor() : null);
  const [phase, setPhase] = useState('idle');
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState({ seen: 0, queued: 0, known: 0, failed: 0 });
  const [issues, setIssues] = useState<string[]>([]);
  const [needsReallow, setNeedsReallow] = useState(false);
  const [jobsOffset, setJobsOffset] = useState(0);
  const [jobs, setJobs] = useState<Jobs>({ jobs: [], counts: {} });
  const active = useRef(false);
  const choosing = useRef(false);
  const stop = useRef(false);
  const consentKey = () => `memora.online-consent:${pairedServer()?.url}:${pairedServer()?.token.slice(0, 16)}`;
  const consented = () => localStorage.getItem(consentKey()) === 'yes';

  async function refreshJobs() {
    const connection = pairedServer();
    if (!connection) return;
    try {
      const response = await apiFetch(`/api/index/jobs?offset=${jobsOffset}&limit=100`);
      if (response.ok) {
        const next = await response.json() as Jobs;
        const current = pairedServer();
        if (current?.url === connection.url && current?.token === connection.token) setJobs(next);
      }
    } catch { /* A network interruption leaves the last known progress visible. */ }
  }

  useEffect(() => { void refreshJobs(); }, [jobsOffset]);

  async function start(_mode: ScanMode = 'full') {
    if (active.current || !pairedServer() || !consented()) return;
    active.current = true;
    // The scan only runs while the app is in front. Keep the screen awake meanwhile, or the
    // phone sleeps a few minutes in and silently stops a long first scan.
    let awake: { release(): Promise<void> } | null = null;
    try { awake = await navigator.wakeLock?.request('screen') ?? null; } catch { /* optional */ }
    stop.current = false;
    setError(null); setIssues([]); setPhase('scanning');
    setProgress({ seen: 0, queued: 0, known: 0, failed: 0 });
    const connection = pairedServer();
    const sameConnection = () => {
      const current = pairedServer();
      return current?.token === connection?.token && current?.url === connection?.url;
    };
    const paths: string[] = [];
    let failed = false;
    try {
      const identity = await apiFetch('/api/device/identity');
      if (!identity.ok) throw new Error('Reconnect this device before indexing.');
      const { device_id } = await identity.json() as { device_id: string };
      const key = `files:${pairedServer()!.url}:${device_id}`;
      const known = await readState<Record<string, SavedFile>>(key) ?? {};
      // Enumerate metadata each time. Timestamp watermarks can permanently lose failed
      // files, backdated copies, or files modified within the same timestamp second.
      for await (const file of discovery.current.scan({ limit: Number.MAX_SAFE_INTEGER })) {
        if (!sameConnection()) throw new Error('Connection changed. Reconnect and rescan to continue.');
        if (stop.current) break;
        paths.push(file.path);
        const fingerprint = `${file.size}:${file.revision ?? file.modifiedAt}`;
        setProgress(p => ({ ...p, seen: p.seen + 1 }));
        if (known[file.path]?.fingerprint === fingerprint) {
          setProgress(p => ({ ...p, known: p.known + 1 }));
          continue;
        }
        try {
          const problem = unsupported(file);
          if (problem) throw new Error(problem);
          // The phone reads what it can and sends only masked text. A type it cannot read
          // falls through to the upload below; a read that fails does not.
          if (extractor.current) {
            const indexed = await indexOnDevice(extractor.current, file);
            if (indexed) {
              // A photo with no text is normal, not a failure. Remember it so the next scan
              // does not read it again.
              known[file.path] = { fingerprint, job: indexed === 'no-text' ? 'no-text' : indexed.memory_id };
              await writeState(key, known);
              setProgress(p => indexed === 'no-text'
                ? { ...p, known: p.known + 1 } : { ...p, queued: p.queued + 1 });
              continue;
            }
          }
          const bytes = await discovery.current.read(file.path);
          if (!sameConnection()) throw new Error('Connection changed. Reconnect and rescan to continue.');
          if (stop.current) break;
          const form = new FormData();
          form.append('file', new Blob([bytes as BlobPart], { type: file.mimeType }), file.name);
          form.append('device_path', file.path);
          const response = await apiFetch('/api/index/jobs', { method: 'POST', body: form });
          if (response.status === 401) throw new Error('Device connection expired. Reconnect to continue.');
          if (!response.ok) {
            const body = await response.json() as { detail?: string };
            throw new Error(body.detail ?? `Upload failed (${response.status}).`);
          }
          const job = await response.json() as Job;
          known[file.path] = { fingerprint, job: job.id };
          // Only acknowledge after the server durably accepts the bytes and job.
          await writeState(key, known);
          setProgress(p => ({ ...p, queued: p.queued + 1 }));
        } catch (err) {
          failed = true;
          setProgress(p => ({ ...p, failed: p.failed + 1 }));
          setIssues(p => [...p.slice(-49), `${file.name}: ${err instanceof Error ? err.message : 'Could not read this file.'}`]);
          if (!pairedServer()) throw err;
        }
      }
      if (!sameConnection()) throw new Error('Connection changed. Reconnect and rescan to continue.');
      if (!stop.current) {
        const browser = discovery.current instanceof BrowserFileDiscovery ? discovery.current : null;
        const prefixes = browser ? browser.pathPrefixes : [null];
        for (const prefix of prefixes) {
          const response = await apiFetch('/api/device/reconcile', { method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths: prefix ? paths.filter(p => p.startsWith(prefix)) : paths,
              complete: !browser?.fallback, path_prefix: prefix }) });
          if (!response.ok) throw new Error('File availability could not be updated. Rescan to retry.');
          if (!browser?.fallback) {
            for (const path of Object.keys(known)) {
              if ((!prefix || path.startsWith(prefix)) && !paths.includes(path)) delete known[path];
            }
          }
        }
        await writeState(key, known);
      }
      setPhase(stop.current ? 'paused' : failed ? 'attention' : 'done');
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Indexing interrupted. Rescan to continue.');
      setPhase('error');
    } finally { active.current = false; void awake?.release().catch(() => undefined); }
  }

  async function choose() {
    if (active.current || choosing.current) return;
    choosing.current = true;
    setError(null);
    try {
      localStorage.setItem(consentKey(), 'yes');
      const permission = await discovery.current.requestPermission();
      if (permission === 'granted') await start();
      else setPhase('permission');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Folder permission was not granted.');
      setPhase('error');
    } finally { choosing.current = false; }
  }

  async function reallow() {
    const browser = discovery.current;
    if (active.current || choosing.current || !(browser instanceof BrowserFileDiscovery)) return;
    choosing.current = true;
    setError(null);
    try {
      const granted = await browser.reallow();
      setNeedsReallow(await browser.pendingFolders() > 0);
      if (granted) await start();
      else setError('Folder access was not granted. Choose the folder again.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Folder permission was not granted.');
    } finally { choosing.current = false; }
  }

  async function retry(id: string) {
    const response = await apiFetch(`/api/index/jobs/${id}/retry`, { method: 'POST' });
    if (!response.ok) setError('Could not retry. Check your connection.');
    await refreshJobs();
  }

  // Controller lives above the routes: opening Search does not stop a scan. Resume and
  // periodically discover while the application is open; never claim OS background work.
  const latest = useRef({ start, refreshJobs });
  latest.current = { start, refreshJobs };
  useEffect(() => {
    stop.current = false;
    const resume = async () => {
      if (!pairedServer() || !consented() || active.current || choosing.current || stop.current || document.hidden) return;
      if (discovery.current instanceof BrowserFileDiscovery) {
        const restored = await discovery.current.restore();
        setNeedsReallow(await discovery.current.pendingFolders() > 0);
        if (!restored) return;
      } else if (await (discovery.current as AndroidFileDiscovery).checkPermission() !== 'granted') return;
      await latest.current.start();
    };
    const refresh = () => { void latest.current.refreshJobs(); };
    const scan = () => { void resume().catch(() => undefined); };
    const jobsTimer = setInterval(refresh, 3000);
    const scanTimer = setInterval(scan, 60000);
    document.addEventListener('visibilitychange', scan);
    window.addEventListener('focus', scan);
    scan(); refresh();
    return () => {
      clearInterval(jobsTimer); clearInterval(scanTimer); stop.current = true;
      document.removeEventListener('visibilitychange', scan);
      window.removeEventListener('focus', scan);
    };
  }, []);

  useEffect(() => {
    if (phase !== 'permission' || !isNative()) return;
    const timer = setInterval(() => {
      void (discovery.current as AndroidFileDiscovery).checkPermission().then(p => {
        if (p === 'granted') void latest.current.start();
      }).catch(() => setError('Could not check Android storage permission.'));
    }, 1500);
    return () => clearInterval(timer);
  }, [phase]);

  return { phase, progress, issues, error, jobs, jobsOffset, setJobsOffset, choose, start, retry,
    needsReallow, reallow,
    cancel: () => { stop.current = true; },
    disable: () => { stop.current = true; localStorage.removeItem(consentKey()); setPhase('paused'); } };
}

function unsupported(file: DiscoveredFile): string | null {
  if (file.size > 25 * 1024 * 1024) return 'Larger than 25 MB. Split or compress this file.';
  if (!/\.(pdf|png|jpe?g|webp|gif|bmp|heic|heif|txt|md|docx?|eml|ics)$/i.test(file.name)) return 'Unsupported format.';
  return null;
}

export const IndexContext = createContext<ReturnType<typeof useIndexController> | null>(null);
export function useDeviceScan() {
  const controller = useContext(IndexContext);
  if (!controller) throw new Error('Index controller is missing.');
  return controller;
}
