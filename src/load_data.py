import csv
import sqlite3
from decimal import Decimal
from pathlib import Path

from src.config import CAMINHO_BANCO, PASTA_DADOS
from src.database import conectar

ESQUEMA_CATALOGO = """
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


def carregar_catalogo(conexao: sqlite3.Connection, pasta_dados: Path) -> None:
    categorias = ler_csv(pasta_dados / "categories.csv")
    ids_categorias = {categoria["category_id"] for categoria in categorias}
    # A validação vem antes do esquema para uma falha não apagar o banco atual.
    produtos = [
        preparar_produto(produto, ids_categorias)
        for produto in ler_csv(pasta_dados / "products.csv")
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
    conexao.commit()


if __name__ == "__main__":
    conexao = conectar(CAMINHO_BANCO)
    carregar_catalogo(conexao, PASTA_DADOS)
    conexao.close()
    print(f"Banco criado em {CAMINHO_BANCO}")
