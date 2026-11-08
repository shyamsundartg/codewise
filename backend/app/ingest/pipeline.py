"""Ingestion: source directory -> RepoIndex (chunks + structured facts)."""

from collections import Counter
from pathlib import Path
import logging

from app.config import Settings
from app.ingest.chunker import chunk_file, language_of
from app.ingest.extractors import extract_dependencies, extract_endpoints
from app.ingest.redact import redact
from app.ingest.source import iter_source_files
from app.models import RepoIndex

log = logging.getLogger(__name__)


def build_index(
    repo_id: str, name: str, root: Path, settings: Settings
) -> tuple[RepoIndex, dict[str, str]]:
    """Returns the index plus the (redacted) file contents for the code viewer."""
    index = RepoIndex(repo_id=repo_id, name=name)
    sources: dict[str, str] = {}
    langs: Counter[str] = Counter()

    for path in iter_source_files(root, settings.max_files, settings.max_file_bytes):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: skip silently
        source = redact(source)

        index.files.append(rel)
        sources[rel] = source
        langs[language_of(rel)] += 1
        index.chunks.extend(chunk_file(rel, source, settings.max_chunk_lines))
        index.endpoints.extend(extract_endpoints(rel, source))
        index.dependencies.extend(extract_dependencies(rel, source))
        if rel.lower() in {"readme.md", "readme.rst", "readme.txt"}:
            index.readme = source[:4000]

    index.languages = dict(langs.most_common())
    log.info(
        "ingested repo",
        extra={"repo_id": repo_id, "files": len(index.files), "chunks": len(index.chunks),
               "endpoints": len(index.endpoints), "dependencies": len(index.dependencies)},
    )
    return index, sources
