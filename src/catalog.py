import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Produto:
    nome: str
    categoria: str
    preco: str


def formatar_preco(centavos: int) -> str:
    reais, resto = divmod(centavos, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{resto:02d}"


def buscar_produtos(conexao: sqlite3.Connection, termo: str) -> list[Produto]:
    palavras = termo.split()
    filtros = " AND ".join("p.name LIKE ?" for _ in palavras)
    linhas = conexao.execute(
        f"""
        SELECT p.name, c.name AS categoria, p.price_cents
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        WHERE {filtros}
        ORDER BY p.name
        """,
        [f"%{palavra}%" for palavra in palavras],
    ).fetchall()
    return [
        Produto(linha["name"], linha["categoria"], formatar_preco(linha["price_cents"]))
        for linha in linhas
    ]
