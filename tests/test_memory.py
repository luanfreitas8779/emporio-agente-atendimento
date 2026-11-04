import sqlite3

import pytest

from src.database import connect
from src.memory import ConversationState, load_state, create_tables, save_state

PHONE = "67996547821"

# conversation_state schemas created in previous versions of the project.
SCHEMA_WITH_OLD_COLUMN = """
CREATE TABLE conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    pergunta_pendente TEXT,
    updated_at TEXT NOT NULL
);
INSERT INTO conversation_state
VALUES ('67996547821', 8, 96, 'canal_de_compra', '2026-03-01T00:00:00+00:00');
"""
SCHEMA_WITHOUT_COLUMN = """
CREATE TABLE conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    updated_at TEXT NOT NULL
);
INSERT INTO conversation_state VALUES ('67996547821', 8, 96, '2026-03-01T00:00:00+00:00');
"""


@pytest.mark.parametrize("schema", [SCHEMA_WITH_OLD_COLUMN, SCHEMA_WITHOUT_COLUMN])
@pytest.mark.regression
def test_previous_database_keeps_working_without_migration(tmp_path, schema):
    previous = sqlite3.connect(tmp_path / "antigo.db")
    previous.executescript(schema)
    previous.close()

    connection = connect(tmp_path / "antigo.db")

    assert load_state(connection, PHONE) == ConversationState(8, 96)
    save_state(connection, PHONE, ConversationState(7, None))
    assert load_state(connection, PHONE) == ConversationState(7, None)
    connection.close()


@pytest.mark.parametrize(
    "product, status",
    [(0, "pending"), (-1, "pending"), (96, "notified")],
)
def test_interests_table_rejects_invalid_values(tmp_path, product, status):
    connection = connect(tmp_path / "novo.db")
    create_tables(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO product_interests (phone, product_id, status, created_at) "
            "VALUES ('67996547821', ?, ?, '2026-03-25')",
            (product, status),
        )
    connection.close()


@pytest.mark.parametrize("reason, summary", [("outro", "Resumo."), ("reclamacao", "")])
def test_handoffs_table_rejects_unknown_reason_and_empty_summary(tmp_path, reason, summary):
    connection = connect(tmp_path / "novo.db")
    create_tables(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO handoffs (phone, reason, summary, created_at) "
            "VALUES ('67996547821', ?, ?, '2026-03-25')",
            (reason, summary),
        )
    connection.close()


@pytest.mark.regression
def test_new_database_already_stores_the_conversation_without_a_setup_step(tmp_path):
    connection = connect(tmp_path / "novo.db")

    save_state(connection, PHONE, ConversationState(order_under_review=8))

    assert load_state(connection, PHONE) == ConversationState(order_under_review=8)
    connection.close()
