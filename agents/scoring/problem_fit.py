"""ProblemFitAgent — scores how well the submission addresses a real problem.

One of the four v0.5.0 specialist scoring agents. Narrow by design:
this lens judges ONLY problem significance and clarity.
"""

from __future__ import annotations

from agents.scoring.base import SpecialistAgent


class ProblemFitAgent(SpecialistAgent):
    """Problem fit: is the problem real, significant, clearly identified?"""

    criterion = "problem_fit"
    guidance = (
        (
            "Identify the specific problem the team claims to solve and "
            "judge how real, significant, and clearly stated it is."
        ),
        (
            "Reward concrete evidence: user research, cited statistics, "
            "named stakeholders, described pain points."
        ),
        (
            "Penalize vague framing ('many people struggle with X') with no "
            "supporting detail, or a solution hunting for a problem."
        ),
    )
