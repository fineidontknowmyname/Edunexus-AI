from __future__ import annotations

import math
from collections import defaultdict
from typing import Sequence

SIMILARITY_THRESHOLD = 0.30
MARGIN = 0.03


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _mean_pool(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    return [x / len(vectors) for x in acc]


def assign_topics(
    chunk_meta: list[dict],
    chunk_vectors: list[list[float]],
    topic_names: list[str],
    topic_vectors: list[list[float]],
) -> dict[int, str | None]:
    if not topic_names:
        return {i: None for i in range(len(chunk_meta))}

    sections: dict[tuple, list[int]] = defaultdict(list)
    for i, meta in enumerate(chunk_meta):
        key = (meta.get("unit"), meta.get("chapter"), meta.get("chapter_name") or "")
        sections[key].append(i)

    result: dict[int, str | None] = {}
    for key, idxs in sections.items():
        pooled = _mean_pool([chunk_vectors[i] for i in idxs])
        sims = sorted(
            ((_cosine(pooled, tv), name) for name, tv in zip(topic_names, topic_vectors)),
            reverse=True,
        )
        best_sim, best_topic = sims[0]
        runner_up = sims[1][0] if len(sims) > 1 else 0.0
        assigned = (
            best_topic
            if best_sim >= SIMILARITY_THRESHOLD and (best_sim - runner_up) >= MARGIN
            else None
        )
        print(
            f"[CLASSIFY] section {key} -> {assigned!r} "
            f"(best={best_sim:.3f} '{best_topic}', next={runner_up:.3f})"
        )
        for i in idxs:
            result[i] = assigned
    return result
