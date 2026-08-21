import { AlertTriangle } from 'lucide-react';

import { isGrounded } from '@memora/core';

import { CitationCard } from './CitationCard';
import type { Message } from './useChat';

function Caret() {
  return <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-accent align-middle" />;
}

export function MessageBubble({ message, streaming }: { message: Message; streaming: boolean }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-card bg-accent px-4 py-2.5 text-sm text-accent-ink">
          {message.text}
        </p>
      </div>
    );
  }

  const { answer } = message;
  const refused = answer?.refused ?? false;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[0.9375rem] leading-relaxed text-ink">
        {message.text}
        {streaming && <Caret />}
      </p>

      {answer && refused && (
        <p className="flex items-start gap-2 rounded-card bg-warn-soft px-3 py-2 text-xs text-warn">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            {answer.refusalReason === 'weak_evidence'
              ? 'Evidence was too weak to answer from. Nothing was inferred.'
              : 'Not found in your memories. Nothing was answered from model knowledge.'}
          </span>
        </p>
      )}

      {answer && answer.citations.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-ink-faint">
            {answer.citations.length} source{answer.citations.length === 1 ? '' : 's'}
          </p>
          {answer.citations.map((citation, i) => (
            <CitationCard key={citation.chunkId} citation={citation} index={i} />
          ))}
        </div>
      )}

      {answer && !isGrounded(answer) && (
        <p className="rounded-card bg-warn-soft px-3 py-2 text-xs text-warn">
          Ungrounded response - no citations and no refusal. This is a failed answer.
        </p>
      )}
    </div>
  );
}
