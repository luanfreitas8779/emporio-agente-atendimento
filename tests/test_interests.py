import pytest

from src.interests import Result, listar_pendentes, registrar
from src.load_data import carregar_dados
from tests.conftest import DATA_DIR

TELEFONE = "(67) 99654-7821"
GIANNINI_GF_3D = 96


def test_registra_interesse_no_giannini_gf_3d(connection):
    result = registrar(connection, TELEFONE, GIANNINI_GF_3D)

    assert result == Result.REGISTRADO
    assert listar_pendentes(connection, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_produto_inexistente_nao_grava_interesse(connection):
    result = registrar(connection, TELEFONE, 99999)

    assert result == Result.PRODUTO_INEXISTENTE
    assert listar_pendentes(connection, TELEFONE) == []
    assert connection.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


@pytest.mark.parametrize("phone", ["", "12345", "abc"])
def test_telefone_invalido_nao_grava_interesse(connection, phone):
    result = registrar(connection, phone, GIANNINI_GF_3D)

    assert result == Result.TELEFONE_INVALIDO
    assert connection.execute("SELECT COUNT(*) FROM product_interests").fetchone()[0] == 0


def test_repetir_o_pedido_nao_duplica_o_interesse(connection):
    registrar(connection, TELEFONE, GIANNINI_GF_3D)

    # Another formatting of the same phone number is the same customer.
    result = registrar(connection, "67996547821", GIANNINI_GF_3D)

    assert result == Result.JA_REGISTRADO
    assert listar_pendentes(connection, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]


def test_nova_carga_dos_dados_preserva_os_interesses(connection):
    registrar(connection, TELEFONE, GIANNINI_GF_3D)

    carregar_dados(connection, DATA_DIR)

    assert listar_pendentes(connection, TELEFONE) == ["Giannini GF-3D Dreadnought Sunburst"]
