import { useCallback, useRef, useState } from 'react';

import type { GroundedAnswer } from '@memora/core';

import { streamMockAnswer } from './stream';

export interface UserMessage {
  role: 'user';
  id: string;
  text: string;
}

export interface AssistantMessage {
  role: 'assistant';
  id: string;
  text: string;
  /** Present once the stream terminates. Absent while still streaming. */
  answer?: GroundedAnswer;
}

export type Message = UserMessage | AssistantMessage;

let counter = 0;
const nextId = () => `m${++counter}`;

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  const send = useCallback(async (text: string) => {
    const query = text.trim();
    if (!query) return;

    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      { role: 'user', id: nextId(), text: query },
      { role: 'assistant', id: assistantId, text: '' },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);

    try {
      for await (const event of streamMockAnswer(query, controller.signal)) {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId || m.role !== 'assistant') return m;
            return event.type === 'token'
              ? { ...m, text: m.text + event.text }
              : { ...m, text: event.answer.answer, answer: event.answer };
          }),
        );
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) throw err;
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  }, []);

  return { messages, isStreaming, send, stop };
}
