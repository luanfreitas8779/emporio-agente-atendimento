import pytest

from src.catalog import search_products
from src.database import connect
from src.load_data import carregar_dados
from src.restock import ErroDeReposicao, principal, repor_estoque
from tests.conftest import DATA_DIR

GIANNINI_GF_3D = 96


def test_reposicao_deixa_o_giannini_gf_3d_disponivel_sem_alterar_a_origem(connection):
    csv_antes = (DATA_DIR / "products.csv").read_bytes()
    (antes,) = search_products(connection, "Giannini GF-3D")
    assert antes.availability == "indisponivel"

    repor_estoque(connection, GIANNINI_GF_3D, 5)

    (depois,) = search_products(connection, "Giannini GF-3D")
    assert depois.availability == "disponivel"
    assert (DATA_DIR / "products.csv").read_bytes() == csv_antes


def test_recusa_produto_inexistente(connection):
    with pytest.raises(ErroDeReposicao, match="does not exist"):
        repor_estoque(connection, 99999, 5)


@pytest.mark.parametrize("quantity", [0, -3])
def test_recusa_quantidade_menor_que_um(connection, quantity):
    with pytest.raises(ErroDeReposicao, match="quantity"):
        repor_estoque(connection, GIANNINI_GF_3D, quantity)

    (product,) = search_products(connection, "Giannini GF-3D")
    assert product.availability == "indisponivel"


@pytest.mark.parametrize("product", [130, 136])  # new release and discontinued
def test_recusa_produto_que_nao_esta_ativo(connection, product):
    with pytest.raises(ErroDeReposicao, match="not active"):
        repor_estoque(connection, product, 5)


def test_comando_repoe_o_banco_indicado_e_a_carga_volta_ao_original(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    connection = connect(banco)
    carregar_dados(connection, DATA_DIR)

    codigo = principal(["96", "--quantity", "3", "--banco", str(banco)])

    assert codigo == 0
    assert "3" in capsys.readouterr().out
    assert search_products(connection, "Giannini GF-3D")[0].availability == "disponivel"

    carregar_dados(connection, DATA_DIR)
    assert search_products(connection, "Giannini GF-3D")[0].availability == "indisponivel"
    connection.close()


def test_comando_informa_o_motivo_da_recusa_sem_traceback(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    connection = connect(banco)
    carregar_dados(connection, DATA_DIR)
    connection.close()

    codigo = principal(["99999", "--banco", str(banco)])

    assert codigo == 1
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.regression
def test_comando_nao_cria_banco_quando_ele_nao_existe(tmp_path, capsys):
    banco = tmp_path / "ausente.db"

    codigo = principal(["96", "--banco", str(banco)])

    assert codigo == 1
    assert "python -m src.load_data" in capsys.readouterr().err
    assert not banco.exists()
