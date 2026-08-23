"""Read-only inspection of Supabase state after end-to-end uploads.

Prints recent submissions, their parsed_submissions row summaries
(text volume + per-image description entries) and the image_cache
contents, so the v0.3.5 DoD can be verified without a dashboard.

Run: python scripts/verify_e2e_state.py [team_name_filter]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from backend.services.supabase import get_client


def truncate(text: str | None, limit: int = 90) -> str:
    if not text:
        return "(none)"
    flat = " ".join(str(text).split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def main() -> None:
    client = get_client()
    team_filter = sys.argv[1] if len(sys.argv) > 1 else None

    # --- Submissions -----------------------------------------------------
    query = (
        client.table("submissions")
        .select("id, team_name, file_type, status, uploaded_at")
        .order("uploaded_at", desc=True)
        .limit(10)
    )
    submissions = query.execute().data
    if team_filter:
        submissions = [s for s in submissions if s["team_name"] == team_filter]

    print(f"=== Submissions ({len(submissions)} shown) ===")
    for s in submissions:
        print(
            f"  {s['id']}  team={s['team_name']!r}  type={s['file_type']}"
            f"  status={s['status']}  at={s['uploaded_at']}"
        )

    # --- Parsed submissions ----------------------------------------------
    print("\n=== Parsed submissions ===")
    for s in submissions:
        rows = (
            client.table("parsed_submissions")
            .select(
                "submission_id, raw_text, sections, source_format,"
                " image_descriptions, parsed_at"
            )
            .eq("submission_id", s["id"])
            .execute()
            .data
        )
        if not rows:
            print(f"  {s['id']} ({s['team_name']}): NO PARSED ROW")
            continue
        p = rows[0]
        print(f"  {s['id']} ({s['team_name']}):")
        print(
            f"    source_format={p['source_format']}  sections={len(p['sections'])}"
            f"  raw_text_chars={len(p['raw_text'] or '')}"
        )
        descs = p.get("image_descriptions") or []
        print(
            f"    image_descriptions: {len(descs)} entr{'y' if len(descs) == 1 else 'ies'}"
        )
        for d in descs:
            flag = "  [NEEDS HUMAN REVIEW]" if d.get("needs_human_review") else ""
            print(
                f"      page/slide {d.get('page')}: {d.get('classification')}"
                f" @ {d.get('confidence'):.2f}{flag}"
            )
            print(f"        phash={d.get('phash')}")
            print(f"        desc: {truncate(d.get('description'))}")

    # --- Image cache -------------------------------------------------------
    cache_rows = (
        client.table("image_cache")
        .select("phash, classification, confidence, description, cached_at")
        .order("cached_at", desc=False)
        .execute()
        .data
    )
    print(f"\n=== image_cache ({len(cache_rows)} rows) ===")
    for c in cache_rows:
        print(
            f"  {c['phash']}  {c['classification']} @ {c['confidence']}"
            f"  cached_at={c['cached_at']}"
        )
        print(f"    desc: {truncate(c.get('description'))}")


if __name__ == "__main__":
    main()
