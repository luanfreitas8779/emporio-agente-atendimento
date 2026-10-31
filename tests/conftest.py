from pathlib import Path

import pytest
from pydantic_ai import models

from src.database import conectar
from src.load_data import carregar_dados

# Garante que nenhum teste automático chame o Gemini de verdade.
models.ALLOW_MODEL_REQUESTS = False

PASTA_DADOS = Path(__file__).parent.parent / "data"


@pytest.fixture
def conexao(tmp_path):
    conexao = conectar(tmp_path / "teste.db")
    carregar_dados(conexao, PASTA_DADOS)
    yield conexao
    conexao.close()
