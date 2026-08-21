import type { GroundedAnswer } from '@memora/core';

import { mockAnswerFor } from '@/mocks/answers';

/**
 * Answer stream events.
 *
 * This is the shape a real SSE reader will emit: tokens as they arrive, then a
 * terminal event carrying citations. CLAUDE.md requires fetch + ReadableStream
 * rather than EventSource, and an async generator is what a reader loop yields -
 * so swapping the mock for the endpoint changes this file only.
 */
export type AnswerEvent =
  | { type: 'token'; text: string }
  | { type: 'done'; answer: GroundedAnswer };

const TOKEN_DELAY_MS = 22;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('aborted', 'AbortError'));
      },
      { once: true },
    );
  });
}

export async function* streamMockAnswer(
  query: string,
  signal?: AbortSignal,
): AsyncGenerator<AnswerEvent> {
  const answer = mockAnswerFor(query);

  // Retrieval latency before the first token - the real thing has to run stage 1
  // and stage 2 first, and the UI should be designed against that pause.
  await sleep(420, signal);

  for (const word of answer.answer.split(/(\s+)/)) {
    if (signal?.aborted) return;
    yield { type: 'token', text: word };
    if (word.trim()) await sleep(TOKEN_DELAY_MS, signal);
  }

  yield { type: 'done', answer };
}
