"""HTTP layer. Thin on purpose: validation + translation to services."""

from pathlib import Path
import json
import logging
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings, settings as default_settings
from app.llm.provider import Provider, get_provider
from app.observability import TraceSink, setup_logging
from app.retrieval.store import RepoStore
from app.services import ChatService, IngestionService

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

log = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    github_url: str = Field(..., max_length=300)


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


def suggested_questions(repo) -> list[str]:
    idx = repo.index
    qs = ["Give me an overview of this repository"]
    code = [c for c in idx.chunks if "test" not in c.path.lower()]
    classes = sorted((c for c in code if c.kind == "class"),
                     key=lambda c: c.end_line - c.start_line, reverse=True)
    if classes:
        qs.append(f"How does `{classes[0].symbol}` work?")
    funcs = [c for c in code if c.kind in {"function", "method"} and not c.symbol.split(".")[-1].startswith("_")]
    if funcs:
        biggest = max(funcs, key=lambda c: c.end_line - c.start_line)
        qs.append(f"Where is `{biggest.symbol}` implemented and what calls it?")
    if idx.endpoints:
        qs.append("List all the API endpoints")
    if idx.dependencies:
        qs.append("What are the main dependencies and what are they used for?")
    return qs[:5]


def create_app(settings: Settings = default_settings, provider: Provider | None = None) -> FastAPI:
    setup_logging()
    provider = provider or get_provider(settings)
    store = RepoStore(settings.data_dir)
    ingestion = IngestionService(settings, store, provider)
    chat = ChatService(settings, store, provider, TraceSink(settings.data_dir))

    app = FastAPI(title="CodeWise", version="0.1.0")
    app.state.ingestion, app.state.store = ingestion, store

    def _require_repo(repo_id: str):
        if not store.exists(repo_id):
            raise HTTPException(404, "Unknown repository")
        return store.load(repo_id)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "provider": provider.name}

    @app.get("/api/repos")
    def list_repos():
        return store.list_repos()

    @app.post("/api/repos", status_code=202)
    def ingest_github(req: IngestRequest):
        return ingestion.start(github_url=req.github_url).to_dict()

    @app.post("/api/repos/upload", status_code=202)
    async def ingest_zip(file: UploadFile = File(...)):
        if not (file.filename or "").lower().endswith(".zip"):
            raise HTTPException(400, "Please upload a .zip file")
        tmp = Path(tempfile.mkstemp(suffix=".zip")[1])
        size = 0
        with tmp.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(413, "Zip is larger than 50 MB")
                out.write(chunk)
        name = Path(file.filename).stem
        return ingestion.start(zip_path=tmp, name=name).to_dict()

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        job = ingestion.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Unknown job")
        return job.to_dict()

    @app.get("/api/repos/{repo_id}")
    def repo_detail(repo_id: str):
        repo = _require_repo(repo_id)
        idx = repo.index
        return {
            "repo_id": idx.repo_id, "name": idx.name, "files": idx.files,
            "languages": idx.languages, "chunk_count": len(idx.chunks),
            "endpoints": [e.to_dict() for e in idx.endpoints],
            "dependencies": [d.to_dict() for d in idx.dependencies],
            "suggested_questions": suggested_questions(repo),
        }

    @app.get("/api/repos/{repo_id}/file")
    def repo_file(repo_id: str, path: str):
        _require_repo(repo_id)
        try:
            return {"path": path, "content": store.read_file(repo_id, path)}
        except FileNotFoundError:
            raise HTTPException(404, "File not found") from None

    @app.post("/api/repos/{repo_id}/chat")
    def ask(repo_id: str, req: ChatRequest):
        _require_repo(repo_id)
        history = [t.model_dump() for t in req.history]

        def stream():
            for event in chat.answer(repo_id, req.question, history):
                yield json.dumps(event) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.get("/")
        def index():
            return FileResponse(FRONTEND_DIR / "index.html")

    return app
