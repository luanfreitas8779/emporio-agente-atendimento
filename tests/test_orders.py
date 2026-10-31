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
    assert pedido.entrega_estimada == "2026-02-28"
