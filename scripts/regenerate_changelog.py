#!/usr/bin/env python3
"""Rebuild CHANGELOG.md from full commit history and release tags.

Runs git-cliff over the repository entire history (no range). Its
keep-a-changelog template emits one section per release tag, newest
first, plus an [Unreleased] section when post-tag commits exist. This
script normalizes that output into the project style (plain section
titles, ``* **scope:** message ([sha](url))`` bullets, Documentation /
chore noise dropped) and REWRITES CHANGELOG.md, preserving only the
hand-written preamble above the first release heading. Entry text is
always tool-derived from Conventional Commits — never hand-written.

Usage:
    venv/Scripts/python.exe scripts/regenerate_changelog.py

Requires git-cliff (installed in the project venv) and release tags of
the form ``vX.Y.Z`` so commits group under the right version sections.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
GIT_CLIFF = str(Path(__file__).resolve().parent.parent / "venv/Scripts/git-cliff.exe")
GITHUB_REPO = "sohanroy676/jury-ai"

# Section headings kept in the changelog (emoji variants from git-cliff
# default template are mapped to their plain titles); anything else is
# dropped. Rendering uses this fixed order.
SECTION_ORDER = ["Bug Fixes", "Features"]
SECTION_TITLES = {
    "Features": "Features",
    "Bug Fixes": "Bug Fixes",
    "🚀 Features": "Features",
    "🐛 Bug Fixes": "Bug Fixes",
}

BULLET_WITH_SCOPE = re.compile(r"^-\s+\*\((?P<scope>[^)]+)\)\*\s+(?P<rest>.+)$")
BULLET_PLAIN = re.compile(r"^-\s+(?P<rest>.+)$")
GROUP_HEADING = re.compile(r"^###\s+(.+)$")
RELEASE_HEADING = re.compile(
    r"^##\s+\[(?P<title>[^]]+)\](?:\s+-\s+(?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)


def _generate() -> tuple[str, dict[str, str]]:
    """Run git-cliff over all history; return raw markdown plus sha links.

    The returned dict maps each commit description (subject minus its
    conventional ``type(scope): `` prefix, lowercased) to a
    ``([short-sha](full-url))`` link so bullets match the file style.
    """
    proc = subprocess.run(
        [GIT_CLIFF],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"git-cliff failed with exit code {proc.returncode}")

    log = subprocess.run(
        ["git", "log", "--format=%H%x1f%s"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    subject_prefix = re.compile(r"^\w+(?:\([^)]*\))?:\s+")
    shas: dict[str, str] = {}
    for record in log.stdout.splitlines():
        if "" not in record:
            continue
        full_sha, subject = record.split("", 1)
        key = subject_prefix.sub("", subject).strip().lower()
        shas[key] = (
            f"([{full_sha[:7]}](https://github.com/{GITHUB_REPO}/commit/{full_sha}))"
        )
    return proc.stdout, shas


def _linkify(bullet_text: str, shas: dict[str, str]) -> str:
    """Append the matching commit link, if one is known."""
    link = shas.get(bullet_text.strip().lower())
    return f"{bullet_text} {link}" if link else bullet_text


def _release_title(raw_title: str) -> str:
    """Normalize git-cliff section titles to project vocabulary."""
    title = raw_title.strip()
    if title.lower() == "unreleased":
        return "Unreleased"
    if title.startswith("v") or not title[:1].isdigit():
        return title
    return f"v{title}"  # git-cliff strips the tag v-prefix; restore it


def _normalize(raw: str, shas: dict[str, str]) -> list[dict]:
    """Convert git-cliff output into ordered per-release section dicts.

    Returns a list of ``{"title": str, "date": str | None,
    "groups": {section_title: [bullet lines]}}`` in output order
    (newest release first).
    """
    releases: list[dict] = []
    current: dict | None = None
    group: str | None = None

    for line in raw.splitlines():
        if line.lstrip().startswith("<!--"):
            continue
        release = RELEASE_HEADING.match(line)
        if release:
            current = {
                "title": _release_title(release.group("title")),
                "date": release.group("date"),
                "groups": {},
            }
            releases.append(current)
            group = None
            continue
        if current is None:
            continue
        heading = GROUP_HEADING.match(line)
        if heading:
            group = SECTION_TITLES.get(heading.group(1).strip())
            if group and group not in current["groups"]:
                current["groups"][group] = []
            continue
        if group is None:
            continue
        scoped = BULLET_WITH_SCOPE.match(line)
        if scoped:
            entry = (
                f"**{scoped.group('scope')}:** {_linkify(scoped.group('rest'), shas)}"
            )
            current["groups"][group].append(f"* {entry}")
        else:
            plain = BULLET_PLAIN.match(line)
            if plain is not None:
                current["groups"][group].append(
                    f"* {_linkify(plain.group('rest'), shas)}"
                )

    # Drop releases whose kept groups are all empty (e.g. docs-only).
    return [r for r in releases if any(r["groups"].values())]


def _read_preamble() -> list[str]:
    """Return CHANGELOG.md lines above the first release heading."""
    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    preamble: list[str] = []
    for line in lines:
        if line.startswith("## "):
            break
        preamble.append(line)
    while preamble and not preamble[-1].strip():
        preamble.pop()
    return preamble


def _render(releases: list[dict], preamble: list[str]) -> str:
    """Render preamble plus normalized releases into the changelog body."""
    out = list(preamble)
    if releases:
        out.append("")
    for release in releases:
        heading = f"## [{release['title']}]"
        if release["date"]:
            heading += f" - {release['date']}"
        out += [heading, ""]
        for section in SECTION_ORDER:
            bullets = release["groups"].get(section)
            if not bullets:
                continue
            out += [f"### {section}", "", *bullets, ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    raw, shas = _generate()
    releases = _normalize(raw, shas)
    if not releases:
        raise SystemExit("git-cliff produced no keepable entries")
    CHANGELOG_PATH.write_text(_render(releases, _read_preamble()), encoding="utf-8")
    total = sum(len(b) for r in releases for b in r["groups"].values())
    titles = ", ".join(r["title"] for r in releases)
    print(f"Rebuilt CHANGELOG.md: {total} bullets across [{titles}]")


if __name__ == "__main__":
    main()
