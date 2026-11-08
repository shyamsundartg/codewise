"""Application services: ingestion jobs and question answering.

The API layer (api.py) stays thin and only translates HTTP <-> these calls.
"""

from collections.abc import Iterator
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import logging
import re
import shutil
import tempfile
import threading
import time
import uuid

from app.config import Settings
from app.ingest.pipeline import build_index
from app.ingest.source import SourceError, clone_github, extract_zip
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt, format_dependencies, format_endpoints
from app.llm.provider import Provider
from app.observability import Trace, TraceSink
from app.retrieval.retriever import Hit, pack_context, search, search_query
from app.retrieval.router import route
from app.retrieval.store import LoadedRepo, RepoStore

log = logging.getLogger(__name__)

_CITATION = re.compile(r"\[(\d+)\]")


# ------------------------------------------------------------------ ingestion


@dataclass
class Job:
    job_id: str
    repo_id: str
    name: str
    status: str = "queued"  # queued | fetching | indexing | embedding | ready | error
    message: str = ""
    started_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "repo"


class IngestionService:
    def __init__(self, settings: Settings, store: RepoStore, provider: Provider):
        self.settings, self.store, self.provider = settings, store, provider
        self.jobs: dict[str, Job] = {}

    def start(self, *, github_url: str | None = None, zip_path: Path | None = None,
              name: str | None = None) -> Job:
        display = name or (github_url.rstrip("/").split("/")[-1].removesuffix(".git") if github_url else "upload")
        digest = hashlib.sha1((github_url or str(zip_path) or "").encode() + str(time.time()).encode())
        repo_id = f"{_slug(display)}-{digest.hexdigest()[:6]}"
        job = Job(job_id=uuid.uuid4().hex[:12], repo_id=repo_id, name=display, started_at=time.time())
        self.jobs[job.job_id] = job
        threading.Thread(target=self._run, args=(job, github_url, zip_path), daemon=True).start()
        return job

    def run_sync(self, job: Job, github_url=None, zip_path=None) -> Job:
        """Same as start() but blocking; used by tests and the eval script."""
        self.jobs[job.job_id] = job
        self._run(job, github_url, zip_path)
        return job

    def _run(self, job: Job, github_url: str | None, zip_path: Path | None) -> None:
        workdir = Path(tempfile.mkdtemp(prefix="codewise-"))
        try:
            job.status = "fetching"
            if github_url:
                root = clone_github(github_url, workdir / "src")
            elif zip_path:
                root = extract_zip(zip_path, workdir / "src")
            else:
                raise SourceError("Provide a GitHub URL or a zip file.")

            job.status = "indexing"
            index, sources = build_index(job.repo_id, job.name, root, self.settings)
            if not index.chunks:
                raise SourceError("No indexable source files were found.")

            job.status = "embedding"
            job.message = f"{len(index.chunks)} chunks from {len(index.files)} files"
            embeddings = self.provider.embed([c.embed_text for c in index.chunks])

            self.store.save(index, embeddings, sources)
            job.status = "ready"
            log.info("ingestion done", extra={"job": job.to_dict(),
                                              "seconds": round(time.time() - job.started_at, 1)})
        except SourceError as e:
            job.status, job.message = "error", str(e)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            log.exception("ingestion failed", extra={"job_id": job.job_id})
            job.status, job.message = "error", f"Ingestion failed: {e}"
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            if zip_path:
                zip_path.unlink(missing_ok=True)


# ----------------------------------------------------------------------- chat


def repo_overview(repo: LoadedRepo, include_readme: bool) -> str:
    idx = repo.index
    top_dirs = sorted({f.split("/")[0] for f in idx.files if "/" in f})[:25]
    top_files = sorted(f for f in idx.files if "/" not in f)[:25]
    lines = [
        f"Repository: {idx.name}",
        f"Files indexed: {len(idx.files)}; languages: "
        + ", ".join(f"{k} ({v})" for k, v in list(idx.languages.items())[:6]),
        f"Top-level directories: {', '.join(top_dirs) or '-'}",
        f"Top-level files: {', '.join(top_files) or '-'}",
        f"Endpoints detected: {len(idx.endpoints)}; dependencies declared: {len(idx.dependencies)}",
    ]
    if include_readme and idx.readme:
        lines.append(f"README (truncated):\n{idx.readme[:2500]}")
    return "\n".join(lines)


def hit_to_source(n: int, hit: Hit) -> dict:
    c = hit.chunk
    return {"n": n, "id": c.id, "path": c.path, "start_line": c.start_line, "end_line": c.end_line,
            "symbol": c.symbol, "kind": c.kind, "score": hit.score, "signals": hit.signals}


class ChatService:
    def __init__(self, settings: Settings, store: RepoStore, provider: Provider, traces: TraceSink):
        self.settings, self.store, self.provider, self.traces = settings, store, provider, traces

    def retrieve(self, repo: LoadedRepo, question: str, history=None) -> list[Hit]:
        query = search_query(question, history)
        qvec = self.provider.embed([query])[0]
        hits = search(repo, query, qvec, self.settings.candidate_k)
        return pack_context(hits, self.settings.top_k, self.settings.context_token_budget)

    def answer(self, repo_id: str, question: str, history: list[dict] | None = None) -> Iterator[dict]:
        """Yields events: meta (route + sources), token*, done (trace summary)."""
        repo = self.store.load(repo_id)
        question = question.strip()[:2000]
        trace = Trace(repo_id=repo_id, question=question, provider=self.provider.name)

        with trace.stage("route"):
            kind = route(question)
        structured = ""
        if kind == "endpoints":
            structured = format_endpoints(repo.index.endpoints)
        elif kind == "dependencies":
            structured = format_dependencies(repo.index.dependencies)

        with trace.stage("retrieve"):
            hits = self.retrieve(repo, question, history)
        sources = [hit_to_source(n, h) for n, h in enumerate(hits, start=1)]
        yield {"type": "meta", "route": kind, "sources": sources}

        prompt = build_user_prompt(
            question, repo_overview(repo, include_readme=kind == "overview"),
            [h.chunk for h in hits], structured, history,
        )

        answer_parts: list[str] = []
        with trace.stage("generate"):
            try:
                for token in self.provider.stream_chat(SYSTEM_PROMPT, prompt):
                    answer_parts.append(token)
                    yield {"type": "token", "text": token}
            except Exception as e:  # noqa: BLE001
                log.exception("generation failed")
                msg = f"\n\n_Generation failed: {e}_"
                answer_parts.append(msg)
                yield {"type": "token", "text": msg}

        answer = "".join(answer_parts)
        cited = {int(n) for n in _CITATION.findall(answer)}
        invalid = sorted(n for n in cited if n < 1 or n > len(sources))

        trace.data.update({
            "route": kind,
            "retrieved": [{"id": s["id"], "score": s["score"], "signals": s["signals"]} for s in sources],
            "prompt_tokens_est": (len(SYSTEM_PROMPT) + len(prompt)) // 4,
            "answer_chars": len(answer),
            "citations": sorted(cited),
            "invalid_citations": invalid,
            "uncited_answer": not cited,
        })
        summary = trace.finish()
        self.traces.write(summary)
        yield {"type": "done", "trace": {k: summary[k] for k in (
            "route", "timings_ms", "total_ms", "prompt_tokens_est", "citations",
            "invalid_citations", "uncited_answer")}}
