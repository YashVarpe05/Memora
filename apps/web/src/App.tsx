import { useEffect, useState } from 'react';

// Proves the workspace link and the DOM-free boundary in one import:
// these come from packages/core, which cannot reference any browser API.
import { Routes, isGrounded, type GroundedAnswer } from '@memora/core';

type ApiState =
  | { kind: 'loading' }
  | { kind: 'up'; app: string; environment: string }
  | { kind: 'down'; detail: string };

/** A refusal is a valid grounded answer — GOLD q006 depends on this. */
const REFUSAL_EXAMPLE: GroundedAnswer = {
  answer: "I don't have that in your memories.",
  citations: [],
  refused: true,
  refusalReason: 'no_evidence',
};

export default function App() {
  const [api, setApi] = useState<ApiState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((body) => setApi({ kind: 'up', app: body.app, environment: body.environment }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setApi({ kind: 'down', detail: err instanceof Error ? err.message : 'unreachable' });
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="mx-auto flex min-h-full max-w-md flex-col gap-6 px-5 py-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Memora</h1>
        <p className="text-sm text-slate-500">
          Ask your memory a human question. Get an answer with proof.
        </p>
      </header>

      <section className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-500">API</h2>
        {api.kind === 'loading' && <p className="text-sm text-slate-500">checking…</p>}
        {api.kind === 'up' && (
          <p className="text-sm">
            <span className="font-medium text-emerald-600">connected</span>
            <span className="text-slate-500">
              {' '}
              — {api.app} ({api.environment})
            </span>
          </p>
        )}
        {api.kind === 'down' && (
          <p className="text-sm">
            <span className="font-medium text-amber-600">not running</span>
            <span className="text-slate-500"> — {api.detail}</span>
            <span className="mt-1 block text-xs text-slate-400">
              start it with: uv run uvicorn memora.main:app --reload
            </span>
          </p>
        )}
      </section>

      <section className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Scaffold checks
        </h2>
        <p className="text-sm text-slate-600">
          packages/core linked — grounded contract {isGrounded(REFUSAL_EXAMPLE) ? 'ok' : 'broken'}
        </p>
        <p className="text-sm text-slate-600">routes declared — {Object.keys(Routes).length}</p>
      </section>

      <p className="mt-auto text-xs text-slate-400">
        Phase 1 scaffold. No ingestion or retrieval yet.
      </p>
    </main>
  );
}
