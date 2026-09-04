import { useCallback, useEffect, useRef, useState } from 'react';

import type { DiscoveredFile, PermissionState } from '@memora/core';

import { AndroidFileDiscovery } from '@/platform/discovery.native';
import { apiFetch, clearPairing } from '@/platform/api';

/**
 * Scanning the phone for documents it already holds, and sending them to the laptop.
 *
 * This is the capability the whole native shell exists for. Everything else in the app
 * runs in a browser; a browser cannot enumerate a gallery.
 */

/** Highest `modifiedAt` sent to the laptop, so a rescan is not a full rescan. */
const MARKER_KEY = 'memora.scan_marker';

/**
 * How many uploads are in flight at once.
 *
 * Not higher: the laptop OCRs and embeds each file as it arrives, so the server is the
 * bottleneck and a deeper queue only moves the waiting from the phone to the socket. Not
 * one: a single file in flight leaves the network idle during every extraction.
 */
const CONCURRENCY = 3;

export type ScanMode = 'quick' | 'full';

export type ScanPhase =
  | 'idle'
  | 'consent'
  | 'permission'
  | 'choosing'
  | 'scanning'
  | 'done'
  | 'error';

export interface ScanProgress {
  /** Candidates the device reported. The denominator, so progress is a count. */
  total: number;
  seen: number;
  uploaded: number;
  /** Already in the corpus - the server deduplicated by content hash. */
  duplicate: number;
  failed: number;
  currentName: string | null;
  elapsedMs: number;
}

const EMPTY: ScanProgress = {
  total: 0,
  seen: 0,
  uploaded: 0,
  duplicate: 0,
  failed: 0,
  currentName: null,
  elapsedMs: 0,
};

function readMarker(): number {
  try {
    return Number(localStorage.getItem(MARKER_KEY) ?? 0) || 0;
  } catch {
    return 0;
  }
}

function writeMarker(value: number): void {
  try {
    localStorage.setItem(MARKER_KEY, String(value));
  } catch {
    // Storage blocked. The next scan re-reads files it has already sent, which the
    // server deduplicates - slower, not wrong.
  }
}

type UploadOutcome = 'uploaded' | 'duplicate' | 'failed' | 'unauthorized';

/** One file, read and posted. Returns what happened so the counters stay honest. */
async function upload(
  discovery: AndroidFileDiscovery,
  file: DiscoveredFile,
): Promise<UploadOutcome> {
  try {
    const bytes = await discovery.read(file.path);
    const form = new FormData();
    form.append('file', new Blob([bytes as BlobPart], { type: file.mimeType }), file.name);
    // Identity for reconciliation. The content hash identifies the bytes; this identifies
    // the place on the device, which is what "is it still there?" asks about.
    form.append('device_path', file.path);

    const response = await apiFetch('/api/uploads', { method: 'POST', body: form });
    // 401 is not a bad file, it is a dead pairing, and lumping the two together hid a
    // total lockout behind a plausible number. The API restarted, its in-memory pairing
    // store emptied, and the scan cheerfully reported "326 skipped" while every single
    // upload was being refused. A per-file failure and a broken connection must never
    // land in the same counter.
    if (response.status === 401) return 'unauthorized';
    if (!response.ok) return 'failed';

    // The upload route returns the existing memory when the hash already matched, so a
    // rescan costs a transfer but never a second copy. Distinguished here only to keep
    // the count meaningful - "412 uploaded" when 400 were already known would be a lie.
    const body = (await response.json()) as { chunks?: number; deduplicated?: boolean };
    return body.deduplicated ? 'duplicate' : 'uploaded';
  } catch {
    // One unreadable or oversized file must not end a scan of thousands.
    return 'failed';
  }
}

export function useDeviceScan() {
  const [phase, setPhase] = useState<ScanPhase>('idle');
  const [permission, setPermission] = useState<PermissionState>('prompt');
  const [progress, setProgress] = useState<ScanProgress>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const cancelled = useRef(false);
  const discovery = useRef(new AndroidFileDiscovery());

  /**
   * Re-read the permission, and never let a bridge failure look like a denial.
   *
   * The rejection this catch exists for was silent for an entire debugging session. The
   * native plugin was not registered, so every call rejected with "not implemented"; the
   * caller discarded the rejection with `void`, the screen stayed on "waiting for file
   * access", and the visible symptom accused Android's permission model of a fault that
   * was six lines of missing Java. A plugin that is absent and a permission that is
   * refused are different problems and must not produce the same screen.
   */
  const recheckPermission = useCallback(async () => {
    try {
      const state = await discovery.current.checkPermission();
      setPermission(state);
      if (state === 'granted') setPhase('choosing');
      return state;
    } catch (err) {
      setError(
        `The app cannot reach its file-scanning plugin: ${
          err instanceof Error ? err.message : 'unknown error'
        }`,
      );
      setPhase('error');
      return 'denied' as PermissionState;
    }
  }, []);

  /**
   * MANAGE_EXTERNAL_STORAGE is granted on a full-screen Settings page with NO result
   * callback — the app is simply resumed — so the grant has to be discovered rather than
   * delivered.
   *
   * **This polls rather than listening, because listening did not work.** The first
   * version hung on `visibilitychange`, which a Capacitor WebView does not reliably fire
   * when another Android activity comes and goes. Observed on device: the permission was
   * granted in Settings, `appops` confirmed `allow`, and this screen sat on "waiting"
   * indefinitely — precisely the failure the plan predicted, arriving through the event
   * that was supposed to prevent it.
   *
   * A poll cannot miss an event that never fires. It runs only while this one screen is
   * open, costs a single AppOps lookup per tick, and stops the moment the phase changes.
   * The visibility listener is kept as the fast path when it does fire.
   */
  useEffect(() => {
    if (phase !== 'permission') return;

    let stopped = false;
    const check = () => {
      if (stopped) return;
      void recheckPermission();
    };

    const timer = setInterval(check, 1500);
    document.addEventListener('visibilitychange', check);
    window.addEventListener('focus', check);
    check();

    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
      window.removeEventListener('focus', check);
    };
  }, [phase, recheckPermission]);

  const requestPermission = useCallback(async () => {
    setPhase('permission');
    try {
      const state = await discovery.current.requestPermission();
      setPermission(state);
      if (state === 'granted') setPhase('choosing');
    } catch (err) {
      // Same reason as above: say the plugin is missing rather than implying the user
      // refused something they were never asked for.
      setError(
        `The app cannot reach its file-scanning plugin: ${
          err instanceof Error ? err.message : 'unknown error'
        }`,
      );
      setPhase('error');
    }
  }, []);

  const start = useCallback(async (mode: ScanMode) => {
    cancelled.current = false;
    setError(null);
    setPhase('scanning');

    const startedAt = performance.now();
    // Quick start is the default and is deliberately partial: a phone holds thousands of
    // files and indexing all of them is hours of OCR. Useful in a minute beats complete
    // in two hours, and a full scan is one tap away.
    const limit = mode === 'quick' ? 500 : Number.MAX_SAFE_INTEGER;
    const marker = mode === 'quick' ? readMarker() : 0;

    let total = 0;
    try {
      // Same `since` the iteration will use, or the denominator describes a
      // different scan from the one running.
      total = await discovery.current.count({ since: marker });
    } catch {
      // A missing denominator degrades progress to a bare count. It does not stop a scan.
      total = 0;
    }
    setProgress({ ...EMPTY, total: mode === 'quick' ? Math.min(total, limit) : total });

    const seenPaths: string[] = [];
    let highest = marker;
    const inFlight = new Set<Promise<void>>();
    let seen = 0;

    let lockedOut = false;

    const track = (result: UploadOutcome, name: string) => {
      if (result === 'unauthorized') {
        lockedOut = true;
        cancelled.current = true;
        return;
      }
      return
      setProgress((p) => ({
        ...p,
        seen: p.seen + 1,
        uploaded: p.uploaded + (result === 'uploaded' ? 1 : 0),
        duplicate: p.duplicate + (result === 'duplicate' ? 1 : 0),
        failed: p.failed + (result === 'failed' ? 1 : 0),
        currentName: name,
        elapsedMs: performance.now() - startedAt,
      }));
    };

    try {
      const source =
        marker > 0
          ? discovery.current.since(marker, { limit })
          : discovery.current.scan({ limit });

      for await (const file of source) {
        if (cancelled.current) break;
        seen += 1;
        if (seen > limit) break;

        seenPaths.push(file.path);
        highest = Math.max(highest, file.modifiedAt);

        // A job removes itself when it settles, so `inFlight.size` is the true depth and
        // Promise.race blocks only until a slot actually frees.
        const job: Promise<void> = upload(discovery.current, file)
          .then((result) => track(result, file.name))
          .finally(() => inFlight.delete(job));
        inFlight.add(job);
        if (inFlight.size >= CONCURRENCY) await Promise.race(inFlight);
      }
      await Promise.all(inFlight);

      if (lockedOut) {
        // The token is gone, so nothing was indexed and nothing can be reconciled.
        // Dropping the stored pairing sends the app back to the QR screen by itself.
        clearPairing();
        setError(
          'Your computer no longer recognises this phone - it has probably been ' +
            'restarted. Nothing was indexed. Scan the QR code again to reconnect.',
        );
        setPhase('error');
        return;
      }

      if (highest > 0) writeMarker(highest);

      // Only a full, uncancelled scan can prove a file is gone. A quick scan sends its
      // paths too, but with complete=false the server explicitly does nothing with them -
      // reading absence from a 500-file page would mark most of the corpus removed.
      await apiFetch('/api/device/reconcile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths: seenPaths,
          complete: mode === 'full' && !cancelled.current,
        }),
      }).catch(() => undefined);

      setProgress((p) => ({ ...p, currentName: null, elapsedMs: performance.now() - startedAt }));
      setPhase('done');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The scan stopped unexpectedly.');
      setPhase('error');
    }
  }, []);

  const cancel = useCallback(() => {
    cancelled.current = true;
  }, []);

  return {
    phase,
    setPhase,
    permission,
    progress,
    error,
    requestPermission,
    recheckPermission,
    start,
    cancel,
  };
}
