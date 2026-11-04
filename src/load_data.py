import csv
import sqlite3
from decimal import Decimal
from pathlib import Path

from src.config import DATABASE_PATH, DATA_DIR
from src.database import connect
from src.orders import ORDER_STATUS, valid_payment
from src.phone import normalize_phone

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


def para_centavos(amount: str) -> int:
    """Converts reais to cents, rejecting negative values and fractions of a cent."""
    cents = Decimal(amount) * 100
    if cents < 0 or cents != cents.to_integral_value():
        raise ValueError(amount)
    return int(cents)


def rejeitar_duplicado(rotulo: str, identificador: str, vistos: set[str]) -> None:
    if identificador in vistos:
        raise ErroDeCarga(f"{rotulo} {identificador}: duplicate id")
    vistos.add(identificador)


def ler_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def preparar_produto(
    product: dict[str, str], categorias: set[str], vistos: set[str]
) -> tuple:
    identificador = product["product_id"]
    rejeitar_duplicado("product", identificador, vistos)
    if product["category_id"] not in categorias:
        raise ErroDeCarga(f"product {identificador}: nonexistent category")
    try:
        registro = (
            int(identificador),
            product["name"],
            int(product["category_id"]),
            para_centavos(product["price_brl"]),
            int(product["stock_quantity"]),
            product["status"],
            product["specs"],
        )
    except (ValueError, ArithmeticError) as error:
        raise ErroDeCarga(f"product {identificador}: invalid value") from error
    if registro[4] < 0 or registro[5] not in STATUS_DE_PRODUTO:
        raise ErroDeCarga(f"product {identificador}: invalid value")
    return registro


def preparar_promocao(
    promocao: dict[str, str], products: set[str], vistos: set[str]
) -> tuple:
    identificador = promocao["promotion_id"]
    rejeitar_duplicado("promotion", identificador, vistos)
    if promocao["product_id"] not in products:
        raise ErroDeCarga(f"promotion {identificador}: nonexistent product")
    try:
        registro = (
            int(identificador),
            int(promocao["product_id"]),
            int(promocao["discount_percent"]),
            promocao["description"],
            int(promocao["is_active"]),
        )
    except ValueError as error:
        raise ErroDeCarga(f"promotion {identificador}: invalid value") from error
    if not 0 <= registro[2] <= 100 or registro[4] not in (0, 1):
        raise ErroDeCarga(f"promotion {identificador}: invalid value")
    return registro


def carregar_catalogo(connection: sqlite3.Connection, pasta_dados: Path) -> None:
    categorias = ler_csv(pasta_dados / "categories.csv")
    ids_categorias = {category["category_id"] for category in categorias}
    # Validation comes before the schema so that a failure does not erase the current database.
    linhas_produtos = ler_csv(pasta_dados / "products.csv")
    vistos: set[str] = set()
    products = [preparar_produto(product, ids_categorias, vistos) for product in linhas_produtos]
    ids_produtos = {product["product_id"] for product in linhas_produtos}
    vistas: set[str] = set()
    promocoes = [
        preparar_promocao(promocao, ids_produtos, vistas)
        for promocao in ler_csv(pasta_dados / "promotions.csv")
    ]

    connection.executescript(ESQUEMA_CATALOGO)
    connection.executemany(
        "INSERT INTO categories (category_id, name) VALUES (:category_id, :name)",
        categorias,
    )
    connection.executemany(
        """
        INSERT INTO products (
            product_id, name, category_id, price_cents, stock_quantity, status, specs
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        products,
    )
    connection.executemany(
        """
        INSERT INTO promotions (
            promotion_id, product_id, discount_percent, description, is_active
        ) VALUES (?, ?, ?, ?, ?)
        """,
        promocoes,
    )
    connection.commit()


def preparar_cliente(customer: dict[str, str], vistos: set[str], telefones: set[str]) -> tuple:
    identificador = customer["customer_id"]
    rejeitar_duplicado("customer", identificador, vistos)
    try:
        number = int(identificador)
    except ValueError as error:
        raise ErroDeCarga(f"customer {identificador}: invalid value") from error
    phone = normalize_phone(customer["phone"])
    if phone is None or not customer["name"].strip():
        raise ErroDeCarga(f"customer {identificador}: invalid value")
    if phone in telefones:
        raise ErroDeCarga(f"customer {identificador}: duplicate phone number")
    telefones.add(phone)
    # E-mail and city are not loaded: the agent does not need them (privacy).
    return (number, customer["name"].strip(), phone)


def carregar_clientes(connection: sqlite3.Connection, pasta_dados: Path) -> None:
    vistos: set[str] = set()
    telefones: set[str] = set()
    clientes = [
        preparar_cliente(customer, vistos, telefones)
        for customer in ler_csv(pasta_dados / "customers.csv")
    ]
    connection.executescript(ESQUEMA_CLIENTES)
    connection.executemany("INSERT INTO customers (customer_id, name, phone) VALUES (?, ?, ?)", clientes)
    connection.commit()


def preparar_pedido(order: dict[str, str], clientes: set[int], vistos: set[str]) -> tuple:
    identificador = order["order_id"]
    rejeitar_duplicado("order", identificador, vistos)
    try:
        customer = int(order["customer_id"])
        total = para_centavos(order["total_brl"])
        number = int(identificador)
    except (ValueError, ArithmeticError) as error:
        raise ErroDeCarga(f"order {identificador}: invalid value") from error
    if order["status"] not in ORDER_STATUS or not valid_payment(order["payment_method"]):
        raise ErroDeCarga(f"order {identificador}: invalid value")
    if customer not in clientes:
        raise ErroDeCarga(f"order {identificador}: nonexistent customer")
    return (
        number,
        customer,
        order["order_date"],
        order["status"],
        total,
        order["payment_method"],
        order["tracking_code"] or None,
        order["estimated_delivery"] or None,
    )


def preparar_item(item: dict[str, str], order_list: set[int], products: set[int]) -> tuple:
    identificador = item["order_id"]
    try:
        number, product, quantity = (
            int(identificador),
            int(item["product_id"]),
            int(item["quantity"]),
        )
    except ValueError as error:
        raise ErroDeCarga(f"order item {identificador}: invalid value") from error
    if quantity < 1:
        raise ErroDeCarga(f"order item {identificador}: invalid value")
    if number not in order_list:
        raise ErroDeCarga(f"order item {identificador}: nonexistent order")
    if product not in products:
        raise ErroDeCarga(f"order item {identificador}: nonexistent product")
    return (number, product, quantity)


def carregar_pedidos(connection: sqlite3.Connection, pasta_dados: Path) -> None:
    clientes = {row[0] for row in connection.execute("SELECT customer_id FROM customers")}
    products = {row[0] for row in connection.execute("SELECT product_id FROM products")}
    # Validation comes before the schema so that a failure does not erase the current database.
    vistos: set[str] = set()
    order_list = [
        preparar_pedido(order, clientes, vistos)
        for order in ler_csv(pasta_dados / "orders.csv")
    ]
    ids_pedidos = {order[0] for order in order_list}
    items = [
        preparar_item(item, ids_pedidos, products)
        for item in ler_csv(pasta_dados / "order_items.csv")
    ]
    connection.executescript(ESQUEMA_PEDIDOS)
    connection.executemany(
        """
        INSERT INTO orders (
            order_id, customer_id, order_date, status, total_cents,
            payment_method, tracking_code, estimated_delivery
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        order_list,
    )
    connection.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)", items
    )
    connection.commit()


def load_all_data(connection: sqlite3.Connection, pasta_dados: Path) -> None:
    # The order follows the foreign keys: orders depend on customers and products.
    carregar_catalogo(connection, pasta_dados)
    carregar_clientes(connection, pasta_dados)
    carregar_pedidos(connection, pasta_dados)


TABELAS_DA_CARGA = ("categories", "products", "promotions", "customers", "orders", "order_items")


def banco_carregado(connection: sqlite3.Connection) -> bool:
    """Says whether the data load has already created the catalog, customer, and order tables."""
    existentes = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if not set(TABELAS_DA_CARGA) <= existentes:
        return False
    # A load from before the specifications lacks the column and requires a new load.
    colunas = {row[1] for row in connection.execute("PRAGMA table_info(products)")}
    return "specs" in colunas


if __name__ == "__main__":
    connection = connect(DATABASE_PATH)
    load_all_data(connection, DATA_DIR)
    connection.close()
    print(f"Database created at {DATABASE_PATH}")
