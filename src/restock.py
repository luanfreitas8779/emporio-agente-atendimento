import sqlite3


def repor_estoque(conexao: sqlite3.Connection, product_id: int, quantidade: int) -> None:
    conexao.execute(
        "UPDATE products SET stock_quantity = stock_quantity + ? WHERE product_id = ?",
        (quantidade, product_id),
    )
    conexao.commit()
