import argparse
import sqlite3
import sys
from pathlib import Path

from src.config import CAMINHO_BANCO
from src.database import connect


class ErroDeReposicao(ValueError):
    """Restock rejected: the database was not changed."""


def repor_estoque(connection: sqlite3.Connection, product_id: int, quantidade: int) -> None:
    if quantidade < 1:
        raise ErroDeReposicao("The quantity must be greater than zero.")
    produto = connection.execute(
        "SELECT status FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if produto is None:
        raise ErroDeReposicao(f"Product {product_id} does not exist.")
    # The status takes precedence over the stock: restocking another status does not change availability.
    if produto["status"] != "active":
        raise ErroDeReposicao(f"Product {product_id} is not active; restocking would have no effect.")
    connection.execute(
        "UPDATE products SET stock_quantity = stock_quantity + ? WHERE product_id = ?",
        (quantidade, product_id),
    )
    connection.commit()


def principal(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        description="Simulates a stock restock in the local database, without changing the source files."
    )
    analisador.add_argument("produto", type=int, help="product id")
    analisador.add_argument("--quantidade", type=int, default=5)
    analisador.add_argument("--banco", default=str(CAMINHO_BANCO))
    escolhidos = analisador.parse_args(argumentos)

    if not Path(escolhidos.banco).exists():
        print(
            f"Database not found at {escolhidos.banco}. Run: python -m src.load_data",
            file=sys.stderr,
        )
        return 1
    connection = connect(escolhidos.banco)
    try:
        repor_estoque(connection, escolhidos.produto, escolhidos.quantidade)
    except ErroDeReposicao as erro:
        print(f"Restock rejected: {erro}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(
        f"Simulated restock: +{escolhidos.quantidade} units of product {escolhidos.produto}. "
        "To return to the original state, run: python -m src.load_data"
    )
    return 0
