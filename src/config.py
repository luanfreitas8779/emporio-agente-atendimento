import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ_PROJETO = Path(__file__).parent.parent
PASTA_DADOS = RAIZ_PROJETO / "data"
CAMINHO_BANCO = PASTA_DADOS / "emporio.db"
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
