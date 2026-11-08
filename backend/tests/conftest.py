from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(llm_provider="fake", data_dir=tmp_path / "data")


@pytest.fixture
def fixture_repo() -> Path:
    return FIXTURE_REPO
