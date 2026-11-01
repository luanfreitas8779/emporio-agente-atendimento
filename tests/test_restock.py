from src.catalog import buscar_produtos
from src.restock import repor_estoque
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
