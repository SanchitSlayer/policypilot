"use client";

import { AlertTriangle, Check, Copy, Download } from "lucide-react";
import { useState } from "react";

import { providerLabel } from "@/components/chat/ChatControls";
import { copyText, downloadJson, reviewToMarkdown, slugify } from "@/lib/reviewExport";
import type { OverallRisk, ReviewReport } from "@/lib/types";

const RISK_STYLES: Record<OverallRisk, string> = {
  low: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  medium: "bg-amber-50 text-amber-800 ring-amber-600/20",
  high: "bg-rose-50 text-rose-700 ring-rose-600/20",
};

const buttonClass =
  "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md border border-slate-300 bg-white px-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50";

export function ReportSummary({ report }: { report: ReviewReport }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const counts = {
    non_compliant: report.findings.filter((f) => f.status === "non_compliant").length,
    needs_review: report.findings.filter((f) => f.status === "needs_review").length,
    compliant: report.findings.filter((f) => f.status === "compliant").length,
  };

  const copyMarkdown = async () => {
    setCopyState((await copyText(reviewToMarkdown(report))) ? "copied" : "failed");
    setTimeout(() => setCopyState("idle"), 2500);
  };

  return (
    <section aria-label="Review summary" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className={`whitespace-nowrap rounded-lg px-2.5 py-1 text-sm font-semibold uppercase tracking-wide ring-1 ring-inset ${RISK_STYLES[report.overall_risk]}`}
          >
            {report.overall_risk} risk
          </span>
          <p className="text-sm text-slate-600">
            <span className="font-medium text-rose-700">{counts.non_compliant} non-compliant</span>
            {" · "}
            <span className="font-medium text-amber-700">{counts.needs_review} need review</span>
            {" · "}
            <span className="font-medium text-emerald-700">{counts.compliant} compliant</span>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={buttonClass}
            onClick={() => downloadJson(`review-${slugify(report.contract_title)}.json`, report)}
          >
            <Download aria-hidden className="h-4 w-4" /> Export JSON
          </button>
          <button type="button" className={buttonClass} onClick={() => void copyMarkdown()}>
            {copyState === "copied" ? (
              <Check aria-hidden className="h-4 w-4 text-emerald-600" />
            ) : (
              <Copy aria-hidden className="h-4 w-4" />
            )}
            {{ idle: "Copy as Markdown", copied: "Copied", failed: "Copy failed" }[copyState]}
          </button>
        </div>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-slate-800">{report.summary}</p>

      {report.message && (
        <p className="mt-3 flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          {report.message}
        </p>
      )}

      <p className="mt-3 text-xs text-slate-400">
        {providerLabel(report.provider)}
        {report.model ? ` · ${report.model}` : ""} · {report.steps_used} agent steps ·{" "}
        {report.tokens_used.toLocaleString()} tokens
      </p>
    </section>
  );
}
