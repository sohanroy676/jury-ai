#!/usr/bin/env python3
"""Regenerate the CHANGELOG.md [Unreleased] section from commit history.

Runs git-cliff over a commit range, normalizes its output into the
project's changelog style (plain headings, `* **scope:** message
([sha](url))` bullets, Documentation/chore noise removed), and merges
the result into the existing `## [Unreleased]` sections. Entry text is
always tool-derived from Conventional Commits — never hand-written.

Usage:
    venv/Scripts/python.exe scripts/regenerate_changelog.py <git-range>

Example:
    venv/Scripts/python.exe scripts/regenerate_changelog.py 937a78f..HEAD

Requires git-cliff (installed in the project venv).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
GIT_CLIFF = str(Path(__file__).resolve().parent.parent / "venv/Scripts/git-cliff.exe")
GITHUB_REPO = "sohanroy676/jury-ai"

# Section headings kept in the changelog (emoji variants from git-cliff's
# default template are mapped to their plain titles); anything else is dropped.
SECTION_TITLES = {
    "Features": "Features",
    "Bug Fixes": "Bug Fixes",
    "🚀 Features": "Features",
    "🐛 Bug Fixes": "Bug Fixes",
}

BULLET_WITH_SCOPE = re.compile(r"^-\s+\*\((?P<scope>[^)]+)\)\*\s+(?P<rest>.+)$")
BULLET_PLAIN = re.compile(r"^-\s+(?P<rest>.+)$")
HEADING = re.compile(r"^###\s+(.+)$")


def _generate(range_spec: str) -> tuple[str, dict[str, str]]:
    """Run git-cliff over the range; return raw markdown plus sha links.

    The returned dict maps each commit subject (lowercased) to a
    ``([short-sha](full-url))`` link so bullets match the file's style.
    """
    proc = subprocess.run(
        [GIT_CLIFF, range_spec],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"git-cliff failed with exit code {proc.returncode}")

    log = subprocess.run(
        ["git", "log", "--format=%H%x1f%s", range_spec],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    # Key commits by their DESCRIPTION ONLY (subject minus the
    # conventional `type(scope): ` prefix, lowercased) — that is what
    # a generated bullet contains after normalization.
    subject_prefix = re.compile(r"^\w+(?:\([^)]*\))?:\s+")
    shas: dict[str, str] = {}
    for record in log.stdout.splitlines():
        if "\x1f" not in record:
            continue
        full_sha, subject = record.split("\x1f", 1)
        key = subject_prefix.sub("", subject).strip().lower()
        shas[key] = (
            f"([{full_sha[:7]}](https://github.com/{GITHUB_REPO}/commit/{full_sha}))"
        )
    return proc.stdout, shas


def _linkify(bullet_text: str, shas: dict[str, str]) -> str:
    """Append the matching commit link, if one is known."""
    link = shas.get(bullet_text.strip().lower())
    return f"{bullet_text} {link}" if link else bullet_text


def _normalize(raw: str, shas: dict[str, str]) -> dict[str, list[str]]:
    """Convert git-cliff output into {section_title: [bullet lines]}."""
    sections: dict[str, list[str]] = {}
    current_title: str | None = None

    for line in raw.splitlines():
        heading = HEADING.match(line)
        if heading:
            current_title = SECTION_TITLES.get(heading.group(1).strip())
            if current_title and current_title not in sections:
                sections[current_title] = []
            continue

        if current_title is None:
            continue

        scoped = BULLET_WITH_SCOPE.match(line)
        if scoped:
            entry = (
                f"**{scoped.group('scope')}:** "
                f"{_linkify(scoped.group('rest'), shas)}"
            )
        else:
            plain = BULLET_PLAIN.match(line)
            if plain is None:
                continue
            entry = _linkify(plain.group("rest"), shas)
        sections[current_title].append(f"* {entry}")

    return sections


def _splice(sections: dict[str, list[str]]) -> None:
    """Merge generated bullets into CHANGELOG.md's [Unreleased] sections.

    Existing sections gain bullets at the TOP (newest-first); missing
    sections are created directly under the `## [Unreleased]` heading.
    """
    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    try:
        anchor = next(
            i for i, line in enumerate(lines) if line.strip() == "## [Unreleased]"
        )
    except StopIteration:
        raise SystemExit("CHANGELOG.md has no '## [Unreleased]' heading") from None

    section_positions: dict[str, int] = {}
    for i in range(anchor + 1, len(lines)):
        line = lines[i]
        if line.startswith("## "):
            break  # reached the next release section — Unreleased region ends
        if line.startswith("### "):
            title = line[4:].strip()
            if title in sections and title not in section_positions:
                section_positions[title] = i

    # Insertion plan (positions relative to current lines), applied
    # bottom-up so earlier positions stay valid.
    insertions: list[tuple[int, list[str]]] = []
    missing_sections: list[str] = []
    for title, bullets in sections.items():
        if not bullets:
            continue
        pos = section_positions.get(title)
        if pos is not None:
            insert_at = pos + 1
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            insertions.append((insert_at, list(reversed(bullets))))
        else:
            missing_sections.append(title)

    if missing_sections:
        block: list[str] = []
        for title in reversed(missing_sections):
            block.append(f"### {title}")
            block.append("")
            block.extend(sections[title])
            block.append("")
        insertions.append((anchor + 1, block))

    for insert_at, block_lines in sorted(insertions, key=lambda item: -item[0]):
        lines[insert_at:insert_at] = block_lines

    CHANGELOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(len(b) for _, b in insertions)
    print(f"Merged {total} generated bullet lines into [Unreleased]")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raw, shas = _generate(sys.argv[1])
    sections = _normalize(raw, shas)
    if not any(sections.values()):
        raise SystemExit("git-cliff produced no keepable entries for the range")
    _splice(sections)


if __name__ == "__main__":
    main()
