# Arnes Sinji Delfini API

## 1) Create Environment

From project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]"
```

Create/update `.env` with at least:

```env
PINECONE_API_KEY=your_pinecone_api_key
JWT_SECRET=your_jwt_secret
JWT_EXPIRES_MINUTES=480
OPENAI_API_KEY=your_openai_api_key
# Optional: defaults to gpt-4o-mini
# OPENAI_CHAT_MODEL=gpt-4o-mini
```

## 2) Run API

```bash
uvicorn API.main:app --reload
```

Default local URL:

- `http://127.0.0.1:8000`

## 3) Setup Database (SQLite)

Call endpoints in this order:

1. Init schema

```bash
curl http://127.0.0.1:8000/schema/init
```

2. Seed data

```bash
curl http://127.0.0.1:8000/schema/seed
```

Seed creates demo users and groups (password `testing`), then dynamically seeds document/group permissions from:

- `data/documents/` for document files (`.txt`, `.csv`)
- `data/permissions.json` for per-document `allowed_groups`

Seeding behavior:

- If a file exists in `data/documents/` but is missing in `data/permissions.json`, it is skipped.
- If `data/permissions.json` references a file not present in `data/documents/` (for example `doc77.txt`), it is ignored.
- `/schema/seed` response includes this in `summary`:
  - `seeded_documents`
  - `seeded_groups_from_permissions`
  - `skipped_files_missing_permissions`
  - `ignored_permissions_missing_files`

## 4) Documents Upsert Flow (Pinecone)

Use this order when reindexing:

1. Clear index

```bash
curl -X POST http://127.0.0.1:8000/index/clear
```

2. Upsert all documents from DB metadata

```bash
curl http://127.0.0.1:8000/upsert/all
```

This reads documents from `data/documents/`, permissions from SQLite tables, and writes vectors to Pinecone.

## 5) Swagger UI

When API is running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
