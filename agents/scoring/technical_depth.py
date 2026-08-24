"""TechnicalDepthAgent — infers technical depth from document content ONLY.

One of the four v0.5.0 specialist scoring agents. Per the updated roadmap
priority: depth is judged entirely from the PDF/PPTX content (architecture
descriptions, tech stack choices, implementation write-up). GitHub repos are
NOT evaluated here — a repo link is at most a later bonus signal (v2.5.0),
never a dependency; the document alone must be sufficient.
"""

from __future__ import annotations

from agents.scoring.base import SpecialistAgent


class TechnicalDepthAgent(SpecialistAgent):
    """Technical depth: engineering sophistication evident in the document."""

    criterion = "technical_depth"
    guidance = (
        (
            "Judge technical depth SOLELY from the document content: "
            "architecture descriptions, tech stack choices, implementation "
            "detail in the write-up or slides. Descriptions of embedded "
            "diagrams count as evidence too - they are part of the "
            "submission text given to you."
        ),
        (
            "GitHub repositories are NOT evaluated. Never penalize or reward "
            "a repo link's presence or absence; the document alone must be "
            "sufficient for a fair score."
        ),
        (
            "Reward specifics over buzzwords: concrete components, data "
            "flow, trade-offs considered, integration points, testing or "
            "deployment detail."
        ),
    )
