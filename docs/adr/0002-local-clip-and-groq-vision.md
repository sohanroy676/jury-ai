# ADR-0002: Local CLIP classification + Groq qwen3.6 vision for image understanding

## Status

Accepted

## Date

2026-08-23

## Context

v0.3.5 (visual content understanding) needs two model capabilities:

1. **Cheap, local triage** of every extracted image (diagram vs. logo vs.
   photo) so template decoration never reaches a paid/vision API.
2. **Structural descriptions** for diagram-like images, via a
   vision-capable LLM.

Constraints: the project is 100% free-tier; PDF/PPTX must remain the only
required inputs; agents stay narrow and independently testable.

## Decision

- **Classification:** run CLIP zero-shot locally via `open_clip`
  (`ViT-B-32`, `openai` pretrained weights) on CPU with the roadmap's six
  candidate labels. Weights (~350 MB) download once and cache locally;
  no API, no cost, no rate limit. Model loads lazily as a thread-safe
  singleton so imports/tests never trigger downloads.
- **Vision descriptions:** use Groq's `qwen/qwen3.6-27b`, verified
  end-to-end against this account's free-tier key (base64 PNG input,
  correct text-in-image reading). Responses include qwen-style reasoning
  blocks, which the describer strips before storing.
- **Routing thresholds:** CLIP confidence >= 0.7 trusts the top label
  (diagram-like -> describe; decorative -> drop); below it, describe AND
  flag `needs_human_review`. All thresholds are env-overridable.

## Alternatives considered

- **Groq llama-4-scout/maverick (roadmap's original suggestion):**
  rejected after live verification — 404 model_not_found on this free
  account; groq/compound rejects multimodal content parts entirely.
- **Google AI Studio Gemini free tier:** viable fallback if Groq vision
  disappears, deliberately NOT built speculatively (no second provider
  code path without a need).
- **Paid vision APIs:** rejected — violates the free-tier constraint.
- **Skipping local CLIP, sending every image to the vision LLM:**
  rejected — wastes rate-limited Groq quota on logos/banners and adds
  latency to every upload.

## Consequences

- New heavy dependencies (`torch`, `torchvision`, `open_clip_torch`,
  `imagehash`) — ~200 MB install plus one-time ~350 MB weight download.
  Acceptable: they're local/free, and Windows PyPI torch wheels are
  CPU-only by default.
- First upload containing images is slow (weight download); documented in
  `docs/setup.md`.
- If Groq removes `qwen/qwen3.6-27b` from the free tier (as it did
  llama-3.3-70b), the describer fails per-image and degrades gracefully
  (`needs_human_review=True`); switching models is a one-line env change
  (`GROQ_VISION_MODEL`), or Gemini becomes the fallback path.