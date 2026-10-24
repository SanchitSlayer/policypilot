"use client";

import { MessageSquarePlus, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { DocumentFilter, PROVIDERS, ProviderSelect } from "@/components/chat/ChatControls";
import { CitationsPanel } from "@/components/chat/CitationsPanel";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import { useChat } from "@/hooks/useChat";
import { useDocuments } from "@/hooks/useDocuments";
import type { ProviderName } from "@/lib/types";

const PROVIDER_KEY = "policypilot.provider";

const EXAMPLES = [
  "What documents are valid as proof of address under KYC rules?",
  "How long must customer records be preserved?",
  "When must KYC be updated for high-risk customers?",
];

function useStoredProvider(): [ProviderName, (p: ProviderName) => void] {
  const [provider, setProvider] = useState<ProviderName>("openai");
  useEffect(() => {
    try {
      const stored = localStorage.getItem(PROVIDER_KEY);
      if (PROVIDERS.some((p) => p.value === stored)) setProvider(stored as ProviderName);
    } catch {
      // storage unavailable (private mode); keep the default
    }
  }, []);
  const update = (p: ProviderName) => {
    setProvider(p);
    try {
      localStorage.setItem(PROVIDER_KEY, p);
    } catch {
      // ignore
    }
  };
  return [provider, update];
}

export default function ChatPage() {
  const [provider, setProvider] = useStoredProvider();
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const { documents } = useDocuments();
  const readyDocuments = useMemo(() => documents.filter((d) => d.status === "ready"), [documents]);
  const { messages, streaming, send, stop, retry, reset } = useChat({ provider, documentIds });

  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // The citations panel follows the latest answer unless the user picked an older one.
  const latestAnswerId = [...messages].reverse().find((m) => m.role === "assistant")?.id ?? null;
  const panelMessage =
    messages.find((m) => m.id === selectedMessageId) ?? messages.find((m) => m.id === latestAnswerId);

  useEffect(() => {
    setSelectedMessageId(null);
    setActiveSource(null);
  }, [latestAnswerId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const selectCitation = (messageId: string, source: number) => {
    setSelectedMessageId(messageId);
    setActiveSource(source);
    // Wide screens show the side panel; only phones and tablets need the bottom sheet.
    setSheetOpen(!window.matchMedia("(min-width: 1024px)").matches);
  };

  const newConversation = () => {
    reset();
    setSelectedMessageId(null);
    setActiveSource(null);
  };

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100%+3rem)] flex-col md:-mx-10 md:-my-8 md:h-[calc(100%+4rem)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 md:px-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Chat</h1>
          <p className="hidden text-xs text-slate-500 sm:block">Answers cite the exact document and page.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DocumentFilter
            documents={readyDocuments}
            selected={documentIds}
            onChange={setDocumentIds}
            disabled={streaming}
          />
          <ProviderSelect value={provider} onChange={setProvider} disabled={streaming} />
          <button
            type="button"
            onClick={newConversation}
            disabled={messages.length === 0}
            className="flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40"
          >
            <MessageSquarePlus aria-hidden className="h-4 w-4" />
            <span className="hidden sm:inline">New conversation</span>
            <span className="sr-only sm:hidden">New conversation</span>
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-8">
            {messages.length === 0 ? (
              <EmptyState hasDocuments={readyDocuments.length > 0} onPick={(q) => void send(q)} />
            ) : (
              <MessageList
                messages={messages}
                selectedMessageId={panelMessage?.id ?? null}
                activeSource={activeSource}
                onCitationClick={selectCitation}
                onRetry={retry}
              />
            )}
          </div>
          <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 md:px-8">
            <Composer streaming={streaming} onSend={(q) => void send(q)} onStop={stop} />
          </div>
        </section>

        <aside
          aria-label="Sources"
          className="hidden w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-slate-50/80 p-4 lg:block"
        >
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Sources</h2>
          <CitationsPanel
            citations={panelMessage?.citations ?? []}
            activeSource={activeSource}
            onSelect={setActiveSource}
          />
        </aside>
      </div>

      {sheetOpen && activeSource !== null && panelMessage && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Source">
          <button
            type="button"
            aria-label="Close sources"
            className="absolute inset-0 bg-slate-900/30"
            onClick={() => setSheetOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[70dvh] overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">Sources</h2>
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                aria-label="Close"
                className="rounded p-1 text-slate-500 hover:bg-slate-100"
              >
                <X aria-hidden className="h-4 w-4" />
              </button>
            </div>
            <CitationsPanel
              citations={panelMessage.citations}
              activeSource={activeSource}
              onSelect={setActiveSource}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState({ hasDocuments, onPick }: { hasDocuments: boolean; onPick: (question: string) => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center pt-8 text-center md:pt-16">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50">
        <ShieldCheck aria-hidden className="h-6 w-6 text-indigo-600" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-slate-900">Ask your compliance documents</h2>
      <p className="mt-1 text-sm text-slate-500">
        {hasDocuments
          ? "Every answer is grounded in your uploaded PDFs and cites the page it came from."
          : "Upload policy PDFs on the Documents page first, then ask questions here."}
      </p>
      {hasDocuments && (
        <div className="mt-6 grid w-full gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onPick(q)}
              className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 hover:border-indigo-300 hover:bg-indigo-50/40"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
