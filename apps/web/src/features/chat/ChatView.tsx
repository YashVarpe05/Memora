import { ArrowUp, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { SUGGESTED_QUERIES } from '@/mocks/answers';

import { MessageBubble } from './MessageBubble';
import { useChat } from './useChat';

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex flex-col gap-4 py-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Ask your memory</h1>
        <p className="text-sm text-ink-muted">
          Describe it the way you remember it - who sent it, roughly when, what it was about.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        {SUGGESTED_QUERIES.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-card border border-line bg-surface px-4 py-3 text-left text-sm text-ink transition-colors hover:border-accent"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatView() {
  const { messages, isStreaming, send, stop } = useChat();
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  function submit(text: string) {
    setDraft('');
    void send(text);
  }

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col px-4">
      <div className="flex flex-1 flex-col gap-6 pb-4">
        {messages.length === 0 ? (
          <EmptyState onPick={submit} />
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={m.id}
              message={m}
              streaming={isStreaming && i === messages.length - 1}
            />
          ))
        )}
        <div ref={endRef} />
      </div>

      <form
        className="sticky bottom-0 flex items-end gap-2 bg-canvas py-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!isStreaming) submit(draft);
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="the PDF a professor sent..."
          className="h-11 min-w-0 flex-1 rounded-lg border border-line bg-surface px-4 text-sm text-ink placeholder:text-ink-faint focus-visible:border-accent focus-visible:outline-none"
        />
        {isStreaming ? (
          <Button type="button" size="icon" variant="subtle" onClick={stop} aria-label="Stop">
            <Square className="size-4" aria-hidden />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!draft.trim()} aria-label="Ask">
            <ArrowUp className="size-5" aria-hidden />
          </Button>
        )}
      </form>
    </div>
  );
}
