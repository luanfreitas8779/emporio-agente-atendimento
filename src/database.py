import sqlite3
from pathlib import Path

from src.memory import criar_tabelas


def conectar(caminho: Path) -> sqlite3.Connection:
    # Pydantic AI runs tools in another thread, one at a time per connection.
    conexao = sqlite3.connect(caminho, check_same_thread=False)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    # The conversation memory does not depend on the data load: a new database already supports it.
    criar_tabelas(conexao)
    return conexao
