from datetime import date

import pytest

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
    assert any("compras online" in aviso for aviso in veredito.avisos)


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


@pytest.mark.parametrize(
    "cliente, numero, aviso",
    [
        (8, 13, "ainda não foi enviado"),
        (6, 9, "ainda não foi enviado"),
        (15, 17, "foi cancelado"),
    ],
)
def test_pedido_sem_entrega_nao_tem_o_que_devolver(conexao, cliente, numero, aviso):
    veredito = avaliar_devolucao(
        conexao, cliente_id=cliente, numero=numero, motivo="defeito", canal=None,
        hoje=date(2026, 3, 25),
    )

    assert veredito.resultado == "nao_se_aplica"
    assert veredito.regras == []
    assert any(aviso in a for a in veredito.avisos)


def test_troca_por_preferencia_vale_7_dias_a_partir_do_recebimento(conexao):
    dentro = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="preferencia", canal=None, hoje=date(2026, 2, 24),
    )
    fora = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="preferencia", canal=None, hoje=date(2026, 2, 25),
    )

    assert [(r.nome, r.prazo_ate) for r in dentro.regras] == [("troca_por_preferencia", "24/02/2026")]
    assert (dentro.resultado, fora.resultado) == ("dentro_do_prazo", "fora_do_prazo")


def test_veredito_informa_que_o_recebimento_e_aproximado_e_depende_da_analise_do_produto(conexao):
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal="online",
        hoje=date(2026, 2, 20),
    )

    assert veredito.data_aproximada is True
    assert veredito.data_de_recebimento == "17/02/2026"
    assert any("entrega estimada" in a for a in veredito.avisos)
    assert any("análise do produto" in a for a in veredito.avisos)
    assert veredito.data_de_referencia == "20/02/2026"


@pytest.mark.parametrize("canal", [None, "presencial", "online"])
def test_pedido_de_outro_cliente_volta_como_nao_encontrado_em_arrependimento_com_qualquer_canal(
    conexao, canal
):
    # O pedido 7 pertence ao cliente 14, e o pedido 999 não existe.
    for numero in (7, 999):
        veredito = avaliar_devolucao(
            conexao, cliente_id=2, numero=numero, motivo="arrependimento", canal=canal,
            hoje=date(2026, 2, 20),
        )

        assert veredito.resultado == "pedido_nao_encontrado"
        assert veredito.faltando == []
