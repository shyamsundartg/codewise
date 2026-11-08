"""Turn source files into retrieval chunks.

Strategy
--------
* Python: parse with the stdlib ``ast`` module and emit one chunk per
  function / class / method, so a chunk is a unit a developer would talk
  about. Each chunk gets a small header (file, symbol, imports) because a
  function body alone often lacks the words a question uses.
* Everything else (and Python that fails to parse): fixed line windows
  with overlap. Markdown is split on headings first.
"""

import ast
from pathlib import Path

from app.models import Chunk

TEXT_WINDOW = 60
TEXT_OVERLAP = 10
MAX_HEADER_IMPORTS = 12


def chunk_file(rel_path: str, source: str, max_chunk_lines: int) -> list[Chunk]:
    if rel_path.endswith(".py"):
        try:
            return chunk_python(rel_path, source, max_chunk_lines)
        except SyntaxError:
            pass  # fall through to plain text chunking
    if rel_path.lower().endswith((".md", ".rst")):
        return chunk_markdown(rel_path, source)
    return chunk_text(rel_path, source)


# --------------------------------------------------------------------- python


def _imports(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names += [f"{base}.{a.name}" if base else a.name for a in node.names]
    return names[:MAX_HEADER_IMPORTS]


def _start_line(node: ast.AST) -> int:
    """Include decorators: they often carry the meaning (e.g. @app.get('/x'))."""
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno] + [d.lineno for d in decorators])


def _header(rel_path: str, symbol: str, kind: str, imports: list[str]) -> str:
    lines = [f"# file: {rel_path}"]
    if symbol:
        lines.append(f"# {kind}: {symbol}")
    if imports:
        lines.append(f"# imports: {', '.join(imports)}")
    return "\n".join(lines)


def _make(rel_path, lines, start, end, kind, symbol, imports, max_lines) -> list[Chunk]:
    """Create one chunk, or several overlapping ones if the node is huge."""
    chunks: list[Chunk] = []
    step = max(max_lines - TEXT_OVERLAP, 1)
    part_start = start
    part = 0
    while True:
        part_end = min(part_start + max_lines - 1, end)
        sym = symbol if part == 0 else f"{symbol} (part {part + 1})"
        chunks.append(
            Chunk(
                id=f"{rel_path}:{part_start}-{part_end}",
                path=rel_path,
                start_line=part_start,
                end_line=part_end,
                kind=kind,
                symbol=sym,
                text="\n".join(lines[part_start - 1 : part_end]),
                header=_header(rel_path, sym, kind, imports),
            )
        )
        if part_end >= end:
            return chunks
        part_start += step
        part += 1


def chunk_python(rel_path: str, source: str, max_lines: int) -> list[Chunk]:
    tree = ast.parse(source)
    lines = source.splitlines()
    imports = _imports(tree)
    chunks: list[Chunk] = []
    covered: set[int] = set()

    def emit(node, kind, symbol):
        start, end = _start_line(node), node.end_lineno
        chunks.extend(_make(rel_path, lines, start, end, kind, symbol, imports, max_lines))
        covered.update(range(start, end + 1))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(node, "function", node.name)
        elif isinstance(node, ast.ClassDef):
            start, end = _start_line(node), node.end_lineno
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if end - start + 1 <= max_lines or not methods:
                emit(node, "class", node.name)
                continue
            # Big class: one chunk for the class "head" (signature, docstring,
            # attributes) and one per method.
            head_end = _start_line(methods[0]) - 1
            chunks.extend(_make(rel_path, lines, start, head_end, "class", node.name, imports, max_lines))
            covered.update(range(start, head_end + 1))
            for m in methods:
                emit(m, "method", f"{node.name}.{m.name}")
            covered.update(range(start, end + 1))

    chunks.extend(_module_level_chunks(rel_path, lines, covered, imports, max_lines))
    return sorted(chunks, key=lambda c: c.start_line)


def _module_level_chunks(rel_path, lines, covered, imports, max_lines) -> list[Chunk]:
    """Group code that lives outside any def/class (constants, app setup...)."""
    chunks: list[Chunk] = []
    run: list[int] = []
    for i in range(1, len(lines) + 2):  # one past the end flushes the last run
        if i <= len(lines) and i not in covered:
            run.append(i)
            continue
        if run:
            text = "\n".join(lines[run[0] - 1 : run[-1]])
            if text.strip():
                chunks.extend(
                    _make(rel_path, lines, run[0], run[-1], "module", "", imports, max_lines)
                )
            run = []
    return chunks


# ----------------------------------------------------------------------- text


def chunk_text(rel_path: str, source: str, offset: int = 0) -> list[Chunk]:
    lines = source.splitlines()
    chunks: list[Chunk] = []
    step = TEXT_WINDOW - TEXT_OVERLAP
    for start in range(0, max(len(lines), 1), step):
        window = lines[start : start + TEXT_WINDOW]
        if not "\n".join(window).strip():
            continue
        s, e = offset + start + 1, offset + start + len(window)
        chunks.append(
            Chunk(
                id=f"{rel_path}:{s}-{e}", path=rel_path, start_line=s, end_line=e,
                kind="text", symbol="", text="\n".join(window),
                header=f"# file: {rel_path}",
            )
        )
        if start + TEXT_WINDOW >= len(lines):
            break
    return chunks


def chunk_markdown(rel_path: str, source: str) -> list[Chunk]:
    lines = source.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.startswith("#")] or [0]
    if starts[0] != 0:
        starts.insert(0, 0)
    chunks: list[Chunk] = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        section = "\n".join(lines[s:e])
        chunks.extend(chunk_text(rel_path, section, offset=s))
    return chunks


def language_of(path: str) -> str:
    return {
        ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript", ".md": "Markdown", ".json": "JSON", ".yml": "YAML",
        ".yaml": "YAML", ".toml": "TOML", ".html": "HTML", ".css": "CSS", ".go": "Go",
        ".java": "Java", ".rs": "Rust", ".sql": "SQL", ".sh": "Shell",
    }.get(Path(path).suffix.lower(), "Other")
