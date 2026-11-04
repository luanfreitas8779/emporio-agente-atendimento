import csv
import sqlite3
from decimal import Decimal
from pathlib import Path

from src.config import DATABASE_PATH, DATA_DIR
from src.database import connect
from src.orders import ORDER_STATUS, valid_payment
from src.phone import normalize_phone

CATALOG_SCHEMA = """
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

CUSTOMERS_SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE
);
"""

ORDERS_SCHEMA = """
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


PRODUCT_STATUSES = {"active", "coming_soon", "discontinued"}


class LoadError(Exception):
    pass


def to_cents(amount: str) -> int:
    """Converts reais to cents, rejecting negative values and fractions of a cent."""
    cents = Decimal(amount) * 100
    if cents < 0 or cents != cents.to_integral_value():
        raise ValueError(amount)
    return int(cents)


def reject_duplicate(label: str, identifier: str, seen_ids: set[str]) -> None:
    if identifier in seen_ids:
        raise LoadError(f"{label} {identifier}: duplicate id")
    seen_ids.add(identifier)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def prepare_product(
    product: dict[str, str], categories: set[str], seen_ids: set[str]
) -> tuple:
    identifier = product["product_id"]
    reject_duplicate("product", identifier, seen_ids)
    if product["category_id"] not in categories:
        raise LoadError(f"product {identifier}: nonexistent category")
    try:
        logger = (
            int(identifier),
            product["name"],
            int(product["category_id"]),
            to_cents(product["price_brl"]),
            int(product["stock_quantity"]),
            product["status"],
            product["specs"],
        )
    except (ValueError, ArithmeticError) as error:
        raise LoadError(f"product {identifier}: invalid value") from error
    if logger[4] < 0 or logger[5] not in PRODUCT_STATUSES:
        raise LoadError(f"product {identifier}: invalid value")
    return logger


def prepare_promotion(
    promotion: dict[str, str], products: set[str], seen_ids: set[str]
) -> tuple:
    identifier = promotion["promotion_id"]
    reject_duplicate("promotion", identifier, seen_ids)
    if promotion["product_id"] not in products:
        raise LoadError(f"promotion {identifier}: nonexistent product")
    try:
        logger = (
            int(identifier),
            int(promotion["product_id"]),
            int(promotion["discount_percent"]),
            promotion["description"],
            int(promotion["is_active"]),
        )
    except ValueError as error:
        raise LoadError(f"promotion {identifier}: invalid value") from error
    if not 0 <= logger[2] <= 100 or logger[4] not in (0, 1):
        raise LoadError(f"promotion {identifier}: invalid value")
    return logger


def load_catalog(connection: sqlite3.Connection, data_folder: Path) -> None:
    categories = read_csv(data_folder / "categories.csv")
    category_ids = {category["category_id"] for category in categories}
    # Validation comes before the schema so that a failure does not erase the current database.
    product_rows = read_csv(data_folder / "products.csv")
    seen_ids: set[str] = set()
    products = [prepare_product(product, category_ids, seen_ids) for product in product_rows]
    product_ids = {product["product_id"] for product in product_rows}
    seen: set[str] = set()
    promotions = [
        prepare_promotion(promotion, product_ids, seen)
        for promotion in read_csv(data_folder / "promotions.csv")
    ]

    connection.executescript(CATALOG_SCHEMA)
    connection.executemany(
        "INSERT INTO categories (category_id, name) VALUES (:category_id, :name)",
        categories,
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
        promotions,
    )
    connection.commit()


def prepare_customer(customer: dict[str, str], seen_ids: set[str], phones: set[str]) -> tuple:
    identifier = customer["customer_id"]
    reject_duplicate("customer", identifier, seen_ids)
    try:
        number = int(identifier)
    except ValueError as error:
        raise LoadError(f"customer {identifier}: invalid value") from error
    phone = normalize_phone(customer["phone"])
    if phone is None or not customer["name"].strip():
        raise LoadError(f"customer {identifier}: invalid value")
    if phone in phones:
        raise LoadError(f"customer {identifier}: duplicate phone number")
    phones.add(phone)
    # E-mail and city are not loaded: the agent does not need them (privacy).
    return (number, customer["name"].strip(), phone)


def load_customers(connection: sqlite3.Connection, data_folder: Path) -> None:
    seen_ids: set[str] = set()
    phones: set[str] = set()
    customers = [
        prepare_customer(customer, seen_ids, phones)
        for customer in read_csv(data_folder / "customers.csv")
    ]
    connection.executescript(CUSTOMERS_SCHEMA)
    connection.executemany("INSERT INTO customers (customer_id, name, phone) VALUES (?, ?, ?)", customers)
    connection.commit()


def prepare_order(order: dict[str, str], customers: set[int], seen_ids: set[str]) -> tuple:
    identifier = order["order_id"]
    reject_duplicate("order", identifier, seen_ids)
    try:
        customer = int(order["customer_id"])
        total = to_cents(order["total_brl"])
        number = int(identifier)
    except (ValueError, ArithmeticError) as error:
        raise LoadError(f"order {identifier}: invalid value") from error
    if order["status"] not in ORDER_STATUS or not valid_payment(order["payment_method"]):
        raise LoadError(f"order {identifier}: invalid value")
    if customer not in customers:
        raise LoadError(f"order {identifier}: nonexistent customer")
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


def prepare_item(item: dict[str, str], order_list: set[int], products: set[int]) -> tuple:
    identifier = item["order_id"]
    try:
        number, product, quantity = (
            int(identifier),
            int(item["product_id"]),
            int(item["quantity"]),
        )
    except ValueError as error:
        raise LoadError(f"order item {identifier}: invalid value") from error
    if quantity < 1:
        raise LoadError(f"order item {identifier}: invalid value")
    if number not in order_list:
        raise LoadError(f"order item {identifier}: nonexistent order")
    if product not in products:
        raise LoadError(f"order item {identifier}: nonexistent product")
    return (number, product, quantity)


def load_orders(connection: sqlite3.Connection, data_folder: Path) -> None:
    customers = {row[0] for row in connection.execute("SELECT customer_id FROM customers")}
    products = {row[0] for row in connection.execute("SELECT product_id FROM products")}
    # Validation comes before the schema so that a failure does not erase the current database.
    seen_ids: set[str] = set()
    order_list = [
        prepare_order(order, customers, seen_ids)
        for order in read_csv(data_folder / "orders.csv")
    ]
    order_ids = {order[0] for order in order_list}
    items = [
        prepare_item(item, order_ids, products)
        for item in read_csv(data_folder / "order_items.csv")
    ]
    connection.executescript(ORDERS_SCHEMA)
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


def load_all_data(connection: sqlite3.Connection, data_folder: Path) -> None:
    # The order follows the foreign keys: orders depend on customers and products.
    load_catalog(connection, data_folder)
    load_customers(connection, data_folder)
    load_orders(connection, data_folder)


LOADED_TABLES = ("categories", "products", "promotions", "customers", "orders", "order_items")


def database_loaded(connection: sqlite3.Connection) -> bool:
    """Says whether the data load has already created the catalog, customer, and order tables."""
    existing = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if not set(LOADED_TABLES) <= existing:
        return False
    # A load from before the specifications lacks the column and requires a new load.
    colunas = {row[1] for row in connection.execute("PRAGMA table_info(products)")}
    return "specs" in colunas


if __name__ == "__main__":
    connection = connect(DATABASE_PATH)
    load_all_data(connection, DATA_DIR)
    connection.close()
    print(f"Database created at {DATABASE_PATH}")
