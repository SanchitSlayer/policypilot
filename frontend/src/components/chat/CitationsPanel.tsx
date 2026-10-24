"use client";

import { BookOpen } from "lucide-react";
import { useEffect, useRef } from "react";

import type { Citation } from "@/lib/types";

type CitationsPanelProps = {
  citations: Citation[];
  activeSource: number | null;
  onSelect: (source: number) => void;
};

export function CitationsPanel({ citations, activeSource, onSelect }: CitationsPanelProps) {
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (activeSource === null) return;
    const item = listRef.current?.querySelector<HTMLElement>(`[data-source="${activeSource}"]`);
    item?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [activeSource]);

  if (citations.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <BookOpen aria-hidden className="h-6 w-6 text-slate-300" />
        <p className="mt-2 text-sm text-slate-500">
          Sources cited in an answer appear here, with document name, page and the exact passage.
        </p>
      </div>
    );
  }

  return (
    <ol ref={listRef} aria-label="Cited sources" className="space-y-2">
      {citations.map((citation) => {
        const active = citation.source === activeSource;
        return (
          <li key={citation.source} data-source={citation.source}>
            <button
              type="button"
              onClick={() => onSelect(citation.source)}
              aria-current={active ? "true" : undefined}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${
                active
                  ? "border-indigo-300 bg-indigo-50/70 ring-2 ring-indigo-500/20"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <div className="flex items-start gap-2">
                <span
                  className={`mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded px-1 text-[11px] font-semibold ${
                    active ? "bg-indigo-600 text-white" : "bg-indigo-50 text-indigo-700"
                  }`}
                >
                  {citation.source}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{citation.document_title}</p>
                  <p className="text-xs text-slate-500">Page {citation.page_number}</p>
                </div>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-600">“{citation.snippet}”</p>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
