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
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Split retrieval matches by role.

    Returns:
        - Matches the user may read (intersection of user groups with metadata ``allowed_groups``).
        - Sorted unique group names that *do* have access on chunks the user *cannot* read
          (so you can tell them who to contact).

    Permission source:
    - ``match["metadata"]["allowed_groups"]`` from Pinecone metadata (list of group name strings).
    """
    user_groups_set = {str(g) for g in user_groups if g is not None and str(g).strip()}
    filtered: list[dict[str, Any]] = []
    contact_groups: set[str] = set()

    for match in matches:
        metadata = match.get("metadata") or {}
        raw = metadata.get("allowed_groups", [])
        if not isinstance(raw, list):
            continue

        allowed_for_chunk = [str(g) for g in raw if g is not None and str(g).strip()]
        if not allowed_for_chunk:
            continue

        if user_groups_set.intersection(allowed_for_chunk):
            filtered.append(match)
        else:
            contact_groups.update(allowed_for_chunk)

    return filtered, sorted(contact_groups)
