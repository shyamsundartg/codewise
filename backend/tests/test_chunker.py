from app.ingest.chunker import chunk_file, chunk_python


def test_python_chunks_follow_functions_and_classes(fixture_repo):
    src = (fixture_repo / "shop/repos/orders.py").read_text()
    chunks = chunk_python("shop/repos/orders.py", src, max_lines=120)
    symbols = {c.symbol: c for c in chunks}

    assert set(symbols) == {"OrderRepo", "calculate_discount"}
    assert symbols["OrderRepo"].kind == "class"
    fn = symbols["calculate_discount"]
    assert fn.text.startswith("def calculate_discount")
    assert "# function: calculate_discount" in fn.header


def test_big_class_is_split_into_methods(fixture_repo):
    src = (fixture_repo / "shop/services/auth.py").read_text()
    chunks = chunk_python("shop/services/auth.py", src, max_lines=8)
    symbols = [c.symbol for c in chunks]

    assert "AuthService.refresh_token" in symbols
    assert "AuthService.issue_token" in symbols
    refresh = next(c for c in chunks if c.symbol == "AuthService.refresh_token")
    assert refresh.kind == "method"
    assert "jwt.decode" in refresh.text


def test_decorators_are_included_in_function_chunk(fixture_repo):
    src = (fixture_repo / "shop/api/routes.py").read_text()
    chunks = chunk_python("shop/api/routes.py", src, max_lines=120)
    login = next(c for c in chunks if c.symbol == "login")
    assert login.text.startswith('@app.post("/login")')


def test_module_level_code_is_not_lost(fixture_repo):
    src = (fixture_repo / "shop/api/routes.py").read_text()
    chunks = chunk_python("shop/api/routes.py", src, max_lines=120)
    module = [c for c in chunks if c.kind == "module"]
    assert any("app = FastAPI()" in c.text for c in module)


def test_line_numbers_point_at_real_code(fixture_repo):
    src = (fixture_repo / "shop/repos/orders.py").read_text()
    lines = src.splitlines()
    for c in chunk_python("shop/repos/orders.py", src, max_lines=120):
        assert c.text == "\n".join(lines[c.start_line - 1 : c.end_line])


def test_oversized_function_is_split_with_overlap():
    body = "\n".join(f"    x{i} = {i}" for i in range(50))
    src = f"def huge():\n{body}\n"
    chunks = chunk_python("big.py", src, max_lines=20)
    assert len(chunks) > 1
    assert chunks[1].start_line < chunks[0].end_line  # overlap
    assert chunks[-1].end_line == 51


def test_invalid_python_falls_back_to_text():
    chunks = chunk_file("broken.py", "def oops(:\n  pass\n", max_chunk_lines=120)
    assert chunks and chunks[0].kind == "text"


def test_markdown_split_on_headings(fixture_repo):
    src = (fixture_repo / "README.md").read_text()
    chunks = chunk_file("README.md", src, max_chunk_lines=120)
    assert len(chunks) == 2
    assert chunks[1].text.startswith("## Auth")
