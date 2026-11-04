import argparse
import sqlite3
import sys
from pathlib import Path

from src.config import DATABASE_PATH
from src.database import connect


class RestockError(ValueError):
    """Restock rejected: the database was not changed."""


def restock(connection: sqlite3.Connection, product_id: int, quantity: int) -> None:
    if quantity < 1:
        raise RestockError("The quantity must be greater than zero.")
    product = connection.execute(
        "SELECT status FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if product is None:
        raise RestockError(f"Product {product_id} does not exist.")
    # The status takes precedence over the stock: restocking another status does not change availability.
    if product["status"] != "active":
        raise RestockError(f"Product {product_id} is not active; restocking would have no effect.")
    connection.execute(
        "UPDATE products SET stock_quantity = stock_quantity + ? WHERE product_id = ?",
        (quantity, product_id),
    )
    connection.commit()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulates a stock restock in the local database, without changing the source files."
    )
    parser.add_argument("product", type=int, help="product id")
    parser.add_argument("--quantity", type=int, default=5)
    parser.add_argument("--db", default=str(DATABASE_PATH))
    args = parser.parse_args(arguments)

    if not Path(args.db).exists():
        print(
            f"Database not found at {args.db}. Run: python -m src.load_data",
            file=sys.stderr,
        )
        return 1
    connection = connect(args.db)
    try:
        restock(connection, args.product, args.quantity)
    except RestockError as error:
        print(f"Restock rejected: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(
        f"Simulated restock: +{args.quantity} units of product {args.product}. "
        "To return to the original state, run: python -m src.load_data"
    )
    return 0
