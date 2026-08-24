"""Drift guards: every version-bearing surface tracks ``version.APP_VERSION``.

The project version previously drifted across surfaces (FastAPI metadata
stuck at 0.1.0, scorer provenance frozen at v0.3.0). These tests fail on
any future drift between the single source and its consumers.
"""

import json
from pathlib import Path

import version
from agents.scoring.scorer import AGENT_VERSION
from backend.main import app


def test_app_version_is_semver():
    parts = version.APP_VERSION.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts), version.APP_VERSION


def test_fastapi_metadata_tracks_app_version():
    assert app.version == version.APP_VERSION
    assert app.title == "JuryAI API"


def test_scorer_agent_version_derives_from_app_version():
    # Persisted per score row as provenance — must follow the release.
    assert AGENT_VERSION == f"v{version.APP_VERSION}"


def test_frontend_package_json_tracks_app_version():
    pkg_path = Path(__file__).resolve().parents[2] / "frontend" / "package.json"
    package = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert package["version"] == version.APP_VERSION
