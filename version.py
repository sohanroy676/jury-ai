"""Single source of truth for the JuryAI project version.

Bump ``APP_VERSION`` as part of every release, together with the git tag,
and keep ``frontend/package.json`` in sync in the same commit (npm cannot
read Python). Consumers:

- ``backend/main.py`` uses it for FastAPI/OpenAPI metadata.
- ``agents/scoring/scorer.py`` derives ``AGENT_VERSION`` from it so every
  stored score row records the release whose scoring logic produced it.
- The README status line states it in prose.

Drift guard: ``backend/tests/test_version.py``.
"""

APP_VERSION = "1.3.0"
