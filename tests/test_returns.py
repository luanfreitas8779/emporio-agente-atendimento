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


def test_compra_presencial_nao_usa_a_regra_de_arrependimento_online(conexao):
    # Dentro de 7 dias da entrega, mas a compra foi na loja (DQ-24).
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal="presencial",
        hoje=date(2026, 2, 20),
    )

    assert veredito.resultado == "nao_se_aplica"
    assert veredito.regras == []


def test_arrependimento_sem_canal_pede_o_canal_de_compra(conexao):
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal=None,
        hoje=date(2026, 2, 20),
    )

    assert veredito.resultado == "faltam_dados"
    assert veredito.faltando == ["canal_de_compra"]
    assert veredito.regras == []


def test_pedido_7_com_defeito_esta_fora_dos_30_dias_e_dentro_da_garantia_legal(conexao):
    # Compra em 03/02/2026 (30 dias até 05/03) e entrega estimada em 17/02/2026 (90 dias até 18/05).
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="defeito", canal=None,
        hoje=date(2026, 3, 25),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert [(r.nome, r.resultado, r.prazo_ate) for r in veredito.regras] == [
        ("troca_por_defeito", "fora_do_prazo", "05/03/2026"),
        ("garantia_legal", "dentro_do_prazo", "18/05/2026"),
    ]


def test_pedido_de_outro_cliente_nao_e_avaliado(conexao):
    # O pedido 7 pertence ao cliente 14.
    veredito = avaliar_devolucao(
        conexao, cliente_id=2, numero=7, motivo="defeito", canal=None, hoje=date(2026, 3, 25),
    )

    assert veredito.resultado == "pedido_nao_encontrado"
    assert veredito.regras == []
