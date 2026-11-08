"""Plain data types shared across ingestion, retrieval and the API."""

from dataclasses import dataclass, asdict, field


@dataclass
class Chunk:
    id: str
    path: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    kind: str  # "function" | "class" | "method" | "module" | "text"
    symbol: str  # e.g. "AuthService.refresh_token"; "" for text chunks
    text: str  # the code itself
    header: str = ""  # context prepended before embedding

    @property
    def embed_text(self) -> str:
        return f"{self.header}\n{self.text}" if self.header else self.text

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Endpoint:
    method: str
    path: str
    handler: str
    file: str
    line: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Dependency:
    name: str
    version: str
    source: str  # manifest file it came from
    ecosystem: str  # "python" | "node"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepoIndex:
    """Everything we know about one ingested repository."""

    repo_id: str
    name: str
    files: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    readme: str = ""
