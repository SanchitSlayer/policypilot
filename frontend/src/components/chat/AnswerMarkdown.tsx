"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const CITATION_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
const CITE_PREFIX = "#cite-";

/** Turn inline [1] / [1, 2] markers into markdown links the renderer turns into buttons. */
export function linkCitations(markdown: string): string {
  return markdown.replace(CITATION_RE, (_match, numbers: string) =>
    numbers
      .split(",")
      .map((n) => `[${n.trim()}](${CITE_PREFIX}${n.trim()})`)
      .join(""),
  );
}

type AnswerMarkdownProps = {
  content: string;
  /** Source numbers that resolved to a real citation; other markers render disabled. */
  validSources: Set<number>;
  activeSource?: number | null;
  onCitationClick?: (source: number) => void;
};

export function AnswerMarkdown({
  content,
  validSources,
  activeSource,
  onCitationClick,
}: AnswerMarkdownProps) {
  const components: Components = {
    a({ href, children, ...props }) {
      if (href?.startsWith(CITE_PREFIX)) {
        const source = Number(href.slice(CITE_PREFIX.length));
        const valid = validSources.has(source);
        const active = activeSource === source;
        return (
          <button
            type="button"
            disabled={!valid}
            onClick={() => onCitationClick?.(source)}
            aria-label={`Show source ${source}`}
            aria-pressed={active}
            className={`mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded px-1 align-middle text-[11px] font-semibold not-prose transition-colors ${
              active
                ? "bg-indigo-600 text-white"
                : valid
                  ? "bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                  : "bg-slate-100 text-slate-400"
            }`}
          >
            {source}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" {...props}>
          {children}
        </a>
      );
    },
  };

  return (
    <div className="prose prose-sm prose-slate max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}
