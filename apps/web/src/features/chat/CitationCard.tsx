import { CalendarDays, Code, FileText, Image, Mail, Mic, StickyNote } from 'lucide-react';

import type { Citation, SourceType } from '@memora/core';
import { Routes } from '@memora/core';

import { useNavigator } from '@/platform/navigator';

const ICONS: Record<SourceType, typeof Mail> = {
  email: Mail,
  pdf: FileText,
  audio: Mic,
  image: Image,
  note: StickyNote,
  calendar: CalendarDays,
  code: Code,
};

/**
 * A citation the reader can act on. Clicking opens the source - in phase 5 that
 * lands on the span highlighted. PRODUCT.md: no citation, no answer.
 */
export function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const navigator = useNavigator();
  const Icon = ICONS[citation.sourceType];

  return (
    <button
      type="button"
      onClick={() => navigator.navigate(Routes.Memory(citation.memoryId))}
      className="flex w-full items-start gap-3 rounded-card border border-line bg-surface p-3 text-left transition-colors hover:border-accent"
    >
      <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-[0.6875rem] font-semibold text-accent">
        {index + 1}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex items-center gap-1.5 text-xs text-ink-muted">
          <Icon className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate">{citation.title}</span>
        </span>
        <span className="line-clamp-2 text-sm text-ink">{citation.snippet}</span>
      </span>
    </button>
  );
}
