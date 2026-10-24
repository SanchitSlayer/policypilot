"use client";

import { AlertTriangle, CheckCheck, FileSearch, Flag, ListTree, Loader2, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ReviewStep } from "@/lib/types";

const TOOL_ICONS: Record<string, LucideIcon> = {
  list_contract_clauses: ListTree,
  search_policies: Search,
  record_finding: CheckCheck,
  finish_review: Flag,
};

type AgentProgressProps = {
  steps: ReviewStep[];
  running: boolean;
  reviewed: number;
  total: number | null;
};

export function AgentProgress({ steps, running, reviewed, total }: AgentProgressProps) {
  return (
    <section aria-label="Agent progress" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-900">Agent activity</h2>
        {total !== null && (
          <span className="text-xs tabular-nums text-slate-500">
            {reviewed}/{total} clauses reviewed
          </span>
        )}
      </div>
      {total !== null && total > 0 && (
        <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-indigo-600 transition-all"
            style={{ width: `${Math.min(100, (reviewed / total) * 100)}%` }}
          />
        </div>
      )}
      <ol className="max-h-72 space-y-1.5 overflow-y-auto pr-1" aria-live="polite">
        {steps.map((step) => {
          const Icon = step.ok ? (TOOL_ICONS[step.tool] ?? FileSearch) : AlertTriangle;
          return (
            <li key={step.index} className="flex items-start gap-2 text-sm">
              <Icon
                aria-hidden
                className={`mt-0.5 h-4 w-4 shrink-0 ${step.ok ? "text-slate-400" : "text-amber-500"}`}
              />
              <span className={step.ok ? "text-slate-700" : "text-amber-700"}>{step.description}</span>
            </li>
          );
        })}
        {running && (
          <li className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 aria-hidden className="h-4 w-4 animate-spin text-indigo-600" />
            {steps.length === 0 ? "Starting the review…" : "Thinking…"}
          </li>
        )}
      </ol>
    </section>
  );
}
