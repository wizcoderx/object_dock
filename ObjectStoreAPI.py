"""
ObjectStoreAPI.py
~~~~~~~~~~~~~~~~~
Main FastAPI application for the Object Store Service (OSS).

Endpoints
---------
POST /upload              — Accept a base64-encoded file, store it on disk,
                            and track it in SQLite.
POST /upload-from-path    — Accept a local file path, read & store the file,
                            and track it in SQLite.
GET  /files/{context_key} — Retrieve a stored file as a base64 string.

Run with:
    uvicorn ObjectStoreAPI:app --reload
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from services.helper import (
    decode_base64,
    detect_extension,
    encode_base64,
    generate_context_key,
    get_file_record_by_context_key,
    init_db,
    insert_file_record,
    load_storage_path,
    read_file_from_path,
)

# ---------------------------------------------------------------------------
# App & startup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Object Store Service",
    description="Accepts base64-encoded files, persists them on the local "
                "filesystem, and tracks metadata in SQLite.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    """Ensure the database table and storage directory exist."""
    init_db()
    load_storage_path()  # creates the directory as a side-effect


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class UploadRequest(BaseModel):
    filename: str
    file_base64: str
    context_key: Optional[str] = None


class UploadFromPathRequest(BaseModel):
    file_path: str
    context_key: Optional[str] = None


class UploadResponse(BaseModel):
    file_name: str
    context_key: str
    response_code: int
    response_message: str


class FileRetrieveResponse(BaseModel):
    context_key: str
    file_base64: str
    response_code: int
    response_message: str


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=UploadResponse)
def upload_file(payload: UploadRequest) -> UploadResponse:
    """
    Accept a base64-encoded file, persist it to disk, and track it in the DB.

    Steps
    -----
    1. Generate a ``context_key`` if one was not supplied.
    2. Decode the base64 payload to raw bytes.
    3. Detect the file extension (filetype → regex fallback).
    4. Insert a DB record to obtain the auto-incremented PK.
    5. Create ``<storage_path>/<PK>/`` and write the file there.
    """
    # 1 — context key
    ctx_key = payload.context_key or generate_context_key()

    # 2 — decode
    try:
        raw_bytes = decode_base64(payload.file_base64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid base64 data: {exc}",
        )

    # 3 — extension
    extension = detect_extension(raw_bytes, payload.filename)

    # 4 — database record
    try:
        pk = insert_file_record(
            filename=payload.filename,
            context_key=ctx_key,
            file_extension=extension,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"A file with context_key '{ctx_key}' already exists. Details: {exc}",
        )

    # 5 — filesystem storage
    storage = load_storage_path()
    folder = storage / str(pk)
    folder.mkdir(parents=True, exist_ok=True)

    file_path = folder / payload.filename
    file_path.write_bytes(raw_bytes)

    return UploadResponse(
        file_name=payload.filename,
        context_key=ctx_key,
        response_code=200,
        response_message=f"File '{payload.filename}' uploaded successfully (PK={pk}).",
    )


# ---------------------------------------------------------------------------
# POST /upload-from-path
# ---------------------------------------------------------------------------

@app.post("/upload-from-path", response_model=UploadResponse)
def upload_file_from_path(payload: UploadFromPathRequest) -> UploadResponse:
    """
    Read a file from a local filesystem path, persist it to the OSS store,
    and track it in the DB.  Follows the same storage logic as ``/upload``.

    Steps
    -----
    1. Read the file from the supplied ``file_path``.
    2. Generate a ``context_key`` if one was not supplied.
    3. Detect the file extension (filetype → regex fallback).
    4. Insert a DB record to obtain the auto-incremented PK.
    5. Create ``<storage_path>/<PK>/`` and write the file there.
    """
    # 1 — read file from local path
    try:
        raw_bytes, filename = read_file_from_path(payload.file_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read file: {exc}",
        )

    # 2 — context key
    ctx_key = payload.context_key or generate_context_key()

    # 3 — extension
    extension = detect_extension(raw_bytes, filename)

    # 4 — database record
    try:
        pk = insert_file_record(
            filename=filename,
            context_key=ctx_key,
            file_extension=extension,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"A file with context_key '{ctx_key}' already exists. Details: {exc}",
        )

    # 5 — filesystem storage
    storage = load_storage_path()
    folder = storage / str(pk)
    folder.mkdir(parents=True, exist_ok=True)

    dest_path = folder / filename
    dest_path.write_bytes(raw_bytes)

    return UploadResponse(
        file_name=filename,
        context_key=ctx_key,
        response_code=200,
        response_message=f"File '{filename}' uploaded from path successfully (PK={pk}).",
    )


# ---------------------------------------------------------------------------
# GET /files/{context_key}
# ---------------------------------------------------------------------------

@app.get("/files/{context_key}", response_model=FileRetrieveResponse)
def get_file(context_key: str) -> FileRetrieveResponse:
    """
    Retrieve a stored file by its ``context_key`` and return it as base64.

    Steps
    -----
    1. Look up the record by ``context_key``.
    2. Resolve the on-disk path via ``<storage_path>/<PK>/<filename>``.
    3. Read the file and encode it to base64.
    """
    record = get_file_record_by_context_key(context_key)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No file found for context_key '{context_key}'.",
        )

    pk = record["id"]
    filename = record["filename"]

    storage = load_storage_path()
    file_path = storage / str(pk) / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found on disk at expected path.",
        )

    raw_bytes = file_path.read_bytes()
    b64 = encode_base64(raw_bytes)

    return FileRetrieveResponse(
        context_key=context_key,
        file_base64=b64,
        response_code=200,
        response_message=f"File '{filename}' retrieved successfully.",
    )
