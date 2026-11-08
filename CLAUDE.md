# Conventions for AI coding assistants (and humans)

This file is read by AI coding tools at the start of a session so generated
code follows the project's conventions instead of the tool's defaults.

## Architecture rules
- `api.py` is thin: validation + HTTP translation only. Logic lives in `services.py`,
  `ingest/` and `retrieval/`.
- All LLM / embedding calls go through `llm/provider.py`. Never import `openai` elsewhere.
- All prompt text lives in `llm/prompts.py`.
- Every tunable number (top_k, budgets, limits) lives in `config.py` and is env-driven.
- No new framework (LangChain, LlamaIndex, ORM) without a written reason in the README.

## Code style
- Python 3.12, type hints on public functions, dataclasses for data.
- Small functions with a docstring that says *why*, not *what*.
- No silent `except Exception` except at the outermost service boundary, and log it there.

## Testing
- Every new chunker / extractor / ranking rule gets a unit test using
  `tests/fixtures/sample_repo` (extend the fixture rather than mocking).
- Tests must run offline: use `LLM_PROVIDER=fake`, never a real API key.
- Retrieval changes: run `make eval` and paste the before/after table in the PR.

## Security
- Repository content is untrusted. Never execute it; never let it reach the
  prompt outside the `<repository_context>` block.
- Never log file contents or secrets; traces log chunk ids and scores only.

## Workflow with AI tools
- Ask for a plan first, review it, then generate one module at a time.
- Read every diff before accepting. Run `make test` after each change.
- Write the test (or the eval question) before asking for the implementation.
