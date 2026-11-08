"""Hybrid retrieval: vector + BM25 + exact symbol match, fused with RRF.

Why three signals?
* vectors   -> vague, conceptual questions ("how is auth handled?")
* BM25      -> exact words/identifiers that embeddings blur ("refresh_token")
* symbols   -> a question naming a function should surface its definition first
"""

from dataclasses import dataclass, field
import re

import numpy as np

from app.models import Chunk
from app.retrieval.fusion import rrf
from app.retrieval.store import LoadedRepo
from app.retrieval.tokenize import tokenize

CHARS_PER_TOKEN = 4  # rough estimate; good enough for budgeting


@dataclass
class Hit:
    chunk: Chunk
    score: float
    signals: dict[str, int] = field(default_factory=dict)  # signal -> rank (1-based)


_DEFINES = re.compile(r"^\s*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)", re.M)


def _symbol_matches(repo: LoadedRepo, question: str) -> list[str]:
    """Chunks that *define* a name mentioned in the question (e.g. a method
    inside a class chunk), ordered by how many mentioned names they define."""
    q_names = {w.lower() for w in re.findall(r"[A-Za-z_]\w{2,}", question)}
    scored = []
    for c in repo.index.chunks:
        defined = {n.lower() for n in _DEFINES.findall(c.text)}
        if c.symbol:
            defined.add(c.symbol.split(" ")[0].split(".")[-1].lower())
        overlap = len(defined & q_names)
        if overlap:
            scored.append((overlap, c.id))
    return [cid for _, cid in sorted(scored, key=lambda x: -x[0])]


ALL_SIGNALS = frozenset({"vector", "keyword", "symbol"})


def search(repo: LoadedRepo, question: str, query_vec: np.ndarray, candidate_k: int,
           use: frozenset[str] = ALL_SIGNALS) -> list[Hit]:
    """``use`` lets the eval switch signals off to measure what each one adds."""
    chunks = repo.index.chunks
    if not chunks:
        return []
    ids = [c.id for c in chunks]
    signals: dict[str, list[str]] = {}

    if "vector" in use:
        vec_scores = repo.embeddings @ query_vec
        signals["vector"] = [ids[i] for i in np.argsort(-vec_scores)[:candidate_k]]
    if "keyword" in use:
        bm25_scores = repo.bm25.get_scores(tokenize(question) or ["_empty_"])
        signals["keyword"] = [ids[i] for i in np.argsort(-bm25_scores)[:candidate_k] if bm25_scores[i] > 0]
    if "symbol" in use:
        signals["symbol"] = _symbol_matches(repo, question)
    fused = rrf([r for r in signals.values() if r])
    hits = []
    for cid, score in fused[:candidate_k]:
        ranks = {name: r.index(cid) + 1 for name, r in signals.items() if cid in r}
        hits.append(Hit(repo.chunk_by_id[cid], round(score, 5), ranks))
    return hits


def _overlaps(a: Chunk, b: Chunk) -> bool:
    return a.path == b.path and a.start_line <= b.end_line and b.start_line <= a.end_line


def pack_context(hits: list[Hit], top_k: int, token_budget: int) -> list[Hit]:
    """Pick the best hits that fit the token budget, skipping overlapping chunks."""
    chosen: list[Hit] = []
    used = 0
    for hit in hits:
        if len(chosen) >= top_k:
            break
        if any(_overlaps(hit.chunk, c.chunk) for c in chosen):
            continue
        cost = len(hit.chunk.text) // CHARS_PER_TOKEN + 30
        if used + cost > token_budget:
            continue
        chosen.append(hit)
        used += cost
    return chosen


def search_query(question: str, history: list[dict] | None) -> str:
    """Short follow-ups ("and where is it called?") lack context on their own,
    so we prepend the previous user question to the retrieval query."""
    if history and len(question.split()) < 8:
        prev = [h["content"] for h in history if h["role"] == "user"]
        if prev:
            return f"{prev[-1]} {question}"
    return question
