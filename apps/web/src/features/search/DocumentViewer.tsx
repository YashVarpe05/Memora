import { Download, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/platform/api';
import { useAuthedMedia } from '@/platform/useAuthedMedia';
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
  const media = useAuthedMedia(`/api${result.file_url}`);
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
    if (!isPdf) return;
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
  }, [isPdf, page, result.memory_id]);
  const src = isPdf ? preview : media.src;
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
      {!src && !error && (isPdf || isImage) && <p role="status" className="p-6">Loading preview…</p>}
      {(error || media.failed) && <p role="alert" className="p-6 text-warn">{error ?? 'File could not be loaded.'}</p>}
      {!isPdf && !isImage && <div className="flex flex-col gap-4 p-6">
        <p className="whitespace-pre-wrap text-sm">{result.snippet}</p>
        {media.src && <a className="text-accent underline" href={media.src} download={result.filename}>Download and open {result.filename}</a>}
      </div>}
    </div>
  </div>;
}
