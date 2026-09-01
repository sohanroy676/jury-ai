"""Tests for the v0.5.0 specialist scoring agents (Groq-powered).

Each criterion is scored by its own narrow ``SpecialistAgent`` subclass.
This file covers per-agent behavior: prompts, response validation,
retries, and error semantics. Orchestration-level behavior (parallel
fan-out, aggregation ordering, fail-closed semantics) lives in
test_scoring_parallel.py.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
from groq import APIConnectionError, RateLimitError

from agents.scoring.base import (
    AGENT_VERSION,
    CRITERIA_NAMES,
    RUBRIC,
    CriterionScore,
    ScoringResult,
    SpecialistAgent,
)
from agents.scoring.feasibility import FeasibilityAgent
from agents.scoring.innovation import InnovationAgent
from agents.scoring.problem_fit import ProblemFitAgent
from agents.scoring.technical_depth import TechnicalDepthAgent

AGENT_CLASSES = [
    ProblemFitAgent,
    TechnicalDepthAgent,
    FeasibilityAgent,
    InnovationAgent,
]

# --- Helpers -----------------------------------------------------------------


def _agent_for(criterion: str) -> SpecialistAgent:
    """Return the specialist instance for a criterion name."""
    cls = next(c for c in AGENT_CLASSES if c.criterion == criterion)
    return cls()


def _valid_response(
    criterion: str,
    score: int = 8,
    justification: str | None = None,
    cited_excerpt: str | None = None,
) -> str:
    """A valid single-criterion JSON response."""
    entry = {
        "score": score,
        "justification": justification or f"Strong {criterion} evidence.",
    }
    if cited_excerpt is not None:
        entry["cited_excerpt"] = cited_excerpt
    return json.dumps({criterion: entry})
def _valid_response(
    criterion: str, score: int = 8, justification: str | None = None
) -> str:
    """A valid single-criterion JSON response."""
    return json.dumps(
        {
            criterion: {
                "score": score,
                "justification": justification or f"Strong {criterion} evidence.",
            }
        }
    )


def _mock_response(content: str) -> Mock:
    """Create a mock Groq chat completion response."""
    resp = Mock()
    resp.choices = [Mock()]
    resp.choices[0].message.content = content
    return resp


def _mock_client(content: str | None = None, side_effect=None):
    """Create a mock AsyncGroq client with an awaitable completions.create.

    ``side_effect`` is a list of raw-content strings or Exception
    instances consumed per call; otherwise every call returns ``content``.
    """
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

    monkeypatch.setattr("agents.scoring.base._sleep", _instant)


# --- Rubric single-source ----------------------------------------------------


def test_rubric_matches_specialist_criteria():
    """The rubric, criteria list, and the four modules stay in lockstep."""
    assert [cls.criterion for cls in AGENT_CLASSES] == CRITERIA_NAMES
    assert set(CRITERIA_NAMES) == {c["name"] for c in RUBRIC["criteria"]}


def test_scoring_result_defaults_to_release_version():
    result = ScoringResult(submission_id="id-1", scores=[])
    assert result.agent_version == AGENT_VERSION


# --- Happy path ---------------------------------------------------------------


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_agent_scores_own_criterion(cls):
    """A valid Groq response yields this agent's CriterionScore."""
    client = _mock_client(_valid_response(cls.criterion))
    agent = cls()

    import asyncio

    score = asyncio.run(agent.score(client, "Some submission text"))

    assert isinstance(score, CriterionScore)
    assert score.criterion == cls.criterion
    assert 1 <= score.score <= 10
    assert score.justification
    assert client.chat.completions.create.call_count == 1


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_system_prompt_names_only_own_criterion(cls):
    """Narrow scope: each prompt references its criterion, never the others."""
    prompt = cls().system_prompt()
    assert cls.criterion in prompt
    for other in CRITERIA_NAMES:
        if other != cls.criterion:
            assert other not in prompt, (
                f"{cls.__name__}'s prompt leaks foreign criterion '{other}'"
            )


def test_technical_depth_prompt_is_document_only():
    """The depth agent judges document content and never requires a repo."""
    prompt = TechnicalDepthAgent().system_prompt()
    assert "SOLELY from the document content" in prompt
    assert "GitHub repositories are NOT evaluated" in prompt
    assert "document alone must be sufficient" in prompt


def test_user_message_wraps_submission_text():
    message = ProblemFitAgent().user_message("proposal body")
    assert "---BEGIN SUBMISSION TEXT---" in message
    assert "proposal body" in message
    assert "'problem_fit'" in message


# --- Response validation (adversarial) ----------------------------------------


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_wrong_criterion_echo_is_retried_then_recovered(cls):
    """A valid JSON keyed for ANOTHER agent counts as missing -> retry."""
    other = next(c for c in CRITERIA_NAMES if c != cls.criterion)
    client = _mock_client(
        side_effect=[_valid_response(other), _valid_response(cls.criterion)]
    )

    score = asyncio.run(cls().score(client, "text"))

    assert score.criterion == cls.criterion
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_boolean_score_is_rejected_and_retried(cls):
    """True is an int subclass — must not sneak through as score 1."""
    bad = json.dumps({cls.criterion: {"score": True, "justification": "x"}})
    client = _mock_client(side_effect=[bad, _valid_response(cls.criterion)])

    score = asyncio.run(cls().score(client, "text"))

    assert score.score >= 1
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
@pytest.mark.parametrize("bad_score", [0, 11])
def test_out_of_range_score_exhausts_retries(cls, bad_score):
    from agents.scoring.base import MAX_RETRIES

    bad = json.dumps({cls.criterion: {"score": bad_score, "justification": "x"}})
    client = _mock_client(side_effect=[bad] * (MAX_RETRIES + 1))

    with pytest.raises(RuntimeError, match=cls.criterion):
        asyncio.run(cls().score(client, "text"))

    assert client.chat.completions.create.call_count == MAX_RETRIES + 1


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_non_numeric_score_word_is_retried(cls):
    bad = json.dumps({cls.criterion: {"score": "seven", "justification": "x"}})
    client = _mock_client(side_effect=[bad, _valid_response(cls.criterion)])

    score = asyncio.run(cls().score(client, "text"))

    assert score.score == 8
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_non_dict_root_is_retried(cls):
    client = _mock_client(
        side_effect=[json.dumps([1, 2]), _valid_response(cls.criterion)]
    )

    score = asyncio.run(cls().score(client, "text"))

    assert score.criterion == cls.criterion
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_non_json_text_is_retried(cls):
    client = _mock_client(side_effect=["hello world", _valid_response(cls.criterion)])

    score = asyncio.run(cls().score(client, "text"))

    assert score.criterion == cls.criterion
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
@pytest.mark.parametrize("empty", ["", "   "])
def test_blank_justification_is_retried(cls, empty):
    bad = json.dumps({cls.criterion: {"score": 5, "justification": empty}})
    client = _mock_client(side_effect=[bad, _valid_response(cls.criterion)])

    score = asyncio.run(cls().score(client, "text"))

    assert score.justification
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_missing_score_or_justification_key_is_retried(cls):
    bad = json.dumps({cls.criterion: {"score": 5}})
    client = _mock_client(side_effect=[bad, _valid_response(cls.criterion)])

    asyncio.run(cls().score(client, "text"))
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("cls", AGENT_CLASSES)
def test_criterion_entry_not_a_dict_is_retried(cls):
    bad = json.dumps({cls.criterion: "excellent"})
    client = _mock_client(side_effect=[bad, _valid_response(cls.criterion)])

    asyncio.run(cls().score(client, "text"))
    assert client.chat.completions.create.call_count == 2


def test_numeric_string_score_is_accepted_leniently():
    """Documents v0.3.0 behavior carried forward: int('8') coerces fine."""
    client = _mock_client(
        json.dumps({"problem_fit": {"score": "8", "justification": "ok"}})
    )

    score = asyncio.run(ProblemFitAgent().score(client, "text"))

    assert score.score == 8


def test_extra_top_level_keys_are_ignored():
    payload = json.dumps(
        {
            "problem_fit": {"score": 7, "justification": "fine"},
            "unrequested_extra": {"anything": True},
        }
    )
    client = _mock_client(payload)

    score = asyncio.run(ProblemFitAgent().score(client, "text"))

    assert score.score == 7


def test_unicode_dashes_normalized_in_justification():
    raw = json.dumps(
        {
            "problem_fit": {
                "score": 8,
                "justification": "cost\u2011per\u2011dollar \u2014 solid",
            }
        }
    )
    client = _mock_client(raw)

    score = asyncio.run(ProblemFitAgent().score(client, "text"))

    assert score.justification == "cost-per-dollar - solid"


# --- Retry semantics ----------------------------------------------------------


def test_malformed_recovery_sends_corrective_prompt():
    criterion = "feasibility"
    client = _mock_client(side_effect=["not json", _valid_response(criterion)])

    asyncio.run(_agent_for(criterion).score(client, "submission text here"))

    second_call = client.chat.completions.create.call_args_list[1]
    user_content = second_call.kwargs["messages"][1]["content"]
    assert "not valid JSON" in user_content
    assert f"criterion '{criterion}'" in user_content
    assert "submission text here" in user_content


def test_rate_limit_retry_then_success():
    client = _mock_client(
        side_effect=[
            _rate_limit_error(),
            _rate_limit_error(),
            _valid_response("innovation"),
        ]
    )

    score = asyncio.run(InnovationAgent().score(client, "text"))

    assert score.criterion == "innovation"
    assert client.chat.completions.create.call_count == 3


def test_rate_limit_exhaustion_raises_rate_limit_error():
    from agents.scoring.base import MAX_RETRIES

    client = _mock_client(side_effect=[_rate_limit_error()] * (MAX_RETRIES + 1))

    with pytest.raises(RateLimitError):
        asyncio.run(InnovationAgent().score(client, "text"))

    assert client.chat.completions.create.call_count == MAX_RETRIES + 1


def test_connection_error_is_retried():
    client = _mock_client(
        side_effect=[_connection_error(), _valid_response("technical_depth")]
    )

    score = asyncio.run(TechnicalDepthAgent().score(client, "text"))

    assert score.criterion == "technical_depth"
    assert client.chat.completions.create.call_count == 2


def test_non_retryable_error_propagates_immediately_unwrapped():
    boom = RuntimeError("auth exploded")
    client = _mock_client(side_effect=[boom])

    with pytest.raises(RuntimeError, match="auth exploded"):
        asyncio.run(ProblemFitAgent().score(client, "text"))

    # No retry loop for non-retryable errors.
    assert client.chat.completions.create.call_count == 1


# --- Facade compatibility -----------------------------------------------------


def test_scorer_facade_still_exports_public_names():
    """Backend routes/tests import these from scorer — paths must survive."""
    from agents.scoring.scorer import (  # noqa: F401
        AGENT_VERSION,
        CRITERIA_NAMES,
        RUBRIC,
        CriterionScore,
        ScoringResult,
        build_scoring_text,
        build_specialist_agents,
        score_submission,
    )

    agents_list = build_specialist_agents()
    assert [a.criterion for a in agents_list] == CRITERIA_NAMES




# --- v2.3.0 Explainability: cited excerpts ----------------------------------


def test_citation_extracted_from_response():
    """A cited_excerpt in the response is parsed into the CriterionScore."""
    raw = json.dumps(
        {
            "problem_fit": {
                "score": 8,
                "justification": "Clear problem statement.",
                "cited_excerpt": "Over 2M students lack access to quality STEM resources.",
            }
        }
    )
    client = _mock_client(raw)
    score = asyncio.run(ProblemFitAgent().score(client, "text"))
    assert score.cited_excerpt == "Over 2M students lack access to quality STEM resources."


def test_citation_defaults_to_empty_when_missing():
    """Responses without cited_excerpt still parse -- citation defaults to ''."""
    raw = json.dumps(
        {
            "feasibility": {
                "score": 6,
                "justification": "Somewhat achievable.",
            }
        }
    )
    client = _mock_client(raw)
    score = asyncio.run(FeasibilityAgent().score(client, "text"))
    assert score.cited_excerpt == ""


def test_citation_defaults_to_empty_when_null():
    """Explicit null cited_excerpt is treated as empty string."""
    raw = json.dumps(
        {
            "innovation": {
                "score": 5,
                "justification": "Incremental improvement.",
                "cited_excerpt": None,
            }
        }
    )
    client = _mock_client(raw)
    score = asyncio.run(InnovationAgent().score(client, "text"))
    assert score.cited_excerpt == ""


def test_citation_unicode_dashes_normalized():
    """Unicode dashes in cited_excerpt are normalized to ASCII hyphens."""
    raw = (
        '{"technical_depth": {"score": 7, "justification": "Solid stack.", '
        '"cited_excerpt": "Uses React\u2011Native \u2014 performant."}}'
    )
    client = _mock_client(raw)
    score = asyncio.run(TechnicalDepthAgent().score(client, "text"))
    assert score.cited_excerpt == "Uses React-Native - performant."


def test_citation_empty_string_is_valid():
    """An empty cited_excerpt string is accepted (agent chose not to cite)."""
    raw = json.dumps(
        {
            "problem_fit": {
                "score": 3,
                "justification": "No clear problem stated in the submission.",
                "cited_excerpt": "",
            }
        }
    )
    client = _mock_client(raw)
    score = asyncio.run(ProblemFitAgent().score(client, "text"))
    assert score.cited_excerpt == ""
    assert score.score == 3


def test_criterion_score_dataclass_accepts_citation():
    """CriterionScore dataclass accepts cited_excerpt as optional field."""
    cs = CriterionScore(
        criterion="innovation",
        score=9,
        justification="Novel approach.",
        cited_excerpt="First to apply LLMs to this domain.",
    )
    assert cs.cited_excerpt == "First to apply LLMs to this domain."


def test_criterion_score_default_citation_empty():
    """CriterionScore defaults cited_excerpt to empty string."""
    cs = CriterionScore(criterion="feasibility", score=7, justification="Doable.")
    assert cs.cited_excerpt == ""
