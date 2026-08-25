import { Loader2, Search } from 'lucide-react';
import { useState } from 'react';

import { DegradedBanner } from '@/components/DegradedBanner';
import { cn } from '@/lib/utils';

import { DocumentViewer } from './DocumentViewer';
import { ResultCard } from './ResultCard';
import { UnderstoodChips } from './UnderstoodChips';
import { useSearch, type SearchResult } from './useSearch';

/** Real queries against the real corpus. They teach the interaction by example. */
const EXAMPLES = [
  'the whatsapp message from aradhana',
  'the mail yash sent to rutuja',
  'the uipath job in chennai',
];

export function SearchView() {
  const search = useSearch();
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState<SearchResult | null>(null);

  const run = (query: string) => {
    setDraft(query);
    void search.search(query);
  };

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col px-4">
      <form
        className="sticky top-0 z-10 -mx-4 bg-canvas px-4 pb-3 pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          run(draft);
        }}
      >
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-faint"
            aria-hidden
          />
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="describe it in your own words…"
            aria-label="Describe the document"
            className={cn(
              'h-12 w-full rounded-card border border-line bg-surface pl-9 pr-3',
              'text-sm text-ink placeholder:text-ink-faint',
              'focus:border-accent focus:outline-none',
            )}
          />
        </div>
      </form>

      <div className="flex min-h-0 flex-1 flex-col gap-3 pb-6">
        {search.status !== 'idle' && (
          <UnderstoodChips
            stage1={search.stage1}
            filters={search.filters}
            detail={search.stage1Detail}
          />
        )}

        <DegradedBanner message={search.degradedMessage} />

        {search.status === 'idle' && (
          <div className="flex flex-col gap-3 pt-6">
            <p className="text-sm text-ink-muted">
              You remember the document, not its filename. Describe it the way you remember
              it — who sent it, roughly when, what it was about.
            </p>
            <div className="flex flex-col gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => run(example)}
                  className={cn(
                    'min-h-11 rounded-card border border-line bg-surface px-3 py-2',
                    'text-left text-sm text-ink-muted hover:border-accent/40 hover:text-ink',
                  )}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {search.error && <p className="pt-6 text-sm text-warn">{search.error}</p>}

        {search.status !== 'idle' && !search.error && search.results.length === 0 && (
          <div className="flex flex-col gap-2 pt-6">
            {search.status === 'searching' ? (
              <p className="flex items-center gap-2 text-sm text-ink-faint">
                <Loader2 className="size-4 animate-spin" aria-hidden /> searching…
              </p>
            ) : (
              <>
                {/* Refusal is a correct answer, not a crash. */}
                <p className="text-sm font-medium text-ink">I don’t have that.</p>
                <p className="text-sm text-ink-muted">
                  {search.reason ??
                    'Nothing in your documents matches that description closely enough to show you.'}
                </p>
              </>
            )}
          </div>
        )}

        {search.results.length > 0 && (
          <ul className="flex flex-col gap-2">
            {search.results.map((result) => (
              <li
                key={result.memory_id}
                // The re-rank animates so reordering reads as an improvement rather than
                // a glitch. The chips appearing above are its visible cause.
                className="transition-all duration-300"
              >
                <ResultCard result={result} query={search.query} onOpen={setOpen} />
              </li>
            ))}
          </ul>
        )}

        {search.status === 'done' && search.results.length > 0 && (
          // Do not hide the known gap. A system that names what it cannot find is more
          // credible than one that silently returns nothing - and it sets up visual
          // search as the answer to a problem already seen.
          <p className="pt-2 text-xs text-ink-faint">
            Some files contain no readable text and can’t be found by description yet.
          </p>
        )}
      </div>

      {open && <DocumentViewer result={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
