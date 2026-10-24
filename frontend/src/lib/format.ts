const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat();

export const formatInt = (n: number) => integer.format(n);

export const formatCompact = (n: number) => compact.format(n);

/** Costs are tiny per call; show enough precision to be useful without noise. */
export function formatUsd(n: number): string {
  if (n === 0) return "$0";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  return `$${integer.format(Math.round(n))}`;
}

export function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${Math.round(ms)} ms`;
}

export const formatPct = (fraction: number) =>
  `${(fraction * 100).toFixed(fraction > 0 && fraction < 0.01 ? 2 : 1)}%`;

/** "2026-10-03" -> "Oct 3" (dates are UTC days from the API). */
export function formatDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

const isoDay = (date: Date) => date.toISOString().slice(0, 10);

/** The last `days` UTC days ending today, inclusive. */
export function presetRange(days: number, today: Date = new Date()): { from: string; to: string } {
  const start = new Date(today);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { from: isoDay(start), to: isoDay(today) };
}
