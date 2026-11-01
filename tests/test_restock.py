import pytest

from src.catalog import buscar_produtos
from src.database import conectar
from src.load_data import carregar_dados
from src.restock import ErroDeReposicao, principal, repor_estoque
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


def test_comando_repoe_o_banco_indicado_e_a_carga_volta_ao_original(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    conexao = conectar(banco)
    carregar_dados(conexao, PASTA_DADOS)

    codigo = principal(["96", "--quantidade", "3", "--banco", str(banco)])

    assert codigo == 0
    assert "3" in capsys.readouterr().out
    assert buscar_produtos(conexao, "Giannini GF-3D")[0].disponibilidade == "disponivel"

    carregar_dados(conexao, PASTA_DADOS)
    assert buscar_produtos(conexao, "Giannini GF-3D")[0].disponibilidade == "indisponivel"
    conexao.close()


def test_comando_informa_o_motivo_da_recusa_sem_traceback(tmp_path, capsys):
    banco = tmp_path / "comando.db"
    conexao = conectar(banco)
    carregar_dados(conexao, PASTA_DADOS)
    conexao.close()

    codigo = principal(["99999", "--banco", str(banco)])

    assert codigo == 1
    assert "inexistente" in capsys.readouterr().err


@pytest.mark.regressao
def test_comando_nao_cria_banco_quando_ele_nao_existe(tmp_path, capsys):
    banco = tmp_path / "ausente.db"

    codigo = principal(["96", "--banco", str(banco)])

    assert codigo == 1
    assert "python -m src.load_data" in capsys.readouterr().err
    assert not banco.exists()
