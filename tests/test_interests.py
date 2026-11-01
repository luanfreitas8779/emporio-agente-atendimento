from src.interests import Resultado, listar_pendentes, registrar

TELEFONE = "(67) 99654-7821"
GIANNINI_GF_3D = 96


def test_registra_interesse_no_giannini_gf_3d(conexao):
    resultado = registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    assert resultado == Resultado.REGISTRADO
    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_repetir_o_pedido_nao_duplica_o_interesse(conexao):
    registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    # Outra formatação do mesmo telefone é o mesmo cliente.
    resultado = registrar(conexao, "67996547821", GIANNINI_GF_3D)

    assert resultado == Resultado.JA_REGISTRADO
    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]
