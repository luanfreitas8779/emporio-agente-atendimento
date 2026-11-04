import pytest

from src.catalog import search_products


def test_gives_the_takamine_gd20_price(connection):
    products = search_products(connection, search_term="Takamine GD20")

    assert len(products) == 1
    assert products[0].name == "Takamine GD20 Dreadnought Natural"
    assert products[0].category == "Violões"
    assert products[0].price == "R$ 2.199,00"


def test_crafter_ht_100_shows_original_price_discount_and_final_price(connection):
    (product,) = search_products(connection, search_term="Crafter HT-100")

    assert product.price == "R$ 2.399,00"
    assert product.discount_percent == 18
    assert product.final_price == "R$ 1.967,18"


def test_inactive_promotion_gives_no_discount(connection):
    # The Crafter CE-15's 10% "Black Friday" promotion is inactive.
    (product,) = search_products(connection, search_term="Crafter CE-15")

    assert product.discount_percent is None
    assert product.final_price == "R$ 3.899,00"


def test_filters_by_category(connection):
    products = search_products(connection, category="violões")

    assert len(products) == 35
    assert {product.category for product in products} == {"Violões"}


def test_search_ignores_accents_and_case(connection):
    assert len(search_products(connection, category="VIOLOES")) == 35
    assert len(search_products(connection, search_term="takamine gd20")) == 1


def test_active_product_without_stock_is_unavailable(connection):
    (product,) = search_products(connection, search_term="Giannini GF-3D")

    assert product.availability == "indisponivel"


def test_discontinued_product_is_out_of_the_catalog(connection):
    (shelby,) = search_products(connection, search_term="Shelby SN-7C")

    assert shelby.availability == "fora_de_catalogo"


def test_discontinued_with_stock_stays_discontinued(connection):
    (ibanez,) = search_products(connection, search_term="Ibanez Bass 2X")

    assert ibanez.availability == "fora_de_catalogo"


def test_new_release_product_has_no_confirmed_availability(connection):
    # The Kala has stock 2, but its status is coming_soon.
    (kala,) = search_products(connection, search_term="Kala KA-ABP-CTG")

    assert kala.availability == "lancamento"


def test_limits_the_search_by_maximum_price(connection):
    products = search_products(connection, category="violões", max_price=1000)

    assert len(products) == 14


def test_max_price_considers_the_promotion_final_price(connection):
    # The Ohana CK-20 costs R$ 549,00, but has a 20% discount: R$ 439,20.
    names = [p.name for p in search_products(connection, category="ukuleles", max_price=450)]

    assert "Ohana CK-20 Concert Natural" in names


def test_available_guitars_up_to_1000_reais_are_12_without_ids_96_and_113(connection):
    products = search_products(
        connection, category="violões", max_price=1000, only_available=True
    )

    ids = {product.id for product in products}
    assert len(products) == 12
    assert 96 not in ids
    assert 113 not in ids


def test_only_on_sale_returns_only_products_with_an_active_promotion(connection):
    products = search_products(connection, only_on_sale=True)

    assert len(products) == 4
    assert all(product.discount_percent for product in products)
    assert "Crafter CE-15" not in " ".join(product.name for product in products)


def test_only_on_sale_combines_with_the_category(connection):
    products = search_products(connection, category="ukuleles", only_on_sale=True)

    assert [product.name for product in products] == [
        "Kalani KAL-700T Tenor Natural",
        "Ohana CK-20 Concert Natural",
    ]
    assert products[1].price == "R$ 549,00"
    assert products[1].discount_percent == 20
    assert products[1].final_price == "R$ 439,20"


def test_category_with_a_typo_finds_the_ukulele_on_sale_up_to_400(connection):
    products = search_products(
        connection, category="Ukelele", max_price=400, only_on_sale=True
    )

    assert [product.name for product in products] == ["Kalani KAL-700T Tenor Natural"]
    assert products[0].price == "R$ 359,00"
    assert products[0].discount_percent == 10
    assert products[0].final_price == "R$ 323,10"


def test_plural_category_with_a_typo_finds_the_same_ukulele(connection):
    products = search_products(
        connection, category="Ukeleles", max_price=400, only_on_sale=True
    )

    assert [product.name for product in products] == ["Kalani KAL-700T Tenor Natural"]


@pytest.mark.parametrize(
    ("wrong", "right"), [("Ukelele", "Ukuleles"), ("Guitaras", "Guitarras")]
)
def test_category_with_a_typo_returns_the_products_of_the_right_category(connection, wrong, right):
    expected_values = search_products(connection, category=right)

    assert expected_values
    assert search_products(connection, category=wrong) == expected_values


@pytest.mark.parametrize("category", ["Saxofones", "Flautas", "Violinos", "Banjos"])
def test_category_the_store_does_not_carry_stays_empty_even_with_tolerance(connection, category):
    assert search_products(connection, category=category) == []


def test_category_tolerance_does_not_invent_a_promotion(connection):
    assert search_products(connection, category="Guitarras", only_on_sale=True) == []


def test_category_tolerance_does_not_loosen_the_max_price(connection):
    assert search_products(connection, category="Ukelele", max_price=100) == []


def test_pix_applies_5_percent_to_the_list_price(connection):
    (product,) = search_products(connection, search_term="Takamine GD20")

    assert product.pix_price == "R$ 2.089,05"


def test_pix_does_not_stack_with_an_active_promotion(connection):
    (product,) = search_products(connection, search_term="Crafter HT-100")

    assert product.pix_price is None


def test_category_without_products_returns_no_results(connection):
    assert search_products(connection, search_term="saxofone") == []
    assert search_products(connection, category="Instrumentos de Sopro") == []


@pytest.mark.regression
def test_max_price_equal_to_the_product_price_includes_the_product(connection):
    # 4.35 * 100 is 434.99999999999994 in floating point.
    connection.execute(
        "INSERT INTO products VALUES (9001, 'Produto Limite', 5, 435, 1, 'active', '{}')"
    )

    products = search_products(connection, search_term="Produto Limite", max_price=4.35)

    assert [p.name for p in products] == ["Produto Limite"]


@pytest.mark.regression
def test_singular_category_finds_the_plural_category(connection):
    plural = search_products(connection, category="Violões")

    assert len(plural) > 0
    for singular in ("violão", "violao", "Violao"):
        assert search_products(connection, category=singular) == plural


@pytest.mark.regression
def test_singular_categories_from_other_plurals(connection):
    assert search_products(connection, category="guitarra") == search_products(
        connection, category="Guitarras"
    )
    assert search_products(connection, category="ukulele") == search_products(
        connection, category="Ukuleles"
    )
    assert search_products(connection, category="baixo") == search_products(
        connection, category="Baixos"
    )


def test_nonexistent_category_finds_no_products(connection):
    assert search_products(connection, category="saxofone") == []


@pytest.mark.regression
def test_search_tolerates_a_missing_letter_in_the_name(connection):
    # Issue #7 validation: "gianini gf 3d" did not find the Giannini GF-3D.
    (product,) = search_products(connection, search_term="gianini gf 3d")

    assert product.name == "Giannini GF-3D Dreadnought Sunburst"


@pytest.mark.parametrize(
    "search_term",
    ["Yamaha F320", "Giannini GF-9X", "Takamine GD21", "Martin D-28E Dreadnought", "Rozini RV-176", "Takamine GC5CF"],
)
def test_search_does_not_confuse_distinct_models_with_similar_codes(connection, search_term):
    assert search_products(connection, search_term=search_term) == []


@pytest.mark.regression
def test_exposes_the_product_registered_specifications(connection):
    product = search_products(connection, search_term="Takamine GD20")[0]

    assert product.specifications["fundo e laterais"] == "Sapele"
    assert product.specifications["braço"] == "Mogno"


@pytest.mark.regression
def test_specifications_arrive_with_names_and_values_in_portuguese(connection):
    product = search_products(connection, search_term="Taylor 110e")[0]

    assert product.specifications == {
        "tampo": "Sitka Spruce Sólido",
        "fundo e laterais": "Walnut",
        "braço": "Tropical Mahogany",
        "cordas": "aço",
        "escala": "648mm",
        "eletrônica": "sim",
        "cor": "Natural",
    }


@pytest.mark.regression
def test_drum_kit_includes_hardware_in_portuguese(connection):
    product = search_products(connection, search_term="Yamaha Kit 1")[0]

    assert product.specifications["ferragens"] == "incluídas"
    assert product.specifications["peças"] == "5"


@pytest.mark.regression
def test_does_not_expose_the_bass_3x_string_count_because_the_record_conflicts(connection):
    # The description and specifications of id 137 disagree (DQ-05): the data is not reliable.
    product = search_products(connection, search_term="Yamaha Bass 3X")[0]

    assert "cordas" not in product.specifications
    assert product.specifications["braço"] == "Maple"


@pytest.mark.regression
def test_reports_whether_stock_meets_the_quantity_without_revealing_the_number(connection):
    # The Yamaha C40 has 12 units in stock.
    meets = search_products(connection, search_term="Yamaha C40", quantity=10)[0]
    does_not_meet = search_products(connection, search_term="Yamaha C40", quantity=13)[0]
    without_order = search_products(connection, search_term="Yamaha C40")[0]

    assert meets.meets_quantity is True
    assert does_not_meet.meets_quantity is False
    assert without_order.meets_quantity is None
    assert "12" not in str(meets)


def test_discontinued_product_never_meets_the_quantity_even_with_stock(connection):
    # Ibanez Bass 2X (id 136) is discontinued and has 13 units (DQ-02).
    product = search_products(connection, search_term="Ibanez Bass 2X", quantity=2)[0]

    assert product.meets_quantity is False


@pytest.mark.regression
def test_quantity_works_with_only_available_and_with_a_typo(connection):
    # "Yamha" is not a substring of "Yamaha": only the fuzzy search finds it.
    (available,) = search_products(connection, search_term="Yamha C40", only_available=True, quantity=10)
    (out_of_stock,) = search_products(connection, search_term="Yamha C40", quantity=13)

    assert available.meets_quantity is True
    assert out_of_stock.meets_quantity is False


@pytest.mark.regression
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("guitarra stratocaster fender", "Fender Stratocaster American Pro II"),
        ("violao takamine", "Takamine GD20 Dreadnought Natural"),
        ("ukulele kala", "Kala KA-C Concert Mogno"),
    ],
)
def test_category_word_together_with_the_name_finds_the_product(connection, query, expected):
    names = [p.name for p in search_products(connection, search_term=query)]

    assert expected in names


@pytest.mark.regression
def test_connecting_words_in_the_query_do_not_prevent_the_search(connection):
    names = [p.name for p in search_products(connection, search_term="guitarra stratocaster da fender")]

    assert names == ["Fender Stratocaster American Pro II"]


def test_query_with_only_connecting_words_does_not_return_the_whole_catalog(connection):
    assert search_products(connection, search_term="o da um") == []


@pytest.mark.regression
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Martin D28", "Martin D-28 Dreadnought Natural"),
        ("GF3D", "Giannini GF-3D Dreadnought Sunburst"),
        ("AC39", "Tagima Memphis AC-39 Nylon Natural"),
        ("KAC", "Kala KA-C Concert Mogno"),
    ],
)
def test_model_code_without_hyphen_finds_the_product(connection, query, expected):
    names = [p.name for p in search_products(connection, search_term=query)]

    assert expected in names


def test_code_without_hyphen_still_does_not_confuse_neighboring_models(connection):
    names = [p.name for p in search_products(connection, search_term="D28E")]

    assert names == ["Martin D-28E Elétrico Aço Natural"]


@pytest.mark.regression
@pytest.mark.parametrize("fragment", ["tar", "iolao", "vio", "ita"])
def test_fragment_of_a_category_word_finds_no_products(connection, fragment):
    assert search_products(connection, search_term=fragment) == []


def test_plural_category_still_matches_by_the_whole_word(connection):
    assert len(search_products(connection, search_term="guitarras")) == 5


@pytest.mark.regression
def test_product_on_sale_explains_that_pix_does_not_stack_with_the_discount(connection):
    (promotional,) = search_products(connection, search_term="Crafter HT-100")
    (without_promotion,) = search_products(connection, search_term="Yamaha C40")

    assert promotional.pix_price is None
    assert promotional.pix_note == "O PIX não soma ao desconto da promoção."
    assert without_promotion.pix_note is None


def test_product_without_promotion_reports_the_pix_percent(connection):
    (without_promotion,) = search_products(connection, search_term="Takamine GD20")
    (promotional,) = search_products(connection, search_term="Crafter HT-100")

    assert without_promotion.pix_percent == "5%"
    assert promotional.pix_percent is None
