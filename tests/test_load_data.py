import pytest

from src.catalog import buscar_produtos
from src.database import conectar
from src.orders import consultar_pedidos, identificar_cliente
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


def test_interrompe_a_carga_quando_o_item_aponta_para_produto_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="item do pedido 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "1,1,99999"
        )


def test_interrompe_a_carga_quando_o_item_aponta_para_pedido_inexistente(tmp_path):
    with pytest.raises(ErroDeCarga, match="item do pedido 7"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "7,1,93"
        )


def test_interrompe_a_carga_quando_o_total_do_pedido_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="pedido 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,abc,pix,,,", "1,1,93"
        )


def carregar_produtos_de(pasta, produtos):
    escrever_catalogo(pasta, produtos)
    (pasta / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )
    conexao = conectar(pasta / "teste.db")
    try:
        carregar_catalogo(conexao, pasta)
    finally:
        conexao.close()


def test_interrompe_a_carga_quando_o_status_do_produto_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="produto 10"):
        carregar_produtos_de(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,1,vendida,{},2024-01-01"
        )


def test_interrompe_a_carga_quando_o_id_do_produto_esta_duplicado(tmp_path):
    linha = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"

    with pytest.raises(ErroDeCarga, match="produto 10: id duplicado"):
        carregar_produtos_de(tmp_path, f"{linha}\n{linha}")


def test_interrompe_a_carga_quando_o_preco_tem_mais_de_duas_casas(tmp_path):
    with pytest.raises(ErroDeCarga, match="produto 10"):
        carregar_produtos_de(
            tmp_path, "10,100.005,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
        )


def test_interrompe_a_carga_quando_o_estoque_e_negativo(tmp_path):
    with pytest.raises(ErroDeCarga, match="produto 10"):
        carregar_produtos_de(
            tmp_path, "10,100,Guitarra Teste,1,Descricao,-1,active,{},2024-01-01"
        )


def test_falha_na_carga_preserva_o_banco_anterior(conexao, tmp_path):
    linha = "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01"
    escrever_catalogo(tmp_path, f"{linha}\n{linha}")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n", encoding="utf-8"
    )

    with pytest.raises(ErroDeCarga):
        carregar_catalogo(conexao, tmp_path)

    assert len(buscar_produtos(conexao, termo="Takamine GD20")) == 1


def carregar_clientes_de(pasta, *clientes):
    (pasta / "customers.csv").write_text(
        "customer_id,name,phone,email,city\n" + "\n".join(clientes) + "\n", encoding="utf-8"
    )
    conexao = conectar(pasta / "teste.db")
    try:
        carregar_clientes(conexao, pasta)
        return identificar_cliente(conexao, "(67) 90000-0001")
    finally:
        conexao.close()


def test_interrompe_a_carga_quando_o_telefone_do_cliente_e_invalido(tmp_path):
    with pytest.raises(ErroDeCarga, match="cliente 1"):
        carregar_clientes_de(tmp_path, "1,Cliente Teste,12345,t@exemplo.com,Campo Grande")


def test_interrompe_a_carga_quando_o_nome_do_cliente_esta_vazio(tmp_path):
    with pytest.raises(ErroDeCarga, match="cliente 1"):
        carregar_clientes_de(tmp_path, "1, ,(67) 90000-0001,t@exemplo.com,Campo Grande")


def test_interrompe_a_carga_quando_o_id_do_cliente_esta_duplicado(tmp_path):
    with pytest.raises(ErroDeCarga, match="cliente 1: id duplicado"):
        carregar_clientes_de(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "1,Dois,(67) 90000-0002,b@exemplo.com,Campo Grande",
        )


def test_interrompe_a_carga_quando_dois_clientes_tem_o_mesmo_telefone(tmp_path):
    with pytest.raises(ErroDeCarga, match="cliente 2: telefone duplicado"):
        carregar_clientes_de(
            tmp_path,
            "1,Um,(67) 90000-0001,a@exemplo.com,Campo Grande",
            "2,Dois,67 90000-0001,b@exemplo.com,Campo Grande",
        )


def test_telefone_com_codigo_do_pais_e_gravado_sem_o_codigo(tmp_path):
    cliente = carregar_clientes_de(
        tmp_path, "1,Um,+55 (67) 90000-0001,a@exemplo.com,Campo Grande"
    )

    assert cliente is not None
    assert cliente.nome == "Um"


@pytest.mark.parametrize(
    "pedido",
    [
        "1,1,2026-01-01,perdido,100,pix,,,",
        "1,1,2026-01-01,delivered,100,cheque,,,",
        "1,1,2026-01-01,delivered,-100,pix,,,",
        "1,1,2026-01-01,delivered,100,credit_13x,,,",
        "1,1,2026-01-01,delivered,100.005,pix,,,",
    ],
)
def test_interrompe_a_carga_quando_o_pedido_tem_dado_invalido(tmp_path, pedido):
    with pytest.raises(ErroDeCarga, match="pedido 1"):
        carregar_pedidos_de(tmp_path, CLIENTE, pedido, "1,1,93")


def test_interrompe_a_carga_quando_o_id_do_pedido_esta_duplicado(tmp_path):
    pedido = "1,1,2026-01-01,delivered,100,pix,,,"

    with pytest.raises(ErroDeCarga, match="pedido 1: id duplicado"):
        carregar_pedidos_de(tmp_path, CLIENTE, f"{pedido}\n{pedido}", "1,1,93")


def test_interrompe_a_carga_quando_a_quantidade_do_item_nao_e_positiva(tmp_path):
    with pytest.raises(ErroDeCarga, match="item do pedido 1"):
        carregar_pedidos_de(
            tmp_path, CLIENTE, "1,1,2026-01-01,delivered,100,pix,,,", "1,0,93"
        )


@pytest.mark.parametrize("promocao", ["1,10,101,Oferta,1", "1,10,-5,Oferta,1", "1,10,10,Oferta,2"])
def test_interrompe_a_carga_quando_a_promocao_tem_dado_invalido(tmp_path, promocao):
    escrever_catalogo(tmp_path, "10,100,Guitarra Teste,1,Descricao,1,active,{},2024-01-01")
    (tmp_path / "promotions.csv").write_text(
        "promotion_id,product_id,discount_percent,description,is_active\n" + promocao + "\n",
        encoding="utf-8",
    )
    conexao = conectar(tmp_path / "teste.db")

    with pytest.raises(ErroDeCarga, match="promoção 1"):
        carregar_catalogo(conexao, tmp_path)

    conexao.close()
