import pytest

from src.interests import Resultado, listar_pendentes, registrar
from src.load_data import carregar_dados
from tests.conftest import PASTA_DADOS

TELEFONE = "(67) 99654-7821"
GIANNINI_GF_3D = 96


def test_registra_interesse_no_giannini_gf_3d(conexao):
    resultado = registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    assert resultado == Resultado.REGISTRADO
    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_produto_inexistente_nao_grava_interesse(conexao):
    resultado = registrar(conexao, TELEFONE, 99999)

    assert resultado == Resultado.PRODUTO_INEXISTENTE
    assert listar_pendentes(conexao, TELEFONE) == []
    assert conexao.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


@pytest.mark.parametrize("telefone", ["", "12345", "abc"])
def test_telefone_invalido_nao_grava_interesse(conexao, telefone):
    resultado = registrar(conexao, telefone, GIANNINI_GF_3D)

    assert resultado == Resultado.TELEFONE_INVALIDO
    assert conexao.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


def test_repetir_o_pedido_nao_duplica_o_interesse(conexao):
    registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    # Outra formatação do mesmo telefone é o mesmo cliente.
    resultado = registrar(conexao, "67996547821", GIANNINI_GF_3D)

    assert resultado == Resultado.JA_REGISTRADO
    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_nova_carga_dos_dados_preserva_os_interesses(conexao):
    registrar(conexao, TELEFONE, GIANNINI_GF_3D)

    carregar_dados(conexao, PASTA_DADOS)

    assert listar_pendentes(conexao, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]
