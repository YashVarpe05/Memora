import { Download, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { apiFetch, isNative } from '@/platform/api';
import { AndroidFileDiscovery } from '@/platform/discovery.native';
import { useAuthedMedia } from '@/platform/useAuthedMedia';
import { isLocalMode } from '@/platform/localMode';
import { localUriFor } from '@/platform/localIndex.native';
import type { SearchResult } from './useSearch';

export function DocumentViewer({ result, onClose }: { result: SearchResult; onClose: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(result.page ?? 1);
  const [pages, setPages] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isPdf = result.source_type === 'pdf';
  const isImage = result.source_type === 'image';
  const local = isLocalMode();
  const media = useAuthedMedia(local ? null : `/api${result.file_url}`);
  // A document found on this phone is indexed from text, so the server holds no file. The
  // phone that found it still has it and opens it itself.
  const [localPath, setLocalPath] = useState<string | null>(null);
  const [localSrc, setLocalSrc] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const serverFileMissing = media.failed || error !== null;
  useEffect(() => {
    if (local) { setLocalPath(localUriFor(result.memory_id)); return; }
    if (!isNative() || !serverFileMissing) return;
    let cancelled = false;
    void apiFetch(`/api/memories/${result.memory_id}/device-paths`).then(async response => {
      if (!response.ok) return;
      const { paths } = await response.json() as { paths: string[] };
      if (!cancelled) setLocalPath(paths.find(path => path.startsWith('content://')) ?? null);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [serverFileMissing, result.memory_id, local]);
  useEffect(() => {
    if (!localPath || !isImage) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    void new AndroidFileDiscovery().read(localPath).then(bytes => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(new Blob([bytes as BlobPart]));
      setLocalSrc(objectUrl);
    }).catch(() => setLocalError('This file could not be read on this phone.'));
    return () => { cancelled = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [localPath, isImage]);
  async function openLocal() {
    if (!localPath) return;
    setLocalError(null);
    try { await new AndroidFileDiscovery().open(localPath); }
    catch (err) { setLocalError(err instanceof Error ? err.message : 'Could not open this file.'); }
  }
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const controls = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], select, input, [tabindex="0"]',
    ) ?? []).filter(element => element.getClientRects().length > 0);
    const first = controls()[0];
    (first ?? dialog.current)?.focus({ preventScroll: true });
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return; }
      if (event.key !== 'Tab') return;
      const items = controls();
      const first = items[0];
      const last = items.at(-1);
      if (!first || !last) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || !dialog.current?.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.current?.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener('keydown', keyboard);
    return () => { window.removeEventListener('keydown', keyboard); previous?.focus({ preventScroll: true }); };
  }, [onClose]);
  useEffect(() => {
    if (!isPdf || local) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setPreview(null); setError(null);
    void apiFetch(`/api/memories/${result.memory_id}/pages/${page}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('This page could not be loaded. Try another page or download the file.');
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        setPages(Number(response.headers.get('X-Page-Count')) || page);
        objectUrl = URL.createObjectURL(blob);
        setPreview(objectUrl);
      }).catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Preview unavailable.');
      });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [isPdf, page, result.memory_id, local]);
  const src = isPdf ? preview : (media.src ?? localSrc);
  return <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label={result.document_label ?? result.title}
    className="fixed inset-0 z-50 flex flex-col bg-canvas">
    <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 pt-safe">
      <div className="flex h-14 min-w-0 flex-1 flex-col justify-center">
        <span className="truncate text-sm font-medium">{result.document_label ?? result.title}</span>
        <span className="truncate text-xs text-ink-faint">{result.filename}</span>
      </div>
      {media.src && <a href={media.src} download={result.filename} aria-label="Download" className="p-3"><Download className="size-5" /></a>}
      <button onClick={onClose} aria-label="Close" className="p-3"><X className="size-5" /></button>
    </header>
    <div className="flex flex-wrap items-center justify-center gap-3 border-b border-line p-2 text-sm">
      {isPdf && <>
        <button className="min-h-11 px-3 disabled:opacity-40" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
        <span>Page {page} / {pages < page ? '…' : pages}</span>
        <button className="min-h-11 px-3 disabled:opacity-40" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
      </>}
      {(isPdf || isImage) && <label>Zoom <select className="rounded bg-surface p-2" value={zoom} onChange={e => setZoom(Number(e.target.value))}>
        {[75, 100, 150, 200, 300].map(n => <option value={n} key={n}>{n}%</option>)}
      </select></label>}
    </div>
    <div tabIndex={0} role="region" aria-label="Document preview" className="min-h-0 flex-1 overflow-auto bg-surface-sunken focus-visible:outline-2 focus-visible:outline-accent">
      {(isPdf || isImage) && src && <img src={src} alt={`${result.document_label ?? result.title}, page ${page}`}
        className="mx-auto max-w-none" style={{ width: `${zoom}%` }} />}
      {!src && !error && !localPath && (isPdf || isImage) && <p role="status" className="p-6">Loading preview…</p>}
      {(error || media.failed) && !localPath && <p role="alert" className="p-6 text-warn">{error ?? 'File could not be loaded. It may be stored only on the device where it was found.'}</p>}
      {localPath && <div className="flex flex-col gap-3 p-6">
        <p className="text-sm">This file is stored on this phone.</p>
        <button className="min-h-11 self-start rounded bg-accent px-4 text-white" onClick={() => void openLocal()}>Open on this phone</button>
        {localError && <p role="alert" className="text-sm text-warn">{localError}</p>}
        {!isImage && <p className="whitespace-pre-wrap text-sm text-ink-muted">{result.snippet}</p>}
      </div>}
      {!isPdf && !isImage && !localPath && <div className="flex flex-col gap-4 p-6">
        <p className="whitespace-pre-wrap text-sm">{result.snippet}</p>
        {media.src && <a className="text-accent underline" href={media.src} download={result.filename}>Download and open {result.filename}</a>}
      </div>}
    </div>
  </div>;
}
