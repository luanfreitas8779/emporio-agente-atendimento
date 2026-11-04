import pytest

from src.catalog import buscar_produtos


def test_informa_o_preco_do_takamine_gd20(connection):
    produtos = buscar_produtos(connection, termo="Takamine GD20")

    assert len(produtos) == 1
    assert produtos[0].nome == "Takamine GD20 Dreadnought Natural"
    assert produtos[0].categoria == "Violões"
    assert produtos[0].preco == "R$ 2.199,00"


def test_crafter_ht_100_mostra_preco_original_desconto_e_preco_final(connection):
    (produto,) = buscar_produtos(connection, termo="Crafter HT-100")

    assert produto.preco == "R$ 2.399,00"
    assert produto.desconto_percentual == 18
    assert produto.preco_final == "R$ 1.967,18"


def test_promocao_inativa_nao_gera_desconto(connection):
    # The Crafter CE-15's 10% "Black Friday" promotion is inactive.
    (produto,) = buscar_produtos(connection, termo="Crafter CE-15")

    assert produto.desconto_percentual is None
    assert produto.preco_final == "R$ 3.899,00"


def test_filtra_por_categoria(connection):
    produtos = buscar_produtos(connection, categoria="violões")

    assert len(produtos) == 35
    assert {produto.categoria for produto in produtos} == {"Violões"}


def test_busca_ignora_acentos_e_maiusculas(connection):
    assert len(buscar_produtos(connection, categoria="VIOLOES")) == 35
    assert len(buscar_produtos(connection, termo="takamine gd20")) == 1


def test_produto_ativo_sem_estoque_e_indisponivel(connection):
    (produto,) = buscar_produtos(connection, termo="Giannini GF-3D")

    assert produto.disponibilidade == "indisponivel"


def test_produto_descontinuado_e_fora_de_catalogo(connection):
    (shelby,) = buscar_produtos(connection, termo="Shelby SN-7C")

    assert shelby.disponibilidade == "fora_de_catalogo"


def test_descontinuado_com_estoque_continua_fora_de_catalogo(connection):
    (ibanez,) = buscar_produtos(connection, termo="Ibanez Bass 2X")

    assert ibanez.disponibilidade == "fora_de_catalogo"


def test_produto_em_lancamento_nao_tem_disponibilidade_confirmada(connection):
    # The Kala has stock 2, but its status is coming_soon.
    (kala,) = buscar_produtos(connection, termo="Kala KA-ABP-CTG")

    assert kala.disponibilidade == "lancamento"


def test_limita_a_busca_pelo_preco_maximo(connection):
    produtos = buscar_produtos(connection, categoria="violões", preco_maximo=1000)

    assert len(produtos) == 14


def test_preco_maximo_considera_o_preco_final_da_promocao(connection):
    # The Ohana CK-20 costs R$ 549,00, but has a 20% discount: R$ 439,20.
    nomes = [p.nome for p in buscar_produtos(connection, categoria="ukuleles", preco_maximo=450)]

    assert "Ohana CK-20 Concert Natural" in nomes


def test_violoes_disponiveis_ate_1000_reais_sao_12_sem_os_ids_96_e_113(connection):
    produtos = buscar_produtos(
        connection, categoria="violões", preco_maximo=1000, somente_disponiveis=True
    )

    ids = {produto.id for produto in produtos}
    assert len(produtos) == 12
    assert 96 not in ids
    assert 113 not in ids


def test_somente_promocao_devolve_so_produtos_com_promocao_ativa(connection):
    produtos = buscar_produtos(connection, somente_promocao=True)

    assert len(produtos) == 4
    assert all(produto.desconto_percentual for produto in produtos)
    assert "Crafter CE-15" not in " ".join(produto.nome for produto in produtos)


def test_somente_promocao_combina_com_a_categoria(connection):
    produtos = buscar_produtos(connection, categoria="ukuleles", somente_promocao=True)

    assert [produto.nome for produto in produtos] == [
        "Kalani KAL-700T Tenor Natural",
        "Ohana CK-20 Concert Natural",
    ]
    assert produtos[1].preco == "R$ 549,00"
    assert produtos[1].desconto_percentual == 20
    assert produtos[1].preco_final == "R$ 439,20"


def test_categoria_com_erro_de_digitacao_acha_o_ukulele_em_promocao_ate_400(connection):
    produtos = buscar_produtos(
        connection, categoria="Ukelele", preco_maximo=400, somente_promocao=True
    )

    assert [produto.nome for produto in produtos] == ["Kalani KAL-700T Tenor Natural"]
    assert produtos[0].preco == "R$ 359,00"
    assert produtos[0].desconto_percentual == 10
    assert produtos[0].preco_final == "R$ 323,10"


def test_categoria_no_plural_com_erro_de_digitacao_acha_o_mesmo_ukulele(connection):
    produtos = buscar_produtos(
        connection, categoria="Ukeleles", preco_maximo=400, somente_promocao=True
    )

    assert [produto.nome for produto in produtos] == ["Kalani KAL-700T Tenor Natural"]


@pytest.mark.parametrize(
    ("errada", "certa"), [("Ukelele", "Ukuleles"), ("Guitaras", "Guitarras")]
)
def test_categoria_com_erro_de_digitacao_devolve_os_produtos_da_categoria_certa(connection, errada, certa):
    esperados = buscar_produtos(connection, categoria=certa)

    assert esperados
    assert buscar_produtos(connection, categoria=errada) == esperados


@pytest.mark.parametrize("categoria", ["Saxofones", "Flautas", "Violinos", "Banjos"])
def test_categoria_que_a_loja_nao_tem_continua_vazia_mesmo_com_tolerancia(connection, categoria):
    assert buscar_produtos(connection, categoria=categoria) == []


def test_tolerancia_da_categoria_nao_inventa_promocao(connection):
    assert buscar_produtos(connection, categoria="Guitarras", somente_promocao=True) == []


def test_tolerancia_da_categoria_nao_afrouxa_o_preco_maximo(connection):
    assert buscar_produtos(connection, categoria="Ukelele", preco_maximo=100) == []


def test_pix_aplica_5_por_cento_sobre_o_preco_de_tabela(connection):
    (produto,) = buscar_produtos(connection, termo="Takamine GD20")

    assert produto.preco_pix == "R$ 2.089,05"


def test_pix_nao_se_soma_a_uma_promocao_ativa(connection):
    (produto,) = buscar_produtos(connection, termo="Crafter HT-100")

    assert produto.preco_pix is None


def test_categoria_sem_produtos_nao_retorna_resultados(connection):
    assert buscar_produtos(connection, termo="saxofone") == []
    assert buscar_produtos(connection, categoria="Instrumentos de Sopro") == []


@pytest.mark.regressao
def test_preco_maximo_igual_ao_preco_do_produto_inclui_o_produto(connection):
    # 4.35 * 100 is 434.99999999999994 in floating point.
    connection.execute(
        "INSERT INTO products VALUES (9001, 'Produto Limite', 5, 435, 1, 'active', '{}')"
    )

    produtos = buscar_produtos(connection, termo="Produto Limite", preco_maximo=4.35)

    assert [p.nome for p in produtos] == ["Produto Limite"]


@pytest.mark.regressao
def test_categoria_no_singular_encontra_a_categoria_no_plural(connection):
    plural = buscar_produtos(connection, categoria="Violões")

    assert len(plural) > 0
    for singular in ("violão", "violao", "Violao"):
        assert buscar_produtos(connection, categoria=singular) == plural


@pytest.mark.regressao
def test_categorias_no_singular_de_outros_plurais(connection):
    assert buscar_produtos(connection, categoria="guitarra") == buscar_produtos(
        connection, categoria="Guitarras"
    )
    assert buscar_produtos(connection, categoria="ukulele") == buscar_produtos(
        connection, categoria="Ukuleles"
    )
    assert buscar_produtos(connection, categoria="baixo") == buscar_produtos(
        connection, categoria="Baixos"
    )


def test_categoria_inexistente_nao_encontra_produtos(connection):
    assert buscar_produtos(connection, categoria="saxofone") == []


@pytest.mark.regressao
def test_busca_tolera_letra_a_menos_no_nome(connection):
    # Issue #7 validation: "gianini gf 3d" did not find the Giannini GF-3D.
    (produto,) = buscar_produtos(connection, termo="gianini gf 3d")

    assert produto.nome == "Giannini GF-3D Dreadnought Sunburst"


@pytest.mark.parametrize(
    "termo",
    ["Yamaha F320", "Giannini GF-9X", "Takamine GD21", "Martin D-28E Dreadnought", "Rozini RV-176", "Takamine GC5CF"],
)
def test_busca_nao_confunde_modelos_distintos_com_codigo_parecido(connection, termo):
    assert buscar_produtos(connection, termo=termo) == []


@pytest.mark.regressao
def test_expoe_as_especificacoes_cadastradas_do_produto(connection):
    produto = buscar_produtos(connection, termo="Takamine GD20")[0]

    assert produto.especificacoes["fundo e laterais"] == "Sapele"
    assert produto.especificacoes["braço"] == "Mogno"


@pytest.mark.regressao
def test_especificacoes_chegam_com_nomes_e_valores_em_portugues(connection):
    produto = buscar_produtos(connection, termo="Taylor 110e")[0]

    assert produto.especificacoes == {
        "tampo": "Sitka Spruce Sólido",
        "fundo e laterais": "Walnut",
        "braço": "Tropical Mahogany",
        "cordas": "aço",
        "escala": "648mm",
        "eletrônica": "sim",
        "cor": "Natural",
    }


@pytest.mark.regressao
def test_bateria_traz_ferragens_incluidas_em_portugues(connection):
    produto = buscar_produtos(connection, termo="Yamaha Kit 1")[0]

    assert produto.especificacoes["ferragens"] == "incluídas"
    assert produto.especificacoes["peças"] == "5"


@pytest.mark.regressao
def test_nao_expoe_o_numero_de_cordas_do_bass_3x_porque_o_cadastro_diverge(connection):
    # The description and specifications of id 137 disagree (DQ-05): the data is not reliable.
    produto = buscar_produtos(connection, termo="Yamaha Bass 3X")[0]

    assert "cordas" not in produto.especificacoes
    assert produto.especificacoes["braço"] == "Maple"


@pytest.mark.regressao
def test_informa_se_o_estoque_atende_a_quantidade_sem_revelar_o_numero(connection):
    # The Yamaha C40 has 12 units in stock.
    atende = buscar_produtos(connection, termo="Yamaha C40", quantidade=10)[0]
    nao_atende = buscar_produtos(connection, termo="Yamaha C40", quantidade=13)[0]
    sem_pedido = buscar_produtos(connection, termo="Yamaha C40")[0]

    assert atende.atende_quantidade is True
    assert nao_atende.atende_quantidade is False
    assert sem_pedido.atende_quantidade is None
    assert "12" not in str(atende)


def test_produto_fora_de_catalogo_nunca_atende_a_quantidade_mesmo_com_estoque(connection):
    # Ibanez Bass 2X (id 136) is discontinued and has 13 units (DQ-02).
    produto = buscar_produtos(connection, termo="Ibanez Bass 2X", quantidade=2)[0]

    assert produto.atende_quantidade is False


@pytest.mark.regressao
def test_quantidade_vale_junto_de_somente_disponiveis_e_do_erro_de_digitacao(connection):
    # "Yamha" is not a substring of "Yamaha": only the fuzzy search finds it.
    (disponivel,) = buscar_produtos(connection, termo="Yamha C40", somente_disponiveis=True, quantidade=10)
    (sem_estoque,) = buscar_produtos(connection, termo="Yamha C40", quantidade=13)

    assert disponivel.atende_quantidade is True
    assert sem_estoque.atende_quantidade is False


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("consulta", "expected"),
    [
        ("guitarra stratocaster fender", "Fender Stratocaster American Pro II"),
        ("violao takamine", "Takamine GD20 Dreadnought Natural"),
        ("ukulele kala", "Kala KA-C Concert Mogno"),
    ],
)
def test_palavra_da_categoria_junto_do_nome_encontra_o_produto(connection, consulta, expected):
    nomes = [p.nome for p in buscar_produtos(connection, termo=consulta)]

    assert expected in nomes


@pytest.mark.regressao
def test_palavras_de_ligacao_na_consulta_nao_impedem_a_busca(connection):
    nomes = [p.nome for p in buscar_produtos(connection, termo="guitarra stratocaster da fender")]

    assert nomes == ["Fender Stratocaster American Pro II"]


def test_consulta_so_com_palavras_de_ligacao_nao_devolve_o_catalogo_inteiro(connection):
    assert buscar_produtos(connection, termo="o da um") == []


@pytest.mark.regressao
@pytest.mark.parametrize(
    ("consulta", "expected"),
    [
        ("Martin D28", "Martin D-28 Dreadnought Natural"),
        ("GF3D", "Giannini GF-3D Dreadnought Sunburst"),
        ("AC39", "Tagima Memphis AC-39 Nylon Natural"),
        ("KAC", "Kala KA-C Concert Mogno"),
    ],
)
def test_codigo_de_modelo_sem_hifen_encontra_o_produto(connection, consulta, expected):
    nomes = [p.nome for p in buscar_produtos(connection, termo=consulta)]

    assert expected in nomes


def test_codigo_sem_hifen_continua_sem_confundir_modelos_vizinhos(connection):
    nomes = [p.nome for p in buscar_produtos(connection, termo="D28E")]

    assert nomes == ["Martin D-28E Elétrico Aço Natural"]


@pytest.mark.regressao
@pytest.mark.parametrize("pedaco", ["tar", "iolao", "vio", "ita"])
def test_pedaco_de_palavra_da_categoria_nao_encontra_produtos(connection, pedaco):
    assert buscar_produtos(connection, termo=pedaco) == []


def test_categoria_no_plural_continua_encontrando_pela_palavra_inteira(connection):
    assert len(buscar_produtos(connection, termo="guitarras")) == 5


@pytest.mark.regressao
def test_produto_em_promocao_explica_que_o_pix_nao_soma_ao_desconto(connection):
    (promocional,) = buscar_produtos(connection, termo="Crafter HT-100")
    (sem_promocao,) = buscar_produtos(connection, termo="Yamaha C40")

    assert promocional.preco_pix is None
    assert promocional.observacao_pix == "O PIX não soma ao desconto da promoção."
    assert sem_promocao.observacao_pix is None


def test_produto_sem_promocao_informa_o_percentual_do_pix(connection):
    (sem_promocao,) = buscar_produtos(connection, termo="Takamine GD20")
    (promocional,) = buscar_produtos(connection, termo="Crafter HT-100")

    assert sem_promocao.percentual_pix == "5%"
    assert promocional.percentual_pix is None
