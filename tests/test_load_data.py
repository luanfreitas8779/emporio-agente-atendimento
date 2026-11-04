import pytest

from src.catalog import search_products
from src.database import connect
from src.load_data import (
    ErroDeCarga,
    banco_carregado,
    carregar_catalogo,
    carregar_clientes,
    carregar_dados,
    carregar_pedidos,
)
from src.orders import get_orders, identify_customer
from tests.conftest import DATA_DIR


def escrever_catalogo(pasta, product):
    (pasta / "categories.csv").write_text(
        "category_id,name,description\n1,Guitarras,Elétricas\n", encoding="utf-8"
    )
    (pasta / "products.csv").write_text(
        "product_id,price_brl,name,category_id,description,stock_quantity,status,specs,created_at\n"
        f"{product}\n",
        encoding="utf-8",
    )


def test_recarregar_recria_o_catalogo_sem_duplicar_produtos(connection):
    carregar_catalogo(connection, DATA_DIR)

    assert len(search_products(connection, search_term="Takamine GD20")) == 1


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_produto_aponta_para_categoria_inexistente(tmp_path):
    escrever_catalogo(tmp_path, '10,100,Guitarra Teste,99,Descricao,1,active,{},2024-01-01')
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="product 10"):
        carregar_catalogo(connection, tmp_path)

    connection.close()


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_preco_e_invalido(tmp_path):
    escrever_catalogo(tmp_path, '10,abc,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="product 10"):
        carregar_catalogo(connection, tmp_path)

    connection.close()


@pytest.mark.regression
def test_interrompe_a_carga_quando_a_promocao_aponta_para_produto_inexistente(tmp_path):
    escrever_catalogo(tmp_path, '10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n"
        "1,99,10,Oferta,1\n",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="promotion 1"):
        carregar_catalogo(connection, tmp_path)

    connection.close()


def test_recarregar_todos_os_dados_nao_duplica_pedidos(connection):
    carregar_dados(connection, DATA_DIR)

    assert len(get_orders(connection, customer_id=3)) == 2


def escrever_pedidos(pasta, customer, order, item):
    (pasta / "customers.csv").write_text(
        f"customer_id,name,phone,email,city\n{customer}\n", encoding="utf-8"
    )
    (pasta / "orders.csv").write_text(
        "order_id,customer_id,order_date,status,total_brl,payment_method,"
        f"tracking_code,estimated_delivery,notes\n{order}\n",
        encoding="utf-8",
    )
    (pasta / "order_items.csv").write_text(
        f"order_id,quantity,product_id\n{item}\n", encoding="utf-8"
    )


def carregar_pedidos_de(pasta, customer, order, item):
    escrever_pedidos(pasta, customer, order, item)
    connection = connect(pasta / "teste.db")
    carregar_catalogo(connection, DATA_DIR)
    carregar_clientes(connection, pasta)
    try:
        carregar_pedidos(connection, pasta)
    finally:
        connection.close()


CLIENTE = "1,Cliente Teste,(67) 90000-0001,teste@exemplo.com,Campo Grande"


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_pedido_aponta_para_cliente_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="order 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,99,2026-01-01,delivered,100,pix,,,", "1,1,93"
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_item_aponta_para_produto_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="order item 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "1,1,99999"
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_item_aponta_para_pedido_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="order item 7"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "7,1,93"
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_total_do_pedido_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="order 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,abc,pix,,,", "1,1,93"
        )


def carregar_produtos_de(pasta, products):
    escrever_catalogo(pasta, products)
    (pasta / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )
    connection = connect(pasta / "teste.db")
    try:
        carregar_catalogo(connection, pasta)
    finally:
        connection.close()


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_status_do_produto_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="product 10"):
        carregar_produtos_de(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,1,vendida,{},2024-01-01"
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_id_do_produto_esta_duplicado(tmp_path):
    row = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"

    with pytest.raises(ErroDeCarga, match="product 10: duplicate id"):
        carregar_produtos_de(tmp_path, f"{row}\n{row}")


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_preco_tem_mais_de_duas_casas(tmp_path):
    with pytest.raises(ErroDeCarga, match="product 10"):
        carregar_produtos_de(
            tmp_path, "10,100.005,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_estoque_e_negativo(tmp_path):
    with pytest.raises(ErroDeCarga, match="product 10"):
        carregar_produtos_de(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,-1,active,{},2024-01-01"
        )


@pytest.mark.regression
def test_falha_na_carga_preserva_o_banco_anterior(connection, tmp_path):
    row = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
    escrever_catalogo(tmp_path, f"{row}\n{row}")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )

    with pytest.raises(ErroDeCarga):
        carregar_catalogo(connection, tmp_path)

    assert len(search_products(connection, search_term="Takamine GD20")) == 1


def carregar_clientes_de(pasta, *clientes):
    (pasta / "customers.csv").write_text(
        "customer_id,name,phone,email,city\n" + "\n".join(clientes) + "\n", encoding="utf-8"
    )
    connection = connect(pasta / "teste.db")
    try:
        carregar_clientes(connection, pasta)
        return identify_customer(connection, "(67) 90000-0001")
    finally:
        connection.close()


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_telefone_do_cliente_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="customer 1"):
        carregar_clientes_de(tmp_path, "1,Cliente Teste,12345,t@exemplo.com,Campo Grande")


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_nome_do_cliente_esta_vazio(tmp_path):
    with pytest.raises(ErroDeCarga, match="customer 1"):
        carregar_clientes_de(tmp_path, "1, ,(67) 90000-0001,t@exemplo.com,Campo Grande")


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_id_do_cliente_esta_duplicado(tmp_path):
    with pytest.raises(ErroDeCarga, match="customer 1: duplicate id"):
        carregar_clientes_de(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "1,Dois,(67) 90000-0002,b@exemplo.com,Campo Grande",
        )


@pytest.mark.regression
def test_interrompe_a_carga_quando_dois_clientes_tem_o_mesmo_telefone(tmp_path):
    with pytest.raises(ErroDeCarga, match="customer 2: duplicate phone number"):
        carregar_clientes_de(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "2,Dois,67 90000-0001,b@exemplo.com,Campo Grande",
        )


def test_telefone_com_codigo_do_pais_e_gravado_sem_o_codigo(tmp_path):
    customer = carregar_clientes_de(
        tmp_path, "1,Um,+55 (67) 90000-0001,a@exemplo.com,Campo Grande"
    )

    assert customer is not None
    assert customer.name == "Um"


@pytest.mark.parametrize(
    "order",
    [
        "1,1,2026-01-01,perdido,100,pix,,,",
        "1,1,2026-01-01,delivered,100,cheque,,,",
        "1,1,2026-01-01,delivered,-100,pix,,,",
        "1,1,2026-01-01,delivered,100,credit_13x,,,",
        "1,1,2026-01-01,delivered,100.005,pix,,,",
    ],
)
@pytest.mark.regression
def test_interrompe_a_carga_quando_o_pedido_tem_dado_invalido(tmp_path, order):
    with pytest.raises(ErroDeCarga, match="order 1"):
        carregar_pedidos_de(tmp_path, CLIENTE, order, "1,1,93")


@pytest.mark.regression
def test_interrompe_a_carga_quando_o_id_do_pedido_esta_duplicado(tmp_path):
    order = "1,1,2026-01-01,delivered,100,pix,,,"

    with pytest.raises(ErroDeCarga, match="order 1: duplicate id"):
        carregar_pedidos_de(tmp_path, CLIENTE, f"{order}\n{order}", "1,1,93")


@pytest.mark.regression
def test_interrompe_a_carga_quando_a_quantidade_do_item_nao_e_positiva(tmp_path):
    with pytest.raises(ErroDeCarga, match="order item 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "1,0,93"
        )


@pytest.mark.parametrize("promocao", ["1,10,101,Oferta,1", "1,10,-5,Oferta,1", "1,10,10,Oferta,2"])
@pytest.mark.regression
def test_interrompe_a_carga_quando_a_promocao_tem_dado_invalido(tmp_path, promocao):
    escrever_catalogo(tmp_path, "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n" + promocao + "\n",
        encoding="utf-8",
    )
    connection = connect(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="promotion 1"):
        carregar_catalogo(connection, tmp_path)

    connection.close()


def test_banco_so_com_a_memoria_nao_esta_carregado(tmp_path):
    vazio = connect(tmp_path / "vazio.db")

    assert not banco_carregado(vazio)
    vazio.close()


def test_banco_com_os_dados_carregados_esta_pronto(connection):
    assert banco_carregado(connection)


@pytest.mark.regression
def test_banco_carregado_antes_das_especificacoes_pede_nova_carga(connection):
    connection.executescript("ALTER TABLE products DROP COLUMN specs;")

    assert not banco_carregado(connection)
