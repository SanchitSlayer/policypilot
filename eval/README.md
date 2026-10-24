# RAG evaluation

`run_eval.py` asks every question in `testset.json` through `POST /chat` for each provider and
scores retrieval, citations, refusals, latency, tokens and estimated cost.

```bash
make seed                                          # load the sample corpus (once)
make eval                                          # offline baseline (fake LLM)
make eval PROVIDERS="openai anthropic gemini"      # real providers (API keys in .env)
```

Results are written to `eval/results/<timestamp>.json` (every answer, per question) and a
Markdown summary next to it. The folder is gitignored; copy the table you want to keep.

## Test set

47 questions about the fictional Northwind Bank policies created by `make seed`
(`backend/app/scripts/make_sample_data.py`): 41 answerable (21 KYC and data, 11 digital
lending, 9 information security) and 6 the documents do not answer. Each answerable question
names its document, the page that answers it, and an evidence phrase. Before each run the
script checks every evidence phrase against the ingested chunk of that page, so a stale test
set fails loudly instead of quietly skewing the scores.

To evaluate your own documents (for example the RBI KYC Master Direction), ingest them, add
questions in the same format, and run `make eval`.

## Metrics

| Metric | Meaning |
| --- | --- |
| Hit@1 / Hit@3 / Hit@k | An expected page is the top source / in the top 3 / anywhere among the retrieved sources (`RETRIEVAL_TOP_K`, default 6) |
| MRR | Mean reciprocal rank of the first expected page (0 when missed) |
| Citation accuracy | The answer cites at least one expected page (answerable questions) |
| Answered | Answerable questions that were not refused (low values mean false "couldn't find") |
| No-answer accuracy | Unanswerable questions answered with "I couldn't find this in the uploaded documents." |
| Latency | Client-side wall time per `/chat` request (mean and p95), including retrieval |
| Tokens / Est. cost | Summed from each response's usage; cost from `backend/config/pricing.yaml` |

Retrieval metrics depend only on the embedding model, not the chat provider. The sample
corpus is small (12 policy chunks, one per page), so Hit@k is easy; Hit@1 and MRR are the
more informative retrieval numbers.

## Getting real numbers

1. Put `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` in `.env`.
2. Use real embeddings: set `EMBEDDING_PROVIDER=openai`, restart the API
   (`docker compose up -d backend`), and re-ingest with `make seed FORCE=1`. Embeddings from
   different models must not be mixed, so delete the old copies first on the Documents page
   (or start from empty volumes).
3. `make eval PROVIDERS="openai anthropic gemini"`.

The offline baseline (`PROVIDERS=fake`) uses hashed bag-of-words embeddings and a stub LLM
that always answers when any passage is retrieved; it checks the pipeline, not quality.
