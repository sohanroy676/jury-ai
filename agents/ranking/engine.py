"""Ranking engine — weighted composites, ordering, shortlisting.

Pure functions only: no Supabase, no I/O. The backend fetches rubric +
scores and delegates here (architecture.md reserves ``agents/ranking``
for exactly this logic).

v0.6.0 semantics:

- ``composite_score = sum(criterion_score * weight)``, rounded to 4
  decimals for stable output.
- Deterministic order: composite DESC -> innovation DESC ->
  submission_id ASC. Equal composites NEVER order arbitrarily.
- Rows whose composite ties another row's are flagged
  ``tied_on_composite`` for manual-review visibility.
- Shortlist via ``top_n`` (first N after sorting) OR ``min_score``
  (inclusive) — never both; the route enforces mutual exclusivity.
- Only complete score sets (all four criteria) are ranked; unscored and
  partial submissions are excluded but counted.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from agents.scoring.base import CRITERIA_NAMES

# Equal weights used when a hackathon has no configured rubric.
DEFAULT_WEIGHTS: dict[str, float] = {c: 0.25 for c in CRITERIA_NAMES}

# Secondary sort key for composite ties (roadmap suggestion).
TIE_BREAK_CRITERION = "innovation"

# Two composites within this distance count as tied.
TIE_EPSILON = 1e-9

# Output precision for composites.
COMPOSITE_DECIMALS = 4

# Tolerance when checking that weights sum to ~1.0 or ~100.
SUM_TOLERANCE = 1e-6


class WeightValidationError(ValueError):
    """Raised when a submitted rubric is malformed (maps to HTTP 422)."""


@dataclass
class RankedSubmission:
    """One row of the leaderboard."""

    rank: int
    submission_id: str
    team_name: str
    composite_score: float
    criterion_scores: dict[str, int]
    shortlisted: bool
    tied_on_composite: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "submission_id": self.submission_id,
            "team_name": self.team_name,
            "composite_score": self.composite_score,
            "criterion_scores": dict(self.criterion_scores),
            "shortlisted": self.shortlisted,
            "tied_on_composite": self.tied_on_composite,
        }


def validate_weights(raw: Any) -> dict[str, float]:
    """Validate a raw weights mapping and return normalized fractions.

    Accepts sums of ~1.0 or ~100 (percentages are divided by 100).
    Requires exactly the four known criteria; each weight must be a
    finite number >= 0 (zero = criterion effectively ignored).

    Raises:
        WeightValidationError: (a ValueError subclass) with a specific,
            human-readable message on any violation.
    """
    if not isinstance(raw, dict):
        raise WeightValidationError("weights must be a JSON object")

    unknown = sorted(str(k) for k in raw if k not in CRITERIA_NAMES)
    if unknown:
        raise WeightValidationError(
            f"unknown criteria {unknown}; allowed: {CRITERIA_NAMES}"
        )
    missing = [c for c in CRITERIA_NAMES if c not in raw]
    if missing:
        raise WeightValidationError(f"missing criteria: {missing}")

    parsed: dict[str, float] = {}
    for criterion in CRITERIA_NAMES:
        weight = raw[criterion]
        # bool is an int subclass - True must not become a weight of 1.
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise WeightValidationError(f"weight for '{criterion}' must be a number")
        if not math.isfinite(weight):
            raise WeightValidationError(f"weight for '{criterion}' must be finite")
        if weight < 0:
            raise WeightValidationError(f"weight for '{criterion}' must be >= 0")
        parsed[criterion] = float(weight)

    total = sum(parsed.values())
    if abs(total - 1.0) <= SUM_TOLERANCE:
        return parsed
    if abs(total - 100.0) <= SUM_TOLERANCE * 100:
        return {criterion: w / 100.0 for criterion, w in parsed.items()}
    raise WeightValidationError(f"weights must sum to ~1.0 or ~100, got {total:.6g}")


def compute_composite(
    criterion_scores: dict[str, float], weights: dict[str, float]
) -> float:
    """Weighted sum over the weight keys; caller guarantees completeness.

    Rounded to COMPOSITE_DECIMALS so equal inputs always produce
    bit-identical floats (tie detection relies on that).
    """
    total = sum(criterion_scores[c] * weights[c] for c in weights)
    return round(total, COMPOSITE_DECIMALS)


def build_ranking(
    submissions: list[dict[str, Any]],
    grouped_scores: dict[str, list[dict[str, Any]]],
    weights: dict[str, float],
    top_n: int | None = None,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Turn raw rows into a ranked, shortlisted leaderboard body.

    Args:
        submissions: ``submissions`` table rows (need ``id``, ``team_name``).
        grouped_scores: scores grouped by ``submission_id``; each row has
            ``criterion`` and ``score``.
        weights: normalized fractions keyed by criterion (see
            :func:`validate_weights`).
        top_n: shortlist the first N rows after sorting (or None).
        min_score: shortlist every row with composite >= this (or None).
            Mutually exclusive with ``top_n`` — enforced upstream.

    Returns:
        ``{"ranked": [...], "scored_count": int, "unscored_count": int,
        "partial_count": int}``
    """
    complete: list[tuple[str, str, dict[str, int], float]] = []
    unscored_count = 0
    partial_count = 0

    for submission in submissions:
        sid = submission["id"]
        by_criterion = {
            row["criterion"]: row["score"]
            for row in grouped_scores.get(sid, [])
            if row.get("criterion") in CRITERIA_NAMES
        }
        if len(by_criterion) == len(CRITERIA_NAMES):
            composite = compute_composite(by_criterion, weights)
            complete.append(
                (sid, str(submission.get("team_name", "")), by_criterion, composite)
            )
        elif not by_criterion:
            unscored_count += 1
        else:
            partial_count += 1

    # Deterministic tie-break chain: composite DESC, innovation DESC,
    # then submission_id ASC so equal composites NEVER order arbitrarily.
    complete.sort(key=lambda row: (-row[3], -row[2][TIE_BREAK_CRITERION], row[0]))

    # Flag every member of a composite tie group (manual-review visibility).
    groups: dict[float, list[int]] = defaultdict(list)
    for index, row in enumerate(complete):
        # Post-rounding, tied composites are bit-identical floats.
        groups[row[3]].append(index)

    ranked: list[RankedSubmission] = []
    total_rows = len(complete)
    for index, (sid, team_name, by_criterion, composite) in enumerate(complete):
        shortlisted = False
        if top_n is not None:
            shortlisted = index < top_n
        elif min_score is not None:
            shortlisted = composite >= min_score - TIE_EPSILON
        tied = len(groups[composite]) > 1
        ranked.append(
            RankedSubmission(
                rank=index + 1,
                submission_id=sid,
                team_name=team_name,
                composite_score=composite,
                criterion_scores=by_criterion,
                shortlisted=shortlisted,
                tied_on_composite=tied,
            )
        )

    return {
        "ranked": [entry.as_dict() for entry in ranked],
        "scored_count": total_rows,
        "unscored_count": unscored_count,
        "partial_count": partial_count,
    }
