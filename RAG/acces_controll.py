from __future__ import annotations

from typing import Any, Iterable


def adaptive_threshold_filter(
    matches: Iterable[dict[str, Any]],
    *,
    min_score: float = 0.35,
    max_gap_from_best: float = 0.12,
) -> list[dict[str, Any]]:
    """
    Keep only retrieval matches that are relevant enough.

    The threshold adapts to query quality:
    - Start from the best score in the batch.
    - Accept items up to `max_gap_from_best` below the best one.
    - Never go below `min_score`.
    """
    match_list = [m for m in matches if m.get("score") is not None]
    if not match_list:
        return []

    best_score = max(float(m["score"]) for m in match_list)
    threshold = max(min_score, best_score - max_gap_from_best)

    return [m for m in match_list if float(m["score"]) >= threshold]


def filter_documents_by_permissions(
    matches: Iterable[dict[str, Any]],
    user_groups: Iterable[str],
    *,
    permissions_by_document: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Keep only matches user is allowed to read.

    Permission source priority:
    1. `permissions_by_document[document_name]` if provided
    2. `match["metadata"]["dovoljene skupine"]` from Pinecone metadata
    """
    user_groups_set = set(user_groups)
    filtered: list[dict[str, Any]] = []

    for match in matches:
        metadata = match.get("metadata") or {}
        document_name = _extract_document_name(match.get("id"))

        allowed_groups = None
        if permissions_by_document and document_name:
            allowed_groups = permissions_by_document.get(document_name)

        if allowed_groups is None:
            allowed_groups = metadata.get("dovoljene skupine", [])

        if not isinstance(allowed_groups, list):
            continue

        if user_groups_set.intersection(allowed_groups):
            filtered.append(match)

    return filtered


def _extract_document_name(match_id: str | None) -> str | None:
    if not match_id:
        return None

    # IDs are inserted as: "<dokument>-chunk-<i>"
    marker = "-chunk-"
    if marker in match_id:
        return match_id.split(marker, 1)[0]
    return match_id
