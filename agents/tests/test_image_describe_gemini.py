"""Tests for the Gemini vision describer (v0.3.6).

The httpx client is mocked; no network calls are made. Retry/backoff
behavior mirrors the Groq describer tests in test_image_describe.py.
"""

from unittest.mock import Mock

import httpx
import pytest
from groq import RateLimitError

from agents.parsing.images import describe_gemini as gemini_module
from agents.parsing.images.describe import VisionRateLimitError
from agents.parsing.images.describe_gemini import describe_image_gemini

PNG_BYTES = b"\x89PNG fake bytes"


def _api_response(status_code: int = 200, text: str | None = None) -> Mock:
    """Build a mocked httpx.Response with a Gemini-shaped JSON body."""
    resp = Mock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=Mock(),
            response=Mock(status_code=status_code),
        )
    else:
        resp.raise_for_status.return_value = None
    if text is not None:
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]
        }
    return resp


def _client(side_effect=None, response: Mock | None = None) -> Mock:
    client = Mock()
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = response
    client.close.return_value = None
    return client


@pytest.fixture(autouse=True)
def _mock_sleep(monkeypatch):
    """Mock time.sleep so tests don't actually wait."""
    monkeypatch.setattr(
        "agents.parsing.images.describe_gemini.time.sleep", lambda x: None
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure Gemini env vars don't leak between tests."""
    for var in ("GEMINI_API_KEY", "GEMINI_VISION_MODEL", "VISION_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


# --- Happy path --------------------------------------------------------------


def test_returns_text(monkeypatch):
    """A successful vision call returns the description text."""
    client = _client(response=_api_response(text="A layered architecture diagram."))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "A layered architecture diagram."
    client.post.assert_called_once()


def test_joins_multiple_text_parts(monkeypatch):
    """Text parts from the first candidate are concatenated."""
    resp = _api_response()
    resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "A flowchart with three stages. "},
                        {"text": "Arrows point left to right."},
                    ],
                }
            }
        ]
    }
    client = _client(response=resp)
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "A flowchart with three stages. Arrows point left to right."


def test_strips_think_blocks_defensively(monkeypatch):
    """Reasoning blocks are stripped even though Gemini doesn't emit them."""
    tag_name = "think"
    open_tag = "<" + tag_name + ">"
    close_tag = "</" + tag_name + ">"
    content = (
        open_tag
        + "internal reasoning omitted"
        + close_tag
        + "The diagram shows a pipeline."
    )
    client = _client(response=_api_response(text=content))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "The diagram shows a pipeline."


def test_normalizes_unicode_dashes(monkeypatch):
    """Typographic dash variants are normalized to ASCII hyphens."""
    content = "flow \u2010 staged \u2011 left \u2012 to \u2013 right \u2014 done"
    client = _client(response=_api_response(text=content))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "flow - staged - left - to - right - done"
    for ch in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014"):
        assert ch not in result


# --- Request shape -----------------------------------------------------------


def test_sends_inline_data_with_detected_mime_and_model_url(monkeypatch):
    """Image goes out base64 inline-data; model appears in the URL."""
    client = _client(response=_api_response(text="desc"))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    png = b"\x89PNG" + bytes([13, 10, 26, 10]) + b"rest-of-png"
    describe_image_gemini(png, api_key="test-key")

    kwargs = client.post.call_args.kwargs
    url = client.post.call_args.args[0]
    assert url.endswith("/models/gemini-2.5-flash:generateContent")
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    payload = kwargs["json"]
    inline = payload["contents"][0]["parts"][1]["inlineData"]
    assert inline["mimeType"] == "image/png"
    assert inline["data"]  # base64 non-empty


def test_env_model_override(monkeypatch):
    """GEMINI_VISION_MODEL env var overrides the default model."""
    monkeypatch.setenv("GEMINI_VISION_MODEL", "gemini-custom-model")
    client = _client(response=_api_response(text="desc"))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    describe_image_gemini(PNG_BYTES, api_key="test-key")

    url = client.post.call_args.args[0]
    assert "/models/gemini-custom-model:generateContent" in url


# --- Error paths -------------------------------------------------------------


def test_raises_without_api_key(monkeypatch):
    """Without an API key (and no env var), raises ValueError."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        describe_image_gemini(PNG_BYTES)


def test_retries_on_429_then_succeeds(monkeypatch):
    """A 429 on the first call is retried and succeeds on the second."""
    client = _client(side_effect=[_api_response(429), _api_response(text="recovered")])
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "recovered"
    assert client.post.call_count == 2


def test_persistent_429_raises_vision_rate_limit_error(monkeypatch):
    """After exhausting retries, VisionRateLimitError is raised and it is
    also a groq.RateLimitError so the pipeline circuit breaker trips."""
    client = _client(response=_api_response(429))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    with pytest.raises(VisionRateLimitError):
        describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert client.post.call_count == 4  # 1 + 3 retries

    # Circuit-breaker parity: catchable as groq.RateLimitError.
    try:
        raise VisionRateLimitError("parity check")
    except RateLimitError:
        pass


def test_empty_description_raises_non_retryable(monkeypatch):
    """An empty description raises immediately (no retries)."""
    client = _client(response=_api_response(text=""))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    with pytest.raises(ValueError, match="empty description"):
        describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert client.post.call_count == 1


def test_no_candidates_raises_empty(monkeypatch):
    """A safety-blocked response (no candidates) counts as empty."""
    resp = _api_response()
    resp.json.return_value = {"promptFeedback": {"blockReason": "SAFETY"}}
    client = _client(response=resp)
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    with pytest.raises(ValueError, match="empty description"):
        describe_image_gemini(PNG_BYTES, api_key="test-key")


def test_non_429_http_error_propagates_without_retry(monkeypatch):
    """Other HTTP errors (e.g. 400) propagate immediately."""
    client = _client(response=_api_response(400))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    with pytest.raises(httpx.HTTPStatusError):
        describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert client.post.call_count == 1


def test_transport_error_is_retried(monkeypatch):
    """Connection errors are retried per policy, then succeed."""
    client = _client(side_effect=[httpx.ConnectError("boom"), _api_response(text="ok")])
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    result = describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert result == "ok"
    assert client.post.call_count == 2


def test_persistent_transport_error_propagates(monkeypatch):
    """Connection failures after all retries propagate to the caller."""
    client = _client(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr(gemini_module, "_get_http_client", lambda: client)

    with pytest.raises(httpx.ConnectError):
        describe_image_gemini(PNG_BYTES, api_key="test-key")

    assert client.post.call_count == 4  # 1 + 3 retries
