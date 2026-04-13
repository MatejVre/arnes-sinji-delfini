from __future__ import annotations
import os
import threading

from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

DEFAULT_INDEX_NAME = "sinji-delfini-test"
TOP_K = 5
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _resolve_index_name() -> str:
    raw = (os.getenv("PINECONE_INDEX_NAME") or DEFAULT_INDEX_NAME).strip()
    return raw or DEFAULT_INDEX_NAME


def create_retrieval_resources() -> tuple[object, SentenceTransformer]:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("Missing PINECONE_API_KEY environment variable.")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(_resolve_index_name())
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return index, model


def find_suitable_documents(
    index: object,
    model: SentenceTransformer,
    query: str,
    encode_lock: threading.Lock | None = None,
):
    """encode_lock serializes embedding when the same model is shared across worker threads."""
    if encode_lock is not None:
        with encode_lock:
            vector = model.encode(query).tolist()
    else:
        vector = model.encode(query).tolist()
    return index.query(
        vector=vector,
        top_k=TOP_K,
        include_metadata=True,
    )

def normalize_retrieval_response(retrieval_response) -> dict:
    matches = []
    raw_matches = getattr(retrieval_response, "matches", None) or []

    for match in raw_matches:
        matches.append(
            {
                "id": getattr(match, "id", None),
                "score": getattr(match, "score", None),
                "metadata": getattr(match, "metadata", None) or {},
            }
        )

    return  matches
