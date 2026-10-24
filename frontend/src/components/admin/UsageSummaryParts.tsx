import { AlertTriangle } from "lucide-react";

import { providerLabel } from "@/components/chat/ChatControls";
import { providerColor } from "@/lib/chartTheme";
import { formatCompact, formatInt, formatMs, formatPct, formatUsd } from "@/lib/format";
import type { UsageBreakdown, UsageStats } from "@/lib/types";

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail && <p className="mt-0.5 text-xs text-slate-500">{detail}</p>}
    </div>
  );
}

export function KpiTiles({ totals }: { totals: UsageStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
      <Tile label="Requests" value={formatInt(totals.requests)} detail={`${formatInt(totals.errors)} failed`} />
      <Tile
        label="Tokens"
        value={formatCompact(totals.total_tokens)}
        detail={`${formatCompact(totals.input_tokens)} in · ${formatCompact(totals.output_tokens)} out`}
      />
      <Tile
        label="Est. cost"
        value={formatUsd(totals.cost_usd)}
        detail={totals.unpriced_requests ? `${formatInt(totals.unpriced_requests)} calls unpriced` : "USD, from pricing table"}
      />
      <Tile label="p95 latency" value={formatMs(totals.p95_latency_ms)} detail={`p50 ${formatMs(totals.p50_latency_ms)}`} />
      <Tile label="Error rate" value={formatPct(totals.error_rate)} detail={`${formatInt(totals.errors)} of ${formatInt(totals.requests)}`} />
    </div>
  );
}

const FEATURE_LABELS: Record<string, string> = {
  chat: "Chat",
  review: "Contract review",
  embedding: "Embeddings",
};

export function BreakdownTable({
  title,
  rows,
  kind,
}: {
  title: string;
  rows: UsageBreakdown[];
  kind: "provider" | "feature";
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <h2 className="px-4 pb-2 pt-4 text-sm font-semibold text-slate-900 sm:px-5">{title}</h2>
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-y border-slate-200 bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2.5 sm:px-5">{kind === "provider" ? "Provider" : "Feature"}</th>
              <th scope="col" className="px-4 py-2.5 text-right">Requests</th>
              <th scope="col" className="px-4 py-2.5 text-right">Tokens</th>
              <th scope="col" className="px-4 py-2.5 text-right">Est. cost</th>
              <th scope="col" className="px-4 py-2.5 text-right">p50</th>
              <th scope="col" className="px-4 py-2.5 text-right">p95</th>
              <th scope="col" className="px-4 py-2.5 text-right sm:pr-5">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 tabular-nums">
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="px-4 py-2.5 sm:px-5">
                  <span className="flex items-center gap-2 font-medium text-slate-900">
                    {kind === "provider" && (
                      <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: providerColor(r.key) }} />
                    )}
                    {kind === "provider" ? providerLabel(r.key) : (FEATURE_LABELS[r.key] ?? r.key)}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right text-slate-700">{formatInt(r.requests)}</td>
                <td className="px-4 py-2.5 text-right text-slate-700">{formatInt(r.total_tokens)}</td>
                <td className="px-4 py-2.5 text-right text-slate-700">
                  {formatUsd(r.cost_usd)}
                  {r.unpriced_requests > 0 && (
                    <span title={`${r.unpriced_requests} calls use a model missing from pricing.yaml`}>
                      <AlertTriangle aria-label="Some calls unpriced" className="ml-1 inline h-3.5 w-3.5 text-amber-500" />
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right text-slate-700">{formatMs(r.p50_latency_ms)}</td>
                <td className="px-4 py-2.5 text-right text-slate-700">{formatMs(r.p95_latency_ms)}</td>
                <td className="px-4 py-2.5 text-right text-slate-700 sm:pr-5">
                  {r.errors > 0 ? `${formatInt(r.errors)} (${formatPct(r.error_rate)})` : "0"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
