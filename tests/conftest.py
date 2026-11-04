from pathlib import Path

import pytest
from pydantic_ai import models

from src.database import connect
from src.load_data import load_all_data

# Ensures that no automated test calls the real Gemini model.
models.ALLOW_MODEL_REQUESTS = False

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(autouse=True)
def log_de_limites_temporario(tmp_path, monkeypatch):
    """No test writes to the local environment's limit log."""
    path = tmp_path / "provider_limits.log"
    monkeypatch.setattr("src.config.LIMITS_LOG_PATH", path)
    return path


@pytest.fixture
def connection(tmp_path):
    connection = connect(tmp_path / "teste.db")
    load_all_data(connection, DATA_DIR)
    yield connection
    connection.close()
