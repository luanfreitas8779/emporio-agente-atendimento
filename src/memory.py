import sqlite3
from datetime import datetime, timezone

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from src.phone import normalizar_telefone

# Diferente das tabelas de origem, estas nunca são recriadas pela carga: guardam
# o que os clientes disseram. Por isso o esquema é idempotente.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations (id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def criar_tabelas(conexao: sqlite3.Connection) -> None:
    conexao.executescript(ESQUEMA)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def carregar_historico(conexao: sqlite3.Connection, telefone: str | None) -> list[ModelMessage]:
    chave = normalizar_telefone(telefone or "")
    if chave is None:
        return []
    linhas = conexao.execute(
        """
        SELECT m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.phone = ? ORDER BY m.id
        """,
        (chave,),
    ).fetchall()
    return [mensagem for linha in linhas for mensagem in ModelMessagesTypeAdapter.validate_json(linha["content"])]


def salvar_mensagens(
    conexao: sqlite3.Connection, telefone: str | None, mensagens: list[ModelMessage]
) -> None:
    chave = normalizar_telefone(telefone or "")
    if chave is None:
        return
    agora = _agora()
    conexao.execute(
        "INSERT INTO conversations (phone, created_at, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone) DO UPDATE SET updated_at = excluded.updated_at",
        (chave, agora, agora),
    )
    conversa = conexao.execute("SELECT id FROM conversations WHERE phone = ?", (chave,)).fetchone()
    conexao.executemany(
        "INSERT INTO messages (conversation_id, content, created_at) VALUES (?, ?, ?)",
        [
            (conversa["id"], ModelMessagesTypeAdapter.dump_json([m]).decode(), agora)
            for m in mensagens
        ],
    )
    conexao.commit()
