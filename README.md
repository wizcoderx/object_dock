# Object Store Service (OSS)

A lightweight **FastAPI** microservice that accepts base64-encoded files, persists them on the local filesystem, and tracks metadata in **SQLite**.

---

## Project Structure

```
object_dock/
├── ObjectStoreAPI.py        # FastAPI application (endpoints)
├── setup.py                 # Package metadata & dependencies
├── README.md
├── data/
│   └── config.ini           # Storage-path configuration
├── services/
│   ├── __init__.py
│   └── helper.py            # DB, base64, extension-detection helpers
└── tests/
    └── test_oss.py           # Automated test suite
```

## Quick Start

### 1. Install dependencies

```bash
pip install -e .
```

### 2. Run the server

```bash
uvicorn ObjectStoreAPI:app --reload
```

The API docs are available at **http://127.0.0.1:8000/docs**.

### 3. Run tests

```bash
pytest tests/ -v
```

---

## Configuration

Edit `data/config.ini` to change where files are stored:

```ini
[storage]
oss_storage_path = oss_store
```

Relative paths are resolved from the project root.

---

## API Endpoints

### `POST /upload`

Upload a base64-encoded file.

**Request body (JSON):**

| Field         | Type   | Required | Description                              |
|---------------|--------|----------|------------------------------------------|
| `filename`    | string | ✅       | Original filename (e.g. `report.pdf`)    |
| `file_base64` | string | ✅       | Base64-encoded file content              |
| `context_key` | string | ❌       | Custom key; auto-generated UUID if omitted |

**Response:**

```json
{
  "file_name": "report.pdf",
  "context_key": "b4f7c2a1-...",
  "response_code": 200,
  "response_message": "File 'report.pdf' uploaded successfully (PK=1)."
}
```

### `GET /files/{context_key}`

Retrieve a file by its context key.

**Response:**

```json
{
  "context_key": "b4f7c2a1-...",
  "file_base64": "JVBERi0xLjQK...",
  "response_code": 200,
  "response_message": "File 'report.pdf' retrieved successfully."
}
```

---

## Extension Detection

The service detects file extensions in two stages:

1. **Primary** — `filetype` package inspects the file's magic bytes.
2. **Fallback** — regex extracts the extension from the provided filename (text after the last `.`).
3. **Default** — if both fail, `.bin` is used.
