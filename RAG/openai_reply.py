"""
Turn RAG chunks already filtered by user role into AI answer via OpenAI.
*there chzange will be make, so it will also be able to tell who to contact
Flow:
1. `/chat` loads `allowed_matches` from Pinecone + permission filters
2. We build one user message: labeled CONTEXT chunks + QUESTION.
3. The system prompt instructs the model to use only that context and not invent facts.

"""

from __future__ import annotations

import os
from typing import Any

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError


def _context_block_from_matches(allowed_matches: list[dict[str, Any]]) -> str:
    """Join chunk texts into a single string the model can read."""
    parts: list[str] = []
    for i, match in enumerate(allowed_matches, start=1):
        meta = match.get("metadata") or {}
        raw = meta.get("text")
        text = raw.strip() if isinstance(raw, str) else (str(raw) if raw is not None else "")
        if not text:
            continue
        parts.append(f"[Izvlek {i}]\n{text}")
    if not parts:
        return "(Za to vprašanje ni na voljo izvlekov dokumentov z vašim dostopom.)"
    return "\n\n".join(parts)


async def generate_rag_reply(user_question: str, allowed_matches: list[dict[str, Any]]) -> str:
    """
    Call OpenAI Chat Completions with the user question and role-filtered chunks only.

    Raises:
        ValueError: missing API key
        APIStatusError, RateLimitError, APIConnectionError: from the SDK (caller maps to HTTP)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise ValueError("OPENAI_API_KEY is not set in the environment.")

    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    context_block = _context_block_from_matches(allowed_matches)

    client = AsyncOpenAI(api_key=api_key)
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Si pomočnik v sistemu z vlogo omejenim dostopom do dokumentov. "
                    "Odgovarjaj izključno na podlagi spodnjega KONTEKSTA. "
                    "Če je kontekst prazen ali ne zadošča, to jasno povej; ne ugibaj in ne uporabljaj znanja izven konteksta. "
                    "Odgovarjaj vedno v slovenščini, razen če uporabnik izrecno prosi za drug jezik. "
                    "Bodi jedrnat."
                ),
            },
            {
                "role": "user",
                "content": f"KONTEKST:\n{context_block}\n\nVPRAŠANJE:\n{user_question.strip()}",
            },
        ],
        temperature=0.2,
        max_tokens=1024,
    )

    message = completion.choices[0].message
    content = message.content if message else None
    return (content or "").strip()


__all__ = ["generate_rag_reply"]
