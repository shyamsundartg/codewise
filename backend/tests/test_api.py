"""End-to-end: ingest the fixture repo through the API and ask questions."""

import json
import shutil
import time

from fastapi.testclient import TestClient

from app.api import create_app


def _upload_fixture(client, fixture_repo, tmp_path) -> str:
    archive = shutil.make_archive(str(tmp_path / "sample_repo"), "zip", fixture_repo)
    with open(archive, "rb") as f:
        resp = client.post("/api/repos/upload", files={"file": ("sample_repo.zip", f, "application/zip")})
    assert resp.status_code == 202
    job = resp.json()
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['job_id']}").json()
        if job["status"] in {"ready", "error"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready", job
    return job["repo_id"]


def _ask(client, repo_id, question):
    resp = client.post(f"/api/repos/{repo_id}/chat", json={"question": question})
    assert resp.status_code == 200
    return [json.loads(line) for line in resp.text.splitlines()]


def test_ingest_and_chat(settings, fixture_repo, tmp_path):
    client = TestClient(create_app(settings))
    repo_id = _upload_fixture(client, fixture_repo, tmp_path)

    detail = client.get(f"/api/repos/{repo_id}").json()
    assert "shop/services/auth.py" in detail["files"]
    assert ".env" not in detail["files"]
    assert len(detail["endpoints"]) == 5
    assert detail["suggested_questions"]

    events = _ask(client, repo_id, "How does refresh_token work?")
    meta, done = events[0], events[-1]
    assert meta["type"] == "meta" and meta["route"] == "code"
    # The class that defines refresh_token must rank first (symbol + keyword signals agree).
    assert meta["sources"][0]["path"] == "shop/services/auth.py"
    assert "symbol" in meta["sources"][0]["signals"]
    assert done["type"] == "done" and done["trace"]["invalid_citations"] == []

    events = _ask(client, repo_id, "List all API endpoints")
    assert events[0]["route"] == "endpoints"


def test_file_endpoint_blocks_path_traversal(settings, fixture_repo, tmp_path):
    client = TestClient(create_app(settings))
    repo_id = _upload_fixture(client, fixture_repo, tmp_path)
    ok = client.get(f"/api/repos/{repo_id}/file", params={"path": "shop/repos/orders.py"})
    assert ok.status_code == 200 and "OrderRepo" in ok.json()["content"]
    bad = client.get(f"/api/repos/{repo_id}/file", params={"path": "../../index.json"})
    assert bad.status_code == 404


def test_secrets_redacted_in_stored_files(settings, fixture_repo, tmp_path):
    client = TestClient(create_app(settings))
    repo_id = _upload_fixture(client, fixture_repo, tmp_path)
    content = client.get(f"/api/repos/{repo_id}/file", params={"path": "shop/services/auth.py"}).json()["content"]
    assert "sk-live" not in content


def test_unknown_repo_404(settings):
    client = TestClient(create_app(settings))
    assert client.post("/api/repos/nope/chat", json={"question": "hi"}).status_code == 404
