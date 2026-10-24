## What changed

<!-- One or two sentences on what this PR does and why. Link the issue if there is one. -->

-

## How to test

<!-- Commands and manual steps a reviewer can follow. -->

- [ ] `make test` passes (backend pytest + frontend lint, type-check, Vitest)
- [ ] `make lint` passes
- [ ] Manual check:

## Screenshots

<!-- UI changes: before / after. Delete this section if there is no UI change. -->

## Checklist

- [ ] No secrets, API keys or real customer data in the diff
- [ ] New settings are read from the environment and listed in `.env.example`
- [ ] LLM calls go through `app/llm/` (provider abstraction + usage logging)
- [ ] Prompt wording changes bump `PROMPT_VERSION` / `REVIEW_PROMPT_VERSION`
