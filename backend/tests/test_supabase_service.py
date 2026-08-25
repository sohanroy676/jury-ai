"""Unit tests for the Supabase service layer's query handling.

Regression coverage for the PGRST116 bug: ``get_parsed_submission``
used PostgREST ``.single()``, which RAISES on zero rows instead of
returning empty data — surfacing as an unhandled 500 when scoring an
unknown/unparsed submission id. The contract is: row found -> dict,
no row -> None.
"""

from types import SimpleNamespace

from backend.services import supabase

# --- Fake query chain --------------------------------------------------------


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Mimics the supabase-py builder: table -> select -> eq -> limit ->
    execute, recording the calls so tests can assert the shape."""

    def __init__(self, data):
        self._data = data
        self.calls: list[tuple] = []

    def select(self, *columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def insert(self, values):
        self.calls.append(("insert", values))
        return self

    def update(self, values):
        self.calls.append(("update", values))
        return self

    def ilike(self, column, value):
        self.calls.append(("ilike", column, value))
        return self

    def is_(self, column, value):
        self.calls.append(("is_", column, value))
        return self

    def order(self, column, desc=False):
        self.calls.append(("order", column, desc))
        return self

    def limit(self, n):
        self.calls.append(("limit", n))
        return self

    def execute(self):
        self.calls.append(("execute",))
        return _FakeResult(self._data)


def _patch_client(monkeypatch, data) -> _FakeQuery:
    query = _FakeQuery(data)
    monkeypatch.setattr(
        supabase, "get_client", lambda: SimpleNamespace(table=lambda name: query)
    )
    return query


# --- get_parsed_submission ---------------------------------------------------


def test_get_parsed_submission_returns_row_when_found(monkeypatch):
    row = {"submission_id": "abc", "raw_text": "hello", "sections": []}
    query = _patch_client(monkeypatch, [row])

    result = supabase.get_parsed_submission("abc")

    assert result == row
    # Must be a bounded single-row fetch, never .single() (PGRST116 risk).
    assert ("limit", 1) in query.calls


def test_get_parsed_submission_returns_none_when_missing(monkeypatch):
    """Zero matching rows must return None — NOT raise APIError PGRST116."""
    _patch_client(monkeypatch, [])

    result = supabase.get_parsed_submission("does-not-exist")

    assert result is None


# --- v1.1.0 re-submission service layer ---------------------------------------


def test_list_submissions_filters_superseded_by_default(monkeypatch):
    """Default listing targets ACTIVE rows only (superseded_at is null)."""
    query = _patch_client(monkeypatch, [])

    supabase.list_submissions()

    assert ("is_", "superseded_at", "null") in query.calls


def test_list_submissions_include_superseded_skips_filter(monkeypatch):
    query = _patch_client(monkeypatch, [])

    supabase.list_submissions(include_superseded=True)

    assert ("is_", "superseded_at", "null") not in query.calls


def test_get_active_submission_by_team_returns_newest_row(monkeypatch):
    row = {"id": "abc", "team_name": "Team Alpha"}
    query = _patch_client(monkeypatch, [row])

    result = supabase.get_active_submission_by_team("Team Alpha")

    assert result == row
    assert ("ilike", "team_name", "Team Alpha") in query.calls
    assert ("is_", "superseded_at", "null") in query.calls
    assert ("order", "uploaded_at", True) in query.calls
    assert ("limit", 1) in query.calls


def test_get_active_submission_by_team_returns_none_when_missing(monkeypatch):
    _patch_client(monkeypatch, [])

    result = supabase.get_active_submission_by_team("Ghost Team")

    assert result is None


def test_get_active_submission_by_team_rejects_pattern_only_match(monkeypatch):
    """``ilike`` treats % and _ as patterns; the Python equality re-check
    must reject rows whose stored name is not literally equal modulo case,
    so a team named e.g. 'Team%' cannot hijack 'TeamX'."""
    row = {"id": "abc", "team_name": "TeamX"}
    _patch_client(monkeypatch, [row])

    # ilike('Team%') matches 'TeamX' as a pattern — guard must veto it.
    result = supabase.get_active_submission_by_team("Team%")

    assert result is None


def test_insert_submission_with_supersedes_archives_first(monkeypatch):
    row = {"id": "new-1", "team_name": "Team Alpha"}
    query = _patch_client(monkeypatch, [row])

    supabase.insert_submission("Team Alpha", "http://file", "pdf", supersedes_team=True)

    kinds = [call[0] for call in query.calls]
    assert kinds.index("update") < kinds.index("insert"), (
        "the archive stamp must happen BEFORE the fresh insert"
    )
    update_call = next(call for call in query.calls if call[0] == "update")
    assert set(update_call[1].keys()) == {"superseded_at"}
    assert ("ilike", "team_name", "Team Alpha") in query.calls
    assert ("is_", "superseded_at", "null") in query.calls


def test_insert_submission_without_supersedes_skips_archive(monkeypatch):
    row = {"id": "new-1", "team_name": "Fresh Team"}
    query = _patch_client(monkeypatch, [row])

    supabase.insert_submission("Fresh Team", "http://file", "pdf")

    assert "update" not in [call[0] for call in query.calls]
