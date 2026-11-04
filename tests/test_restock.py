import pytest

from src.catalog import buscar_produtos
from src.database import connect
from src.load_data import carregar_dados
from src.restock import ErroDeReposicao, principal, repor_estoque
from tests.conftest import PASTA_DADOS

GIANNINI_GF_3D = 96


def test_reposicao_deixa_o_giannini_gf_3d_disponivel_sem_alterar_a_origem(connection):
    csv_antes = (PASTA_DADOS / "products.csv").read_bytes()
    (antes,) = buscar_produtos(connection, "Giannini GF-3D")
    assert antes.disponibilidade == "indisponivel"

    repor_estoque(connection, GIANNINI_GF_3D, 5)

    (depois,) = buscar_produtos(connection, "Giannini GF-3D")
    assert depois.disponibilidade == "disponivel"
    assert (PASTA_DADOS / "products.csv").read_bytes() == csv_antes


def test_recusa_produto_inexistente(connection):
    with pytest.raises(ErroDeReposicao, match="does not exist"):
        repor_estoque(connection, 99999, 5)


@pytest.mark.parametrize("quantidade", [0, -3])
def test_recusa_quantidade_menor_que_um(connection, quantidade):
    with pytest.raises(ErroDeReposicao, match="quantity"):
        repor_estoque(connection, GIANNINI_GF_3D, quantidade)

    (produto,) = buscar_produtos(connection, "Giannini GF-3D")
    assert produto.disponibilidade == "indisponivel"


@pytest.mark.parametrize("produto", [130, 136])  # new release and discontinued
def test_recusa_produto_que_nao_esta_ativo(connection, produto):
    with pytest.raises(ErroDeReposicao, match="not active"):
        repor_estoque(connection, produto, 5)


def test_comando_repoe_o_banco_indicado_e_a_carga_volta_ao_original(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    connection = connect(banco)
    carregar_dados(connection, PASTA_DADOS)

    codigo = principal(["96", "--quantidade", "3", "--banco", str(banco)])

    assert codigo == 0
    assert "3" in capsys.readouterr().out
    assert buscar_produtos(connection, "Giannini GF-3D")[0].disponibilidade == "disponivel"

    carregar_dados(connection, PASTA_DADOS)
    assert buscar_produtos(connection, "Giannini GF-3D")[0].disponibilidade == "indisponivel"
    connection.close()


def test_comando_informa_o_motivo_da_recusa_sem_traceback(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    connection = connect(banco)
    carregar_dados(connection, PASTA_DADOS)
    connection.close()

    codigo = principal(["99999", "--banco", str(banco)])

    assert codigo == 1
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.regressao
def test_comando_nao_cria_banco_quando_ele_nao_existe(tmp_path, capsys):
    banco = tmp_path / "ausente.db"

    codigo = principal(["96", "--banco", str(banco)])

    assert codigo == 1
    assert "python -m src.load_data" in capsys.readouterr().err
    assert not banco.exists()
