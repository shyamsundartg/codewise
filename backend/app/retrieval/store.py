"""Persistence for indexed repos: JSON metadata + a NumPy matrix of embeddings.

Why not a vector database? A repo is a few thousand chunks; brute-force
cosine similarity over that is ~1 ms in NumPy. A file-based store keeps
the app to one container. The ``RepoStore`` interface is the seam where
pgvector / OpenSearch would plug in for multi-tenant production use.
"""

from dataclasses import dataclass, field
from pathlib import Path
import json
import threading

import numpy as np
from rank_bm25 import BM25Okapi

from app.models import Chunk, Dependency, Endpoint, RepoIndex
from app.retrieval.tokenize import tokenize


@dataclass
class LoadedRepo:
    index: RepoIndex
    embeddings: np.ndarray
    bm25: BM25Okapi
    chunk_by_id: dict[str, Chunk] = field(default_factory=dict)


class RepoStore:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "repos"
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, LoadedRepo] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- write path
    def save(self, index: RepoIndex, embeddings: np.ndarray, sources: dict[str, str]) -> None:
        d = self.root / index.repo_id
        (d / "files").mkdir(parents=True, exist_ok=True)
        meta = {
            "repo_id": index.repo_id,
            "name": index.name,
            "files": index.files,
            "languages": index.languages,
            "readme": index.readme,
            "chunks": [c.to_dict() for c in index.chunks],
            "endpoints": [e.to_dict() for e in index.endpoints],
            "dependencies": [x.to_dict() for x in index.dependencies],
        }
        (d / "index.json").write_text(json.dumps(meta))
        np.save(d / "embeddings.npy", embeddings)
        for rel, text in sources.items():
            target = d / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        with self._lock:
            self._cache.pop(index.repo_id, None)

    # -------------------------------------------------------------- read path
    def exists(self, repo_id: str) -> bool:
        return (self.root / repo_id / "index.json").exists()

    def list_repos(self) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir()):
            meta_path = d / "index.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                out.append({"repo_id": meta["repo_id"], "name": meta["name"],
                            "files": len(meta["files"]), "chunks": len(meta["chunks"])})
        return out

    def load(self, repo_id: str) -> LoadedRepo:
        with self._lock:
            if repo_id in self._cache:
                return self._cache[repo_id]
        d = self.root / repo_id
        meta = json.loads((d / "index.json").read_text())
        index = RepoIndex(
            repo_id=meta["repo_id"], name=meta["name"], files=meta["files"],
            chunks=[Chunk(**c) for c in meta["chunks"]],
            endpoints=[Endpoint(**e) for e in meta["endpoints"]],
            dependencies=[Dependency(**x) for x in meta["dependencies"]],
            languages=meta["languages"], readme=meta["readme"],
        )
        corpus = [tokenize(c.embed_text) or ["_empty_"] for c in index.chunks] or [["_empty_"]]
        loaded = LoadedRepo(
            index=index,
            embeddings=np.load(d / "embeddings.npy"),
            bm25=BM25Okapi(corpus),
            chunk_by_id={c.id: c for c in index.chunks},
        )
        with self._lock:
            self._cache[repo_id] = loaded
        return loaded

    def read_file(self, repo_id: str, rel_path: str) -> str:
        base = (self.root / repo_id / "files").resolve()
        target = (base / rel_path).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise FileNotFoundError(rel_path)
        return target.read_text(encoding="utf-8")
