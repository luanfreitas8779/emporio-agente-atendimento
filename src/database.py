import sqlite3
from pathlib import Path

from src.memory import criar_tabelas


def conectar(caminho: Path) -> sqlite3.Connection:
    # O Pydantic AI executa ferramentas em outra thread, uma de cada vez por conexão.
    conexao = sqlite3.connect(caminho, check_same_thread=False)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    # A memória da conversa não depende da carga de dados: um banco novo já a comporta.
    criar_tabelas(conexao)
    return conexao
