from src.orders import identificar_cliente


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
