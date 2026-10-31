import csv
import sqlite3
from decimal import Decimal
from pathlib import Path

from src.config import CAMINHO_BANCO, PASTA_DADOS
from src.database import conectar

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
    status TEXT NOT NULL
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


class ErroDeCarga(Exception):
    pass


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def preparar_produto(produto: dict[str, str], categorias: set[str]) -> tuple:
    identificador = produto["product_id"]
    if produto["category_id"] not in categorias:
        raise ErroDeCarga(f"produto {identificador}: categoria inexistente")
    try:
        return (
            int(identificador),
            produto["name"],
            int(produto["category_id"]),
            int(Decimal(produto["price_brl"]) * 100),
            int(produto["stock_quantity"]),
            produto["status"],
        )
    except (ValueError, ArithmeticError) as erro:
        raise ErroDeCarga(f"produto {identificador}: valor inválido") from erro


def preparar_promocao(promocao: dict[str, str], produtos: set[str]) -> tuple:
    identificador = promocao["promotion_id"]
    if promocao["product_id"] not in produtos:
        raise ErroDeCarga(f"promoção {identificador}: produto inexistente")
    try:
        return (
            int(identificador),
            int(promocao["product_id"]),
            int(promocao["discount_percent"]),
            promocao["description"],
            int(promocao["is_active"]),
        )
    except ValueError as erro:
        raise ErroDeCarga(f"promoção {identificador}: valor inválido") from erro


def carregar_catalogo(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    categorias = ler_csv(pasta_dados / "categories.csv")
    ids_categorias = {categoria["category_id"] for categoria in categorias}
    # A validação vem antes do esquema para uma falha não apagar o banco atual.
    produtos = [
        preparar_produto(produto, ids_categorias)
        for produto in ler_csv(pasta_dados / "products.csv")
    ]

    ids_produtos = {produto["product_id"] for produto in ler_csv(pasta_dados / "products.csv")}
    promocoes = [
        preparar_promocao(promocao, ids_produtos)
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
            product_id, name, category_id, price_cents, stock_quantity, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        produtos,
    )
    conexao.executemany(
        "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)",
        promocoes,
    )
    conexao.commit()


def somente_digitos(telefone: str) -> str:
    return "".join(c for c in telefone if c.isdigit())


def carregar_clientes(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    # E-mail e cidade não são carregados: o agente não precisa deles (privacidade).
    clientes = [
        (int(cliente["customer_id"]), cliente["name"], somente_digitos(cliente["phone"]))
        for cliente in ler_csv(pasta_dados / "customers.csv")
    ]
    conexao.executescript(ESQUEMA_CLIENTES)
    conexao.executemany("INSERT INTO customers VALUES (?, ?, ?)", clientes)
    conexao.commit()


def carregar_pedidos(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    pedidos = [
        (
            int(pedido["order_id"]),
            int(pedido["customer_id"]),
            pedido["order_date"],
            pedido["status"],
            int(Decimal(pedido["total_brl"]) * 100),
            pedido["payment_method"],
            pedido["tracking_code"] or None,
            pedido["estimated_delivery"] or None,
        )
        for pedido in ler_csv(pasta_dados / "orders.csv")
    ]
    conexao.executescript(ESQUEMA_PEDIDOS)
    itens = [
        (int(item["order_id"]), int(item["product_id"]), int(item["quantity"]))
        for item in ler_csv(pasta_dados / "order_items.csv")
    ]
    conexao.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", pedidos)
    conexao.executemany("INSERT INTO order_items VALUES (?, ?, ?)", itens)
    conexao.commit()


def carregar_dados(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    # A ordem respeita as chaves estrangeiras: pedidos dependem de clientes e produtos.
    carregar_catalogo(conexao, pasta_dados)
    carregar_clientes(conexao, pasta_dados)
    carregar_pedidos(conexao, pasta_dados)


if __name__ == "__main__":
    conexao = conectar(CAMINHO_BANCO)
    carregar_dados(conexao, PASTA_DADOS)
    conexao.close()
    print(f"Banco criado em {CAMINHO_BANCO}")
