"""Notification email service (v1.2.0).

Sends team-facing emails through the transport selected by
``EMAIL_PROVIDER``: ``smtp`` (Gmail free tier via App Password, the
default) or ``resend`` (Resend REST API free tier). Mirrors the Supabase
service pattern: this is the ONLY module that touches smtplib/httpx for
mail, so the rest of the backend never deals with transports directly.

Contract — deliberately different from Supabase/Groq errors: email
problems NEVER propagate as exceptions. Every send returns an
``EmailResult``, so a broken or unconfigured mail transport can never
fail an upload or a feedback request (the same graceful-degradation
philosophy as the image-understanding stage).

Resend note (ADR-0004): the official SDK requires httpx>=0.28, which
conflicts with supabase==2.9.0's transitive httpx<0.28 pin, so Resend is
a thin REST call over the already-pinned httpx — zero new dependencies.
"""

from __future__ import annotations

import html
import logging
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_S = 1.0

# Indirection so tests patch sleeping instead of wall-clock waiting
# (house convention shared with the scoring/vision agents).
_sleep = time.sleep

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# CR/LF and other control chars must never reach message headers.
_CONTROL_CHARS_RE = re.compile(r"[\r\n\x00-\x1f]+")

_FILE_TYPE_LABELS = {"pdf": "PDF document", "pptx": "PowerPoint deck"}


@dataclass(frozen=True)
class EmailResult:
    """Outcome of one notification attempt — returned, never raised."""

    status: str  # "sent" | "skipped" | "failed"
    reason: str  # machine-readable why (e.g. "unconfigured")
    detail: str = ""  # human-readable context for logs/API responses


def is_valid_email(address: str) -> bool:
    """Basic shape check: ``local@domain.tld`` with no whitespace."""
    return bool(_EMAIL_RE.match((address or "").strip()))


def _clean_header_value(value: str) -> str:
    """Strip CR/LF/control characters so header injection is impossible."""
    return _CONTROL_CHARS_RE.sub(" ", value or "").strip()


def _clean_address(raw: str) -> str:
    """Normalize a recipient address; empty string when unusable."""
    address = _clean_header_value(raw)
    return address if is_valid_email(address) else ""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _outcome_note_html(note: str) -> str:
    return f'<p style="color:#444">{_esc(note)}</p>' if note else ""


# --- Message content ------------------------------------------------------


def _confirmation_content(
    *, team_name: str, file_type: str, uploaded_at: str
) -> tuple[str, str, str]:
    """Build (subject, text, html) for the submission confirmation."""
    team = team_name.strip()
    type_label = _FILE_TYPE_LABELS.get(file_type, file_type.upper())
    subject = f"Submission received - {team}"
    text = (
        f"Hi {team},\n\n"
        "JuryAI successfully received your hackathon submission.\n\n"
        f"  Submitted at : {uploaded_at} UTC\n"
        f"  File         : {type_label}\n\n"
        "Your deck will now be evaluated by four specialist AI agents\n"
        "(problem fit, technical depth, feasibility, innovation).\n"
        "We will email your written feedback and result to this address\n"
        "as soon as they are ready.\n\n"
        "- JuryAI\n"
    )
    html_body = (
        '<html><body style="font-family:sans-serif;color:#1a1a1a">'
        f"<p>Hi {_esc(team)},</p>"
        "<p>JuryAI successfully received your hackathon submission.</p>"
        '<table cellpadding="6" style="border-collapse:collapse">'
        f"<tr><td><b>Submitted at</b></td><td>{_esc(uploaded_at)} UTC</td></tr>"
        f"<tr><td><b>File</b></td><td>{_esc(type_label)}</td></tr>"
        "</table>"
        "<p>Your deck will now be evaluated by four specialist AI agents "
        "(problem fit, technical depth, feasibility, innovation). We will "
        "email your written feedback and result to this address when they "
        "are ready.</p>"
        "<p>- JuryAI</p></body></html>"
    )
    return subject, text, html_body


def _results_content(
    *,
    team_name: str,
    submission_id: str,
    composite_score: float,
    rank: int,
    scored_count: int,
    shortlisted: bool,
    scores: list[dict],
    feedback: dict,
) -> tuple[str, str, str]:
    """Build (subject, text, html) for the results-with-feedback email.

    Tone follows the shortlist decision, mirroring FeedbackAgent.
    """
    team = team_name.strip()
    if shortlisted:
        headline = "Congratulations - your submission made the shortlist!"
        outcome_note = ""
    else:
        # State the outcome explicitly: the previous vague headline left
        # non-shortlisted teams unable to tell whether they made the cut.
        headline = "Result: your submission was not shortlisted."
        outcome_note = (
            "Your submission was evaluated across all four criteria but "
            "did not make this event's shortlist cutoff. Full scores and "
            "written feedback below."
        )
    link = f"{settings.frontend_url}/submissions/{submission_id}"
    composite = f"{float(composite_score):.2f}"
    strengths = [str(s) for s in (feedback.get("strengths") or [])]
    weaknesses = [str(w) for w in (feedback.get("weaknesses") or [])]
    suggestion = str(feedback.get("suggestion") or "")

    def crit_text(row: dict) -> str:
        return f"  - {row['criterion']}: {row['score']}/10 - {row['justification']}"

    opening = f"Hi {team},\n\n{headline}\n"
    if outcome_note:
        opening += f"\n{outcome_note}\n"
    text = (
        f"{opening}\n"
        f"  Composite score : {composite} / 10\n"
        f"  Rank            : {rank} of {scored_count} scored teams\n\n"
        "Criterion scores:\n"
        + "\n".join(crit_text(row) for row in scores)
        + "\n\nStrengths:\n"
        + ("\n".join(f"  + {item}" for item in strengths) or "  (none recorded)")
        + "\n\nAreas to improve:\n"
        + ("\n".join(f"  - {item}" for item in weaknesses) or "  (none recorded)")
        + f"\n\nOne actionable suggestion:\n  {suggestion}\n\n"
        f"Full report: {link}\n\n- JuryAI\n"
    )

    crit_rows = "".join(
        "<tr>"
        f'<td style="padding:4px 10px">{_esc(row["criterion"])}</td>'
        f'<td style="padding:4px 10px"><b>{_esc(row["score"])}/10</b></td>'
        f'<td style="padding:4px 10px">{_esc(row["justification"])}</td>'
        "</tr>"
        for row in scores
    )

    def bullets(items: list[str]) -> str:
        if not items:
            return "<li>(none recorded)</li>"
        return "".join(f"<li>{_esc(item)}</li>" for item in items)

    html_body = (
        '<html><body style="font-family:sans-serif;color:#1a1a1a">'
        f"<p>Hi {_esc(team)},</p>"
        f"<h2>{_esc(headline)}</h2>"
        + _outcome_note_html(outcome_note)
        + '<table cellpadding="6" style="border-collapse:collapse">'
        f"<tr><td><b>Composite score</b></td><td>{_esc(composite)} / 10</td></tr>"
        f"<tr><td><b>Rank</b></td><td>{_esc(rank)} of {_esc(scored_count)} "
        "scored teams</td></tr></table>"
        "<h3>Criterion scores</h3>"
        '<table border="1" cellpadding="6" style="border-collapse:collapse">'
        f"{crit_rows}</table>"
        "<h3>Strengths</h3><ul>" + bullets(strengths) + "</ul>"
        "<h3>Areas to improve</h3><ul>" + bullets(weaknesses) + "</ul>"
        f"<h3>One actionable suggestion</h3><p>{_esc(suggestion)}</p>"
        f'<p><a href="{_esc(link)}">Open your full report</a></p>'
        "<p>- JuryAI</p></body></html>"
    )
    return f"JuryAI results - {team}", text, html_body


def _send_via_smtp(
    *, subject: str, text_body: str, html_body: str, to_address: str
) -> None:
    """Send via SMTP + STARTTLS (Gmail App Password path)."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from
    message["To"] = to_address
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def _send_via_resend(
    *, subject: str, text_body: str, html_body: str, to_address: str
) -> None:
    """Send via Resend's REST API over the pinned httpx (ADR-0004).

    Retries ONLY rate limits (429) and transport errors — mirroring the
    Gemini describer's backoff contract; anything else is terminal.
    """
    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    payload = {
        "from": settings.email_from,
        "to": [to_address],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    backoff = _INITIAL_BACKOFF_S
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = httpx.post(
                _RESEND_ENDPOINT, json=payload, headers=headers, timeout=30
            )
            resp.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            last_error = exc
        except httpx.TransportError as exc:  # timeouts / connection resets
            last_error = exc
        if attempt < _MAX_ATTEMPTS:
            _sleep(backoff)
            backoff *= 2
    if last_error is not None:
        raise last_error
    raise RuntimeError("Resend send failed without a recorded error.")


def _dispatch(
    *, subject: str, text_body: str, html_body: str, to_address: str
) -> EmailResult:
    """Validate, route to the configured transport, degrade gracefully."""
    recipient = _clean_address(to_address)
    if not recipient:
        return EmailResult(
            "skipped",
            "no_valid_recipient",
            "Submission has no usable contact email.",
        )
    if settings.email_provider not in ("smtp", "resend"):
        return EmailResult(
            "skipped",
            "unknown_provider",
            f"EMAIL_PROVIDER '{settings.email_provider}' is not smtp|resend.",
        )
    if not settings.is_email_configured:
        return EmailResult(
            "skipped",
            "unconfigured",
            f"EMAIL_PROVIDER={settings.email_provider} credentials are "
            "incomplete; notification skipped.",
        )

    clean_subject = _clean_header_value(subject) or "JuryAI notification"
    sender = _send_via_smtp if settings.email_provider == "smtp" else _send_via_resend
    try:
        sender(
            subject=clean_subject,
            text_body=text_body,
            html_body=html_body,
            to_address=recipient,
        )
    # Deliberate breadth: mail problems must never break an upload or a
    # feedback request; the failure travels back as an EmailResult instead.
    except Exception as exc:
        logger.warning(
            "Notification email failed (%s)", settings.email_provider, exc_info=True
        )
        return EmailResult("failed", "provider_error", str(exc)[:300])
    return EmailResult("sent", "sent")


def send_submission_confirmation(
    *,
    team_name: str,
    team_email: str,
    file_type: str,
    uploaded_at: str,
) -> EmailResult:
    """Confirm a successful upload (fires after parse-complete persists)."""
    subject, text_body, html_body = _confirmation_content(
        team_name=team_name, file_type=file_type, uploaded_at=uploaded_at
    )
    return _dispatch(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_address=team_email,
    )


def send_results_notification(
    *,
    team_name: str,
    team_email: str,
    submission_id: str,
    composite_score: float,
    rank: int,
    scored_count: int,
    shortlisted: bool,
    scores: list[dict],
    feedback: dict,
) -> EmailResult:
    """Deliver written feedback + score breakdown after generation."""
    subject, text_body, html_body = _results_content(
        team_name=team_name,
        submission_id=submission_id,
        composite_score=composite_score,
        rank=rank,
        scored_count=scored_count,
        shortlisted=shortlisted,
        scores=scores,
        feedback=feedback,
    )
    return _dispatch(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_address=team_email,
    )


# --- Appeal notifications (v1.3.0) ---------------------------------------


def _appeal_submitted_content(
    *, team_name: str, submission_id: str, reason: str
) -> tuple[str, str, str]:
    """Build (subject, text, html) for the appeal-received confirmation."""
    team = team_name.strip()
    link = f"{settings.frontend_url}/submissions/{submission_id}"
    subject = f"Appeal received - {team}"
    text = (
        f"Hi {team},\n\n"
        "We have received your appeal and it is now in the evaluator's queue.\n\n"
        f"Your reason: {reason}\n\n"
        "You will be notified once a final decision is logged.\n\n"
        f"Submission: {link}\n\n- JuryAI\n"
    )
    html_body = (
        '<html><body style="font-family:sans-serif;color:#1a1a1a">'
        f"<p>Hi {_esc(team)},</p>"
        "<p>We have received your appeal and it is now in the evaluator's "
        "queue.</p>"
        f"<p><b>Your reason:</b></p><p>{_esc(reason)}</p>"
        "<p>You will be notified once a final decision is logged.</p>"
        f'<p><a href="{_esc(link)}">View your submission</a></p>'
        "<p>- JuryAI</p></body></html>"
    )
    return subject, text, html_body


def _appeal_resolved_content(
    *,
    team_name: str,
    submission_id: str,
    decision: str,
    decision_note: str,
) -> tuple[str, str, str]:
    """Build (subject, text, html) for the appeal-outcome email."""
    team = team_name.strip()
    link = f"{settings.frontend_url}/submissions/{submission_id}"
    subject = f"Appeal {decision} - {team}"
    headline = (
        "Your appeal was upheld."
        if decision == "upheld"
        else "Your appeal was dismissed."
    )
    text = (
        f"Hi {team},\n\n{headline}\n\n"
        f"Decision: {decision}\n"
        + (f"Evaluator note: {decision_note}\n" if decision_note else "")
        + f"\nSubmission: {link}\n\n- JuryAI\n"
    )
    html_body = (
        '<html><body style="font-family:sans-serif;color:#1a1a1a">'
        f"<p>Hi {_esc(team)},</p>"
        f"<h2>{_esc(headline)}</h2>"
        f"<p><b>Decision</b>: {_esc(decision)}</p>"
        + (
            f"<p><b>Evaluator note</b>: {_esc(decision_note)}</p>"
            if decision_note
            else ""
        )
        + f'<p><a href="{_esc(link)}">View your submission</a></p>'
        + "<p>- JuryAI</p></body></html>"
    )
    return subject, text, html_body


def send_appeal_submitted(
    *, team_name: str, team_email: str, submission_id: str, reason: str
) -> EmailResult:
    """Confirm an appeal was filed (non-blocking; never raises)."""
    subject, text_body, html_body = _appeal_submitted_content(
        team_name=team_name,
        submission_id=submission_id,
        reason=reason,
    )
    return _dispatch(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_address=team_email,
    )


def send_appeal_resolved(
    *,
    team_name: str,
    team_email: str,
    submission_id: str,
    decision: str,
    decision_note: str,
) -> EmailResult:
    """Notify the team of an appeal decision (non-blocking; never raises)."""
    subject, text_body, html_body = _appeal_resolved_content(
        team_name=team_name,
        submission_id=submission_id,
        decision=decision,
        decision_note=decision_note,
    )
    return _dispatch(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        to_address=team_email,
    )
