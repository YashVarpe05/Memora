import type { components } from '@memora/core/types/api';

type SearchResponse = components['schemas']['SearchResponse'];
type SearchResult = components['schemas']['SearchResult'];

/** One hit as the native index returns it. */
export interface LocalHit {
  id: number;
  uri: string;
  name: string;
  mime: string;
  size: number;
  title: string;
  docType: string | null;
  snippet: string;
  page: number;
  score: number;
  lexical: boolean;
  typeMatch: boolean;
}

const LABELS: Record<string, string> = {
  aadhaar: 'Aadhaar card', pan: 'PAN card', marksheet: 'Marksheet', resume: 'Resume',
  ticket: 'Ticket', receipt: 'Receipt', invoice: 'Invoice', certificate: 'Certificate',
  letter: 'Letter', passport: 'Passport', licence: 'Driving licence',
};

function sourceType(mime: string, name: string): string {
  if (mime === 'application/pdf' || /\.pdf$/i.test(name)) return 'pdf';
  if (mime.startsWith('image/')) return 'image';
  return 'text';
}

function label(docType: string | null): string | null {
  if (!docType) return null;
  return LABELS[docType] ?? docType.charAt(0).toUpperCase() + docType.slice(1);
}

/**
 * Shape the phone's own results like the server's, so the screens do not know which one
 * answered. There is no semantic score on the phone, so nothing is ever "closest in meaning":
 * a hit exists only because a word or the document type matched.
 */
export function toSearchResponse(hits: LocalHit[]): SearchResponse {
  const results: SearchResult[] = hits.map((hit, index) => ({
    byte_size: hit.size,
    document_label: label(hit.docType),
    document_type: hit.docType,
    file_url: '',
    filename: hit.name,
    match_explanation: hit.typeMatch && hit.lexical ? 'Matched the words and the document type'
      : hit.typeMatch ? 'Matched the document type' : 'Matched words in the document',
    matched_chunk_id: null,
    memory_id: String(hit.id),
    page: hit.page,
    rank: index + 1,
    raw_score: hit.score,
    score: hit.score,
    snippet: hit.snippet,
    source_type: sourceType(hit.mime, hit.name),
    thumbnail_url: null,
    title: hit.title,
    uncertain: !hit.lexical && !hit.typeMatch,
  }));
  return {
    chunks_examined: results.length,
    corpus_exhausted: true,
    documents_in_window: results.length,
    filters: null,
    refused: results.length === 0,
    reason: results.length === 0 ? 'no_match' : null,
    results,
    stage1_failed: false,
    stage1_skipped: true,
    stage1_skip_reason: 'on-device search',
    total: results.length,
    widenings: 0,
  };
}
