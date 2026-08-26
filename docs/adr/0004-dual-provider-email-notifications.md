# ADR-0004: Dual-provider notification email (Gmail SMTP | Resend)

## Status

Accepted (2026-08-26)

## Context

v1.2.0 adds team-facing notifications (submission confirmation,
results-with-feedback). The roadmap listed Gmail SMTP or Resend free tier
with the choice deferred to implementation time. Constraints: 100%
free-tier, no paid dependencies, supabase==2.9.0 pins httpx<0.28, and the
codebase already established both a narrow-service-seam pattern
(`services/supabase.py`) and a pluggable-provider pattern
(`VISION_PROVIDER`, ADR-0003).

## Decision

Build BOTH transports behind one env switch, `EMAIL_PROVIDER`
(`smtp` | `resend`, default `smtp`), inside a single new seam module
`backend/services/email.py`:

- **smtp**: stdlib `smtplib` + `email.message.EmailMessage` over Gmail's
  STARTTLS endpoint with an App Password — zero new dependencies.
- **resend**: thin REST call over the already-pinned httpx
  (`api.resend.com/emails`). The official SDK was rejected without
  installing: it requires httpx>=0.28, conflicting with supabase's pin —
  exactly the trap documented in ADR-0003 for google-genai.

Contract (deliberately unlike Supabase/Groq errors): sends NEVER raise to
callers. Every attempt returns an `EmailResult(status, reason, detail)`
where status ∈ sent|skipped|failed, so mail problems can never fail an
upload or feedback request — same graceful-degradation philosophy as the
image-understanding stage. Recipients/subjects are CR/LF-sanitized before
reaching headers; HTML bodies escape all interpolated values (mirrors the
PDF exporter).

## Alternatives considered

- **Gmail SMTP only** — simplest, but locks out Resend's cleaner API and
  deliverability if the pilot outgrows a personal inbox.
- **Resend SDK** — rejected: httpx>=0.28 dependency conflict; unpinning
  httpx/pydantic was already rejected in v0.3.6 for breaking supabase.
- **Single hard-coded provider** — rejected by explicit user decision;
  switching later would be code change instead of configuration.
- **Notification log table** — deferred; response payloads + logs cover
  verification for pilot scale without new schema surface.

## Consequences

- Switching providers is pure `.env` configuration; no code change.
- Two transports to maintain; both are small and fully mocked-tested.
- Resend free tier caps ~100/day and only mails your own verified email
  until a domain is added — documented in setup.md; Gmail's ~500/day is
  the better burst profile for results day, hence the default.
- Scheduled deadline reminders remain OUT of scope until a roster +
  deadline data model exists (roadmap §v1.2.0 amended accordingly).
- Live verification needs real credentials in `.env`; unit tests mock
  both transports like every other network boundary.