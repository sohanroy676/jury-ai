"""InnovationAgent — scores novelty and creativity of the solution.

One of the four v0.5.0 specialist scoring agents. Narrow by design:
this lens judges ONLY freshness of approach versus existing solutions.
"""

from __future__ import annotations

from agents.scoring.base import SpecialistAgent


class InnovationAgent(SpecialistAgent):
    """Innovation: is there a fresh approach or meaningful improvement?"""

    criterion = "innovation"
    guidance = (
        (
            "Judge how novel the approach is relative to existing solutions "
            "for the same problem, and whether any claimed uniqueness is "
            "explained."
        ),
        (
            "Reward creative combinations, underserved-user insights, or a "
            "meaningful twist on a known idea - not novelty for its own sake."
        ),
        (
            "Penalize boilerplate clones of well-known apps presented as "
            "new, unless a genuinely different angle is articulated."
        ),
    )
