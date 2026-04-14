import csv
import os
from pathlib import Path
from typing import Any

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

from DB.db import Db

DEFAULT_INDEX_NAME = "sinji-delfini-test"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _resolve_index_name() -> str:
    raw = (os.getenv("PINECONE_INDEX_NAME") or DEFAULT_INDEX_NAME).strip()
    return raw or DEFAULT_INDEX_NAME
VECTOR_DIMENSION = 384
VECTOR_METRIC = "cosine"
VECTOR_CLOUD = "aws"
VECTOR_REGION = "us-east-1"

CHUNK_SIZE = 200
CHUNK_OVERLAP = 20
ROWS_PER_CHUNK = 2

BASE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOCUMENTS_DIR = os.path.join(BASE_DIRECTORY, "../data/documents")


def create_upsert_resources() -> tuple[object, SentenceTransformer]:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("Missing PINECONE_API_KEY environment variable.")

    pc = Pinecone(api_key=api_key)
    index_name = _resolve_index_name()
    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            vector_type="dense",
            dimension=VECTOR_DIMENSION,
            metric=VECTOR_METRIC,
            spec=ServerlessSpec(
                cloud=VECTOR_CLOUD,
                region=VECTOR_REGION,
            ),
            deletion_protection="disabled",
            tags={"environment": "development"},
        )

    index = pc.Index(index_name)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return index, model


def upsert_all_documents_from_db(
    db: Db,
    index: object,
    model: SentenceTransformer,
    documents_dir: str = DEFAULT_DOCUMENTS_DIR,
) -> dict[str, Any]:
    documents = db.fetch_documents_with_groups()
    summary: dict[str, Any] = {
        "processed_documents": len(documents),
        "upserted_documents": 0,
        "upserted_vectors": 0,
        "skipped_files": [],
        "documents": [],
    }

    docs_path = Path(documents_dir)

    for document in documents:
        document_id = document["document_id"]
        document_name = document["document_name"]
        allowed_groups = document["allowed_groups"]
        file_path = docs_path / document_name

        if not file_path.exists():
            summary["skipped_files"].append(document_name)
            summary["documents"].append(
                {
                    "document_id": document_id,
                    "document_name": document_name,
                    "status": "skipped_missing_file",
                    "allowed_groups": allowed_groups,
                }
            )
            continue

        text = _read_document(str(file_path))
        chunks = _chunk_text(document_name, text)
        if not chunks:
            summary["documents"].append(
                {
                    "document_id": document_id,
                    "document_name": document_name,
                    "status": "skipped_empty_document",
                    "allowed_groups": allowed_groups,
                }
            )
            continue

        embeddings = [model.encode(chunk).tolist() for chunk in chunks]
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            vectors.append(
                {
                    "id": f"{document_name}-chunk-{i}",
                    "values": embedding,
                    "metadata": {
                        "text": chunk,
                        "document_id": document_id,
                        "document_name": document_name,
                        "allowed_groups": allowed_groups,
                    },
                }
            )

        index.upsert(vectors=vectors)
        summary["upserted_documents"] += 1
        summary["upserted_vectors"] += len(vectors)
        summary["documents"].append(
            {
                "document_id": document_id,
                "document_name": document_name,
                "status": "upserted",
                "allowed_groups": allowed_groups,
                "chunks": len(chunks),
                "vectors_upserted": len(vectors),
            }
        )

    return summary
def _read_document(filepath: str) -> str:
    if filepath.endswith(".csv"):
        rows = []
        with open(filepath, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                rows.append(", ".join(f"{k}: {v}" for k, v in row.items()))
        return "\n".join(rows)

    with open(filepath, "r", encoding="utf-8") as file:
        return file.read()


def _chunk_text(
    document_name: str,
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    rows_per_chunk: int = ROWS_PER_CHUNK,
) -> list[str]:
    if document_name.endswith(".csv"):
        rows = [row for row in text.split("\n") if row.strip()]
        return ["\n".join(rows[i : i + rows_per_chunk]) for i in range(0, len(rows), rows_per_chunk)]

    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + chunk_size]))
        i += chunk_size - overlap
    return chunks
