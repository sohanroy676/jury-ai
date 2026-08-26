"""Tests for the v1.2.0 notification email service.

The transports are always mocked (FakeSMTP / fake httpx.post) so tests
never touch the network — including when the developer's real .env holds
live credentials. These tests pin the degrade-gracefully contract:
whatever happens, callers get an EmailResult and no exception escapes.
"""

from __future__ import annotations

import smtplib
from typing import ClassVar

import httpx
import pytest

from backend.config import settings
from backend.services import email as email_service

# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def smtp_env(monkeypatch):
    """Complete Gmail-SMTP-style configuration."""
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_from", "jury@example.com")
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "jury@example.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password-1234")


@pytest.fixture
def resend_env(monkeypatch):
    """Complete Resend REST configuration."""
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "email_from", "jury@example.com")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")


@pytest.fixture
def sleep_log(monkeypatch):
    """Record backoff sleeps instead of waiting."""
    calls: list[float] = []
    monkeypatch.setattr(email_service, "_sleep", lambda seconds: calls.append(seconds))
    return calls


@pytest.fixture
def smtp_calls(monkeypatch):
    """Replace both transports with recorders; returns the call lists."""
    smtp_recorded: list[dict] = []
    resend_recorded: list[dict] = []

    def fake_smtp(**kwargs):
        smtp_recorded.append(kwargs)

    def fake_resend(**kwargs):
        resend_recorded.append(kwargs)

    monkeypatch.setattr(email_service, "_send_via_smtp", fake_smtp)
    monkeypatch.setattr(email_service, "_send_via_resend", fake_resend)
    return {"smtp": smtp_recorded, "resend": resend_recorded}


# --- Payload builders --------------------------------------------------------


def confirmation_kwargs(**over):
    kwargs = {
        "team_name": "Team Alpha",
        "team_email": "alpha@example.com",
        "file_type": "pdf",
        "uploaded_at": "2026-08-26T10:00:00+00:00",
    }
    kwargs.update(over)
    return kwargs


def results_kwargs(**over):
    kwargs = {
        "team_name": "Team Alpha",
        "team_email": "alpha@example.com",
        "submission_id": "sub-123",
        "composite_score": 7.25,
        "rank": 2,
        "scored_count": 9,
        "shortlisted": True,
        "scores": [
            {"criterion": criterion, "score": score, "justification": f"{criterion} ev"}
            for criterion, score in (
                ("problem_fit", 8),
                ("technical_depth", 7),
                ("feasibility", 6),
                ("innovation", 8),
            )
        ],
        "feedback": {
            "strengths": ["Cited farmer survey"],
            "weaknesses": ["No metrics"],
            "suggestion": "Add benchmarks.",
            "verdict": "shortlist",
        },
    }
    kwargs.update(over)
    return kwargs


# --- Dispatch contract (provider routing / graceful degradation) -------------


def test_smtp_provider_routes_to_smtp_sender(smtp_env, smtp_calls):
    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert (result.status, result.reason) == ("sent", "sent")
    assert len(smtp_calls["smtp"]) == 1
    assert smtp_calls["resend"] == []
    sent = smtp_calls["smtp"][0]
    assert sent["to_address"] == "alpha@example.com"
    assert "Team Alpha" in sent["subject"]


def test_resend_provider_routes_to_resend_sender(resend_env, smtp_calls):
    result = email_service.send_results_notification(**results_kwargs())

    assert (result.status, result.reason) == ("sent", "sent")
    assert len(smtp_calls["resend"]) == 1
    assert smtp_calls["smtp"] == []


def test_unconfigured_smtp_skips_without_sending(monkeypatch, smtp_calls):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_from", "jury@example.com")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")

    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert (result.status, result.reason) == ("skipped", "unconfigured")
    assert smtp_calls["smtp"] == []


def test_unconfigured_resend_skips_without_sending(monkeypatch, smtp_calls):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "email_from", "jury@example.com")
    monkeypatch.setattr(settings, "resend_api_key", "")

    result = email_service.send_results_notification(**results_kwargs())

    assert (result.status, result.reason) == ("skipped", "unconfigured")
    assert smtp_calls["resend"] == []


def test_unknown_provider_skips_without_sending(monkeypatch, smtp_env, smtp_calls):
    monkeypatch.setattr(settings, "email_provider", "carrier-pigeon")

    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert (result.status, result.reason) == ("skipped", "unknown_provider")
    assert smtp_calls["smtp"] == []


def test_blank_recipient_skips_without_sending(smtp_env, smtp_calls):
    result = email_service.send_submission_confirmation(
        **confirmation_kwargs(team_email="")
    )

    assert (result.status, result.reason) == ("skipped", "no_valid_recipient")
    assert smtp_calls["smtp"] == []


def test_header_injection_recipient_is_rejected(smtp_env, smtp_calls):
    result = email_service.send_results_notification(
        **results_kwargs(team_email="a@b.com\r\nBcc: victim@evil.com")
    )

    assert (result.status, result.reason) == ("skipped", "no_valid_recipient")
    assert smtp_calls["resend"] == []


def test_transport_failure_becomes_failed_result_never_raises(smtp_env, monkeypatch):
    def exploding(**kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(email_service, "_send_via_smtp", exploding)

    result = email_service.send_results_notification(**results_kwargs())

    assert (result.status, result.reason) == ("failed", "provider_error")
    assert "connection reset" in result.detail


def test_subject_control_characters_are_sanitized(smtp_env, smtp_calls):
    result = email_service.send_submission_confirmation(
        **confirmation_kwargs(team_name="Team\r\nAlpha\tX")
    )

    assert result.status == "sent"
    subject = smtp_calls["smtp"][0]["subject"]
    assert "\r" not in subject and "\n" not in subject


# --- SMTP transport ------------------------------------------------------------


class FakeSMTP:
    """Records the smtplib call sequence; optionally fails an operation."""

    behavior: ClassVar[dict] = {}
    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.calls: list[tuple] = []
        self.sent_message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls",))

    def login(self, user, password):
        if FakeSMTP.behavior.get("fail_login"):
            raise smtplib.SMTPAuthenticationError(535, b"Bad credentials")
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send_message",))
        self.sent_message = message


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.behavior = {}
    FakeSMTP.instances = []
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_smtp_sends_starttls_login_and_mime_message(smtp_env, fake_smtp):
    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert result.status == "sent"
    server = fake_smtp.instances[0]
    assert (server.host, server.port) == ("smtp.gmail.com", 587)
    assert [c[0] for c in server.calls] == ["starttls", "login", "send_message"]
    assert server.calls[1][1:] == ("jury@example.com", "app-password-1234")
    message = server.sent_message
    assert message.is_multipart()
    assert message["To"] == "alpha@example.com"
    assert "Team Alpha" in message["Subject"]


def test_smtp_auth_failure_maps_to_failed_result(smtp_env, fake_smtp):
    fake_smtp.behavior["fail_login"] = True

    result = email_service.send_results_notification(**results_kwargs())

    assert (result.status, result.reason) == ("failed", "provider_error")
    assert "credentials" in result.detail.lower()


# --- Resend transport ----------------------------------------------------------


class FakeResponse:
    """httpx.Response stand-in that raises like raise_for_status does."""

    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", email_service._RESEND_ENDPOINT)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )


class PostRecorder(list):
    """Call list that also carries the queued outcomes for fake_post."""

    queue: ClassVar[list] = []


@pytest.fixture
def resend_posts(monkeypatch):
    """Queue FakeResponses for httpx.post; records every call."""
    calls = PostRecorder()
    calls.queue = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        outcome = calls.queue.pop(0) if calls.queue else FakeResponse(200)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(email_service.httpx, "post", fake_post)
    return calls


def test_resend_posts_expected_payload_and_auth(resend_env, resend_posts):
    result = email_service.send_results_notification(**results_kwargs())

    assert result.status == "sent"
    assert len(resend_posts) == 1
    call = resend_posts[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["headers"]["Authorization"] == "Bearer re_test_key"
    payload = call["json"]
    assert payload["from"] == "jury@example.com"
    assert payload["to"] == ["alpha@example.com"]
    assert "Team Alpha" in payload["subject"]
    assert "<html>" in payload["html"]
    assert "problem_fit" in payload["text"]


def test_resend_429_then_success_retries_with_backoff(
    resend_env, resend_posts, sleep_log
):
    resend_posts.queue.extend([FakeResponse(429), FakeResponse(200)])

    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert result.status == "sent"
    assert len(resend_posts) == 2
    assert sleep_log == [1.0]


def test_resend_persistent_429_fails_after_backoff_attempts(
    resend_env, resend_posts, sleep_log
):
    resend_posts.queue.extend([FakeResponse(429)] * 5)

    result = email_service.send_results_notification(**results_kwargs())

    assert (result.status, result.reason) == ("failed", "provider_error")
    assert len(resend_posts) == email_service._MAX_ATTEMPTS
    assert sleep_log == [1.0, 2.0]


def test_resend_401_is_terminal_no_retry(resend_env, resend_posts, sleep_log):
    resend_posts.queue.append(FakeResponse(401))

    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert (result.status, result.reason) == ("failed", "provider_error")
    assert len(resend_posts) == 1
    assert sleep_log == []


def test_resend_transport_error_retries_then_succeeds(
    resend_env, resend_posts, sleep_log
):
    resend_posts.queue.extend([httpx.ConnectError("boom"), FakeResponse(200)])

    result = email_service.send_submission_confirmation(**confirmation_kwargs())

    assert result.status == "sent"
    assert len(resend_posts) == 2
    assert sleep_log == [1.0]


# --- Content building ------------------------------------------------------------


def test_confirmation_html_escapes_hostile_team_name(smtp_env, smtp_calls):
    email_service.send_submission_confirmation(
        **confirmation_kwargs(team_name="<script>alert(1)</script> & Co")
    )

    html_body = smtp_calls["smtp"][0]["html_body"]
    assert "&lt;script&gt;" in html_body
    assert "<script>" not in html_body
    assert "&amp; Co" in html_body


def test_confirmation_content_carries_timestamp_and_type(smtp_env, smtp_calls):
    email_service.send_submission_confirmation(**confirmation_kwargs(file_type="pptx"))

    body = smtp_calls["smtp"][0]["text_body"]
    assert "2026-08-26T10:00:00+00:00" in body
    assert "PowerPoint deck" in body


def test_results_content_tone_follows_shortlist(smtp_env, smtp_calls):
    email_service.send_results_notification(**results_kwargs(shortlisted=True))
    shortlisted_body = smtp_calls["smtp"][0]["text_body"]

    email_service.send_results_notification(**results_kwargs(shortlisted=False))
    rejected_body = smtp_calls["smtp"][1]["text_body"]

    assert "made the shortlist" in shortlisted_body
    assert "fully evaluated" in rejected_body


def test_results_content_lists_criteria_composite_and_link(smtp_env, smtp_calls):
    result = email_service.send_results_notification(**results_kwargs())
    assert result.status == "sent"

    body = smtp_calls["smtp"][0]["text_body"]
    for criterion in ("problem_fit", "technical_depth", "feasibility", "innovation"):
        assert criterion in body
    assert "7.25 / 10" in body
    assert "2 of 9 scored teams" in body
    assert f"{settings.frontend_url}/submissions/sub-123" in body
    assert "Add benchmarks." in body


def test_is_valid_email_shapes():
    assert email_service.is_valid_email("team+tag@example.co.uk")
    assert email_service.is_valid_email(" a@b.io ")
    assert not email_service.is_valid_email("not-an-email")
    assert not email_service.is_valid_email("a@b")
    assert not email_service.is_valid_email("a b@c.com")
    assert not email_service.is_valid_email("")
    assert not email_service.is_valid_email(None)
