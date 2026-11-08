"""Getting source files onto disk (git clone / zip) and deciding which to index."""

from pathlib import Path
import re
import subprocess
import zipfile

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".next", ".idea", ".vscode",
    "coverage", "site-packages", ".tox", "target",
}

# Files that may contain secrets are never read, let alone sent to an LLM.
SECRET_FILE_PATTERNS = [
    re.compile(p) for p in (r"^\.env(\..*)?$", r".*\.pem$", r".*\.key$", r"^id_rsa.*", r".*\.p12$")
]

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock"}

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".rs", ".cs", ".php",
    ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini",
    ".html", ".css", ".sql", ".sh", ".dockerfile",
}
TEXT_FILENAMES = {"Dockerfile", "Makefile", "Procfile", "requirements.txt"}

GITHUB_URL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$")


class SourceError(ValueError):
    """Raised for user-facing problems with the provided source."""


def clone_github(url: str, dest: Path) -> Path:
    url = url.strip()
    if not GITHUB_URL.match(url):
        raise SourceError("Only public https://github.com/<owner>/<repo> URLs are supported.")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", url, str(dest)],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise SourceError(f"git clone failed: {result.stderr.strip()[:300]}")
    return dest


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            # Zip-slip guard: refuse entries that escape the destination.
            if not target.is_relative_to(root):
                raise SourceError(f"Unsafe path in zip: {member.filename}")
        zf.extractall(dest)
    # If the zip wraps everything in one top-level folder, use that as the root.
    children = [p for p in dest.iterdir() if not p.name.startswith("__MACOSX")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return dest


def is_secret_file(name: str) -> bool:
    return any(p.match(name) for p in SECRET_FILE_PATTERNS)


def should_index(path: Path, max_bytes: int) -> bool:
    name = path.name
    if is_secret_file(name) or name in LOCKFILES:
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS and name not in TEXT_FILENAMES:
        return False
    try:
        return 0 < path.stat().st_size <= max_bytes
    except OSError:
        return False


def iter_source_files(root: Path, max_files: int, max_bytes: int) -> list[Path]:
    """Return indexable files under root, sorted for deterministic output."""
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if path.is_file() and should_index(path, max_bytes):
            found.append(path)
            if len(found) >= max_files:
                break
    return found
