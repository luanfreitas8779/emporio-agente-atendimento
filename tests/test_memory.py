import sqlite3

import pytest

from src.database import connect
from src.memory import Estado, carregar_estado, create_tables, salvar_estado

PHONE = "67996547821"

# conversation_state schemas created in previous versions of the project.
ESQUEMA_COM_COLUNA_ANTIGA = """
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
ESQUEMA_SEM_COLUNA = """
CREATE TABLE conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    updated_at TEXT NOT NULL
);
INSERT INTO conversation_state VALUES ('67996547821', 8, 96, '2026-03-01T00:00:00+00:00');
"""


@pytest.mark.parametrize("esquema", [ESQUEMA_COM_COLUNA_ANTIGA, ESQUEMA_SEM_COLUNA])
@pytest.mark.regression
def test_banco_anterior_continua_funcionando_sem_migracao(tmp_path, esquema):
    previous = sqlite3.connect(tmp_path / "antigo.db")
    previous.executescript(esquema)
    previous.close()

    connection = connect(tmp_path / "antigo.db")

    assert carregar_estado(connection, PHONE) == Estado(8, 96)
    salvar_estado(connection, PHONE, Estado(7, None))
    assert carregar_estado(connection, PHONE) == Estado(7, None)
    connection.close()


@pytest.mark.parametrize(
    "product, status",
    [(0, "pending"), (-1, "pending"), (96, "notified")],
)
def test_tabela_de_interesses_recusa_valores_invalidos(tmp_path, product, status):
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
def test_tabela_de_encaminhamentos_recusa_motivo_desconhecido_e_resumo_vazio(tmp_path, reason, summary):
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
def test_banco_novo_ja_guarda_a_conversa_sem_etapa_de_preparo(tmp_path):
    connection = connect(tmp_path / "novo.db")

    salvar_estado(connection, PHONE, Estado(pedido_em_analise=8))

    assert carregar_estado(connection, PHONE) == Estado(pedido_em_analise=8)
    connection.close()
