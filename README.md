# Arnes Sinji Delfini API

## 1) Create Environment

From project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create/update `.env` with at least:

```env
PINECONE_API_KEY=your_pinecone_api_key
JWT_SECRET=your_jwt_secret
JWT_EXPIRES_MINUTES=480
USE_LOCAL_LLM=1
LLM_BASE_MODEL_ID=cjvt/GaMS3-12B-Instruct
LLM_USE_4BIT=1
LLM_ENABLE_CPU_OFFLOAD=1
LLM_DEVICE_MAP=auto
```

## LLM Mode Selection

`/chat` can run in 2 modes:

- Local model mode (`USE_LOCAL_LLM=1`)
- Hosted API mode (`USE_LOCAL_LLM=0`)

OpenAI and Gemini are different native APIs, but this project uses one internal adapter so `/chat` input/output stays the same.

### Local mode example

```env
USE_LOCAL_LLM=1
LLM_BASE_MODEL_ID=cjvt/GaMS3-12B-Instruct
LLM_USE_4BIT=1
LLM_ENABLE_CPU_OFFLOAD=1
LLM_DEVICE_MAP=auto
```

### OpenAI mode example

```env
USE_LOCAL_LLM=0
LLM_API_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1-mini
# optional:
# OPENAI_BASE_URL=https://api.openai.com/v1
```

### Gemini mode example

```env
USE_LOCAL_LLM=0
LLM_API_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash
# optional (OpenAI-compatible Gemini endpoint):
# GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

When `USE_LOCAL_LLM=0`, missing provider/model env values cause startup errors.
If provider calls fail during `/chat`, the API returns `502 Bad Gateway` (no automatic fallback to local model).

`LLM_USE_4BIT` controls model quantization:

- `1` (default): enable 4-bit quantization (GPU/CUDA required)
- `0`: disable quantization

`LLM_ENABLE_CPU_OFFLOAD` controls whether quantized loading may offload some layers to CPU/disk:

- `1` (default): allow offload (more stable on limited VRAM, can be slower)
- `0`: disable offload (requires enough GPU VRAM)

`LLM_DEVICE_MAP` controls model placement strategy used by Transformers:

- `auto` (default): automatic placement
- `cpu`: force CPU
- `cuda` (or other valid device string): force a specific GPU

`LLM_BASE_MODEL_ID` controls which base model is loaded. The loader uses the model basename
(for example `GaMS3-12B-Instruct`) for local cache and finetuning folder matching.

### 4-bit Troubleshooting

If you see an error like:

`Params4bit.__new__() got an unexpected keyword argument '_is_hf_initialized'`

it means your quantization dependency versions are mismatched. This project pins compatible versions in `requirements.txt`.

Fix:

```bash
pip install -r requirements.txt --upgrade
```

At runtime, if this compatibility error still appears, loader will automatically retry once without 4-bit quantization so API startup can continue.

## 2) LLM Folder Setup

Before running the API, create this structure for optional finetuned adapters:

```text
LLM/
  finetuning/
    <model_basename>/
```

Example:

```text
LLM/finetuning/GaMS3-12B-Instruct/
```

Required files inside each model folder:

- `adapter_config.json`
- `adapter_model.safetensors`
- `tokenizer.json`
- `tokenizer_config.json`

Optional but recommended:

- `chat_template.jinja`

Notes:

- Base model is downloaded on first run and cached locally in `LLM/models/<model_basename>/`.
- If `LLM/finetuning/<model_basename>/` exists with required files, loader uses base model + qLoRA adapter.
- If finetuning folder is missing/incomplete, loader falls back to base model only (startup still succeeds).
- Subsequent runs load model from local files.

## 3) Run API

```bash
uvicorn API.main:app --reload
```

Default local URL:

- `http://127.0.0.1:8000`

## 4) Setup Database (SQLite)

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

Seeded data overview:

| Source | Table(s) | Seeded data |
|---|---|---|
| `DB/seed.sql` | `users` | `šef`, `finance`, `HR` (all with password `testing`) |
| `DB/seed.sql` | `groups` | `finance`, `HR`, `CEO` |
| `DB/seed.sql` | `user_group` | `šef -> finance, HR, CEO`; `finance -> finance`; `HR -> HR` |
| `DB/seed.sql` | `documents` | Base demo docs: `doc1.txt` ... `doc6.txt`, `stroski_2023.csv` |
| `DB/seed.sql` | `document_group` | Base links: `doc1->finance`, `doc2->HR`, `doc3->finance`, `doc4->CEO`, `doc5->finance`, `doc6->CEO`, `stroski_2023.csv->finance` |
| Dynamic (`Db._seed_documents_from_data`) | `documents`, `groups`, `document_group` | Reads `data/documents/` + `data/permissions.json`, inserts missing docs/groups, and links docs to `allowed_groups` |

Notes:

- SQL seed uses `INSERT OR IGNORE`, so repeated seed runs are idempotent.
- Dynamic seeding can add new documents/groups beyond the base demo rows from `seed.sql`.

## 5) Documents Upsert Flow (Pinecone)

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

## 6) Swagger UI

When API is running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
