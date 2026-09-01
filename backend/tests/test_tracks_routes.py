"""Tests for track management API routes (v3.1.0)."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import supabase

client = TestClient(app)


class FakeTrackStore:
    """In-memory stand-in for track data in Supabase."""

    def __init__(self):
        self.tracks = [
            {"id": "default", "name": "Default track", "description": "Built-in track", "created_at": "2026-09-01T00:00:00Z"}
        ]
        self.submissions: list[dict] = []
        self.rubrics: dict[tuple[str, str], float] = {}

    def list_tracks(self):
        return list(self.tracks)

    def get_track(self, track_id: str):
        return next((t for t in self.tracks if t["id"] == track_id), None)

    def create_track(self, track_id: str, name: str, description: str | None = None):
        row = {
            "id": track_id,
            "name": name,
            "description": description,
            "created_at": "2026-09-01T00:00:00Z",
        }
        self.tracks.append(row)
        return dict(row)

    def delete_track(self, track_id: str):
        prev_len = len(self.tracks)
        self.tracks = [t for t in self.tracks if t["id"] != track_id]
        return len(self.tracks) < prev_len

    def get_all_submissions(self, hackathon_id: str = "default"):
        return [s for s in self.submissions if s.get("hackathon_id", "default") == hackathon_id]

    def upsert_rubric(self, hackathon_id: str, weights: dict[str, float]):
        for c, w in weights.items():
            self.rubrics[(hackathon_id, c)] = w
        return weights


@pytest.fixture
def store(monkeypatch):
    fake = FakeTrackStore()
    monkeypatch.setattr(supabase, "list_tracks", fake.list_tracks)
    monkeypatch.setattr(supabase, "get_track", fake.get_track)
    monkeypatch.setattr(supabase, "create_track", fake.create_track)
    monkeypatch.setattr(supabase, "delete_track", fake.delete_track)
    monkeypatch.setattr(supabase, "get_all_submissions", fake.get_all_submissions)
    monkeypatch.setattr(supabase, "upsert_rubric", fake.upsert_rubric)
    return fake


def test_list_tracks(store):
    resp = client.get("/api/tracks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tracks"]) == 1
    assert body["tracks"][0]["id"] == "default"


def test_create_track_success(store):
    resp = client.post(
        "/api/tracks",
        json={"id": "sih-2026", "name": "Smart India Hackathon", "description": "Hardware and software"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["track"]["id"] == "sih-2026"
    assert len(store.tracks) == 2


def test_create_track_duplicate_rejected(store):
    resp = client.post(
        "/api/tracks",
        json={"id": "default", "name": "Duplicate Track"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_create_track_invalid_id(store):
    resp = client.post(
        "/api/tracks",
        json={"id": "invalid id with spaces!", "name": "Test Track"},
    )
    assert resp.status_code == 422


def test_delete_track_success(store):
    store.create_track("temp-track", "Temp Track")
    resp = client.delete("/api/tracks/temp-track")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "id": "temp-track"}


def test_delete_track_with_submissions_rejected(store):
    store.create_track("active-track", "Active Track")
    store.submissions.append({"id": "sub-1", "hackathon_id": "active-track"})
    resp = client.delete("/api/tracks/active-track")
    assert resp.status_code == 409
    assert "submission(s) exist" in resp.json()["detail"]


def test_delete_nonexistent_track(store):
    resp = client.delete("/api/tracks/nonexistent")
    assert resp.status_code == 404
