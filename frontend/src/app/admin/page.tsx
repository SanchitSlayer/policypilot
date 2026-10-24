"use client";

import { BarChart3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { CostByProviderChart, LatencyByProviderChart, RequestsPerDayChart } from "@/components/admin/UsageCharts";
import { BreakdownTable, KpiTiles } from "@/components/admin/UsageSummaryParts";
import { PageHeader } from "@/components/PageHeader";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { getUsage } from "@/lib/api";
import { presetRange } from "@/lib/format";
import type { UsageSummary } from "@/lib/types";

const PRESETS = [7, 30, 90] as const;

export default function AdminPage() {
  const [range, setRange] = useState(() => presetRange(30));
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getUsage(range.from, range.to));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load usage.");
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    void load();
  }, [load]);

  const activePreset = PRESETS.find((days) => {
    const preset = presetRange(days);
    return preset.from === range.from && preset.to === range.to;
  });

  const inputClass =
    "h-8 rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20";

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Admin"
        description="Requests, tokens, latency and estimated cost across providers and features (UTC days)."
      />

      <div className="mb-6 flex flex-wrap items-center gap-3" role="group" aria-label="Date range">
        <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
          {PRESETS.map((days) => (
            <button
              key={days}
              type="button"
              aria-pressed={activePreset === days}
              onClick={() => setRange(presetRange(days))}
              className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                activePreset === days ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {days}d
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          From
          <input
            type="date"
            value={range.from}
            max={range.to}
            onChange={(e) => e.target.value && setRange((r) => ({ ...r, from: e.target.value }))}
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          To
          <input
            type="date"
            value={range.to}
            min={range.from}
            onChange={(e) => e.target.value && setRange((r) => ({ ...r, to: e.target.value }))}
            className={inputClass}
          />
        </label>
        <button
          type="button"
          onClick={() => void load()}
          aria-label="Refresh"
          className="ml-auto rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
        >
          <RefreshCw aria-hidden className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      {!data && loading && (
        <div className="space-y-4" aria-label="Loading usage">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-[92px] animate-pulse rounded-xl bg-slate-200/60" />
            ))}
          </div>
          <div className="h-72 animate-pulse rounded-xl bg-slate-200/60" />
        </div>
      )}

      {data && (
        <div className={`space-y-6 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <KpiTiles totals={data.totals} />
          {data.totals.requests === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <BarChart3 aria-hidden className="mx-auto h-8 w-8 text-slate-300" />
              <p className="mt-3 text-sm font-medium text-slate-700">No LLM calls in this range</p>
              <p className="mt-1 text-sm text-slate-500">
                Ask a question in Chat or run a Contract Review, then refresh.
              </p>
            </div>
          ) : (
            <>
              <RequestsPerDayChart daily={data.daily} />
              <div className="grid gap-6 lg:grid-cols-2">
                <LatencyByProviderChart rows={data.by_provider} />
                <CostByProviderChart rows={data.by_provider} />
              </div>
              <BreakdownTable title="By provider" rows={data.by_provider} kind="provider" />
              <BreakdownTable title="By feature" rows={data.by_feature} kind="feature" />
            </>
          )}
        </div>
      )}
    </div>
  );
}
