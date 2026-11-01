import sqlite3


class ErroDeReposicao(ValueError):
    """Reposição recusada: o banco não foi alterado."""


def repor_estoque(conexao: sqlite3.Connection, product_id: int, quantidade: int) -> None:
    if quantidade < 1:
        raise ErroDeReposicao("A quantidade deve ser maior que zero.")
    produto = conexao.execute(
        "SELECT status FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    if produto is None:
        raise ErroDeReposicao(f"Produto {product_id} inexistente.")
    # O status tem prioridade sobre o estoque: repor outro status não muda a disponibilidade.
    if produto["status"] != "active":
        raise ErroDeReposicao(f"O produto {product_id} não está ativo; a reposição não teria efeito.")
    conexao.execute(
        "UPDATE products SET stock_quantity = stock_quantity + ? WHERE product_id = ?",
        (quantidade, product_id),
    )
    conexao.commit()
