from pathlib import Path

import pytest
from pydantic_ai import models

from src.database import connect
from src.load_data import carregar_dados

# Ensures that no automated test calls the real Gemini model.
models.ALLOW_MODEL_REQUESTS = False

PASTA_DADOS = Path(__file__).parent.parent / "data"


@pytest.fixture(autouse=True)
def log_de_limites_temporario(tmp_path, monkeypatch):
    """No test writes to the local environment's limit log."""
    path = tmp_path / "limites_provedor.log"
    monkeypatch.setattr("src.config.CAMINHO_LOG_DE_LIMITES", path)
    return path


@pytest.fixture
def connection(tmp_path):
    connection = connect(tmp_path / "teste.db")
    carregar_dados(connection, PASTA_DADOS)
    yield connection
    connection.close()
