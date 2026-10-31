import pytest

from src.catalog import buscar_produtos
from src.database import conectar
from src.orders import consultar_pedidos
from src.load_data import ErroDeCarga, carregar_catalogo, carregar_clientes, carregar_dados, carregar_pedidos
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


def test_interrompe_a_carga_quando_a_promocao_aponta_para_produto_inexistente(tmp_path):
    escrever_catalogo(tmp_path, '10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01')
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n"
        "1,99,10,Oferta,1\n",
        encoding="utf-8",
    )
    conexao = conectar(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="promoção 1"):
        carregar_catalogo(conexao, tmp_path)

    conexao.close()


def test_recarregar_todos_os_dados_nao_duplica_pedidos(conexao):
    carregar_dados(conexao, PASTA_DADOS)

    assert len(consultar_pedidos(conexao, cliente_id=3)) == 2


def escrever_pedidos(pasta, cliente, pedido, item):
    (pasta / "customers.csv").write_text(
        f"customer_id,name,phone,email,city\n{cliente}\n", encoding="utf-8"
    )
    (pasta / "orders.csv").write_text(
        "order_id,customer_id,order_date,status,total_brl,payment_method,"
        f"tracking_code,estimated_delivery,notes\n{pedido}\n",
        encoding="utf-8",
    )
    (pasta / "order_items.csv").write_text(
        f"order_id,quantity,product_id\n{item}\n", encoding="utf-8"
    )


def carregar_pedidos_de(pasta, cliente, pedido, item):
    escrever_pedidos(pasta, cliente, pedido, item)
    conexao = conectar(pasta / "teste.db")
    carregar_catalogo(conexao, PASTA_DADOS)
    carregar_clientes(conexao, pasta)
    try:
        carregar_pedidos(conexao, pasta)
    finally:
        conexao.close()


CLIENTE = "1,Cliente Teste,(67) 90000-0001,teste@exemplo.com,Campo Grande"


def test_interrompe_a_carga_quando_o_pedido_aponta_para_cliente_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="pedido 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,99,2026-01-01,delivered,100,pix,,,", "1,1,93"
        )
