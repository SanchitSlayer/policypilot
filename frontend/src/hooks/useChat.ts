"use client";

import { useCallback, useRef, useState } from "react";

import { streamChat } from "@/lib/api";
import type { ChatUsage, Citation, ProviderName } from "@/lib/types";

export type MessageStatus = "streaming" | "done" | "stopped" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  status: MessageStatus;
  error?: string;
  usage?: ChatUsage;
  /** For assistant messages: the question that produced it (used by Retry). */
  question?: string;
}

const newId = () => crypto.randomUUID();

export function useChat({ provider, documentIds }: { provider: ProviderName; documentIds: string[] }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = useCallback((id: string, update: (m: ChatMessage) => ChatMessage) => {
    setMessages((current) => current.map((m) => (m.id === id ? update(m) : m)));
  }, []);

  const send = useCallback(
    async (rawQuestion: string) => {
      const question = rawQuestion.trim();
      if (!question || abortRef.current) return;

      const assistantId = newId();
      setMessages((current) => [
        ...current,
        { id: newId(), role: "user", content: question, citations: [], status: "done" },
        { id: assistantId, role: "assistant", content: "", citations: [], status: "streaming", question },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      try {
        await streamChat(
          {
            question,
            provider,
            conversation_id: conversationId,
            document_ids: documentIds.length > 0 ? documentIds : null,
          },
          {
            onToken: (text) => patch(assistantId, (m) => ({ ...m, content: m.content + text })),
            onCitations: (event) => {
              setConversationId(event.conversation_id);
              patch(assistantId, (m) => ({ ...m, citations: event.citations }));
            },
            onDone: (event) =>
              patch(assistantId, (m) => ({ ...m, content: event.answer, usage: event.usage, status: "done" })),
          },
          controller.signal,
        );
        patch(assistantId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
      } catch (error) {
        if (controller.signal.aborted) {
          patch(assistantId, (m) => ({ ...m, status: "stopped" }));
        } else {
          const message = error instanceof Error ? error.message : "Something went wrong.";
          patch(assistantId, (m) => ({ ...m, status: "error", error: message }));
        }
      } finally {
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [provider, documentIds, conversationId, patch],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** Drop a failed answer (and its question) and ask again. */
  const retry = useCallback(
    (assistantId: string) => {
      const index = messages.findIndex((m) => m.id === assistantId);
      const question = messages[index]?.question;
      if (index < 1 || !question) return;
      setMessages((current) => current.filter((_, i) => i !== index && i !== index - 1));
      void send(question);
    },
    [messages, send],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
  }, []);

  return { messages, conversationId, streaming, send, stop, retry, reset };
}
