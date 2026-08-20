"""Tests for the submission upload endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import supabase

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_supabase(monkeypatch):
    """Mock the Supabase service layer so tests never hit the network."""

    def fake_upload(file_bytes, file_name, file_type):
        return f"https://example.supabase.co/storage/v1/object/public/submissions/{file_name}"

    def fake_insert(team_name, file_url, file_type):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "team_name": team_name,
            "file_url": file_url,
            "file_type": file_type,
            "status": "submitted",
        }

    monkeypatch.setattr(supabase, "upload_submission_file", fake_upload)
    monkeypatch.setattr(supabase, "insert_submission", fake_insert)


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content"


def _pptx_bytes() -> bytes:
    return b"PK\x03\x04 fake pptx content"


def test_upload_pdf_success():
    """A valid PDF upload returns 201 and the stored row."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Alpha"},
        files={"file": ("proposal.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["team_name"] == "Team Alpha"
    assert body["file_type"] == "pdf"
    assert body["status"] == "submitted"
    assert body["file_url"].startswith("https://")


def test_upload_pptx_success():
    """A valid PPTX upload returns 201 and the stored row."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Beta"},
        files={"file": ("deck.pptx", _pptx_bytes(), "application/octet-stream")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["team_name"] == "Team Beta"
    assert body["file_type"] == "pptx"


def test_upload_rejects_unsupported_extension():
    """Uploading a .exe file is rejected with 400."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Gamma"},
        files={"file": ("malware.exe", b"MZ fake", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_upload_rejects_docx():
    """Uploading a .docx file is rejected with 400."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Delta"},
        files={"file": ("notes.docx", b"PK fake docx", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_rejects_empty_team_name():
    """A blank team name is rejected with 400."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "   "},
        files={"file": ("proposal.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Team name" in resp.json()["detail"]


def test_upload_rejects_empty_file():
    """An empty file is rejected with 400."""
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Epsilon"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_rejects_oversized_file(monkeypatch):
    """A file larger than MAX_UPLOAD_BYTES is rejected with 413."""
    from backend.routes import submissions as routes

    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 10)  # 10 bytes
    resp = client.post(
        "/api/submissions",
        data={"team_name": "Team Zeta"},
        files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_health():
    """The health endpoint returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
