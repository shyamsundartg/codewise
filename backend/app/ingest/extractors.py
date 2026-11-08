"""Structured facts that vector search answers badly: endpoints and dependencies.

"List all endpoints" needs *every* route, scattered over many files. Top-k
retrieval would return a random subset, so we extract them deterministically
at ingestion time and answer those questions from tables instead.
"""

import ast
import json
import re
import tomllib
from pathlib import PurePosixPath

from app.models import Dependency, Endpoint

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}

# Express / Koa style: app.get('/path', ...) or router.post("/path", ...)
_JS_ROUTE = re.compile(
    r"""\b(\w+)\.(get|post|put|patch|delete|all)\(\s*['"`]([^'"`]+)['"`]"""
)


# ------------------------------------------------------------------ endpoints


def _const_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def python_endpoints(rel_path: str, source: str) -> list[Endpoint]:
    """FastAPI (@app.get) and Flask (@app.route / @bp.route) decorators."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[Endpoint] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            attr = dec.func.attr.lower()
            path = _const_str(dec.args[0]) if dec.args else None
            if path is None:
                continue
            if attr in HTTP_METHODS:
                methods = [attr.upper()]
            elif attr == "route":
                methods = ["GET"]
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        methods = [m.upper() for m in map(_const_str, kw.value.elts) if m]
            else:
                continue
            for m in methods:
                found.append(Endpoint(m, path, node.name, rel_path, dec.lineno))
    return found


def js_endpoints(rel_path: str, source: str) -> list[Endpoint]:
    found: list[Endpoint] = []
    for i, line in enumerate(source.splitlines(), start=1):
        for obj, method, path in _JS_ROUTE.findall(line):
            if obj in {"app", "router", "server", "api"} or obj.endswith("Router"):
                found.append(Endpoint(method.upper(), path, f"{obj}.{method}", rel_path, i))
    return found


def extract_endpoints(rel_path: str, source: str) -> list[Endpoint]:
    if rel_path.endswith(".py"):
        return python_endpoints(rel_path, source)
    if rel_path.endswith((".js", ".ts", ".mjs", ".cjs")):
        return js_endpoints(rel_path, source)
    return []


# --------------------------------------------------------------- dependencies

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*([<>=!~].*)?$")


def _requirements(rel_path: str, source: str) -> list[Dependency]:
    deps = []
    for line in source.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            deps.append(Dependency(m.group(1), (m.group(2) or "").strip(), rel_path, "python"))
    return deps


def _pyproject(rel_path: str, source: str) -> list[Dependency]:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return []
    deps = []
    for spec in data.get("project", {}).get("dependencies", []):
        m = _REQ_LINE.match(spec.split(";")[0])
        if m:
            deps.append(Dependency(m.group(1), (m.group(2) or "").strip(), rel_path, "python"))
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, ver in poetry.items():
        if name.lower() != "python":
            deps.append(Dependency(name, ver if isinstance(ver, str) else "", rel_path, "python"))
    return deps


def _package_json(rel_path: str, source: str) -> list[Dependency]:
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return []
    deps = []
    for section in ("dependencies", "devDependencies"):
        for name, ver in (data.get(section) or {}).items():
            label = name if section == "dependencies" else f"{name} (dev)"
            deps.append(Dependency(label, str(ver), rel_path, "node"))
    return deps


def extract_dependencies(rel_path: str, source: str) -> list[Dependency]:
    name = PurePosixPath(rel_path).name
    if name.startswith("requirements") and name.endswith(".txt"):
        return _requirements(rel_path, source)
    if name == "pyproject.toml":
        return _pyproject(rel_path, source)
    if name == "package.json":
        return _package_json(rel_path, source)
    return []
