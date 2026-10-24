"""RAG evaluation: ask every test-set question through POST /chat and score the answers.

    python eval/run_eval.py --providers fake openai anthropic gemini
    make eval PROVIDERS="openai anthropic gemini"

Per provider it reports:
  - retrieval hit@1 / hit@3 / hit@k and MRR: was an expected page among the retrieved sources
  - citation accuracy: did the answer cite an expected page (answerable questions)
  - answered rate: share of answerable questions not refused
  - no-answer accuracy: share of unanswerable questions correctly refused
  - latency (mean, p95), total tokens and estimated cost (from backend/config/pricing.yaml)

Before running, every answerable question's evidence phrase is checked against the ingested
chunk of its expected page, so a stale test set fails loudly instead of skewing the scores.
Results go to eval/results/<timestamp>.json and a Markdown summary next to it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

EVAL_DIR = Path(__file__).resolve().parent
# The pricing table lives in the backend package: ../backend in the repo, /app in the container.
BACKEND_DIR = next(
    (c for c in (EVAL_DIR.parent / "backend", Path("/app")) if (c / "app" / "llm").is_dir()),
    EVAL_DIR.parent / "backend",
)
sys.path.insert(0, str(BACKEND_DIR))
from app.llm.pricing import PricingTable  # noqa: E402

NO_ANSWER_RE = re.compile(r"couldn.?t find this in the uploaded documents", re.IGNORECASE)
RETRYABLE = {429, 500, 502, 503, 504}


# --- test set ---------------------------------------------------------------------------


@dataclass
class Question:
    id: str
    question: str
    category: str
    answerable: bool = True
    expected_document: str | None = None
    expected_pages: list[int] = field(default_factory=list)
    evidence: str | None = None


def load_testset(path: Path) -> list[Question]:
    data = json.loads(path.read_text())
    questions = [Question(**q) for q in data["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate question ids in the test set.")
    for q in questions:
        if q.answerable and not (q.expected_document and q.expected_pages):
            raise SystemExit(
                f"{q.id}: answerable questions need expected_document and expected_pages"
            )
    return questions


_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _normalise(text: str) -> str:
    """Compare text the way PDF extraction produces it: curly quotes and line breaks vary."""
    return " ".join(text.translate(_QUOTES).split()).lower()


async def resolve_documents(
    client: httpx.AsyncClient, questions: list[Question]
) -> dict[str, dict[str, Any]]:
    """filename -> document detail (with chunks) for every document the test set expects."""
    documents = (await client.get("/documents")).raise_for_status().json()
    by_name = {d["filename"]: d for d in documents if d["status"] == "ready"}
    needed = {q.expected_document for q in questions if q.answerable}
    missing = sorted(n for n in needed if n not in by_name)  # type: ignore[misc]
    if missing:
        raise SystemExit(
            f"Not ingested (or not ready): {', '.join(missing)}. Run `make seed` first."
        )
    details = {}
    for name in needed:
        details[name] = (
            (await client.get(f"/documents/{by_name[name]['id']}")).raise_for_status().json()
        )  # type: ignore[index]
    return details  # type: ignore[return-value]


def check_evidence(questions: list[Question], documents: dict[str, dict[str, Any]]) -> list[str]:
    """Problems where the evidence phrase is not on any expected page."""
    problems = []
    for q in questions:
        if not q.answerable or not q.evidence:
            continue
        chunks = documents[q.expected_document]["chunks"]  # type: ignore[index]
        pages_text = " ".join(c["content"] for c in chunks if c["page_number"] in q.expected_pages)
        if _normalise(q.evidence) not in _normalise(pages_text):
            problems.append(
                f"{q.id}: evidence {q.evidence!r} not found on pages {q.expected_pages}"
            )
    return problems


# --- running ----------------------------------------------------------------------------


@dataclass
class Result:
    question_id: str
    provider: str
    answerable: bool
    ok: bool
    error: str | None = None
    answer: str = ""
    refused: bool = False
    retrieval_rank: int | None = None  # 1-based rank of the first expected page, None = missed
    retrieved: int = 0
    cited_expected: bool = False
    citations: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None
    cost_usd: float = 0.0
    prompt_version: str | None = None


def score(
    q: Question,
    provider: str,
    body: dict[str, Any],
    doc_ids: dict[str, str],
    latency_ms: float,
    pricing: PricingTable,
) -> Result:
    expected = {(doc_ids.get(q.expected_document or ""), page) for page in q.expected_pages}
    ranks = [
        s["number"] for s in body["sources"] if (s["document_id"], s["page_number"]) in expected
    ]
    usage = body["usage"]
    cost = pricing.estimate(usage["model"], usage["input_tokens"], usage["output_tokens"])
    return Result(
        question_id=q.id,
        provider=provider,
        answerable=q.answerable,
        ok=True,
        answer=body["answer"],
        refused=bool(NO_ANSWER_RE.search(body["answer"])),
        retrieval_rank=min(ranks) if ranks else None,
        retrieved=len(body["sources"]),
        cited_expected=any(
            (c["document_id"], c["page_number"]) in expected for c in body["citations"]
        ),
        citations=[f"{c['document_title']} p.{c['page_number']}" for c in body["citations"]],
        latency_ms=round(latency_ms, 1),
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        model=usage["model"],
        cost_usd=cost.usd,
        prompt_version=body.get("prompt_version"),
    )


async def ask(
    client: httpx.AsyncClient,
    q: Question,
    provider: str,
    doc_ids: dict[str, str],
    pricing: PricingTable,
    semaphore: asyncio.Semaphore,
    retries: int = 2,
) -> Result:
    payload = {"question": q.question, "provider": provider, "persist": False}
    async with semaphore:
        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                response = await client.post("/chat", json=payload)
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == 200:
                    latency = (time.perf_counter() - started) * 1000
                    return score(q, provider, response.json(), doc_ids, latency, pricing)
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                if response.status_code not in RETRYABLE:
                    break
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
    return Result(
        question_id=q.id, provider=provider, answerable=q.answerable, ok=False, error=error
    )


# --- metrics ----------------------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def metrics(results: list[Result]) -> dict[str, Any]:
    ok = [r for r in results if r.ok]
    answerable = [r for r in ok if r.answerable]
    unanswerable = [r for r in ok if not r.answerable]
    latencies = sorted(r.latency_ms for r in ok)
    p95 = (
        latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
        if latencies
        else None
    )
    return {
        "questions": len(results),
        "errors": len(results) - len(ok),
        "retrieval_hit@1": _rate(sum(r.retrieval_rank == 1 for r in answerable), len(answerable)),
        "retrieval_hit@3": _rate(
            sum((r.retrieval_rank or 99) <= 3 for r in answerable), len(answerable)
        ),
        "retrieval_hit@k": _rate(
            sum(r.retrieval_rank is not None for r in answerable), len(answerable)
        ),
        "mrr": round(
            statistics.fmean(1 / r.retrieval_rank if r.retrieval_rank else 0 for r in answerable), 4
        )
        if answerable
        else None,
        "citation_accuracy": _rate(sum(r.cited_expected for r in answerable), len(answerable)),
        "answered_rate": _rate(sum(not r.refused for r in answerable), len(answerable)),
        "no_answer_accuracy": _rate(sum(r.refused for r in unanswerable), len(unanswerable)),
        "avg_latency_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(p95, 1) if p95 is not None else None,
        "total_tokens": sum(r.input_tokens + r.output_tokens for r in ok),
        "cost_usd": round(sum(r.cost_usd for r in ok), 6),
        "model": next((r.model for r in ok if r.model), None),
    }


# --- reporting --------------------------------------------------------------------------

COLUMNS = [
    ("provider", "Provider", "{}"),
    ("model", "Model", "{}"),
    ("retrieval_hit@1", "Hit@1", "pct"),
    ("retrieval_hit@3", "Hit@3", "pct"),
    ("retrieval_hit@k", "Hit@k", "pct"),
    ("mrr", "MRR", "{:.3f}"),
    ("citation_accuracy", "Citation acc.", "pct"),
    ("answered_rate", "Answered", "pct"),
    ("no_answer_accuracy", "No-answer acc.", "pct"),
    ("avg_latency_ms", "Avg latency", "ms"),
    ("p95_latency_ms", "p95 latency", "ms"),
    ("total_tokens", "Tokens", "{:,}"),
    ("cost_usd", "Est. cost", "usd"),
    ("errors", "Errors", "{}"),
]


def _fmt(value: Any, style: str) -> str:
    if value is None:
        return "—"
    if style == "pct":
        return f"{value * 100:.1f}%"
    if style == "ms":
        return f"{value / 1000:.2f} s" if value >= 1000 else f"{value:.0f} ms"
    if style == "usd":
        return f"${value:.4f}"
    return style.format(value)


def table_rows(summary: dict[str, dict[str, Any]]) -> list[list[str]]:
    return [
        [_fmt(m.get(key) if key != "provider" else p, style) for key, _, style in COLUMNS]
        for p, m in summary.items()
    ]


def console_table(summary: dict[str, dict[str, Any]]) -> str:
    headers = [title for _, title, _ in COLUMNS]
    rows = table_rows(summary)
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))  # noqa: E731
    return "\n".join([line(headers), line(["-" * w for w in widths]), *(line(r) for r in rows)])


def markdown_report(run: dict[str, Any]) -> str:
    headers = [title for _, title, _ in COLUMNS]
    rows = table_rows(run["summary"])
    md = [
        f"# RAG evaluation — {run['started_at'][:16].replace('T', ' ')} UTC",
        "",
        f"- Test set: `{run['testset']}` ({run['questions']['answerable']} answerable, "
        f"{run['questions']['unanswerable']} unanswerable)",
        f"- API: `{run['api_url']}` · prompt version `{run['prompt_version'] or 'n/a'}`",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(r) + " |" for r in rows),
        "",
        "Hit@k: an expected page is among the retrieved sources. Citation accuracy: the answer "
        "cites an expected page. No-answer accuracy: unanswerable questions answered with the "
        '"couldn\'t find" sentence. Costs use backend/config/pricing.yaml.',
    ]
    failures = [
        r for r in run["results"] if r["ok"] and r["answerable"] and not r["cited_expected"]
    ]
    if failures:
        md += ["", "## Answerable questions without a correct citation", ""]
        md += [
            f"- `{r['provider']}` {r['question_id']}: cited "
            f"{', '.join(r['citations']) or 'nothing'}"
            for r in failures[:40]
        ]
    return "\n".join(md) + "\n"


# --- main -------------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> int:
    questions = load_testset(args.testset)
    if args.limit:
        questions = questions[: args.limit]
    pricing = PricingTable.from_yaml(args.pricing)

    async with httpx.AsyncClient(base_url=args.api_url, timeout=args.timeout) as client:
        documents = await resolve_documents(client, questions)
        problems = check_evidence(questions, documents)
        if problems:
            print("Test set does not match the ingested documents:\n  " + "\n  ".join(problems))
            return 2
        print(
            f"Test set OK: {len(questions)} questions, evidence verified against ingested chunks."
        )
        doc_ids = {name: d["id"] for name, d in documents.items()}

        semaphore = asyncio.Semaphore(args.concurrency)
        started = datetime.now(UTC)
        results: list[Result] = []
        for provider in args.providers:
            t0 = time.perf_counter()
            batch = await asyncio.gather(
                *(ask(client, q, provider, doc_ids, pricing, semaphore) for q in questions)
            )
            results.extend(batch)
            failed = [r for r in batch if not r.ok]
            elapsed = time.perf_counter() - t0
            print(f"{provider}: {len(batch) - len(failed)}/{len(batch)} ok in {elapsed:.1f}s")
            for r in failed[:3]:
                print(f"  {r.question_id}: {r.error}")

    summary = {p: metrics([r for r in results if r.provider == p]) for p in args.providers}
    stamp = started.strftime("%Y-%m-%d_%H%M%S")
    record = {
        "started_at": started.isoformat(),
        "api_url": args.api_url,
        "testset": str(
            args.testset.relative_to(EVAL_DIR.parent)
            if args.testset.is_relative_to(EVAL_DIR.parent)
            else args.testset
        ),
        "questions": {
            "answerable": sum(q.answerable for q in questions),
            "unanswerable": sum(not q.answerable for q in questions),
        },
        "providers": args.providers,
        "prompt_version": next((r.prompt_version for r in results if r.prompt_version), None),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / f"{stamp}.json"
    md_path = args.out / f"{stamp}.md"
    json_path.write_text(json.dumps(record, indent=2))
    md_path.write_text(markdown_report(record))

    print()
    print(console_table(summary))
    print(f"\nSaved {json_path} and {md_path}")
    return 1 if all(m["errors"] == m["questions"] for m in summary.values()) else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["fake"],
        choices=["openai", "anthropic", "gemini", "fake"],
    )
    parser.add_argument("--testset", type=Path, default=EVAL_DIR / "testset.json")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results")
    parser.add_argument("--pricing", type=Path, default=BACKEND_DIR / "config" / "pricing.yaml")
    parser.add_argument("--concurrency", type=int, default=4, help="Parallel requests per provider")
    parser.add_argument("--timeout", type=float, default=120.0, help="Seconds per request")
    parser.add_argument("--limit", type=int, help="Only the first N questions (smoke test)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
