"""Tests for the v0.6.0 ranking engine (pure functions, no I/O)."""

from __future__ import annotations

import pytest

from agents.ranking.engine import (
    COMPOSITE_DECIMALS,
    DEFAULT_WEIGHTS,
    WeightValidationError,
    build_ranking,
    compute_composite,
    validate_weights,
)

# --- Helpers ------------------------------------------------------------------


def _weights(innovation=0.25, problem_fit=0.25, technical_depth=0.25, feasibility=0.25):
    return {
        "problem_fit": problem_fit,
        "technical_depth": technical_depth,
        "feasibility": feasibility,
        "innovation": innovation,
    }


def _submission(sid: str, team: str = "Team") -> dict:
    return {"id": sid, "team_name": team}


def _scores_for(sid: str, pf=5, td=5, fe=5, inno=5) -> list[dict]:
    """Score rows for one submission, as the service layer returns them."""
    return [
        {"submission_id": sid, "criterion": "problem_fit", "score": pf},
        {"submission_id": sid, "criterion": "technical_depth", "score": td},
        {"submission_id": sid, "criterion": "feasibility", "score": fe},
        {"submission_id": sid, "criterion": "innovation", "score": inno},
    ]


def _grouped(*score_lists: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for rows in score_lists:
        if rows:
            grouped.setdefault(rows[0]["submission_id"], []).extend(rows)
    return grouped


# --- validate_weights ----------------------------------------------------------


def test_validate_weights_accepts_fractions():
    weights = _weights()
    assert validate_weights(weights) == weights


def test_validate_weights_normalizes_percentages():
    """Roadmap allows sums of ~100 - they are normalized to fractions."""
    raw = {
        "problem_fit": 20,
        "technical_depth": 30,
        "feasibility": 10,
        "innovation": 40,
    }
    assert validate_weights(raw) == {
        "problem_fit": 0.20,
        "technical_depth": 0.30,
        "feasibility": 0.10,
        "innovation": 0.40,
    }


def test_validate_weights_rejects_unknown_criterion():
    raw = _weights()
    raw["style"] = 0.1
    raw["problem_fit"] = 0.2  # keep the sum plausible
    with pytest.raises(WeightValidationError, match="unknown criteria"):
        validate_weights(raw)


def test_validate_weights_rejects_missing_criterion():
    raw = _weights()
    del raw["feasibility"]
    with pytest.raises(WeightValidationError, match="missing criteria"):
        validate_weights(raw)


@pytest.mark.parametrize("bad", ["0.25", None, True])
def test_validate_weights_rejects_non_numeric(bad):
    raw = _weights()
    raw["problem_fit"] = bad
    with pytest.raises(WeightValidationError, match="must be a number"):
        validate_weights(raw)


def test_validate_weights_rejects_non_finite():
    raw = _weights()
    raw["innovation"] = float("nan")
    with pytest.raises(WeightValidationError, match="finite"):
        validate_weights(raw)


def test_validate_weights_rejects_negative():
    raw = _weights()
    raw["feasibility"] = -0.1
    raw["innovation"] = 0.35  # keep the sum at 1.0 so only negativity trips
    with pytest.raises(WeightValidationError, match=">= 0"):
        validate_weights(raw)


@pytest.mark.parametrize("total", [0.8, 1.5, 50.0, 120.0])
def test_validate_weights_rejects_bad_sum(total):
    base = {"problem_fit": 0.25, "technical_depth": 0.25, "feasibility": 0.25}
    raw = {**base, "innovation": total - 0.75}
    with pytest.raises(WeightValidationError, match="must sum"):
        validate_weights(raw)


def test_validate_weights_accepts_zero_weight():
    """Zero is legal: that criterion is effectively ignored."""
    raw = _weights(
        feasibility=0.0, problem_fit=0.3, technical_depth=0.35, innovation=0.35
    )
    assert validate_weights(raw)["feasibility"] == 0.0


def test_validate_weights_rejects_non_dict():
    with pytest.raises(WeightValidationError, match="JSON object"):
        validate_weights([0.25, 0.25, 0.25, 0.25])


# --- compute_composite ---------------------------------------------------------


def test_compute_composite_known_values():
    scores = {"problem_fit": 8, "technical_depth": 7, "feasibility": 6, "innovation": 9}
    weights = _weights(
        innovation=0.4, problem_fit=0.2, technical_depth=0.2, feasibility=0.2
    )
    # 8*0.2 + 7*0.2 + 6*0.2 + 9*0.4 = 1.6 + 1.4 + 1.2 + 3.6 = 7.8
    assert compute_composite(scores, weights) == 7.8


def test_compute_composite_rounds_to_output_precision():
    scores = {"problem_fit": 1, "technical_depth": 1, "feasibility": 1, "innovation": 1}
    weights = _weights(
        problem_fit=0.3333, technical_depth=0.3333, feasibility=0.3334, innovation=0.0
    )
    composite = compute_composite(scores, weights)
    assert composite == round(composite, COMPOSITE_DECIMALS)


# --- build_ranking: ordering ---------------------------------------------------


def _pool_specs() -> list[tuple[str, dict[str, int]]]:
    """Five submissions with distinct, known profiles."""
    return [
        (
            "id-a",
            {"problem_fit": 8, "technical_depth": 7, "feasibility": 6, "innovation": 9},
        ),
        (
            "id-b",
            {"problem_fit": 9, "technical_depth": 9, "feasibility": 9, "innovation": 5},
        ),
        (
            "id-c",
            {"problem_fit": 4, "technical_depth": 3, "feasibility": 8, "innovation": 6},
        ),
        (
            "id-d",
            {
                "problem_fit": 2,
                "technical_depth": 2,
                "feasibility": 2,
                "innovation": 10,
            },
        ),
        (
            "id-e",
            {"problem_fit": 6, "technical_depth": 6, "feasibility": 6, "innovation": 6},
        ),
    ]


def _build(specs=None, weights=None, **kwargs):
    specs = specs if specs is not None else _pool_specs()
    subs = [_submission(sid) for sid, _ in specs]
    name_map = {
        "problem_fit": "pf",
        "technical_depth": "td",
        "feasibility": "fe",
        "innovation": "inno",
    }
    grouped = _grouped(
        *[
            _scores_for(sid, **{name_map[c]: v for c, v in sc.items()})
            for sid, sc in specs
        ]
    )
    return build_ranking(subs, grouped, weights or DEFAULT_WEIGHTS, **kwargs)


def test_ranks_descending_by_composite():
    body = _build()
    order = [row["submission_id"] for row in body["ranked"]]
    composites = [row["composite_score"] for row in body["ranked"]]
    assert composites == sorted(composites, reverse=True)
    # Composites: b=8.0, a=7.5, e=6.0, c=5.25, d=4.0.
    assert order == ["id-b", "id-a", "id-e", "id-c", "id-d"]
    assert [row["rank"] for row in body["ranked"]] == [1, 2, 3, 4, 5]
    assert body["scored_count"] == 5


def test_weight_change_flips_ranking():
    """Roadmap DoD: innovation 20% -> 40% changes the order accordingly."""
    # Balanced baseline: composites are id-b=8.0 > id-a=7.5.
    balanced_order = [r["submission_id"] for r in _build(weights=_weights())["ranked"]]
    assert balanced_order[:2] == ["id-b", "id-a"]

    # Shifting weight toward innovation (a: 9 > b: 5) flips the top two:
    #   id-a: 8*0.15 + 7*0.20 + 6*0.25 + 9*0.40 = 7.70
    #   id-b: 9*0.15 + 9*0.20 + 9*0.25 + 5*0.40 = 7.40
    innovation_heavy = _weights(
        problem_fit=0.15, technical_depth=0.20, feasibility=0.25, innovation=0.40
    )
    heavy_order = [
        r["submission_id"] for r in _build(weights=innovation_heavy)["ranked"]
    ]
    assert heavy_order[:2] == ["id-a", "id-b"]
    assert heavy_order != balanced_order


# --- build_ranking: ties -------------------------------------------------------


def test_exact_tie_broken_by_innovation_then_id():
    """DoD: equal composites resolve by rule, never arbitrary order."""
    # All four scores 6 for both -> composite 6.0 exactly; innovation is
    # also tied here, so submission_id ASC decides.
    s1 = _scores_for("id-x", pf=6, td=6, fe=6, inno=6)
    s2 = _scores_for("id-w", pf=6, td=6, fe=6, inno=6)
    body = build_ranking(
        [_submission("id-x"), _submission("id-w")], _grouped(s1, s2), DEFAULT_WEIGHTS
    )
    assert [r["submission_id"] for r in body["ranked"]] == ["id-w", "id-x"]
    assert all(r["tied_on_composite"] for r in body["ranked"])

    # Same 6.0 composite via different mixes -> higher innovation wins.
    #   id-lo: 9 + 8 + 2 + 5 = 24 -> composite 6.0, innovation 5
    #   id-hi: 3 + 3 + 8 + 10 = 24 -> composite 6.0, innovation 10
    t1 = _scores_for("id-lo", pf=9, td=8, fe=2, inno=5)
    t2 = _scores_for("id-hi", pf=3, td=3, fe=8, inno=10)
    body2 = build_ranking(
        [_submission("id-lo"), _submission("id-hi")],
        _grouped(t1, t2),
        DEFAULT_WEIGHTS,
    )
    assert body2["ranked"][0]["submission_id"] == "id-hi"
    assert {r["tied_on_composite"] for r in body2["ranked"]} == {True}


def test_tie_order_is_stable_across_repeated_calls():
    s1 = _scores_for("id-p", pf=7, td=7, fe=7, inno=7)
    s2 = _scores_for("id-q", pf=7, td=7, fe=7, inno=7)
    s3 = _scores_for("id-r", pf=7, td=7, fe=7, inno=7)
    orders = {
        tuple(
            r["submission_id"]
            for r in build_ranking(
                [_submission("id-p"), _submission("id-q"), _submission("id-r")],
                _grouped(s1, s2, s3),
                DEFAULT_WEIGHTS,
            )["ranked"]
        )
        for _ in range(10)
    }
    assert len(orders) == 1  # fully deterministic


def test_non_tied_rows_are_not_flagged():
    body = _build()
    assert all(not r["tied_on_composite"] for r in body["ranked"])


# --- build_ranking: shortlisting -----------------------------------------------


def test_top_n_shortlists_exactly_n():
    """Roadmap DoD: cutoff at top 5 -> exactly 5 shortlisted."""
    # Grow the pool to 8 submissions.
    specs = _pool_specs() + [
        (
            f"id-{i}",
            {"problem_fit": 5, "technical_depth": 5, "feasibility": 5, "innovation": i},
        )
        for i in range(1, 4)  # id-1..id-3
    ]
    body = _build(specs=specs, top_n=5)
    flagged = [r for r in body["ranked"] if r["shortlisted"]]
    unflagged = [r for r in body["ranked"] if not r["shortlisted"]]
    assert len(flagged) == 5
    assert len(unflagged) == 3
    assert [r["rank"] for r in flagged] == [1, 2, 3, 4, 5]
    assert [r["rank"] for r in unflagged] == [6, 7, 8]


def test_top_n_larger_than_pool_shortlists_everything():
    specs = [
        (
            "id-a",
            {"problem_fit": 8, "technical_depth": 7, "feasibility": 6, "innovation": 9},
        ),
        (
            "id-b",
            {"problem_fit": 9, "technical_depth": 9, "feasibility": 9, "innovation": 5},
        ),
    ]
    body = _build(specs=specs, top_n=10)
    assert all(r["shortlisted"] for r in body["ranked"])


def test_min_score_cutoff_is_inclusive():
    # Composites: id-a=7.5, id-b=8.0, id-e=6.0, id-c=5.25, id-d=4.0.
    body = _build(min_score=6.0)
    shortlisted = {r["submission_id"] for r in body["ranked"] if r["shortlisted"]}
    assert shortlisted == {"id-a", "id-b", "id-e"}  # id-e sits exactly on 6.0


def test_no_cutoff_means_nothing_shortlisted():
    body = _build(top_n=None)
    assert all(not r["shortlisted"] for r in body["ranked"])


# --- build_ranking: exclusions & empties ---------------------------------------


def test_unscored_and_partial_submissions_are_excluded_but_counted():
    subs = [
        _submission("id-full"),
        _submission("id-none"),
        _submission("id-partial"),
    ]
    partial_rows = [
        {"submission_id": "id-partial", "criterion": "problem_fit", "score": 7},
        {"submission_id": "id-partial", "criterion": "technical_depth", "score": 6},
        # missing feasibility + innovation
    ]
    grouped = _grouped(
        _scores_for("id-full"),
        partial_rows,
        # id-none has no rows at all
    )
    body = build_ranking(subs, grouped, DEFAULT_WEIGHTS)
    assert [r["submission_id"] for r in body["ranked"]] == ["id-full"]
    assert body["scored_count"] == 1
    assert body["unscored_count"] == 1
    assert body["partial_count"] == 1


def test_empty_inputs_yield_empty_result_with_zero_counts():
    body = build_ranking([], {}, DEFAULT_WEIGHTS)
    assert body == {
        "ranked": [],
        "scored_count": 0,
        "unscored_count": 0,
        "partial_count": 0,
    }


def test_team_name_passes_through_to_rows():
    s = _scores_for("sid-1")
    body = build_ranking(
        [_submission("sid-1", "NebulaDrift")], _grouped(s), DEFAULT_WEIGHTS
    )
    assert body["ranked"][0]["team_name"] == "NebulaDrift"
