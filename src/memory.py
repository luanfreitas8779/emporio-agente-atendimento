import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from src.phone import normalize_phone

# Unlike the source tables, these are never recreated by the load: they store
# what the customers said. That is why the schema is idempotent.
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

CREATE TABLE IF NOT EXISTS conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_interests (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL,
    product_id INTEGER NOT NULL CHECK (product_id > 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending')),
    created_at TEXT NOT NULL,
    UNIQUE (phone, product_id)
);

CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY,
    phone TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('reclamacao', 'sem_resposta_segura', 'atendente_solicitado')),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    created_at TEXT NOT NULL
);
"""

MAX_MENSAGENS_NO_HISTORICO = 30


@dataclass
class Estado:
    """What needs to carry across messages, kept in code and not in the model's memory."""

    pedido_em_analise: int | None = None
    produto_em_foco: int | None = None


def create_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(ESQUEMA)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inicia_um_turno(mensagem: ModelMessage) -> bool:
    # A request with the customer's message and no tool result does not answer
    # any previous call: it is a safe point to start the history.
    return isinstance(mensagem, ModelRequest) and (
        any(isinstance(p, UserPromptPart) for p in mensagem.parts)
        and not any(isinstance(p, ToolReturnPart) for p in mensagem.parts)
    )


def limitar_historico(mensagens: list[ModelMessage]) -> list[ModelMessage]:
    """Keeps the latest messages without separating a tool call from its result.

    The cut starts at the first whole turn that fits the limit; a turn that
    exceeds the limit is discarded entirely.
    """
    inicio = max(0, len(mensagens) - MAX_MENSAGENS_NO_HISTORICO)
    for i in range(inicio, len(mensagens)):
        if _inicia_um_turno(mensagens[i]):
            return mensagens[i:]
    return []


def _ler_mensagens(connection: sqlite3.Connection, phone: str | None) -> list[ModelMessage]:
    chave = normalize_phone(phone or "")
    if chave is None:
        return []
    rows = connection.execute(
        """
        SELECT m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.phone = ? ORDER BY m.id
        """,
        (chave,),
    ).fetchall()
    mensagens: list[ModelMessage] = []
    for row in rows:
        try:
            mensagens.extend(ModelMessagesTypeAdapter.validate_json(row["content"]))
        except ValidationError:
            # An unreadable row cannot block the service or leave a turn
            # half-done: the history starts again after it.
            mensagens = []
    return mensagens


def carregar_historico(connection: sqlite3.Connection, phone: str | None) -> list[ModelMessage]:
    return limitar_historico(_ler_mensagens(connection, phone))


def exibir_conversa(connection: sqlite3.Connection, phone: str | None) -> list[tuple[str, str]]:
    """The customer's message and the final answer of each turn, as the customer saw them."""
    conversa: list[tuple[str, str]] = []
    resposta: str | None = None
    for mensagem in _ler_mensagens(connection, phone):
        if _inicia_um_turno(mensagem):
            if resposta is not None:
                conversa.append(("assistant", resposta))
                resposta = None
            text = " ".join(
                str(p.content) for p in mensagem.parts if isinstance(p, UserPromptPart)
            )
            conversa.append(("user", text))
        elif isinstance(mensagem, ModelResponse):
            textos = [p.content for p in mensagem.parts if isinstance(p, TextPart)]
            if textos:
                # Answers rejected by the guardrail are overwritten by the next one.
                resposta = " ".join(textos)
    if resposta is not None:
        conversa.append(("assistant", resposta))
    return conversa


def salvar_mensagens(
    connection: sqlite3.Connection, phone: str | None, mensagens: list[ModelMessage]
) -> None:
    chave = normalize_phone(phone or "")
    if chave is None:
        return
    momento = agora()
    connection.execute(
        "INSERT INTO conversations (phone, created_at, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone) DO UPDATE SET updated_at = excluded.updated_at",
        (chave, momento, momento),
    )
    conversa = connection.execute("SELECT id FROM conversations WHERE phone = ?", (chave,)).fetchone()
    connection.executemany(
        "INSERT INTO messages (conversation_id, content, created_at) VALUES (?, ?, ?)",
        [
            (conversa["id"], ModelMessagesTypeAdapter.dump_json([m]).decode(), momento)
            for m in mensagens
        ],
    )
    connection.commit()


def carregar_estado(connection: sqlite3.Connection, phone: str | None) -> Estado:
    chave = normalize_phone(phone or "")
    row = connection.execute(
        "SELECT pedido_em_analise, produto_em_foco FROM conversation_state WHERE phone = ?",
        (chave,),
    ).fetchone()
    return Estado(row["pedido_em_analise"], row["produto_em_foco"]) if row else Estado()


def salvar_estado(connection: sqlite3.Connection, phone: str | None, estado: Estado) -> None:
    chave = normalize_phone(phone or "")
    if chave is None:
        return
    connection.execute(
        """
        INSERT INTO conversation_state (phone, pedido_em_analise, produto_em_foco, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (phone) DO UPDATE SET
            pedido_em_analise = excluded.pedido_em_analise,
            produto_em_foco = excluded.produto_em_foco,
            updated_at = excluded.updated_at
        """,
        (chave, estado.pedido_em_analise, estado.produto_em_foco, agora()),
    )
    connection.commit()
