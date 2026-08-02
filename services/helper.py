"""
services/helper.py
~~~~~~~~~~~~~~~~~~~
Utility functions for the Object Store Service:
  - Configuration parsing   (config.ini → storage path)
  - SQLite database setup    (table creation, CRUD)
  - Base64 decoding/encoding
  - File-extension detection (filetype package + regex fallback)
"""

import base64
import configparser
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Tuple

import filetype


# ---------------------------------------------------------------------------
# Paths — resolved relative to the *project root* (one level above services/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "data" / "config.ini"
_DB_PATH = _PROJECT_ROOT / "data" / "oss_tracker.db"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_storage_path() -> Path:
    """Read `oss_storage_path` from data/config.ini and return it as a
    resolved :class:`Path`.  Relative paths are resolved against the
    project root.
    """
    cfg = configparser.ConfigParser()
    cfg.read(str(_CONFIG_PATH))
    raw = cfg.get("storage", "oss_storage_path", fallback="oss_store")
    storage = Path(raw)
    if not storage.is_absolute():
        storage = _PROJECT_ROOT / storage
    storage.mkdir(parents=True, exist_ok=True)
    return storage


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection (creates the DB file if needed)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the `files` table if it does not already exist."""
    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                filename       TEXT    NOT NULL,
                context_key    TEXT    NOT NULL UNIQUE,
                file_extension TEXT    NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_file_record(
    filename: str,
    context_key: str,
    file_extension: str,
) -> int:
    """Insert a new record and return the auto-generated Primary Key."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO files (filename, context_key, file_extension) VALUES (?, ?, ?)",
            (filename, context_key, file_extension),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def get_file_record_by_context_key(context_key: str) -> Optional[sqlite3.Row]:
    """Look up a file record by its context_key.  Returns ``None`` if not
    found.
    """
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT id, filename, context_key, file_extension FROM files WHERE context_key = ?",
            (context_key,),
        ).fetchone()
        return row
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Base64 helpers
# ---------------------------------------------------------------------------

def decode_base64(data: str) -> bytes:
    """Decode a base64-encoded string to raw bytes."""
    return base64.b64decode(data)


def encode_base64(raw: bytes) -> str:
    """Encode raw bytes to a base64 string."""
    return base64.b64encode(raw).decode("utf-8")


# ---------------------------------------------------------------------------
# File-extension detection
# ---------------------------------------------------------------------------

def detect_extension(raw_bytes: bytes, filename: str) -> str:
    """Determine the file extension.

    Strategy
    --------
    1. Use the ``filetype`` package to sniff the magic bytes.
    2. **Fallback**: extract the extension from *filename* (text after the
       last dot) using a regex.
    3. If neither method succeeds, default to ``"bin"``.

    Returns the extension **without** a leading dot (e.g. ``"png"``).
    """
    # --- primary: magic-byte detection ---
    kind = filetype.guess(raw_bytes)
    if kind is not None:
        return kind.extension  # e.g. "png", "pdf", "zip"

    # --- fallback: regex on the filename ---
    match = re.search(r"\.([a-zA-Z0-9]+)$", filename)
    if match:
        return match.group(1).lower()

    # --- last resort ---
    return "bin"


# ---------------------------------------------------------------------------
# Context-key generation
# ---------------------------------------------------------------------------

def generate_context_key() -> str:
    """Return a new UUID4 string to use as a context key."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def read_file_from_path(file_path: str) -> tuple[bytes, str]:
    """Read a file from a local filesystem path.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the file on disk.

    Returns
    -------
    tuple[bytes, str]
        A tuple of (raw_bytes, filename) where *filename* is the basename
        of the supplied path.

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    IsADirectoryError
        If the path points to a directory instead of a file.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {file_path}")
    if p.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")
    return p.read_bytes(), p.name

