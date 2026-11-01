import pytest

from src.catalog import buscar_produtos
from src.restock import ErroDeReposicao, repor_estoque
from tests.conftest import PASTA_DADOS

GIANNINI_GF_3D = 96


def test_reposicao_deixa_o_giannini_gf_3d_disponivel_sem_alterar_a_origem(conexao):
    csv_antes = (PASTA_DADOS / "products.csv").read_bytes()
    (antes,) = buscar_produtos(conexao, "Giannini GF-3D")
    assert antes.disponibilidade == "indisponivel"

    repor_estoque(conexao, GIANNINI_GF_3D, 5)

    (depois,) = buscar_produtos(conexao, "Giannini GF-3D")
    assert depois.disponibilidade == "disponivel"
    assert (PASTA_DADOS / "products.csv").read_bytes() == csv_antes


def test_recusa_produto_inexistente(conexao):
    with pytest.raises(ErroDeReposicao, match="inexistente"):
        repor_estoque(conexao, 99999, 5)


@pytest.mark.parametrize("quantidade", [0, -3])
def test_recusa_quantidade_menor_que_um(conexao, quantidade):
    with pytest.raises(ErroDeReposicao, match="quantidade"):
        repor_estoque(conexao, GIANNINI_GF_3D, quantidade)

    (produto,) = buscar_produtos(conexao, "Giannini GF-3D")
    assert produto.disponibilidade == "indisponivel"


@pytest.mark.parametrize("produto", [130, 136])  # lançamento e fora de catálogo
def test_recusa_produto_que_nao_esta_ativo(conexao, produto):
    with pytest.raises(ErroDeReposicao, match="ativo"):
        repor_estoque(conexao, produto, 5)
