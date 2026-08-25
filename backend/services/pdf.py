"""ReportLab-backed per-team PDF report (v0.7.0).

Free, open-source rendering — no paid PDF API, per project rules. The
report combines the leaderboard context (composite, rank, shortlist),
the four criterion scores with justifications, and — when already
generated — the written feedback.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any
from xml.sax import saxutils

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_CRITERIA_TITLES = {
    "problem_fit": "Problem Fit",
    "technical_depth": "Technical Depth",
    "feasibility": "Feasibility",
    "innovation": "Innovation",
}


def _esc(text: Any) -> str:
    """Escape text for safe embedding in ReportLab Paragraph markup."""
    return saxutils.escape(str(text))


def _bullet_list(items: list[str], styles) -> list:
    return [Paragraph(f"&bull; {_esc(item)}", styles["BodyText"]) for item in items]


def render_submission_report(
    *,
    team_name: str,
    hackathon_id: str,
    rank: int | None,
    total_scored: int | None,
    composite_score: float,
    shortlisted: bool,
    tied_on_composite: bool,
    scores: list[dict[str, Any]],
    feedback: dict[str, Any] | None,
    agent_version: str,
) -> bytes:
    """Render one team's evaluation report and return PDF bytes.

    Args:
        team_name: The submission's team name.
        hackathon_id: Hackathon scope the numbers were computed under.
        rank: Leaderboard rank (1-based), when ranked.
        total_scored: How many submissions were ranked in total.
        composite_score: Weighted composite from the ranking engine.
        shortlisted: Whether the team made the shortlist cutoff.
        tied_on_composite: Whether the composite ties another team's.
        scores: Score rows with ``criterion``, ``score``, ``justification``.
        feedback: Stored feedback row (``strengths``, ``weaknesses``,
            ``suggestion``, ``verdict``), or ``None`` when not yet
            generated.
        agent_version: Provenance string for the header.

    Returns:
        The rendered PDF as bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=f"JuryAI Evaluation - {team_name}",
        author="JuryAI",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "SectionHeading", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4
    )
    story: list = []

    # --- Header -------------------------------------------------------
    story.append(Paragraph(f"Evaluation Report - {_esc(team_name)}", styles["Title"]))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(
        Paragraph(
            f"Hackathon: {_esc(hackathon_id)} &nbsp;|&nbsp; Generated "
            f"{generated_at} by JuryAI ({_esc(agent_version)})",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    # --- Summary ------------------------------------------------------
    standing = f"{rank} of {total_scored}" if rank is not None else "-"
    summary_rows = [
        ["Composite score", f"{composite_score:g}"],
        ["Rank", standing],
        ["Shortlist status", "SHORTLISTED" if shortlisted else "Not shortlisted"],
        ["Tie flagged", "Yes" if tied_on_composite else "No"],
    ]
    summary_table = Table(summary_rows, colWidths=[45 * mm, 60 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(Paragraph("Summary", heading))
    story.append(summary_table)
    story.append(Spacer(1, 4 * mm))

    # --- Criterion scores ----------------------------------------------
    score_rows: list = [["Criterion", "Score", "Justification"]]
    for row in scores:
        title = _CRITERIA_TITLES.get(row["criterion"], row["criterion"])
        score_rows.append(
            [
                Paragraph(_esc(title), styles["BodyText"]),
                f"{row['score']}/10",
                Paragraph(_esc(row["justification"]), styles["BodyText"]),
            ]
        )
    scores_table = Table(score_rows, colWidths=[32 * mm, 16 * mm, 122 * mm])
    scores_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(Paragraph("Criterion Scores", heading))
    story.append(scores_table)
    story.append(Spacer(1, 4 * mm))

    # --- Feedback -------------------------------------------------------
    story.append(Paragraph("Written Feedback", heading))
    if feedback:
        story.append(Paragraph("Strengths", styles["Heading3"]))
        story.extend(_bullet_list(feedback.get("strengths") or [], styles))
        story.append(Paragraph("Weaknesses", styles["Heading3"]))
        story.extend(_bullet_list(feedback.get("weaknesses") or [], styles))
        story.append(Paragraph("Suggested improvement", styles["Heading3"]))
        story.append(
            Paragraph(_esc(feedback.get("suggestion", "")), styles["BodyText"])
        )
        verdict = str(feedback.get("verdict", "")).replace("_", " ").upper()
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>Recommendation: {verdict}</b>", styles["Normal"]))
    else:
        story.append(
            Paragraph(
                "<i>Feedback has not been generated yet. Trigger it via POST "
                "/api/submissions/{id}/feedback.</i>",
                styles["Normal"],
            )
        )

    doc.build(story)
    return buf.getvalue()
