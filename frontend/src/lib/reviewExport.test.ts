import { describe, expect, it } from "vitest";

import { reviewToMarkdown, slugify } from "./reviewExport";
import type { ReviewReport } from "./types";

const report: ReviewReport = {
  contract_id: "c",
  contract_title: "Vendor | KYC Agreement",
  provider: "anthropic",
  model: "claude-haiku-5-5",
  summary: "Retention clause breaches the five-year rule.",
  overall_risk: "high",
  steps_used: 6,
  tokens_used: 9000,
  message: null,
  prompt_version: "review-v1",
  findings: [
    {
      clause_id: "c5",
      clause_title: "5. Data retention",
      clause_page: 2,
      status: "non_compliant",
      reason: "Deletes after 12 months;\npolicy requires 5 years.",
      policy_citations: [
        { source_id: "S1", document_id: "d", document_title: "KYC Policy", page_number: 4, snippet: "…" },
      ],
    },
    {
      clause_id: "c11",
      clause_title: "11. Governing law",
      clause_page: null,
      status: "compliant",
      reason: "No policy issue.",
      policy_citations: [],
    },
  ],
};

describe("reviewToMarkdown", () => {
  it("renders risk, summary and one table row per finding", () => {
    const md = reviewToMarkdown(report);

    expect(md).toContain("# Contract review: Vendor | KYC Agreement");
    expect(md).toContain("**Overall risk:** HIGH");
    expect(md).toContain("anthropic (claude-haiku-5-5)");
    expect(md).toContain(
      "| 5. Data retention (p.2) | Non-compliant | Deletes after 12 months; policy requires 5 years. | KYC Policy, p.4 |",
    );
    expect(md).toContain("| 11. Governing law | Compliant | No policy issue. | — |");
  });

  it("escapes pipes inside cells and includes limit notes", () => {
    const md = reviewToMarkdown({
      ...report,
      message: "Stopped after 25 steps.",
      findings: [{ ...report.findings[1], reason: "A | B" }],
    });

    expect(md).toContain("A \\| B");
    expect(md).toContain("> Note: Stopped after 25 steps.");
  });
});

describe("slugify", () => {
  it("makes safe file names", () => {
    expect(slugify("Vendor | KYC Agreement (v2)")).toBe("vendor-kyc-agreement-v2");
    expect(slugify("???")).toBe("review");
  });
});
