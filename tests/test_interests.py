from src.interests import Resultado, listar_pendentes, registrar

TELEFONE = "(67) 99654-7821"
GIANNINI_GF_3D = 96


def test_registra_interesse_no_giannini_gf_3d(conexao):
    resultado = registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    assert resultado == Resultado.REGISTRADO
    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]
