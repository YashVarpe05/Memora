import { useCallback, useRef, useState } from 'react';

import { apiFetch } from '@/platform/api';

import type { components } from '@memora/core/types/api';

type SearchResponse = components['schemas']['SearchResponse'];
export type SearchResult = components['schemas']['SearchResult'];

/**
 * How stage 1 ended up for this search. A skip is a choice and a failure is a fault,
 * and the API keeps them apart deliberately - conflating them lets a quota outage hide
 * inside a field that looks intentional. That distinction has to survive into the UI.
 */
export type Stage1State = 'pending' | 'applied' | 'skipped' | 'failed' | 'off';

export interface SearchState {
  status: 'idle' | 'searching' | 'done' | 'error';
  query: string;
  results: SearchResult[];
  /** Which filters stage 1 extracted. Rendered as chips; also the cause of the re-rank. */
  filters: Record<string, unknown> | null;
  stage1: Stage1State;
  stage1Detail: string | null;
  degradedMessage: string | null;
  refused: boolean;
  reason: string | null;
  error: string | null;
}

const EMPTY: SearchState = {
  status: 'idle',
  query: '',
  results: [],
  filters: null,
  stage1: 'pending',
  stage1Detail: null,
  degradedMessage: null,
  refused: false,
  reason: null,
  error: null,
};

async function post(query: string, stage1: boolean, signal: AbortSignal): Promise<SearchResponse> {
  // POST, never GET: "find my aadhaar card" is a personal description and a GET would put
  // it in the URL, the browser history, and every access log in between.
  // apiFetch, not fetch: on a paired device this resolves to the laptop's LAN
  // address and attaches the token. In the browser it stays a relative path.
  const response = await apiFetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit: 10, stage1 }),
    signal,
  });
  if (!response.ok) throw new Error(`search failed: ${response.status}`);
  return (await response.json()) as SearchResponse;
}

function stateOf(body: SearchResponse): Stage1State {
  if (body.stage1_failed) return 'failed';
  if (body.stage1_skipped) return 'skipped';
  return 'applied';
}

/** One hybrid request per query; abort superseded searches and ignore stale responses. */
export function useSearch() {
  const [state, setState] = useState<SearchState>(EMPTY);
  const inflight = useRef<AbortController | null>(null);

  const search = useCallback(async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;

    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;

    setState({ ...EMPTY, status: 'searching', query: trimmed });

    const understood = post(trimmed, true, controller.signal)
      .then((body) => {
        const stage1 = stateOf(body);
        setState((prev) =>
          inflight.current !== controller || prev.query !== trimmed
            ? prev
            : {
                ...prev,
                status: 'done',
                results: body.results,
                filters: body.filters ?? null,
                stage1,
                stage1Detail:
                  stage1 === 'failed'
                    ? (body.stage1_failure_reason ?? null)
                    : stage1 === 'skipped'
                      ? (body.stage1_skip_reason ?? null)
                      : null,
                degradedMessage: body.degraded_message ?? null,
                refused: body.refused,
                reason: body.reason ?? null,
              },
        );
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        // Keep any results already on screen when a request fails.
        setState((prev) =>
          inflight.current !== controller || prev.query !== trimmed
            ? prev
            : {
                ...prev,
                status: prev.results.length ? 'done' : 'error',
                stage1: 'failed',
                stage1Detail: err instanceof Error ? err.message : 'request failed',
                error: prev.results.length ? null : 'Search is unavailable.',
              },
        );
      });

    await understood;
  }, []);

  const reset = useCallback(() => {
    inflight.current?.abort();
    setState(EMPTY);
  }, []);

  return { ...state, search, reset };
}
