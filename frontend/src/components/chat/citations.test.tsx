import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnswerMarkdown, linkCitations } from "./AnswerMarkdown";
import { CitationsPanel } from "./CitationsPanel";
import type { Citation } from "@/lib/types";

const citation = (source: number, title: string, page: number): Citation => ({
  source,
  chunk_id: `c${source}`,
  document_id: `d${source}`,
  document_title: title,
  page_number: page,
  snippet: `Snippet for source ${source}`,
});

describe("linkCitations", () => {
  it("expands single and grouped markers into one link per source", () => {
    expect(linkCitations("A [1]. B [2, 3].")).toBe("A [1](#cite-1). B [2](#cite-2)[3](#cite-3).");
  });

  it("leaves partial markers from an unfinished stream alone", () => {
    expect(linkCitations("Passport [1")).toBe("Passport [1");
  });
});

describe("AnswerMarkdown", () => {
  it("renders citation markers as buttons and reports clicks", async () => {
    const onClick = vi.fn();
    render(
      <AnswerMarkdown
        content={"Valid documents:\n\n- **Passport** [1]\n- Aadhaar [2]"}
        validSources={new Set([1, 2])}
        onCitationClick={onClick}
      />,
    );

    expect(screen.getByText("Passport").tagName).toBe("STRONG");
    await userEvent.click(screen.getByRole("button", { name: "Show source 2" }));

    expect(onClick).toHaveBeenCalledWith(2);
  });

  it("marks the active source and disables markers without a citation", () => {
    render(
      <AnswerMarkdown content="A [1] B [4]" validSources={new Set([1])} activeSource={1} />,
    );

    expect(screen.getByRole("button", { name: "Show source 1" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Show source 4" })).toBeDisabled();
  });
});

describe("CitationsPanel", () => {
  it("lists document title, page and snippet, and highlights the active source", async () => {
    const onSelect = vi.fn();
    render(
      <CitationsPanel
        citations={[citation(1, "KYC Direction", 12), citation(2, "Digital Lending", 4)]}
        activeSource={2}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByText("KYC Direction")).toBeInTheDocument();
    expect(screen.getByText("Page 12")).toBeInTheDocument();
    expect(screen.getByText("“Snippet for source 2”")).toBeInTheDocument();
    const items = screen.getAllByRole("button");
    expect(items[1]).toHaveAttribute("aria-current", "true");
    expect(items[0]).not.toHaveAttribute("aria-current");

    await userEvent.click(items[0]);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("shows an explanation when there are no citations", () => {
    render(<CitationsPanel citations={[]} activeSource={null} onSelect={() => {}} />);
    expect(screen.getByText(/Sources cited in an answer appear here/)).toBeInTheDocument();
  });
});
