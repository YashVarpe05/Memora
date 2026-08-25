import { Loader2, SlashIcon, Sparkles, TriangleAlert } from 'lucide-react';

import type { Stage1State } from './useSearch';

/**
 * What the system understood from the query, shown above the results.
 *
 * This does three jobs at once, which is why it earns the space:
 *
 * 1. It proves stage 1 ran, rather than the user taking a number on trust.
 * 2. It is the visible cause of the re-rank. Rows reordering under a reading user is a
 *    glitch; rows reordering as "understood: from aradhana, chat" appears is an
 *    improvement.
 * 3. It puts the two-stage architecture — the project's central contribution — on screen
 *    without anyone narrating it.
 *
 * Skipped and failed render differently on purpose. The API keeps them apart because a
 * skip is a choice and a failure is a fault, and an ambiguous empty row would throw that
 * away at the last inch.
 */

const LABELS: Record<string, string> = {
  source_types: 'type',
  sender: 'from',
  entities: 'about',
  after: 'after',
  before: 'before',
  document_type: 'document',
};

function chipsFrom(filters: Record<string, unknown> | null): string[] {
  if (!filters) return [];
  const out: string[] = [];
  for (const [key, value] of Object.entries(filters)) {
    if (key === 'semantic_query' || key === 'needs_time_resolution') continue;
    if (value === null || value === undefined || value === '') continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      out.push(`${LABELS[key] ?? key}: ${value.join(', ')}`);
    } else {
      out.push(`${LABELS[key] ?? key}: ${String(value)}`);
    }
  }
  return out;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-faint">{children}</div>
  );
}

export function UnderstoodChips({
  stage1,
  filters,
  detail,
}: {
  stage1: Stage1State;
  filters: Record<string, unknown> | null;
  detail: string | null;
}) {
  if (stage1 === 'off') return null;

  if (stage1 === 'pending') {
    return (
      <Shell>
        <Loader2 className="size-3 animate-spin" aria-hidden />
        <span>reading your description…</span>
      </Shell>
    );
  }

  if (stage1 === 'failed') {
    // Distinct from a skip, deliberately. Something went wrong.
    return (
      <Shell>
        <TriangleAlert className="mt-0.5 size-3 shrink-0 text-warn" aria-hidden />
        <span className="text-warn">
          could not read your description, so these are plain-similarity results and may be
          less precise{detail ? ` — ${detail.split('.')[0]}` : ''}
        </span>
      </Shell>
    );
  }

  if (stage1 === 'skipped') {
    // Distinct from a failure, deliberately. Nothing went wrong; there was nothing to find.
    return (
      <Shell>
        <SlashIcon className="size-3" aria-hidden />
        <span>no filters needed — searched everything</span>
      </Shell>
    );
  }

  const chips = chipsFrom(filters);
  if (!chips.length) {
    return (
      <Shell>
        <Sparkles className="size-3" aria-hidden />
        <span>understood as a content search</span>
      </Shell>
    );
  }

  return (
    <Shell>
      <Sparkles className="size-3 text-accent" aria-hidden />
      <span>understood:</span>
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent"
        >
          {chip}
        </span>
      ))}
    </Shell>
  );
}
