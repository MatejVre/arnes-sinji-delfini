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
) -> list[dict[str, Any]]:
    """
    Keep only matches user is allowed to read.

    Permission source:
    - `match["metadata"]["allowed_groups"]` from Pinecone metadata
    """
    user_groups_set = set(user_groups)
    filtered: list[dict[str, Any]] = []

    for match in matches:
        metadata = match.get("metadata") or {}
        allowed_groups = metadata.get("allowed_groups", [])

        if not isinstance(allowed_groups, list):
            continue

        if user_groups_set.intersection(allowed_groups):
            filtered.append(match)

    return filtered
