"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { providerLabel } from "@/components/chat/ChatControls";
import { INK, LATENCY_COLORS, orderProviders, providerColor } from "@/lib/chartTheme";
import { formatCompact, formatDay, formatInt, formatMs, formatUsd } from "@/lib/format";
import type { DailyUsage, UsageBreakdown } from "@/lib/types";

import { ChartCard, TooltipBox } from "./ChartCard";

const AXIS_TICK = { fill: INK.muted, fontSize: 11 };
const HEIGHT = 240;

type TooltipProps<T> = { active?: boolean; payload?: ReadonlyArray<{ payload?: T }> };

// --- Requests per day (stacked by provider) ------------------------------------------------

export function RequestsPerDayChart({ daily }: { daily: DailyUsage[] }) {
  const providers = orderProviders(daily.flatMap((d) => Object.keys(d.by_provider)));
  const data = daily.map((d) => ({ date: d.date, total: d.requests, ...d.by_provider }));

  const tooltip = ({ active, payload }: TooltipProps<(typeof data)[number]>) => {
    const row = payload?.[0]?.payload;
    if (!active || !row) return null;
    return (
      <TooltipBox
        title={formatDay(row.date)}
        rows={[
          ...providers.map((p) => ({
            label: providerLabel(p),
            value: formatInt(Number((row as Record<string, unknown>)[p] ?? 0)),
            color: providerColor(p),
          })),
          { label: "Total", value: formatInt(row.total), strong: true },
        ]}
      />
    );
  };

  return (
    <ChartCard
      title="Requests per day"
      description="LLM and embedding calls, by provider"
      legend={providers.length > 1 ? providers.map((p) => ({ label: providerLabel(p), color: providerColor(p) })) : undefined}
    >
      <div style={{ height: HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke={INK.grid} />
            <XAxis
              dataKey="date"
              tickFormatter={formatDay}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: INK.axis }}
              minTickGap={24}
            />
            <YAxis allowDecimals={false} tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatCompact} />
            <Tooltip content={tooltip} cursor={{ fill: "rgba(11,11,11,0.04)" }} />
            {providers.map((p) => (
              <Bar
                key={p}
                dataKey={p}
                stackId="requests"
                fill={providerColor(p)}
                stroke={INK.surface}
                strokeWidth={2}
                maxBarSize={28}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

// --- Latency by provider (p50 / p95) -------------------------------------------------------

export function LatencyByProviderChart({ rows }: { rows: UsageBreakdown[] }) {
  const data = orderProviders(rows.map((r) => r.key)).map((key) => {
    const row = rows.find((r) => r.key === key)!;
    return { provider: providerLabel(key), p50: row.p50_latency_ms, p95: row.p95_latency_ms, requests: row.requests };
  });

  const tooltip = ({ active, payload }: TooltipProps<(typeof data)[number]>) => {
    const row = payload?.[0]?.payload;
    if (!active || !row) return null;
    return (
      <TooltipBox
        title={row.provider}
        rows={[
          { label: "p50", value: formatMs(row.p50), color: LATENCY_COLORS.p50 },
          { label: "p95", value: formatMs(row.p95), color: LATENCY_COLORS.p95 },
          { label: "Requests", value: formatInt(row.requests) },
        ]}
      />
    );
  };

  return (
    <ChartCard
      title="Latency by provider"
      description="Median (p50) and tail (p95) per call"
      legend={[
        { label: "p50", color: LATENCY_COLORS.p50 },
        { label: "p95", color: LATENCY_COLORS.p95 },
      ]}
    >
      <div style={{ height: HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -4 }} barGap={2}>
            <CartesianGrid vertical={false} stroke={INK.grid} />
            <XAxis dataKey="provider" tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: INK.axis }} />
            <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={(v: number) => formatMs(v)} width={64} />
            <Tooltip content={tooltip} cursor={{ fill: "rgba(11,11,11,0.04)" }} />
            <Bar dataKey="p50" fill={LATENCY_COLORS.p50} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
            <Bar dataKey="p95" fill={LATENCY_COLORS.p95} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}

// --- Cost by provider (horizontal, direct labels) -------------------------------------------

export function CostByProviderChart({ rows }: { rows: UsageBreakdown[] }) {
  const data = orderProviders(rows.map((r) => r.key)).map((key) => {
    const row = rows.find((r) => r.key === key)!;
    return { key, provider: providerLabel(key), cost: row.cost_usd, unpriced: row.unpriced_requests, requests: row.requests };
  });

  const tooltip = ({ active, payload }: TooltipProps<(typeof data)[number]>) => {
    const row = payload?.[0]?.payload;
    if (!active || !row) return null;
    return (
      <TooltipBox
        title={row.provider}
        rows={[
          { label: "Est. cost", value: formatUsd(row.cost), color: providerColor(row.key), strong: true },
          { label: "Requests", value: formatInt(row.requests) },
          ...(row.unpriced ? [{ label: "Unpriced calls", value: formatInt(row.unpriced) }] : []),
        ]}
      />
    );
  };

  return (
    <ChartCard title="Estimated cost by provider" description="From config/pricing.yaml (USD)">
      <div style={{ height: Math.max(120, data.length * 44 + 24) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal={false} stroke={INK.grid} />
            <XAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatUsd} />
            <YAxis type="category" dataKey="provider" tick={{ ...AXIS_TICK, fill: INK.secondary }} tickLine={false} axisLine={{ stroke: INK.axis }} width={80} />
            <Tooltip content={tooltip} cursor={{ fill: "rgba(11,11,11,0.04)" }} />
            <Bar dataKey="cost" radius={[0, 4, 4, 0]} maxBarSize={20} isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.key} fill={providerColor(d.key)} />
              ))}
              <LabelList dataKey="cost" position="right" formatter={(v: unknown) => formatUsd(Number(v))} fill={INK.secondary} fontSize={11} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
