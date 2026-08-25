"""Tests for the v0.7.0 FeedbackAgent (Groq-powered).

Covers prompts, strict response validation, corrective re-prompting,
rate-limit backoff semantics, and the generate_feedback entry point.
Route wiring lives in backend/tests/test_feedback_routes.py.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
from groq import APIConnectionError, RateLimitError

import version
from agents.feedback import (
    AGENT_VERSION,
    DEFAULT_MODEL,
    VALID_VERDICTS,
    FeedbackAgent,
    FeedbackResult,
    generate_feedback,
)

SUB_ID = "fb-sub-1"

SCORES = [
    {
        "criterion": "problem_fit",
        "score": 8,
        "justification": "Cites a 2024 survey of 500 farmers - concrete pain points.",
    },
    {
        "criterion": "technical_depth",
        "score": 5,
        "justification": "Mentions Kubernetes but shows no architecture diagram.",
    },
    {
        "criterion": "feasibility",
        "score": 7,
        "justification": "Scope fits a hackathon; hardware BOM is realistic.",
    },
    {
        "criterion": "innovation",
        "score": 9,
        "justification": "Offline-first LoRa sync is a fresh angle vs prior art.",
    },
]


def _valid_response(
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    suggestion: str = "Add a load-test report for the sync layer.",
    verdict: str = "shortlist",
) -> str:
    return json.dumps(
        {
            "strengths": strengths
            or ["Backed by a cited 500-farmer survey", "Novel offline-first LoRa sync"],
            "weaknesses": weaknesses or ["No architecture diagram despite K8s claims"],
            "suggestion": suggestion,
            "verdict": verdict,
        }
    )


def _mock_response(content: str) -> Mock:
    resp = Mock()
    resp.choices = [Mock()]
    resp.choices[0].message.content = content
    return resp


def _mock_client(content: str | None = None, side_effect=None):
    client = Mock()
    effects = list(side_effect) if side_effect is not None else None

    async def create(**kwargs):
        if effects is not None:
            effect = effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return _mock_response(effect)
        return _mock_response(content)

    client.chat.completions.create.side_effect = create
    return client


def _rate_limit_error() -> RateLimitError:
    return RateLimitError("rate limited", response=Mock(), body=None)


def _connection_error() -> APIConnectionError:
    return APIConnectionError(request=Mock())


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make backoff waits instant — never actually wait in unit tests."""

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("agents.feedback.agent._sleep", _instant)


# --- Provenance & constants ---------------------------------------------------


def test_agent_version_derives_from_app_version():
    assert AGENT_VERSION == f"v{version.APP_VERSION}"


def test_valid_verdicts_are_the_two_framings():
    assert set(VALID_VERDICTS) == {"shortlist", "reject"}


def test_model_matches_scoring_specialists():
    from agents.scoring.base import DEFAULT_MODEL as SCORING_MODEL

    assert DEFAULT_MODEL == SCORING_MODEL


# --- Prompts ------------------------------------------------------------------


def test_system_prompt_fixes_json_contract_and_tone_rules():
    prompt = FeedbackAgent().system_prompt()
    assert '"strengths"' in prompt and '"weaknesses"' in prompt
    assert '"suggestion"' in prompt and '"verdict"' in prompt
    assert "shortlist" in prompt and "reject" in prompt
    # Tone adaptation is instructed explicitly (roadmap DoD).
    assert "encouraging" in prompt.lower()


def test_user_message_carries_full_context():
    msg = FeedbackAgent().user_message(
        team_name="QuantumQuokka",
        scores=SCORES,
        composite_score=7.25,
        rank=2,
        total_scored=8,
        shortlisted=True,
    )
    assert "QuantumQuokka" in msg
    for row in SCORES:
        assert row["criterion"] in msg
        assert str(row["score"]) in msg
        assert row["justification"] in msg
    assert "7.25" in msg
    assert "rank 2 of 8" in msg
    assert "IS shortlisted" in msg


def test_user_message_flags_non_shortlisted_teams():
    msg = FeedbackAgent().user_message(
        team_name="Bravo",
        scores=SCORES,
        composite_score=3.5,
        rank=6,
        total_scored=8,
        shortlisted=False,
    )
    assert "NOT shortlisted" in msg


# --- Response validation ------------------------------------------------------


def test_parse_happy_path_roundtrip():
    result = FeedbackAgent().parse_feedback(_valid_response(), SUB_ID)
    assert isinstance(result, FeedbackResult)
    assert result.submission_id == SUB_ID
    assert len(result.strengths) == 2
    assert result.suggestion.startswith("Add a load-test")
    assert result.verdict == "shortlist"


def test_parse_normalizes_unicode_dashes_in_every_field():
    raw = json.dumps(
        {
            "strengths": ["Solid \u2013 well argued"],
            "weaknesses": ["Vague metrics \u2212 no baselines"],
            "suggestion": "Add benchmarks \u2014 before finals",
            "verdict": "reject",
        }
    )
    result = FeedbackAgent().parse_feedback(raw, SUB_ID)
    assert result.strengths == ["Solid - well argued"]
    assert result.weaknesses == ["Vague metrics - no baselines"]
    assert result.suggestion == "Add benchmarks - before finals"


@pytest.mark.parametrize("raw_verdict", ["Shortlist", "REJECT"])
def test_parse_accepts_verdict_case_insensitively(raw_verdict):
    result = FeedbackAgent().parse_feedback(
        _valid_response(verdict=raw_verdict), SUB_ID
    )
    assert result.verdict == raw_verdict.lower()


def test_parse_rejects_unknown_verdict():
    bad = _valid_response(verdict="maybe")
    with pytest.raises(ValueError, match="verdict"):
        FeedbackAgent().parse_feedback(bad, SUB_ID)


def test_parse_rejects_missing_fields():
    with pytest.raises(ValueError, match="Missing"):
        FeedbackAgent().parse_feedback(json.dumps({"strengths": ["x"]}), SUB_ID)


def test_parse_rejects_non_dict_root():
    with pytest.raises(TypeError, match="JSON object"):
        FeedbackAgent().parse_feedback(json.dumps(["nope"]), SUB_ID)


def test_parse_rejects_malformed_json():
    with pytest.raises(json.JSONDecodeError):
        FeedbackAgent().parse_feedback("not json at all", SUB_ID)


@pytest.mark.parametrize(
    "payload",
    [
        {"strengths": [], "weaknesses": ["w"], "suggestion": "s", "verdict": "reject"},
        {"strengths": ["ok"], "weaknesses": [], "suggestion": "s", "verdict": "reject"},
        {
            "strengths": [""],
            "weaknesses": ["w"],
            "suggestion": "s",
            "verdict": "reject",
        },
        {
            "strengths": ["   "],
            "weaknesses": ["w"],
            "suggestion": "s",
            "verdict": "reject",
        },
    ],
)
def test_parse_rejects_empty_or_blank_bullet_lists(payload):
    with pytest.raises(ValueError):
        FeedbackAgent().parse_feedback(json.dumps(payload), SUB_ID)


@pytest.mark.parametrize("bad", ["single string not a list", {"a": 1}, True])
def test_parse_rejects_wrong_typed_bullets(bad):
    payload = {
        "strengths": bad,
        "weaknesses": ["w"],
        "suggestion": "s",
        "verdict": "reject",
    }
    with pytest.raises(TypeError):
        FeedbackAgent().parse_feedback(json.dumps(payload), SUB_ID)


@pytest.mark.parametrize("bad_suggestion", [42, True, ["a"]])
def test_parse_rejects_non_string_suggestions(bad_suggestion):
    payload = {
        "strengths": ["s"],
        "weaknesses": ["w"],
        "suggestion": bad_suggestion,
        "verdict": "reject",
    }
    with pytest.raises(TypeError):
        FeedbackAgent().parse_feedback(json.dumps(payload), SUB_ID)


def test_parse_missing_suggestion_is_value_error():
    payload = {"strengths": ["s"], "weaknesses": ["w"], "verdict": "reject"}
    with pytest.raises(ValueError, match="Missing"):
        FeedbackAgent().parse_feedback(json.dumps(payload), SUB_ID)


def test_parse_rejects_blank_suggestion():
    payload = {
        "strengths": ["s"],
        "weaknesses": ["w"],
        "suggestion": "   ",
        "verdict": "reject",
    }
    with pytest.raises(ValueError, match="suggestion"):
        FeedbackAgent().parse_feedback(json.dumps(payload), SUB_ID)


# --- Retry semantics -----------------------------------------------------------


def test_generate_recovers_from_invalid_json_with_reprompt():
    client = _mock_client(side_effect=["not json", _valid_response()])
    result = asyncio.run(
        FeedbackAgent().generate(
            client,
            submission_id=SUB_ID,
            team_name="Team",
            scores=SCORES,
            composite_score=7.25,
            shortlisted=True,
        )
    )
    assert result.verdict == "shortlist"
    assert client.chat.completions.create.call_count == 2
    # The corrective re-prompt carries the context again.
    second_call = client.chat.completions.create.call_args_list[1]
    assert "was not valid JSON" in second_call.kwargs["messages"][1]["content"]


def test_generate_raises_runtime_error_when_never_valid():
    client = _mock_client(content="still not json")
    from agents.feedback.agent import MAX_RETRIES

    with pytest.raises(RuntimeError, match=SUB_ID):
        asyncio.run(
            FeedbackAgent().generate(
                client,
                submission_id=SUB_ID,
                team_name="Team",
                scores=SCORES,
                composite_score=7.0,
                shortlisted=False,
            )
        )
    assert client.chat.completions.create.call_count == MAX_RETRIES + 1


def test_generate_retries_then_succeeds_on_rate_limit():
    client = _mock_client(side_effect=[_rate_limit_error(), _valid_response()])
    result = asyncio.run(
        FeedbackAgent().generate(
            client,
            submission_id=SUB_ID,
            team_name="Team",
            scores=SCORES,
            composite_score=7.0,
            shortlisted=False,
        )
    )
    assert result.verdict == "shortlist"
    assert client.chat.completions.create.call_count == 2


def test_generate_propagates_rate_limits_after_exhaustion():
    client = _mock_client(side_effect=[_rate_limit_error()] * 10)
    from agents.feedback.agent import MAX_RETRIES

    with pytest.raises(RateLimitError):
        asyncio.run(
            FeedbackAgent().generate(
                client,
                submission_id=SUB_ID,
                team_name="Team",
                scores=SCORES,
                composite_score=7.0,
                shortlisted=True,
            )
        )
    assert client.chat.completions.create.call_count == MAX_RETRIES + 1


def test_generate_retries_connection_errors():
    client = _mock_client(side_effect=[_connection_error(), _valid_response()])
    result = asyncio.run(
        FeedbackAgent().generate(
            client,
            submission_id=SUB_ID,
            team_name="Team",
            scores=SCORES,
            composite_score=7.0,
            shortlisted=True,
        )
    )
    assert result.suggestion
    assert client.chat.completions.create.call_count == 2


def test_generate_does_not_retry_unexpected_errors():
    client = _mock_client(side_effect=[KeyError("boom")])
    with pytest.raises(KeyError):
        asyncio.run(
            FeedbackAgent().generate(
                client,
                submission_id=SUB_ID,
                team_name="Team",
                scores=SCORES,
                composite_score=7.0,
                shortlisted=True,
            )
        )
    assert client.chat.completions.create.call_count == 1


def test_call_uses_json_object_response_format():
    client = _mock_client(content=_valid_response())
    asyncio.run(
        FeedbackAgent().generate(
            client,
            submission_id=SUB_ID,
            team_name="Team",
            scores=SCORES,
            composite_score=7.0,
            shortlisted=True,
        )
    )
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["response_format"] == {"type": "json_object"}


# --- Entry point ---------------------------------------------------------------


def test_missing_groq_api_key_raises_value_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        asyncio.run(
            generate_feedback(
                submission_id=SUB_ID,
                team_name="Team",
                scores=SCORES,
                composite_score=7.0,
                shortlisted=True,
            )
        )


def test_generate_feedback_end_to_end_with_mocked_client(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(
        "agents.feedback.agent._get_async_groq_client",
        lambda api_key: _mock_client(content=_valid_response()),
    )
    result = asyncio.run(
        generate_feedback(
            submission_id=SUB_ID,
            team_name="QuantumQuokka",
            scores=SCORES,
            composite_score=7.25,
            shortlisted=True,
            rank=2,
            total_scored=8,
        )
    )
    assert isinstance(result, FeedbackResult)
    assert result.submission_id == SUB_ID
    assert result.verdict == "shortlist"
    assert result.agent_version == AGENT_VERSION
