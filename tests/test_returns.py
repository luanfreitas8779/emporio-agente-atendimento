from datetime import date

import pytest

from src.config import reference_date
from src.returns import avaliar_devolucao


def test_compra_online_tres_dias_apos_a_entrega_esta_dentro_do_prazo_de_arrependimento(connection):
    # Order 7 (customer 14): estimated delivery on 17/02/2026, 7-day deadline until 24/02/2026.
    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="arrependimento", canal="online",
        today=date(2026, 2, 20),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert [(r.name, r.resultado, r.prazo_ate) for r in veredito.regras] == [
        ("arrependimento", "dentro_do_prazo", "24/02/2026")
    ]


def test_pedido_7_com_a_data_padrao_esta_fora_do_prazo_de_arrependimento(connection, monkeypatch):
    monkeypatch.delenv("DATA_DE_REFERENCIA", raising=False)

    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="arrependimento", canal="online",
        today=reference_date(),
    )

    assert veredito.resultado == "fora_do_prazo"
    assert veredito.regras[0].prazo_ate == "24/02/2026"


def test_compra_presencial_nao_usa_a_regra_de_arrependimento_online(connection):
    # Within 7 days of delivery, but the purchase was made in the store (DQ-24).
    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="arrependimento", canal="presencial",
        today=date(2026, 2, 20),
    )

    assert veredito.resultado == "nao_se_aplica"
    assert veredito.regras == []
    assert any("compras online" in warning for warning in veredito.notices)


def test_arrependimento_sem_canal_pede_o_canal_de_compra(connection):
    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="arrependimento", canal=None,
        today=date(2026, 2, 20),
    )

    assert veredito.resultado == "faltam_dados"
    assert veredito.faltando == ["canal_de_compra"]
    assert veredito.regras == []


def test_pedido_7_com_defeito_esta_fora_dos_30_dias_e_dentro_da_garantia_legal(connection):
    # Purchase on 03/02/2026 (30 days until 05/03) and estimated delivery on 17/02/2026 (90 days until 18/05).
    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="defeito", canal=None,
        today=date(2026, 3, 25),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert [(r.name, r.resultado, r.prazo_ate) for r in veredito.regras] == [
        ("troca_por_defeito", "fora_do_prazo", "05/03/2026"),
        ("garantia_legal", "dentro_do_prazo", "18/05/2026"),
    ]


def test_pedido_de_outro_cliente_nao_e_avaliado(connection):
    # Order 7 belongs to customer 14.
    veredito = avaliar_devolucao(
        connection, customer_id=2, number=7, motivo="defeito", canal=None, today=date(2026, 3, 25),
    )

    assert veredito.resultado == "pedido_nao_encontrado"
    assert veredito.regras == []


@pytest.mark.parametrize(
    "customer, number, warning",
    [
        (8, 13, "ainda não foi enviado"),
        (6, 9, "ainda não foi enviado"),
        (15, 17, "foi cancelado"),
    ],
)
def test_pedido_sem_entrega_nao_tem_o_que_devolver(connection, customer, number, warning):
    veredito = avaliar_devolucao(
        connection, customer_id=customer, number=number, motivo="defeito", canal=None,
        today=date(2026, 3, 25),
    )

    assert veredito.resultado == "nao_se_aplica"
    assert veredito.regras == []
    assert any(warning in a for a in veredito.notices)


def test_troca_por_preferencia_vale_7_dias_a_partir_do_recebimento(connection):
    dentro = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="preferencia", canal=None, today=date(2026, 2, 24),
    )
    fora = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="preferencia", canal=None, today=date(2026, 2, 25),
    )

    assert [(r.name, r.prazo_ate) for r in dentro.regras] == [("troca_por_preferencia", "24/02/2026")]
    assert (dentro.resultado, fora.resultado) == ("dentro_do_prazo", "fora_do_prazo")


def test_veredito_informa_que_o_recebimento_e_aproximado_e_depende_da_analise_do_produto(connection):
    veredito = avaliar_devolucao(
        connection, customer_id=14, number=7, motivo="arrependimento", canal="online",
        today=date(2026, 2, 20),
    )

    assert veredito.data_aproximada is True
    assert veredito.data_de_recebimento == "17/02/2026"
    assert any("entrega estimada" in a for a in veredito.notices)
    assert any("análise do produto" in a for a in veredito.notices)
    assert veredito.reference_date == "20/02/2026"


@pytest.mark.parametrize("canal", [None, "presencial", "online"])
@pytest.mark.regression
def test_pedido_de_outro_cliente_volta_como_nao_encontrado_em_arrependimento_com_qualquer_canal(
    connection, canal
):
    # Order 7 belongs to customer 14, and order 999 does not exist.
    for number in (7, 999):
        veredito = avaliar_devolucao(
            connection, customer_id=2, number=number, motivo="arrependimento", canal=canal,
            today=date(2026, 2, 20),
        )

        assert veredito.resultado == "pedido_nao_encontrado"
        assert veredito.faltando == []


def test_pedido_enviado_com_entrega_estimada_futura_avisa_que_o_prazo_conta_do_recebimento(connection):
    # Order 8 (customer 2): shipped, estimated delivery on 28/02/2026.
    veredito = avaliar_devolucao(
        connection, customer_id=2, number=8, motivo="arrependimento", canal="online",
        today=date(2026, 2, 20),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert any("ainda não chegou" in warning for warning in veredito.notices)


def test_pedido_cuja_entrega_estimada_ja_passou_nao_recebe_o_aviso_de_pedido_a_caminho(connection):
    veredito = avaliar_devolucao(
        connection, customer_id=2, number=8, motivo="arrependimento", canal="online",
        today=date(2026, 3, 25),
    )

    assert veredito.resultado == "fora_do_prazo"
    assert not any("ainda não chegou" in warning for warning in veredito.notices)
