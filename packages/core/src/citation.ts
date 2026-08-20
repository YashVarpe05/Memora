/**
 * The citation contract.
 *
 * PRODUCT.md: "Every answer cites specific source memories." An answer without
 * chunk ids is a failed response, so the shape is defined here — platform-neutral,
 * shared by the API client and every renderer.
 */
export type SourceType = 'email' | 'pdf' | 'audio' | 'image' | 'note' | 'calendar' | 'code';

export interface Citation {
  chunkId: string;
  memoryId: string;
  sourceType: SourceType;
  title: string;
  /** Character offsets into the source text, for highlighting the exact span. */
  span?: { start: number; end: number };
  snippet: string;
  score?: number;
}

/** Set when the system declines to answer. GOLD q006 grades PASS only on a refusal. */
export type RefusalReason = 'no_evidence' | 'weak_evidence' | 'out_of_scope';

export interface GroundedAnswer {
  answer: string;
  citations: Citation[];
  refused: boolean;
  refusalReason?: RefusalReason;
}

/** An answer is only valid if it refused or it cited something. */
export function isGrounded(answer: GroundedAnswer): boolean {
  return answer.refused || answer.citations.length > 0;
}
