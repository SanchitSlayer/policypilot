"use client";

import { Check, ChevronDown, Files } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { DocumentOut, ProviderName } from "@/lib/types";

export const PROVIDERS: { value: ProviderName; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Claude" },
  { value: "gemini", label: "Gemini" },
  { value: "fake", label: "Fake (offline)" },
];

export const providerLabel = (value: string) =>
  PROVIDERS.find((p) => p.value === value)?.label ?? value;

const controlClass =
  "h-9 rounded-md border border-slate-300 bg-white px-2.5 text-sm text-slate-800 hover:border-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-60";

export function ProviderSelect({
  value,
  onChange,
  disabled,
}: {
  value: ProviderName;
  onChange: (value: ProviderName) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      <span className="hidden sm:inline">Model</span>
      <select
        aria-label="LLM provider"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as ProviderName)}
        className={controlClass}
      >
        {PROVIDERS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function DocumentFilter({
  documents,
  selected,
  onChange,
  disabled,
}: {
  documents: DocumentOut[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const toggle = (id: string) =>
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);

  const label =
    selected.length === 0 ? "All documents" : selected.length === 1 ? "1 document" : `${selected.length} documents`;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={`${controlClass} flex items-center gap-1.5`}
      >
        <Files aria-hidden className="h-4 w-4 text-slate-400" />
        <span className="max-w-[9rem] truncate">{label}</span>
        <ChevronDown aria-hidden className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          <fieldset>
            <legend className="px-2 py-1.5 text-xs font-medium text-slate-500">Search only in</legend>
            {documents.length === 0 && (
              <p className="px-2 py-2 text-sm text-slate-500">No ready documents yet.</p>
            )}
            <div className="max-h-64 overflow-y-auto">
              {documents.map((doc) => (
                <label
                  key={doc.id}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(doc.id)}
                    onChange={() => toggle(doc.id)}
                    className="h-4 w-4 rounded border-slate-300 accent-indigo-600"
                  />
                  <span className="truncate" title={doc.title}>
                    {doc.title}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="mt-1 flex w-full items-center gap-2 rounded-md border-t border-slate-100 px-2 py-1.5 text-sm text-indigo-700 hover:bg-indigo-50"
            >
              <Check aria-hidden className="h-4 w-4" /> Search all documents
            </button>
          )}
        </div>
      )}
    </div>
  );
}
