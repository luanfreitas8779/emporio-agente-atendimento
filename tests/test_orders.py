from datetime import date

import pytest

from src.orders import consultar_pedidos, identificar_cliente


def test_identifica_o_cliente_pelo_telefone_com_mascara(conexao):
    cliente = identificar_cliente(conexao, "(67) 99654-7821")

    assert cliente is not None
    assert cliente.id == 2
    assert cliente.nome == "Ana Carolina Ferreira"


def test_telefone_sem_cadastro_nao_identifica_ninguem(conexao):
    assert identificar_cliente(conexao, "(67) 90000-0000") is None


def test_identifica_o_cliente_pelo_telefone_so_com_digitos(conexao):
    cliente = identificar_cliente(conexao, "67996547821")

    assert cliente is not None
    assert cliente.id == 2


def test_cliente_2_consulta_o_pedido_8_com_status_e_rastreio(conexao):
    (pedido,) = consultar_pedidos(conexao, cliente_id=2, numero=8)

    assert pedido.numero == 8
    assert pedido.status == "shipped"
    assert pedido.rastreio == "BRJL5544332BR"
    assert pedido.entrega_estimada == "28/02/2026"


def test_pedido_de_outro_cliente_e_tratado_como_nao_encontrado(conexao):
    # Order 5 belongs to customer 5.
    assert consultar_pedidos(conexao, cliente_id=2, numero=5) == []


def test_sem_numero_lista_apenas_os_pedidos_do_cliente(conexao):
    pedidos = consultar_pedidos(conexao, cliente_id=3)

    assert [p.numero for p in pedidos] == [1, 19]


def test_pedido_mostra_itens_data_e_pagamento(conexao):
    (pedido,) = consultar_pedidos(conexao, cliente_id=2, numero=8)

    assert pedido.order_date == "15/02/2026"
    assert pedido.pagamento == "débito"
    assert [(i.nome, i.quantidade) for i in pedido.itens] == [("Kala KA-C Concert Mogno", 1)]


def test_exibe_o_total_registrado_mesmo_quando_difere_da_soma_dos_itens(conexao):
    # Order 3: 2 x R$ 1.749,00 add up to R$ 3.498,00, but the recorded total is R$ 3.450,00.
    (pedido,) = consultar_pedidos(conexao, cliente_id=12, numero=3)

    assert pedido.total == "R$ 3.450,00"
    assert pedido.pagamento == "cartão de crédito em 12x"
    assert [(i.nome, i.quantidade) for i in pedido.itens] == [
        ("Kala KA-ABP-CTG Barítono Cedar", 2)
    ]


def test_identifica_o_cliente_pelo_telefone_com_codigo_do_pais(conexao):
    for phone in ("+55 (67) 99654-7821", "5567996547821"):
        cliente = identificar_cliente(conexao, phone)

        assert cliente is not None
        assert cliente.id == 2


def test_telefone_incompleto_nao_identifica_ninguem(conexao):
    assert identificar_cliente(conexao, "99654-7821") is None
    assert identificar_cliente(conexao, "") is None


def test_o_cliente_informa_o_primeiro_nome(conexao):
    cliente = identificar_cliente(conexao, "(67) 99654-7821")

    assert cliente.primeiro_nome == "Ana"


@pytest.mark.parametrize(
    "cliente, numero, situacao",
    [
        (3, 1, "entregue"),
        (6, 9, "confirmado"),
        (8, 13, "pendente"),
        (2, 8, "enviado"),
        (15, 17, "cancelado"),
    ],
)
def test_pedido_traz_a_situacao_traduzida_em_codigo(conexao, cliente, numero, situacao):
    (pedido,) = consultar_pedidos(conexao, cliente_id=cliente, numero=numero)

    assert pedido.situacao == situacao


@pytest.mark.regressao
def test_pedido_enviado_depois_da_entrega_estimada_informa_os_dias_de_atraso(conexao):
    # Order 8: shipped, estimated delivery on 28/02/2026 (DQ-16).
    (pedido,) = consultar_pedidos(conexao, cliente_id=2, numero=8, hoje=date(2026, 3, 25))

    assert pedido.atraso == "A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso."


def test_pedido_dentro_da_previsao_nao_tem_atraso(conexao):
    (pedido,) = consultar_pedidos(conexao, cliente_id=2, numero=8, hoje=date(2026, 2, 28))

    assert pedido.atraso is None
