from src.catalog import buscar_produtos


def test_informa_o_preco_do_takamine_gd20(conexao):
    produtos = buscar_produtos(conexao, termo="Takamine GD20")

    assert len(produtos) == 1
    assert produtos[0].nome == "Takamine GD20 Dreadnought Natural"
    assert produtos[0].categoria == "Violões"
    assert produtos[0].preco == "R$ 2.199,00"


def test_mostra_preco_original_desconto_e_preco_final_da_promocao_ativa(conexao):
    produtos = buscar_produtos(conexao, termo="Crafter HT-100")

    assert len(produtos) == 1
    assert produtos[0].preco == "R$ 2.399,00"
    assert produtos[0].desconto_percentual == 18
    assert produtos[0].preco_final == "R$ 1.967,18"


def test_busca_violoes_disponiveis_ate_1000_reais_retorna_12_sem_esgotados_ou_descontinuados(
    conexao,
):
    produtos = buscar_produtos(
        conexao, categoria="violões", preco_maximo=1000, somente_disponiveis=True
    )

    ids = {produto.id for produto in produtos}
    assert len(produtos) == 12
    assert 96 not in ids
    assert 113 not in ids


def test_pix_aplica_5_por_cento_sobre_o_preco_de_tabela_sem_promocao(conexao):
    (produto,) = buscar_produtos(conexao, termo="Takamine GD20")

    assert produto.preco_pix == "R$ 2.089,05"


def test_pix_nao_se_soma_a_uma_promocao_ativa(conexao):
    (produto,) = buscar_produtos(conexao, termo="Crafter HT-100")

    assert produto.preco_pix is None


def test_produto_ativo_sem_estoque_e_indisponivel(conexao):
    (produto,) = buscar_produtos(conexao, termo="Giannini GF-3D")

    assert produto.disponibilidade == "indisponivel"


def test_produto_descontinuado_e_fora_de_catalogo_mesmo_sem_estoque_zero(conexao):
    (sem_estoque,) = buscar_produtos(conexao, termo="Shelby SN-7C")
    (com_estoque,) = buscar_produtos(conexao, termo="Ibanez Bass 2X")

    assert sem_estoque.disponibilidade == "fora_de_catalogo"
    assert com_estoque.disponibilidade == "fora_de_catalogo"


def test_produto_em_lancamento_nao_tem_disponibilidade_confirmada(conexao):
    (produto,) = buscar_produtos(conexao, termo="Kala KA-ABP-CTG")

    assert produto.disponibilidade == "lancamento"


def test_promocao_inativa_nao_gera_desconto(conexao):
    # A promoção 1 (Black Friday) do produto 102 está inativa.
    produto = next(p for p in buscar_produtos(conexao) if p.id == 102)

    assert produto.desconto_percentual is None
    assert produto.preco_final == produto.preco


def test_categoria_sem_produtos_retorna_lista_vazia(conexao):
    assert buscar_produtos(conexao, termo="saxofone") == []
    assert buscar_produtos(conexao, categoria="Instrumentos de Sopro") == []
