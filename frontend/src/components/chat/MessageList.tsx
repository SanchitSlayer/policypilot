"use client";

import { AlertCircle, RotateCcw } from "lucide-react";

import { AnswerMarkdown } from "@/components/chat/AnswerMarkdown";
import { providerLabel } from "@/components/chat/ChatControls";
import type { ChatMessage } from "@/hooks/useChat";

type MessageListProps = {
  messages: ChatMessage[];
  selectedMessageId: string | null;
  activeSource: number | null;
  onCitationClick: (messageId: string, source: number) => void;
  onRetry: (messageId: string) => void;
};

export function MessageList({
  messages,
  selectedMessageId,
  activeSource,
  onCitationClick,
  onRetry,
}: MessageListProps) {
  return (
    <ol aria-label="Conversation" className="space-y-6">
      {messages.map((message) =>
        message.role === "user" ? (
          <li key={message.id} className="flex justify-end">
            <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-slate-900 px-4 py-2.5 text-sm text-white">
              {message.content}
            </p>
          </li>
        ) : (
          <li key={message.id} aria-busy={message.status === "streaming"}>
            <AssistantMessage
              message={message}
              activeSource={message.id === selectedMessageId ? activeSource : null}
              onCitationClick={(source) => onCitationClick(message.id, source)}
              onRetry={() => onRetry(message.id)}
            />
          </li>
        ),
      )}
    </ol>
  );
}

function AssistantMessage({
  message,
  activeSource,
  onCitationClick,
  onRetry,
}: {
  message: ChatMessage;
  activeSource: number | null;
  onCitationClick: (source: number) => void;
  onRetry: () => void;
}) {
  const validSources = new Set(message.citations.map((c) => c.source));
  const waiting = message.status === "streaming" && message.content === "";

  return (
    <div className="max-w-3xl">
      {waiting ? (
        <div className="flex items-center gap-1.5 py-2" aria-label="Searching your documents">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
          <span className="ml-2 text-xs text-slate-500">Searching your documents…</span>
        </div>
      ) : (
        <AnswerMarkdown
          content={message.content}
          validSources={validSources}
          activeSource={activeSource}
          onCitationClick={onCitationClick}
        />
      )}

      {message.citations.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {message.citations.map((c) => (
            <button
              key={c.source}
              type="button"
              onClick={() => onCitationClick(c.source)}
              className={`max-w-full truncate rounded-md border px-2 py-0.5 text-xs transition-colors ${
                activeSource === c.source
                  ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
              }`}
            >
              <span className="font-semibold">[{c.source}]</span> {c.document_title}, p.{c.page_number}
            </button>
          ))}
        </div>
      )}

      {message.status === "error" && (
        <div role="alert" className="mt-2 flex flex-wrap items-center gap-2 text-sm text-rose-700">
          <AlertCircle aria-hidden className="h-4 w-4" />
          <span>{message.error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-medium hover:bg-rose-50"
          >
            <RotateCcw aria-hidden className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}
      {message.status === "stopped" && <p className="mt-1 text-xs text-slate-500">Stopped.</p>}
      {message.usage && message.status === "done" && (
        <p className="mt-1.5 text-xs text-slate-400">
          {providerLabel(message.usage.provider)} · {message.usage.model} ·{" "}
          {(message.usage.latency_ms / 1000).toFixed(1)}s ·{" "}
          {message.usage.input_tokens + message.usage.output_tokens} tokens
        </p>
      )}
    </div>
  );
}
