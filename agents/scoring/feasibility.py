"""FeasibilityAgent — scores realism within hackathon constraints.

One of the four v0.5.0 specialist scoring agents. Narrow by design:
this lens judges ONLY whether the solution could actually be built
and deployed as described.
"""

from __future__ import annotations

from agents.scoring.base import SpecialistAgent


class FeasibilityAgent(SpecialistAgent):
    """Feasibility: realistic and achievable as described?"""

    criterion = "feasibility"
    guidance = (
        (
            "Judge whether the described scope could realistically be built "
            "and deployed by a small team within a hackathon timeframe."
        ),
        (
            "Reward scoped-down MVPs, honest assumptions, and use of "
            "appropriate existing tools or free-tier services."
        ),
        (
            "Penalize grandiose claims with no credible path (e.g. training "
            "large models from scratch, unsupported hardware promises, "
            "unrealistic timelines), and note unaddressed blockers only if "
            "the document should have covered them."
        ),
    )
