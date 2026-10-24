"use client";

import { MessageSquare, Trash2 } from "lucide-react";

import type { ConversationSummary } from "@/lib/types";

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

type ConversationListProps = {
  conversations: ConversationSummary[];
  activeId: string | null;
  loading: boolean;
  error: string | null;
  onOpen: (id: string) => void;
  onDelete: (conversation: ConversationSummary) => void;
};

export function ConversationList({
  conversations,
  activeId,
  loading,
  error,
  onOpen,
  onDelete,
}: ConversationListProps) {
  if (loading) {
    return (
      <div className="space-y-2" aria-label="Loading history">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded-md bg-slate-200/70" />
        ))}
      </div>
    );
  }
  if (error) return <p className="px-2 text-xs text-rose-700">{error}</p>;
  if (conversations.length === 0) {
    return <p className="px-2 text-xs text-slate-500">Past conversations appear here.</p>;
  }

  return (
    <ul aria-label="Past conversations" className="space-y-0.5">
      {conversations.map((c) => {
        const active = c.conversation_id === activeId;
        return (
          <li key={c.conversation_id} className="group relative">
            <button
              type="button"
              onClick={() => onOpen(c.conversation_id)}
              aria-current={active ? "true" : undefined}
              className={`flex w-full items-start gap-2 rounded-md py-2 pl-2 pr-8 text-left transition-colors ${
                active ? "bg-indigo-50 text-indigo-900" : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <MessageSquare aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
              <span className="min-w-0">
                <span className="block truncate text-sm">{c.title}</span>
                <span className="block text-xs text-slate-500">{timeAgo(c.updated_at)}</span>
              </span>
            </button>
            <button
              type="button"
              onClick={() => onDelete(c)}
              aria-label={`Delete conversation: ${c.title}`}
              className="absolute right-1 top-2 rounded p-1 text-slate-400 opacity-0 hover:bg-rose-50 hover:text-rose-600 focus:opacity-100 group-hover:opacity-100"
            >
              <Trash2 aria-hidden className="h-3.5 w-3.5" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
