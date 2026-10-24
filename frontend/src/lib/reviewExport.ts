import type { FindingStatus, ReviewReport } from "./types";

export const FINDING_LABELS: Record<FindingStatus, string> = {
  compliant: "Compliant",
  non_compliant: "Non-compliant",
  needs_review: "Needs review",
};

const escapeCell = (text: string) => text.replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ");

/** A Markdown checklist suitable for pasting into a ticket, email or wiki. */
export function reviewToMarkdown(report: ReviewReport): string {
  const lines = [
    `# Contract review: ${report.contract_title}`,
    "",
    `**Overall risk:** ${report.overall_risk.toUpperCase()}  `,
    `**Reviewed with:** ${report.provider}${report.model ? ` (${report.model})` : ""}`,
    "",
    report.summary,
    "",
  ];
  if (report.message) lines.push(`> Note: ${report.message}`, "");
  lines.push("| Clause | Status | Reason | Policy citations |", "| --- | --- | --- | --- |");
  for (const f of report.findings) {
    const clause = `${f.clause_title}${f.clause_page ? ` (p.${f.clause_page})` : ""}`;
    const citations =
      f.policy_citations.map((c) => `${c.document_title}, p.${c.page_number}`).join("; ") || "—";
    lines.push(
      `| ${escapeCell(clause)} | ${FINDING_LABELS[f.status]} | ${escapeCell(f.reason)} | ${escapeCell(citations)} |`,
    );
  }
  return lines.join("\n") + "\n";
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "review";
}

/** Copy text, falling back to a hidden textarea when the Clipboard API is denied. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      area.remove();
    }
  }
}
