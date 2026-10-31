from src.catalog import buscar_produtos


def test_informa_o_preco_do_takamine_gd20(conexao):
    produtos = buscar_produtos(conexao, termo="Takamine GD20")

    assert len(produtos) == 1
    assert produtos[0].nome == "Takamine GD20 Dreadnought Natural"
    assert produtos[0].categoria == "Violões"
    assert produtos[0].preco == "R$ 2.199,00"
