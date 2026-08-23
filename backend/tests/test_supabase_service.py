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
