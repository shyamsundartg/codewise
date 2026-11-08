from pathlib import Path
import zipfile

import pytest

from app.ingest.redact import REDACTED, redact
from app.ingest.source import SourceError, extract_zip, iter_source_files


def test_env_files_are_never_indexed(fixture_repo):
    files = {p.name for p in iter_source_files(fixture_repo, 1000, 300_000)}
    assert ".env" not in files
    assert "auth.py" in files


def test_hardcoded_keys_are_redacted():
    src = 'API_KEY = "sk-live-abcdefghijklmnopqrstuvwxyz123456"\npassword = "hunter2hunter2"'
    out = redact(src)
    assert "sk-live" not in out and "hunter2" not in out
    assert out.count(REDACTED) == 2


def test_zip_slip_is_rejected(tmp_path: Path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../../evil.py", "print('x')")
    with pytest.raises(SourceError):
        extract_zip(bad, tmp_path / "out")
