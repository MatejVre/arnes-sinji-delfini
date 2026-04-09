import os

from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

INDEX_NAME = "sinji-delfini-test"
TOP_K = 5
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def create_retrieval_resources() -> tuple[object, SentenceTransformer]:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("Missing PINECONE_API_KEY environment variable.")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(INDEX_NAME)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return index, model


def find_suitable_documents(index: object, model: SentenceTransformer, query: str):

    return index.query(
        vector=model.encode(query).tolist(),
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
