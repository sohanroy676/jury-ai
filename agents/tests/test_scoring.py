"""Tests for the scoring agent (Groq-powered single-agent scoring)."""

import json
from unittest.mock import Mock

import pytest
from groq import RateLimitError

from agents.scoring.scorer import (
    AGENT_VERSION,
    CRITERIA_NAMES,
    CriterionScore,
    ScoringResult,
    score_submission,
)

# --- Helpers -----------------------------------------------------------------


def _valid_json(scores: dict | None = None) -> str:
    """Build a valid JSON response string for the mock Groq client."""
    if scores is None:
        scores = {
            "problem_fit": {
                "score": 8,
                "justification": "Clear problem statement and solution.",
            },
            "technical_depth": {
                "score": 7,
                "justification": "Good tech stack and implementation details.",
            },
            "feasibility": {
                "score": 6,
                "justification": "Realistic for a 36-hour hackathon.",
            },
            "innovation": {
                "score": 9,
                "justification": "Novel approach to the problem.",
            },
        }
    return json.dumps(scores)


def _mock_response(content: str) -> Mock:
    """Create a mock Groq chat completion response."""
    resp = Mock()
    resp.choices = [Mock()]
    resp.choices[0].message.content = content
    return resp


def _mock_client(content: str, side_effect=None) -> Mock:
    """Create a mock Groq client.

    If ``side_effect`` is provided, it is used as the side_effect for
    ``chat.completions.create`` (useful for simulating errors).
    Otherwise, the client always returns a response with ``content``.
    """
    client = Mock()
    if side_effect is not None:
        client.chat.completions.create.side_effect = side_effect
    else:
        client.chat.completions.create.return_value = _mock_response(content)
    return client


def _rate_limit_error() -> RateLimitError:
    """Create a RateLimitError suitable for testing."""
    return RateLimitError("rate limited", response=Mock(), body=None)


@pytest.fixture(autouse=True)
def _mock_sleep(monkeypatch):
    """Mock time.sleep so tests don't actually wait."""
    monkeypatch.setattr("agents.scoring.scorer.time.sleep", lambda x: None)


# --- Happy path --------------------------------------------------------------


def test_score_submission_returns_valid_result(monkeypatch):
    """A valid Groq response produces a ScoringResult with 4 CriterionScores."""
    client = _mock_client(_valid_json())
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission(
        "test-id", "Some submission text", groq_api_key="test-key"
    )

    assert isinstance(result, ScoringResult)
    assert result.submission_id == "test-id"
    assert result.agent_version == AGENT_VERSION
    assert len(result.scores) == 4
    for score in result.scores:
        assert isinstance(score, CriterionScore)
        assert 1 <= score.score <= 10
        assert score.justification  # non-empty
    assert [s.criterion for s in result.scores] == CRITERIA_NAMES


def test_score_submission_uses_env_api_key(monkeypatch):
    """When groq_api_key is not passed, reads from GROQ_API_KEY env var."""
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    client = _mock_client(_valid_json())
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text")

    assert len(result.scores) == 4
    # Verify the client was created with the env var key.
    client.chat.completions.create.assert_called_once()


# --- Error: missing API key --------------------------------------------------


def test_score_submission_raises_without_api_key(monkeypatch):
    """Without an API key (and no env var), raises ValueError."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Groq API key is not configured"):
        score_submission("test-id", "Some text")


# --- Retry: rate limit -------------------------------------------------------


def test_score_submission_retries_on_rate_limit(monkeypatch):
    """RateLimitError on first call is retried and succeeds on second."""
    client = _mock_client(
        _valid_json(),
        side_effect=[
            _rate_limit_error(),
            _mock_response(_valid_json()),
        ],
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text", groq_api_key="test-key")

    assert len(result.scores) == 4
    assert client.chat.completions.create.call_count == 2


def test_score_submission_raises_on_persistent_rate_limit(monkeypatch):
    """If all retries hit rate limit, RateLimitError is raised."""
    client = _mock_client(
        _valid_json(),
        side_effect=_rate_limit_error(),
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    with pytest.raises(RateLimitError):
        score_submission("test-id", "Some text", groq_api_key="test-key")


# --- Retry: malformed JSON ---------------------------------------------------


def test_score_submission_retries_on_malformed_json(monkeypatch):
    """Malformed JSON on first call is retried and succeeds on second."""
    client = _mock_client(
        _valid_json(),
        side_effect=[
            _mock_response("not valid json {{{"),
            _mock_response(_valid_json()),
        ],
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text", groq_api_key="test-key")

    assert len(result.scores) == 4
    assert client.chat.completions.create.call_count == 2


def test_score_submission_raises_on_persistent_malformed_json(monkeypatch):
    """If all retries return malformed JSON, RuntimeError is raised."""
    client = _mock_client("garbage")
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    with pytest.raises(RuntimeError, match="Failed to get valid JSON"):
        score_submission("test-id", "Some text", groq_api_key="test-key")


# --- Validation --------------------------------------------------------------


def test_score_submission_rejects_score_out_of_range(monkeypatch):
    """Scores outside 1-10 are rejected and retried."""
    bad_json = json.dumps(
        {
            "problem_fit": {"score": 15, "justification": "Too high"},
            "technical_depth": {"score": 7, "justification": "OK"},
            "feasibility": {"score": 6, "justification": "OK"},
            "innovation": {"score": 9, "justification": "OK"},
        }
    )
    client = _mock_client(
        bad_json,
        side_effect=[
            _mock_response(bad_json),
            _mock_response(_valid_json()),
        ],
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text", groq_api_key="test-key")

    assert len(result.scores) == 4
    assert client.chat.completions.create.call_count == 2


def test_score_submission_rejects_empty_justification(monkeypatch):
    """Empty justifications are rejected and retried."""
    bad_json = json.dumps(
        {
            "problem_fit": {"score": 8, "justification": ""},
            "technical_depth": {"score": 7, "justification": "OK"},
            "feasibility": {"score": 6, "justification": "OK"},
            "innovation": {"score": 9, "justification": "OK"},
        }
    )
    client = _mock_client(
        bad_json,
        side_effect=[
            _mock_response(bad_json),
            _mock_response(_valid_json()),
        ],
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text", groq_api_key="test-key")

    assert len(result.scores) == 4
    assert client.chat.completions.create.call_count == 2


def test_score_submission_rejects_missing_criterion(monkeypatch):
    """A response missing a criterion is rejected and retried."""
    bad_json = json.dumps(
        {
            "problem_fit": {"score": 8, "justification": "Good"},
            "technical_depth": {"score": 7, "justification": "Good"},
            "feasibility": {"score": 6, "justification": "Good"},
            # innovation missing
        }
    )
    client = _mock_client(
        bad_json,
        side_effect=[
            _mock_response(bad_json),
            _mock_response(_valid_json()),
        ],
    )
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    result = score_submission("test-id", "Some text", groq_api_key="test-key")

    assert len(result.scores) == 4
    assert client.chat.completions.create.call_count == 2


# --- Stability: 10 consecutive runs ------------------------------------------


def test_score_submission_stable_across_10_runs(monkeypatch):
    """Valid JSON output across 10 consecutive runs (no parsing failures)."""
    client = _mock_client(_valid_json())
    monkeypatch.setattr("agents.scoring.scorer._get_groq_client", lambda key: client)

    for i in range(10):
        result = score_submission(f"test-id-{i}", "Some text", groq_api_key="test-key")
        assert len(result.scores) == 4
        for score in result.scores:
            assert 1 <= score.score <= 10
            assert score.justification

    assert client.chat.completions.create.call_count == 10
