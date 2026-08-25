import { CalendarDays, FileText, Image as ImageIcon, Mail, MessageSquare } from 'lucide-react';
import { useState } from 'react';

import { cn } from '@/lib/utils';

import type { SearchResult } from './useSearch';

const ICONS: Record<string, typeof FileText> = {
  pdf: FileText,
  image: ImageIcon,
  calendar: CalendarDays,
  email: Mail,
  chat: MessageSquare,
};

/** Escape before injecting into a regex — filenames and queries contain regex characters. */
function escape(term: string): string {
  return term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const STOPWORDS = new Set([
  'the', 'a', 'an', 'my', 'of', 'in', 'on', 'at', 'to', 'that', 'this', 'i', 'was',
  'is', 'it', 'and', 'for', 'with', 'me', 'they', 'where', 'what', 'when',
]); // fmt: skip

/**
 * Highlight the query's own words inside the snippet.
 *
 * Answers "why this one" in the place the eye is already looking, and makes the match a
 * fact the reader can check rather than a claim the ranking makes. Done in the component:
 * the API returns data, the shell renders it.
 */
function Highlighted({ text, query }: { text: string; query: string }) {
  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .map((t) => t.replace(/[^a-z0-9]/g, ''))
    .filter((t) => t.length > 2 && !STOPWORDS.has(t));

  if (!terms.length) return <>{text}</>;

  const parts = text.split(new RegExp(`(${terms.map(escape).join('|')})`, 'gi'));
  return (
    <>
      {parts.map((part, i) =>
        terms.includes(part.toLowerCase()) ? (
          <mark key={i} className="rounded bg-accent-soft px-0.5 text-accent">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

/**
 * Why this document ranked where it did.
 *
 * `score` is the boosted score and `raw_score` is the similarity refusal is decided on;
 * the gap between them is exactly the filter bonus. Surfacing it turns FILTER_BONUS from
 * an implementation detail into the visible reason the right answer won.
 */
function whyItWon(result: SearchResult): string {
  const boosted = result.score - result.raw_score;
  if (boosted > 0.001) return 'matched content and your filters';
  if (boosted < -0.001) return 'matched content, but not your filters';
  return 'matched on content';
}

export function ResultCard({
  result,
  query,
  onOpen,
}: {
  result: SearchResult;
  query: string;
  onOpen: (result: SearchResult) => void;
}) {
  const [thumbBroken, setThumbBroken] = useState(false);
  const Icon = ICONS[result.source_type] ?? FileText;
  const showThumb = result.thumbnail_url && !thumbBroken;

  return (
    <button
      type="button"
      onClick={() => onOpen(result)}
      className={cn(
        'flex w-full items-start gap-3 rounded-card border border-line bg-surface p-3',
        'text-left transition-colors hover:border-accent/40 active:bg-surface-sunken',
      )}
    >
      <div className="relative shrink-0">
        {showThumb ? (
          <img
            src={`/api${result.thumbnail_url}`}
            alt=""
            loading="lazy"
            onError={() => setThumbBroken(true)}
            className="size-14 rounded-md border border-line object-cover"
          />
        ) : (
          // Not a broken image. Several corpus files have no thumbnail at all.
          <div className="flex size-14 items-center justify-center rounded-md border border-line bg-surface-sunken">
            <Icon className="size-5 text-ink-faint" aria-hidden />
          </div>
        )}
        <span
          className={cn(
            'absolute -left-1 -top-1 flex size-5 items-center justify-center rounded-full',
            'text-[0.625rem] font-semibold',
            result.rank === 1 ? 'bg-accent text-white' : 'bg-surface-sunken text-ink-faint',
          )}
          aria-label={`rank ${result.rank}`}
        >
          {result.rank}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm font-medium text-ink">{result.title}</span>
        {/* min-w-0 + truncate: "WhatsApp Image 2026-07-03 at 01.24.47 (1).jpeg" is real. */}
        <span className="truncate text-xs text-ink-faint">
          {result.filename} · {result.source_type}
          {result.page ? ` · p.${result.page}` : ''}
        </span>
        {result.snippet ? (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-muted">
            <Highlighted text={result.snippet} query={query} />
          </p>
        ) : (
          <p className="mt-1 text-xs italic text-ink-faint">no readable text in this file</p>
        )}
        {result.rank === 1 && (
          <span className="mt-1 text-[0.6875rem] text-ink-faint">{whyItWon(result)}</span>
        )}
      </div>
    </button>
  );
}
