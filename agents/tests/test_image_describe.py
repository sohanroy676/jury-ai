"""Tests for the Groq vision describer (v0.3.5).

The Groq client is mocked; no network calls are made. Retry/backoff
behavior mirrors the scoring agent's test conventions.
"""

from unittest.mock import Mock

import pytest
from groq import RateLimitError

from agents.parsing.images import describe as describe_module
from agents.parsing.images.describe import describe_image

# --- Helpers (mirroring agents/tests/test_scoring.py) ------------------------


def _mock_response(content: str) -> Mock:
    resp = Mock()
    resp.choices = [Mock()]
    resp.choices[0].message.content = content
    return resp


def _mock_client(side_effect=None, content: str = "ok") -> Mock:
    client = Mock()
    if side_effect is not None:
        client.chat.completions.create.side_effect = side_effect
    else:
        client.chat.completions.create.return_value = _mock_response(content)
    return client


def _rate_limit_error() -> RateLimitError:
    return RateLimitError("rate limited", response=Mock(), body=None)


@pytest.fixture(autouse=True)
def _mock_sleep(monkeypatch):
    """Mock time.sleep so tests don't actually wait."""
    monkeypatch.setattr("agents.parsing.images.describe.time.sleep", lambda x: None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure GROQ_VISION_MODEL doesn't leak between tests."""
    monkeypatch.delenv("GROQ_VISION_MODEL", raising=False)


# --- Happy path --------------------------------------------------------------


def test_describe_returns_text(monkeypatch):
    """A successful vision call returns the description text."""
    client = _mock_client(content="A three-tier architecture diagram.")
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    result = describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    assert result == "A three-tier architecture diagram."
    client.chat.completions.create.assert_called_once()


def test_describe_strips_think_blocks(monkeypatch):
    """qwen-style reasoning blocks are removed from the response."""
    # Built piece-by-piece because contiguous XML-looking tag strings
    # do not survive being written into source files.
    tag_name = "think"
    open_tag = "<" + tag_name + ">"
    close_tag = "</" + tag_name + ">"
    content = (
        open_tag
        + "internal reasoning omitted"
        + close_tag
        + "The diagram shows a client-server-database flow."
    )
    client = _mock_client(content=content)
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    result = describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    assert result == "The diagram shows a client-server-database flow."


def test_describe_strips_unterminated_think_block(monkeypatch):
    """A reasoning block cut off by the token limit (no closing tag) is
    stripped to the end; if nothing remains, that's an empty response."""
    tag_name = "think"
    open_tag = "<" + tag_name + ">"
    # Truncated: opening tag, reasoning, but NO closing tag.
    truncated = open_tag + " The user wants a description of the provided"
    client = _mock_client(content=truncated)
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    with pytest.raises(ValueError, match="empty description"):
        describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    # Closed block followed by an answer still strips correctly.
    good = open_tag + " reasoning" + ("</" + tag_name + ">") + "A bar chart."
    client2 = _mock_client(content=good)
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client2)

    assert (
        describe_image(b"\x89PNG fake bytes", groq_api_key="test-key") == "A bar chart."
    )


def test_describe_normalizes_unicode_dashes(monkeypatch):
    """Typographic dashes in the description become ASCII hyphens."""
    client = _mock_client(content="flow \u2014 left to right \u2013 staged")
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    result = describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    assert result == "flow - left to right - staged"
    for ch in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014"):
        assert ch not in result


def test_describe_sends_image_as_data_url(monkeypatch):
    """The image is sent base64-encoded with a detected MIME type."""
    client = _mock_client(content="desc")
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    # PNG magic bytes built without escape sequences (they do not
    # survive being written into source files).
    png = b"\x89PNG" + bytes([13, 10, 26, 10]) + b"rest-of-png"
    describe_image(png, groq_api_key="test-key")

    kwargs = client.chat.completions.create.call_args.kwargs
    user_msg = kwargs["messages"][1]
    image_part = next(p for p in user_msg["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_describe_uses_env_model_override(monkeypatch):
    """GROQ_VISION_MODEL env var overrides the default model."""
    monkeypatch.setenv("GROQ_VISION_MODEL", "custom/vision-model")
    client = _mock_client(content="desc")
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "custom/vision-model"


# --- Error paths -------------------------------------------------------------


def test_describe_raises_without_api_key(monkeypatch):
    """Without an API key (and no env var), raises ValueError."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Groq API key is not configured"):
        describe_image(b"\x89PNG fake bytes")


def test_describe_retries_on_rate_limit(monkeypatch):
    """RateLimitError on first call is retried and succeeds on second."""
    client = _mock_client(
        side_effect=[
            _rate_limit_error(),
            _mock_response("recovered description"),
        ]
    )
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    result = describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    assert result == "recovered description"
    assert client.chat.completions.create.call_count == 2


def test_describe_raises_on_persistent_rate_limit(monkeypatch):
    """If all retries hit rate limit, RateLimitError is raised."""
    client = _mock_client(side_effect=_rate_limit_error())
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    with pytest.raises(RateLimitError):
        describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    assert client.chat.completions.create.call_count == 4  # 1 + 3 retries


def test_describe_empty_after_think_strip_raises(monkeypatch):
    """A response that is ONLY a think block is treated as empty and
    raises immediately (non-retryable)."""
    client = _mock_client(content="")
    monkeypatch.setattr(describe_module, "_get_groq_client", lambda key: client)

    with pytest.raises(ValueError, match="empty description"):
        describe_image(b"\x89PNG fake bytes", groq_api_key="test-key")

    # Non-retryable: exactly one call.
    assert client.chat.completions.create.call_count == 1
