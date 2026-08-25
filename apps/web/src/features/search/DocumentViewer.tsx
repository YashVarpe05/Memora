import { Download, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { cn } from '@/lib/utils';

import type { SearchResult } from './useSearch';

/**
 * The answer is the file, and a file you cannot open is not an answer.
 *
 * Full-screen on mobile rather than a modal inside a scrolling page — at 375px a dialog
 * with its own scroll container inside another one is unusable.
 *
 * PDFs render in an <object>, which delegates to the browser's viewer. If that fails —
 * and it does, on some mobile browsers — the fallback is download, not a blank frame.
 */
export function DocumentViewer({
  result,
  onClose,
}: {
  result: SearchResult;
  onClose: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const src = `/api${result.file_url}`;
  const isImage = result.source_type === 'image';
  const isPdf = result.source_type === 'pdf';

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={result.title}
      className="fixed inset-0 z-50 flex flex-col bg-canvas"
    >
      <header
        className={cn(
          'flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 pt-safe',
        )}
      >
        <div className="flex h-14 min-w-0 flex-1 flex-col justify-center">
          <span className="truncate text-sm font-medium">{result.title}</span>
          <span className="truncate text-xs text-ink-faint">{result.filename}</span>
        </div>
        <a
          href={src}
          download={result.filename}
          className={cn(
            'flex size-11 items-center justify-center rounded-lg text-ink-muted',
            'hover:bg-surface-sunken hover:text-ink',
          )}
          aria-label="Download"
        >
          <Download className="size-5" aria-hidden />
        </a>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className={cn(
            'flex size-11 items-center justify-center rounded-lg text-ink-muted',
            'hover:bg-surface-sunken hover:text-ink',
          )}
        >
          <X className="size-5" aria-hidden />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto bg-surface-sunken">
        {isImage && !failed && (
          <img
            src={src}
            alt={result.title}
            onError={() => setFailed(true)}
            className="mx-auto max-w-full"
          />
        )}
        {isPdf && !failed && (
          <object data={src} type="application/pdf" className="h-full w-full">
            {/* Rendered when the browser has no PDF viewer. */}
            <Fallback filename={result.filename} src={src} />
          </object>
        )}
        {(failed || (!isImage && !isPdf)) && <Fallback filename={result.filename} src={src} />}
      </div>
    </div>
  );
}

function Fallback({ filename, src }: { filename: string; src: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-sm text-ink-muted">This file can’t be previewed here.</p>
      <a
        href={src}
        download={filename}
        className={cn(
          'inline-flex min-h-11 items-center gap-2 rounded-lg border border-line',
          'bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-sunken',
        )}
      >
        <Download className="size-4" aria-hidden /> Download {filename}
      </a>
    </div>
  );
}
