"""LLM + embedding providers behind one small interface.

The rest of the app only calls ``embed`` and ``stream_chat``. Chat and
embeddings are chosen independently, because not every vendor offers both
(Anthropic has no embeddings API):

    LLM_PROVIDER       = openai | anthropic | fake
    EMBEDDING_PROVIDER = openai | local | hash   (default: openai for openai, local otherwise)

``fake`` / ``hash`` keep tests and the eval runnable offline at zero cost.
"""

from collections.abc import Iterator
from typing import Protocol
import hashlib
import re

import numpy as np

from app.config import Settings

MAX_EMBED_CHARS = 24_000  # ~6k tokens; stays under the 8k OpenAI embedding limit
EMBED_BATCH = 96


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class ChatModel(Protocol):
    name: str

    def stream_chat(self, system: str, user: str) -> Iterator[str]: ...


class Provider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...

    def stream_chat(self, system: str, user: str) -> Iterator[str]: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


# ------------------------------------------------------------------ embedders


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, settings: Settings):
        from openai import OpenAI  # lazy import: tests don't need the SDK configured

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set (or use EMBEDDING_PROVIDER=local).")
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=3)
        self.model = settings.embedding_model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = [t[:MAX_EMBED_CHARS] or " " for t in texts[i : i + EMBED_BATCH]]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(d.embedding for d in resp.data)
        return _normalize(np.array(vectors, dtype=np.float32))


class LocalEmbedder:
    """On-device embeddings with fastembed (ONNX, CPU). No API key, no data
    leaves the machine. The model (~70 MB) downloads once on first use."""

    name = "local"

    def __init__(self, settings: Settings):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(settings.local_embedding_model)

    def embed(self, texts: list[str]) -> np.ndarray:
        # bge-small has a 512-token window; longer chunks are truncated by the
        # tokenizer, and the header (path/symbol/imports) is at the front.
        vectors = list(self.model.embed([t[:4000] or " " for t in texts], batch_size=32))
        return _normalize(np.array(vectors, dtype=np.float32))


class HashEmbedder:
    """Deterministic hashed bag-of-words. Offline tests / demo only."""

    name = "hash"
    DIM = 512

    def embed(self, texts: list[str]) -> np.ndarray:
        m = np.zeros((len(texts), self.DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in re.findall(r"[a-z0-9]+", text.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                m[row, h % self.DIM] += 1.0
        return _normalize(m)


# ---------------------------------------------------------------- chat models


class OpenAIChat:
    name = "openai"

    def __init__(self, settings: Settings):
        from openai import OpenAI

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set (or use LLM_PROVIDER=anthropic / fake).")
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=3)
        self.model = settings.chat_model or "gpt-4.1-mini"

    def stream_chat(self, system: str, user: str) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            stream=True,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content


class AnthropicChat:
    name = "anthropic"

    def __init__(self, settings: Settings):
        from anthropic import Anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self.client = Anthropic(api_key=settings.anthropic_api_key, timeout=60, max_retries=3)
        self.model = settings.chat_model or "claude-sonnet-5-5"

    def stream_chat(self, system: str, user: str) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            yield from stream.text_stream


class FakeChat:
    """Extractive stand-in that just points at the top sources."""

    name = "fake"

    def stream_chat(self, system: str, user: str) -> Iterator[str]:
        sources = re.findall(r'<source id="(\d+)" location="([^"]+)"', user)
        if not sources:
            yield "I couldn't find anything relevant to that in this codebase."
            return
        yield "(Offline demo mode, no LLM.) The most relevant code I found:\n\n"
        for sid, loc in sources[:3]:
            yield f"- `{loc}` [{sid}]\n"


# -------------------------------------------------------------------- wiring


class CompositeProvider:
    def __init__(self, chat: ChatModel, embedder: Embedder):
        self.chat, self.embedder = chat, embedder
        self.name = f"{chat.name}+{embedder.name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.embedder.embed(texts)

    def stream_chat(self, system: str, user: str) -> Iterator[str]:
        return self.chat.stream_chat(system, user)


# Kept for tests and the offline demo.
def FakeProvider() -> CompositeProvider:  # noqa: N802
    return CompositeProvider(FakeChat(), HashEmbedder())


_CHAT = {"openai": OpenAIChat, "anthropic": AnthropicChat, "fake": lambda s: FakeChat()}
_EMBED = {"openai": OpenAIEmbedder, "local": LocalEmbedder, "hash": lambda s: HashEmbedder()}


def get_provider(settings: Settings) -> CompositeProvider:
    chat_name = settings.llm_provider
    embed_name = settings.embedding_provider or {
        "openai": "openai", "fake": "hash"
    }.get(chat_name, "local")
    if chat_name not in _CHAT:
        raise ValueError(f"Unknown LLM_PROVIDER: {chat_name}")
    if embed_name not in _EMBED:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {embed_name}")
    return CompositeProvider(_CHAT[chat_name](settings), _EMBED[embed_name](settings))
