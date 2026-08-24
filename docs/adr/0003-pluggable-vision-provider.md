# ADR-0003: Pluggable vision provider (Groq qwen | Gemini)

## Status

Accepted (2026-08-24)

## Context

ADR-0002 chose local CLIP classification plus Groq's qwen vision model
for image descriptions and explicitly deferred building a second
provider "speculatively". Two things changed:

1. **Live evidence of need:** v0.3.5 testing hit Groq's free-tier
   per-model tokens-per-DAY cap (qwen3.6: 200k TPD). Once exhausted,
   every vision call 429s until the daily window resets and images
   degrade to `needs_human_review`. The roadmap already anticipated
   wiring Google AI Studio's Gemini tier as free redundancy.
2. **Explicit request:** the user asked for Gemini as an *option* for
   image descriptions only, configured via `.env`, with the qwen path
   untouched and scoring still on Groq.

A direct attempt to add Google's official `google-genai` SDK failed
verification: it requires `httpx>=0.28`, which conflicts with
`supabase==2.9.0`'s transitive `httpx<0.28` constraint (supabase,
postgrest, storage3, supafunc). Unpinning httpx/pydantic was rejected
— those pins exist deliberately (pydantic 2.12.4 is required for
Python 3.14 wheels; httpx 0.27.2 satisfies supabase).

## Decision

- Introduce `VISION_PROVIDER` (`groq` | `gemini`, default `groq`) in
  `.env`. It selects only the *image-describer* function inside
  `agents/parsing/images/pipeline.py`; scoring/text agents are
  untouched and always use Groq.
- Implement the Gemini describer (`describe_gemini.py`) as a thin REST
  client over the project's already-pinned `httpx`
  (`generativelanguage.googleapis.com/v1beta ... :generateContent`),
  adding **no new dependency**. Key: `GEMINI_API_KEY`; model:
  `GEMINI_VISION_MODEL` (default `gemini-2.5-flash`, all Gemini models
  are multimodal per current docs).
- Mirror the Groq contract exactly: same system prompt, MIME
  detection, think-block stripping (defensive), unicode-dash
  normalization, empty-response → `ValueError`, exponential-backoff
  retries for HTTP 429 / transport errors only.
- Add provider-neutral `VisionRateLimitError` (subclassing
  `groq.RateLimitError`) raised after persistent 429s so the existing
  pipeline circuit breaker trips identically for both providers —
  preserving the fix from commit `89daf5b`.

## Consequences

- Default behavior is byte-for-byte unchanged (`VISION_PROVIDER=groq`
  or unset).
- Switching providers is pure configuration; no code change needed to
  adopt newer Gemini models.
- One more hand-rolled REST payload to maintain — accepted in exchange
  for zero dependency-conflict risk; covered by a mocked test suite
  mirroring the qwen describer tests.
- Live verification against the real Gemini API requires a real
  `GEMINI_API_KEY`; unit tests mock the network like all agent tests.