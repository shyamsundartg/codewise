from app.ingest.extractors import extract_dependencies, extract_endpoints


def test_fastapi_endpoints(fixture_repo):
    src = (fixture_repo / "shop/api/routes.py").read_text()
    eps = {(e.method, e.path, e.handler) for e in extract_endpoints("shop/api/routes.py", src)}
    assert eps == {
        ("POST", "/login", "login"),
        ("GET", "/orders/{order_id}", "get_order"),
        ("DELETE", "/orders/{order_id}", "cancel_order"),
    }


def test_flask_route_with_methods():
    src = '@bp.route("/items", methods=["GET", "POST"])\ndef items():\n    pass\n'
    eps = extract_endpoints("app.py", src)
    assert {e.method for e in eps} == {"GET", "POST"}


def test_express_endpoints(fixture_repo):
    src = (fixture_repo / "web/server.js").read_text()
    eps = {(e.method, e.path) for e in extract_endpoints("web/server.js", src)}
    assert eps == {("GET", "/health"), ("POST", "/webhooks/payment")}


def test_requirements_txt(fixture_repo):
    deps = extract_dependencies("requirements.txt", (fixture_repo / "requirements.txt").read_text())
    assert [(d.name, d.version) for d in deps] == [
        ("fastapi", ">=0.110"), ("pyjwt", "==2.8.0"), ("sqlalchemy", ""),
    ]


def test_package_json_marks_dev_deps(fixture_repo):
    deps = extract_dependencies("web/package.json", (fixture_repo / "web/package.json").read_text())
    assert {d.name for d in deps} == {"express", "jest (dev)"}


def test_pyproject():
    src = '[project]\ndependencies = ["httpx>=0.27", "rich"]\n'
    deps = extract_dependencies("pyproject.toml", src)
    assert [d.name for d in deps] == ["httpx", "rich"]
