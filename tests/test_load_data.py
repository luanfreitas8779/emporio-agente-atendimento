import pytest

from src.catalog import buscar_produtos
from src.database import conectar
from src.load_data import ErroDeCarga, carregar_catalogo
from tests.conftest import PASTA_DADOS


def escrever_catalogo(pasta, produto):
    (pasta / "categories.csv").write_text(
        "category_id,name,description\n1,Guitarras,Elétricas\n", encoding="utf-8"
    )
    (pasta / "products.csv").write_text(
        "product_id,price_brl,name,category_id,description,stock_quantity,status,specs,created_at\n"
        f"{produto}\n",
        encoding="utf-8",
    )


def test_recarregar_recria_o_catalogo_sem_duplicar_produtos(conexao):
    carregar_catalogo(conexao, PASTA_DADOS)

    assert len(buscar_produtos(conexao, termo="Takamine GD20")) == 1


def test_interrompe_a_carga_quando_o_produto_aponta_para_categoria_inexistente(tmp_path):
    escrever_catalogo(tmp_path, '10,100,Guitarra Teste,99,Descricao,1,active,{},2024-01-01')
    conexao = conectar(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="produto 10"):
        carregar_catalogo(conexao, tmp_path)

    conexao.close()


def test_interrompe_a_carga_quando_o_preco_e_invalido(tmp_path):
    escrever_catalogo(tmp_path, '10,abc,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    conexao = conectar(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="produto 10"):
        carregar_catalogo(conexao, tmp_path)

    conexao.close()
