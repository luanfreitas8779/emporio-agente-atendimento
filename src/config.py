import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ_PROJETO = Path(__file__).parent.parent
PASTA_DADOS = RAIZ_PROJETO / "data"
CAMINHO_BANCO = PASTA_DADOS / "emporio.db"
CAMINHO_LOG_DE_LIMITES = PASTA_DADOS / "limites_provedor.log"
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

DATA_DE_REFERENCIA_PADRAO = "2026-03-25"


def data_de_referencia() -> date:
    """Data usada como "hoje" nos prazos. Os pedidos vão até 2026-03-22 (docs/03-data.md, 5.3)."""
    texto = os.getenv("DATA_DE_REFERENCIA", DATA_DE_REFERENCIA_PADRAO)
    try:
        return date.fromisoformat(texto)
    except ValueError as erro:
        raise ValueError(f"DATA_DE_REFERENCIA inválida: use o formato AAAA-MM-DD, não {texto!r}.") from erro
