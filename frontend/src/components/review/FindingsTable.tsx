"use client";

import { useState } from "react";

import { FINDING_LABELS } from "@/lib/reviewExport";
import type { FindingOut, FindingStatus, PolicyCitation } from "@/lib/types";

const STATUS_STYLES: Record<FindingStatus, string> = {
  compliant: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  non_compliant: "bg-rose-50 text-rose-700 ring-rose-600/20",
  needs_review: "bg-amber-50 text-amber-800 ring-amber-600/20",
};

export function FindingBadge({ status }: { status: FindingStatus }) {
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}
    >
      {FINDING_LABELS[status]}
    </span>
  );
}

function CitationChips({ citations }: { citations: PolicyCitation[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (citations.length === 0) return <span className="text-slate-400">—</span>;
  const active = citations.find((c) => c.source_id === open);

  return (
    <div>
      <div className="flex flex-wrap gap-1">
        {citations.map((c) => (
          <button
            key={c.source_id}
            type="button"
            aria-expanded={open === c.source_id}
            onClick={() => setOpen(open === c.source_id ? null : c.source_id)}
            className={`max-w-full truncate rounded-md border px-1.5 py-0.5 text-left text-xs transition-colors ${
              open === c.source_id
                ? "border-indigo-300 bg-indigo-50 text-indigo-800"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
            }`}
            title={`${c.document_title}, page ${c.page_number}`}
          >
            {c.document_title}, p.{c.page_number}
          </button>
        ))}
      </div>
      {active && (
        <blockquote className="mt-2 rounded-md border-l-2 border-indigo-300 bg-slate-50 px-2 py-1.5 text-xs leading-relaxed text-slate-600">
          “{active.snippet}”
        </blockquote>
      )}
    </div>
  );
}

export function FindingsTable({ findings }: { findings: FindingOut[] }) {
  return (
    <div className="relative overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full min-w-[860px] divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="w-44 px-4 py-3">Clause</th>
            <th scope="col" className="w-32 px-4 py-3">Status</th>
            <th scope="col" className="px-4 py-3">Reason</th>
            <th scope="col" className="w-56 px-4 py-3">Policy citations</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 align-top">
          {findings.map((f) => (
            <tr key={f.clause_id}>
              <td className="px-4 py-3">
                <p className="font-medium text-slate-900">{f.clause_title}</p>
                {f.clause_page !== null && <p className="text-xs text-slate-500">Page {f.clause_page}</p>}
              </td>
              <td className="px-4 py-3">
                <FindingBadge status={f.status} />
              </td>
              <td className="px-4 py-3 leading-relaxed text-slate-700">{f.reason}</td>
              <td className="px-4 py-3">
                <CitationChips citations={f.policy_citations} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
