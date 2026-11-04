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
SCHEMA = """
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

MAX_HISTORY_MESSAGES = 30


@dataclass
class ConversationState:
    """What needs to carry across messages, kept in code and not in the model's memory."""

    order_under_review: int | None = None
    product_in_focus: int | None = None


def create_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _starts_a_turn(message: ModelMessage) -> bool:
    # A request with the customer's message and no tool result does not answer
    # any previous call: it is a safe point to start the history.
    return isinstance(message, ModelRequest) and (
        any(isinstance(p, UserPromptPart) for p in message.parts)
        and not any(isinstance(p, ToolReturnPart) for p in message.parts)
    )


def trim_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Keeps the latest messages without separating a tool call from its result.

    The cut starts at the first whole turn that fits the limit; a turn that
    exceeds the limit is discarded entirely.
    """
    start = max(0, len(messages) - MAX_HISTORY_MESSAGES)
    for i in range(start, len(messages)):
        if _starts_a_turn(messages[i]):
            return messages[i:]
    return []


def _read_messages(connection: sqlite3.Connection, phone: str | None) -> list[ModelMessage]:
    key = normalize_phone(phone or "")
    if key is None:
        return []
    rows = connection.execute(
        """
        SELECT m.content FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.phone = ? ORDER BY m.id
        """,
        (key,),
    ).fetchall()
    messages: list[ModelMessage] = []
    for row in rows:
        try:
            messages.extend(ModelMessagesTypeAdapter.validate_json(row["content"]))
        except ValidationError:
            # An unreadable row cannot block the service or leave a turn
            # half-done: the history starts again after it.
            messages = []
    return messages


def load_history(connection: sqlite3.Connection, phone: str | None) -> list[ModelMessage]:
    return trim_history(_read_messages(connection, phone))


def conversation_for_display(connection: sqlite3.Connection, phone: str | None) -> list[tuple[str, str]]:
    """The customer's message and the final answer of each turn, as the customer saw them."""
    conversation: list[tuple[str, str]] = []
    answer: str | None = None
    for message in _read_messages(connection, phone):
        if _starts_a_turn(message):
            if answer is not None:
                conversation.append(("assistant", answer))
                answer = None
            text = " ".join(
                str(p.content) for p in message.parts if isinstance(p, UserPromptPart)
            )
            conversation.append(("user", text))
        elif isinstance(message, ModelResponse):
            texts = [p.content for p in message.parts if isinstance(p, TextPart)]
            if texts:
                # Answers rejected by the guardrail are overwritten by the next one.
                answer = " ".join(texts)
    if answer is not None:
        conversation.append(("assistant", answer))
    return conversation


def save_messages(
    connection: sqlite3.Connection, phone: str | None, messages: list[ModelMessage]
) -> None:
    key = normalize_phone(phone or "")
    if key is None:
        return
    moment_iso = now_iso()
    connection.execute(
        "INSERT INTO conversations (phone, created_at, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone) DO UPDATE SET updated_at = excluded.updated_at",
        (key, moment_iso, moment_iso),
    )
    conversation = connection.execute("SELECT id FROM conversations WHERE phone = ?", (key,)).fetchone()
    connection.executemany(
        "INSERT INTO messages (conversation_id, content, created_at) VALUES (?, ?, ?)",
        [
            (conversation["id"], ModelMessagesTypeAdapter.dump_json([m]).decode(), moment_iso)
            for m in messages
        ],
    )
    connection.commit()


def load_state(connection: sqlite3.Connection, phone: str | None) -> ConversationState:
    key = normalize_phone(phone or "")
    row = connection.execute(
        "SELECT pedido_em_analise, produto_em_foco FROM conversation_state WHERE phone = ?",
        (key,),
    ).fetchone()
    return ConversationState(row["pedido_em_analise"], row["produto_em_foco"]) if row else ConversationState()


def save_state(connection: sqlite3.Connection, phone: str | None, state: ConversationState) -> None:
    key = normalize_phone(phone or "")
    if key is None:
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
        (key, state.order_under_review, state.product_in_focus, now_iso()),
    )
    connection.commit()
