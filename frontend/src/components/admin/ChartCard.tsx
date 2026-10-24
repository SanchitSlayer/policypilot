import type { ReactNode } from "react";

export type LegendItem = { label: string; color: string };

export function ChartCard({
  title,
  description,
  legend,
  children,
}: {
  title: string;
  description?: string;
  legend?: LegendItem[];
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
        </div>
        {legend && legend.length > 0 && (
          <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={`${title} legend`}>
            {legend.map((item) => (
              <li key={item.label} className="flex items-center gap-1.5 text-xs text-slate-600">
                <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: item.color }} />
                {item.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      {children}
    </section>
  );
}

/** Tooltip body: text stays in ink colours; a swatch beside each row carries identity. */
export function TooltipBox({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string; color?: string; strong?: boolean }[];
}) {
  return (
    <div className="min-w-[160px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-slate-900">{title}</p>
      <dl className="space-y-0.5">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4">
            <dt className="flex items-center gap-1.5 text-slate-600">
              {row.color && <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: row.color }} />}
              {row.label}
            </dt>
            <dd className={`tabular-nums ${row.strong ? "font-semibold text-slate-900" : "text-slate-800"}`}>
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
