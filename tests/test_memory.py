import sqlite3

import pytest

from src.database import conectar
from src.memory import Estado, carregar_estado, criar_tabelas, salvar_estado

TELEFONE = "67996547821"

# Esquemas de conversation_state criados em versões anteriores do projeto.
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
@pytest.mark.regressao
def test_banco_anterior_continua_funcionando_sem_migracao(tmp_path, esquema):
    conexao = conectar(tmp_path / "antigo.db")
    conexao.executescript(esquema)

    criar_tabelas(conexao)

    assert carregar_estado(conexao, TELEFONE) == Estado(8, 96)
    salvar_estado(conexao, TELEFONE, Estado(7, None))
    assert carregar_estado(conexao, TELEFONE) == Estado(7, None)
    conexao.close()


@pytest.mark.parametrize(
    "produto, status",
    [(0, "pending"), (-1, "pending"), (96, "notified")],
)
def test_tabela_de_interesses_recusa_valores_invalidos(tmp_path, produto, status):
    conexao = conectar(tmp_path / "novo.db")
    criar_tabelas(conexao)

    with pytest.raises(sqlite3.IntegrityError):
        conexao.execute(
            "INSERT INTO product_interests (phone, product_id, status, created_at) "
            "VALUES ('67996547821', ?, ?, '2026-03-25')",
            (produto, status),
        )
    conexao.close()
