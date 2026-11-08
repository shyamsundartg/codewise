"""Reciprocal Rank Fusion: merge ranked lists without calibrating their scores.

BM25 scores and cosine similarities live on different scales; RRF only
uses ranks, so it needs no tuning. k=60 is the value from the original
paper (Cormack et al., 2009).
"""

from collections import defaultdict


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
