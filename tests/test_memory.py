from src.database import conectar
from src.memory import Estado, carregar_estado, criar_tabelas, salvar_estado

TELEFONE = "67996547821"

# Esquema de conversation_state antes da issue #6, sem pergunta_pendente.
ESQUEMA_ANTIGO = """
CREATE TABLE conversation_state (
    phone TEXT PRIMARY KEY,
    pedido_em_analise INTEGER CHECK (pedido_em_analise > 0),
    produto_em_foco INTEGER CHECK (produto_em_foco > 0),
    updated_at TEXT NOT NULL
);
INSERT INTO conversation_state VALUES ('67996547821', 8, 96, '2026-03-01T00:00:00+00:00');
"""


def test_banco_anterior_ganha_a_pergunta_pendente_sem_perder_o_estado(tmp_path):
    conexao = conectar(tmp_path / "antigo.db")
    conexao.executescript(ESQUEMA_ANTIGO)

    criar_tabelas(conexao)
    criar_tabelas(conexao)  # idempotente

    assert carregar_estado(conexao, TELEFONE) == Estado(8, 96, None)
    salvar_estado(conexao, TELEFONE, Estado(8, 96, "canal_de_compra"))
    assert carregar_estado(conexao, TELEFONE) == Estado(8, 96, "canal_de_compra")
    conexao.close()
