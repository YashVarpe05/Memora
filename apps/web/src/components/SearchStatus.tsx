import { useEffect, useState } from 'react';
import type { components } from '@memora/core/types/api';
import { apiFetch, pairedServer } from '@/platform/api';
import { DegradedBanner } from './DegradedBanner';

type Coverage = components['schemas']['EmbeddingCoverageResponse'];
type Health = components['schemas']['ReadinessResponse'];

export function coverageMessage(coverage: Coverage): string | null {
  if (!coverage.configured) return 'Meaning-based search is off. Word and document-type search is available.';
  if (coverage.model_ready === false) {
    return 'Meaning-based search is configured, but the model is not ready. Word and document-type search is available.';
  }
  if (!coverage.available_documents) return null;
  if (!coverage.text_documents) return 'These documents have no readable text yet. Meaning-based search cannot use them.';
  const progress = `Meaning search indexed for ${coverage.semantic_documents} of ${coverage.text_documents} text documents.`;
  const pending = coverage.pending_documents
    ? ` ${coverage.pending_documents} still need processing; word and document-type search is available now.` : '';
  const noText = coverage.no_text_documents
    ? ` ${coverage.no_text_documents} documents have no readable text.` : '';
  return progress + pending + noText;
}

/** Configuration is not index coverage. Counts come only from this paired library. */
export function SearchStatus({ route }: { route: string }) {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = false;
    setMessage(null);
    const refresh = async () => {
      if (active || controller.signal.aborted) return;
      active = true;
      const connection = pairedServer();
      try {
        const [healthResponse, coverageResponse] = await Promise.all([
          apiFetch('/api/health/ready', { signal: controller.signal }),
          connection ? apiFetch('/api/index/coverage', { signal: controller.signal }) : null,
        ]);
        const health = healthResponse.ok ? await healthResponse.json() as Health : null;
        const coverage = coverageResponse?.ok ? await coverageResponse.json() as Coverage : null;
        const current = pairedServer();
        if (controller.signal.aborted || connection?.url !== current?.url || connection?.token !== current?.token) return;
        setMessage(coverage ? coverageMessage(coverage) : health?.search_mode === 'lexical'
          ? health.degraded_message ?? 'Word and document-type search is enabled. Meaning-based search is off.' : null);
      } catch { /* Connection and search screens report unavailable services. */ }
      finally { active = false; }
    };
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 5000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [route]);
  return message ? <div className="px-4 pt-3"><DegradedBanner message={message} /></div> : null;
}
