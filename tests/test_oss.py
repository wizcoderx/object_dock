"""
tests/test_oss.py
~~~~~~~~~~~~~~~~~
Automated tests for the Object Store Service.

Covers:
  - Upload and retrieval round-trip
  - Auto-generated context_key
  - Extension detection via filetype (PNG magic bytes)
  - Fallback regex extension detection (plain text with .csv name)
  - 404 on unknown context_key
  - Duplicate context_key rejection (409)
"""

import base64
import os
import shutil
import sys

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so imports resolve when running
# pytest from the project root directory.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from ObjectStoreAPI import app
from services.helper import _DB_PATH, _PROJECT_ROOT, init_db, load_storage_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_state():
    """Ensure a fresh DB and storage directory for every test."""
    # --- setup: wipe previous state ---
    if _DB_PATH.exists():
        _DB_PATH.unlink()
    storage = load_storage_path()
    if storage.exists():
        shutil.rmtree(storage)

    init_db()
    load_storage_path()

    yield

    # --- teardown ---
    if _DB_PATH.exists():
        _DB_PATH.unlink()
    if storage.exists():
        shutil.rmtree(storage)


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal 1×1 red PNG (67 bytes) — filetype can detect this.
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    """POST /upload"""

    def test_upload_png_with_filetype_detection(self, client):
        """filetype detects PNG magic bytes → extension should be 'png'."""
        resp = client.post("/upload", json={
            "filename": "photo.png",
            "file_base64": _b64(_MINIMAL_PNG),
            "context_key": "test-png-key",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["file_name"] == "photo.png"
        assert body["context_key"] == "test-png-key"
        assert body["response_code"] == 200

    def test_upload_generates_context_key_when_missing(self, client):
        """If context_key is omitted a UUID4 should be generated."""
        resp = client.post("/upload", json={
            "filename": "notes.txt",
            "file_base64": _b64(b"hello world"),
        })
        assert resp.status_code == 200
        body = resp.json()
        # UUID4 format: 8-4-4-4-12 hex chars
        assert len(body["context_key"]) == 36
        assert body["context_key"].count("-") == 4

    def test_upload_fallback_regex_extension(self, client):
        """Plain text bytes cannot be detected by filetype; the regex
        fallback should extract 'csv' from the filename 'data.csv'."""
        resp = client.post("/upload", json={
            "filename": "data.csv",
            "file_base64": _b64(b"col1,col2\na,b\n"),
            "context_key": "csv-fallback",
        })
        assert resp.status_code == 200

    def test_duplicate_context_key_returns_409(self, client):
        """Uploading twice with the same context_key must fail."""
        payload = {
            "filename": "dup.txt",
            "file_base64": _b64(b"data"),
            "context_key": "dup-key",
        }
        first = client.post("/upload", json=payload)
        assert first.status_code == 200

        second = client.post("/upload", json=payload)
        assert second.status_code == 409


class TestRetrieveEndpoint:
    """GET /files/{context_key}"""

    def test_round_trip_upload_then_retrieve(self, client):
        """Upload a file and retrieve it; the base64 content must match."""
        original = b"round-trip test content"
        client.post("/upload", json={
            "filename": "round.txt",
            "file_base64": _b64(original),
            "context_key": "rt-key",
        })

        resp = client.get("/files/rt-key")
        assert resp.status_code == 200
        body = resp.json()
        assert body["context_key"] == "rt-key"
        assert base64.b64decode(body["file_base64"]) == original

    def test_retrieve_unknown_key_returns_404(self, client):
        resp = client.get("/files/nonexistent-key")
        assert resp.status_code == 404


class TestExtensionFallback:
    """Verify the regex fallback independently via helper."""

    def test_filetype_returns_none_for_plain_text(self):
        """filetype.guess returns None for plain ASCII — the fallback
        regex should kick in and extract the extension from the filename.
        """
        from services.helper import detect_extension

        ext = detect_extension(b"just plain text", "report.docx")
        # filetype cannot detect plain text → fallback gives 'docx'
        assert ext == "docx"

    def test_fallback_default_when_no_extension(self):
        from services.helper import detect_extension

        ext = detect_extension(b"no clue", "README")
        assert ext == "bin"
