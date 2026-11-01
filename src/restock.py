import argparse
import sqlite3
import sys

from src.config import CAMINHO_BANCO
from src.database import conectar


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


def principal(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        description="Simula a reposição de estoque no banco local, sem alterar os arquivos de origem."
    )
    analisador.add_argument("produto", type=int, help="id do produto")
    analisador.add_argument("--quantidade", type=int, default=5)
    analisador.add_argument("--banco", default=str(CAMINHO_BANCO))
    escolhidos = analisador.parse_args(argumentos)

    conexao = conectar(escolhidos.banco)
    try:
        repor_estoque(conexao, escolhidos.produto, escolhidos.quantidade)
    except ErroDeReposicao as erro:
        print(f"Reposição recusada: {erro}", file=sys.stderr)
        return 1
    finally:
        conexao.close()
    print(
        f"Reposição simulada: +{escolhidos.quantidade} unidades no produto {escolhidos.produto}. "
        "Para voltar ao estado original, rode: python -m src.load_data"
    )
    return 0
