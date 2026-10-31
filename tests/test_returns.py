from datetime import date

from src.config import data_de_referencia
from src.returns import avaliar_devolucao


def test_compra_online_tres_dias_apos_a_entrega_esta_dentro_do_prazo_de_arrependimento(conexao):
    # Pedido 7 (cliente 14): entrega estimada em 17/02/2026, prazo de 7 dias até 24/02/2026.
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal="online",
        hoje=date(2026, 2, 20),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert [(r.nome, r.resultado, r.prazo_ate) for r in veredito.regras] == [
        ("arrependimento", "dentro_do_prazo", "24/02/2026")
    ]


def test_pedido_7_com_a_data_padrao_esta_fora_do_prazo_de_arrependimento(conexao, monkeypatch):
    monkeypatch.delenv("DATA_DE_REFERENCIA", raising=False)

    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal="online",
        hoje=data_de_referencia(),
    )

    assert veredito.resultado == "fora_do_prazo"
    assert veredito.regras[0].prazo_ate == "24/02/2026"
