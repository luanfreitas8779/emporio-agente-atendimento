import csv
import sqlite3
from decimal import Decimal
from pathlib import Path

from src.config import CAMINHO_BANCO, PASTA_DADOS
from src.database import conectar
from src.orders import STATUS_DE_PEDIDO, pagamento_valido
from src.phone import normalizar_telefone

ESQUEMA_CATALOGO = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (category_id),
    price_cents INTEGER NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    specs TEXT NOT NULL
);

CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    discount_percent INTEGER NOT NULL,
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL
);
"""

ESQUEMA_CLIENTES = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE
);
"""

ESQUEMA_PEDIDOS = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    payment_method TEXT NOT NULL,
    tracking_code TEXT,
    estimated_delivery TEXT
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders (order_id),
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    quantity INTEGER NOT NULL
);
"""


STATUS_DE_PRODUTO = {"active", "coming_soon", "discontinued"}


class ErroDeCarga(Exception):
    pass


def para_centavos(valor: str) -> int:
    """Converts reais to cents, rejecting negative values and fractions of a cent."""
    centavos = Decimal(valor) * 100
    if centavos < 0 or centavos != centavos.to_integral_value():
        raise ValueError(valor)
    return int(centavos)


def rejeitar_duplicado(rotulo: str, identificador: str, vistos: set[str]) -> None:
    if identificador in vistos:
        raise ErroDeCarga(f"{rotulo} {identificador}: duplicate id")
    vistos.add(identificador)


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def preparar_produto(
    produto: dict[str, str], categorias: set[str], vistos: set[str]
) -> tuple:
    identificador = produto["product_id"]
    rejeitar_duplicado("product", identificador, vistos)
    if produto["category_id"] not in categorias:
        raise ErroDeCarga(f"product {identificador}: nonexistent category")
    try:
        registro = (
            int(identificador),
            produto["name"],
            int(produto["category_id"]),
            para_centavos(produto["price_brl"]),
            int(produto["stock_quantity"]),
            produto["status"],
            produto["specs"],
        )
    except (ValueError, ArithmeticError) as erro:
        raise ErroDeCarga(f"product {identificador}: invalid value") from erro
    if registro[4] < 0 or registro[5] not in STATUS_DE_PRODUTO:
        raise ErroDeCarga(f"product {identificador}: invalid value")
    return registro


def preparar_promocao(
    promocao: dict[str, str], produtos: set[str], vistos: set[str]
) -> tuple:
    identificador = promocao["promotion_id"]
    rejeitar_duplicado("promotion", identificador, vistos)
    if promocao["product_id"] not in produtos:
        raise ErroDeCarga(f"promotion {identificador}: nonexistent product")
    try:
        registro = (
            int(identificador),
            int(promocao["product_id"]),
            int(promocao["discount_percent"]),
            promocao["description"],
            int(promocao["is_active"]),
        )
    except ValueError as erro:
        raise ErroDeCarga(f"promotion {identificador}: invalid value") from erro
    if not 0 <= registro[2] <= 100 or registro[4] not in (0, 1):
        raise ErroDeCarga(f"promotion {identificador}: invalid value")
    return registro


def carregar_catalogo(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    categorias = ler_csv(pasta_dados / "categories.csv")
    ids_categorias = {categoria["category_id"] for categoria in categorias}
    # Validation comes before the schema so that a failure does not erase the current database.
    linhas_produtos = ler_csv(pasta_dados / "products.csv")
    vistos: set[str] = set()
    produtos = [preparar_produto(produto, ids_categorias, vistos) for produto in linhas_produtos]
    ids_produtos = {produto["product_id"] for produto in linhas_produtos}
    vistas: set[str] = set()
    promocoes = [
        preparar_promocao(promocao, ids_produtos, vistas)
        for promocao in ler_csv(pasta_dados / "promotions.csv")
    ]

    conexao.executescript(ESQUEMA_CATALOGO)
    conexao.executemany(
        "INSERT INTO categories (category_id, name) VALUES (:category_id, :name)",
        categorias,
    )
    conexao.executemany(
        """
        INSERT INTO products (
            product_id, name, category_id, price_cents, stock_quantity, status, specs
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        produtos,
    )
    conexao.executemany(
        """
        INSERT INTO promotions (
            promotion_id, product_id, discount_percent, description, is_active
        ) VALUES (?, ?, ?, ?, ?)
        """,
        promocoes,
    )
    conexao.commit()


def preparar_cliente(cliente: dict[str, str], vistos: set[str], telefones: set[str]) -> tuple:
    identificador = cliente["customer_id"]
    rejeitar_duplicado("customer", identificador, vistos)
    try:
        numero = int(identificador)
    except ValueError as erro:
        raise ErroDeCarga(f"customer {identificador}: invalid value") from erro
    telefone = normalizar_telefone(cliente["phone"])
    if telefone is None or not cliente["name"].strip():
        raise ErroDeCarga(f"customer {identificador}: invalid value")
    if telefone in telefones:
        raise ErroDeCarga(f"customer {identificador}: duplicate phone number")
    telefones.add(telefone)
    # E-mail and city are not loaded: the agent does not need them (privacy).
    return (numero, cliente["name"].strip(), telefone)


def carregar_clientes(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    vistos: set[str] = set()
    telefones: set[str] = set()
    clientes = [
        preparar_cliente(cliente, vistos, telefones)
        for cliente in ler_csv(pasta_dados / "customers.csv")
    ]
    conexao.executescript(ESQUEMA_CLIENTES)
    conexao.executemany("INSERT INTO customers (customer_id, name, phone) VALUES (?, ?, ?)", clientes)
    conexao.commit()


def preparar_pedido(pedido: dict[str, str], clientes: set[int], vistos: set[str]) -> tuple:
    identificador = pedido["order_id"]
    rejeitar_duplicado("order", identificador, vistos)
    try:
        cliente = int(pedido["customer_id"])
        total = para_centavos(pedido["total_brl"])
        numero = int(identificador)
    except (ValueError, ArithmeticError) as erro:
        raise ErroDeCarga(f"order {identificador}: invalid value") from erro
    if pedido["status"] not in STATUS_DE_PEDIDO or not pagamento_valido(pedido["payment_method"]):
        raise ErroDeCarga(f"order {identificador}: invalid value")
    if cliente not in clientes:
        raise ErroDeCarga(f"order {identificador}: nonexistent customer")
    return (
        numero,
        cliente,
        pedido["order_date"],
        pedido["status"],
        total,
        pedido["payment_method"],
        pedido["tracking_code"] or None,
        pedido["estimated_delivery"] or None,
    )


def preparar_item(item: dict[str, str], pedidos: set[int], produtos: set[int]) -> tuple:
    identificador = item["order_id"]
    try:
        numero, produto, quantidade = (
            int(identificador),
            int(item["product_id"]),
            int(item["quantity"]),
        )
    except ValueError as erro:
        raise ErroDeCarga(f"order item {identificador}: invalid value") from erro
    if quantidade < 1:
        raise ErroDeCarga(f"order item {identificador}: invalid value")
    if numero not in pedidos:
        raise ErroDeCarga(f"order item {identificador}: nonexistent order")
    if produto not in produtos:
        raise ErroDeCarga(f"order item {identificador}: nonexistent product")
    return (numero, produto, quantidade)


def carregar_pedidos(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    clientes = {linha[0] for linha in conexao.execute("SELECT customer_id FROM customers")}
    produtos = {linha[0] for linha in conexao.execute("SELECT product_id FROM products")}
    # Validation comes before the schema so that a failure does not erase the current database.
    vistos: set[str] = set()
    pedidos = [
        preparar_pedido(pedido, clientes, vistos)
        for pedido in ler_csv(pasta_dados / "orders.csv")
    ]
    ids_pedidos = {pedido[0] for pedido in pedidos}
    itens = [
        preparar_item(item, ids_pedidos, produtos)
        for item in ler_csv(pasta_dados / "order_items.csv")
    ]
    conexao.executescript(ESQUEMA_PEDIDOS)
    conexao.executemany(
        """
        INSERT INTO orders (
            order_id, customer_id, order_date, status, total_cents,
            payment_method, tracking_code, estimated_delivery
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        pedidos,
    )
    conexao.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)", itens
    )
    conexao.commit()


def carregar_dados(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    # The order follows the foreign keys: orders depend on customers and products.
    carregar_catalogo(conexao, pasta_dados)
    carregar_clientes(conexao, pasta_dados)
    carregar_pedidos(conexao, pasta_dados)


TABELAS_DA_CARGA = ("categories", "products", "promotions", "customers", "orders", "order_items")


def banco_carregado(conexao: sqlite3.Connection) -> bool:
    """Says whether the data load has already created the catalog, customer, and order tables."""
    existentes = {
        linha[0] for linha in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if not set(TABELAS_DA_CARGA) <= existentes:
        return False
    # A load from before the specifications lacks the column and requires a new load.
    colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(products)")}
    return "specs" in colunas


if __name__ == "__main__":
    conexao = conectar(CAMINHO_BANCO)
    carregar_dados(conexao, PASTA_DADOS)
    conexao.close()
    print(f"Database created at {CAMINHO_BANCO}")
