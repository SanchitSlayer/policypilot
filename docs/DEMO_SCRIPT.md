# PolicyPilot: 2-minute demo script

For recording a walkthrough video or GIF. Total runtime about 2 minutes.

## Before recording

- `make up && make seed` (or use the deployed URL). Upload nothing else, so the corpus is the
  three Northwind policies and the vendor contract.
- Pick the provider you will show (Claude or OpenAI with keys; **Fake (offline)** works without).
- Run one throwaway chat and one review first, so the Admin page has data.
- Browser at 1440×900, zoom 100%, close other tabs. In dev mode, hide the Next.js indicator.

## Script

| Time | Screen | Do | Say |
| --- | --- | --- | --- |
| 0:00 | Documents | Show the table: three policies, one contract, page and chunk counts, Ready badges. Drag a PDF onto the upload area and let it go from Processing to Ready. | "PolicyPilot is a compliance copilot. I upload policies and regulations; each page is split into chunks and embedded into Postgres with pgvector, so every answer can cite an exact page." |
| 0:20 | Chat | Ask **"How long must KYC records be kept after an account is closed?"** Let it stream. | "Answers stream in and only use the uploaded documents." |
| 0:35 | Chat | Click the `[1]` marker; point at the Sources panel (document, page 4, passage). | "Every claim is cited. Clicking a citation shows the exact passage, so a compliance officer can verify it in seconds." |
| 0:45 | Chat | Ask **"What interest rate does the bank pay on fixed deposits?"** | "When the documents don't cover something, it says so instead of guessing." |
| 0:55 | Chat | Switch the provider menu (for example Claude → Gemini) and ask **"Can a lending app read the borrower's contacts?"** | "The same pipeline works with OpenAI, Claude or Gemini; switching is one setting per request." |
| 1:10 | Contract Review | Pick *sample vendor kyc agreement*, click **Run review**, let the activity log run. | "Now an agent reviews a vendor contract. It reads the clauses, searches our policies for each one, and records a finding with citations. Its tool calls are validated, so it can't cite a passage it never retrieved." |
| 1:30 | Contract Review | Show the risk badge and summary; point at clause 5 (12-month retention) and clause 4 (full Aadhaar storage) as non-compliant; expand a citation chip. Click **Copy as Markdown**. | "It flags the planted problems: records deleted after 12 months against a five-year rule, full Aadhaar numbers stored. The checklist exports to Markdown or JSON." |
| 1:45 | Admin | Show the KPI tiles and the requests and cost charts; hover a bar. | "Every LLM and embedding call is logged with tokens, latency and estimated cost, per provider and per feature." |
| 1:55 | — | End on the Admin page or the GitHub README. | "FastAPI, pgvector, MongoDB, Next.js, deployed on Cloud Run with CI and an evaluation suite. Thanks for watching." |

## Recording tips

- Record at 1440×900 or larger, export the GIF at about 1200 px wide, and keep it under ~10 MB
  so GitHub renders it inline (`docs/demo.gif`, then uncomment the line in the README).
- If a real model is slow, cut the waiting time in editing rather than switching to Fake.
- For the review, say which findings a real model flagged: the Fake provider marks every
  clause "needs review" by design.
