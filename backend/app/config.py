"""Runtime configuration, read once from environment variables.

Every knob that affects retrieval quality lives here so experiments
(e.g. changing top_k) are a one-line env change, not a code change.
"""

from dataclasses import dataclass, field
from pathlib import Path
import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # Chat: "openai" | "anthropic" | "fake" (tests / offline demo).
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "openai"))
    # Embeddings: "openai" | "local" | "hash". Empty = sensible default for llm_provider.
    embedding_provider: str = field(default_factory=lambda: _env("EMBEDDING_PROVIDER", ""))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", ""))
    # Empty = provider default (gpt-4.1-mini / claude-sonnet-5-5).
    chat_model: str = field(default_factory=lambda: _env("CHAT_MODEL", ""))
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    local_embedding_model: str = field(
        default_factory=lambda: _env("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    )

    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")))

    # Ingestion limits (guardrails against huge repos).
    max_files: int = field(default_factory=lambda: int(_env("MAX_FILES", "2000")))
    max_file_bytes: int = field(default_factory=lambda: int(_env("MAX_FILE_BYTES", "300000")))
    max_chunk_lines: int = field(default_factory=lambda: int(_env("MAX_CHUNK_LINES", "120")))

    # Retrieval.
    top_k: int = field(default_factory=lambda: int(_env("TOP_K", "8")))
    candidate_k: int = field(default_factory=lambda: int(_env("CANDIDATE_K", "30")))
    context_token_budget: int = field(
        default_factory=lambda: int(_env("CONTEXT_TOKEN_BUDGET", "6000"))
    )


settings = Settings()
