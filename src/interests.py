import sqlite3
from enum import StrEnum

from src.catalog import nome_do_produto
from src.memory import _agora
from src.phone import normalizar_telefone


class Resultado(StrEnum):
    REGISTRADO = "registrado"
    JA_REGISTRADO = "ja_registrado"
    PRODUTO_INEXISTENTE = "produto_inexistente"
    TELEFONE_INVALIDO = "telefone_invalido"


def registrar(conexao: sqlite3.Connection, telefone: str, product_id: int) -> Resultado:
    chave = normalizar_telefone(telefone)
    if chave is None:
        return Resultado.TELEFONE_INVALIDO
    if nome_do_produto(conexao, product_id) is None:
        return Resultado.PRODUTO_INEXISTENTE
    cursor = conexao.execute(
        "INSERT INTO product_interests (phone, product_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone, product_id) DO NOTHING",
        (chave, product_id, _agora()),
    )
    conexao.commit()
    return Resultado.REGISTRADO if cursor.rowcount else Resultado.JA_REGISTRADO


def listar_pendentes(conexao: sqlite3.Connection, telefone: str) -> list[str]:
    linhas = conexao.execute(
        """
        SELECT p.name FROM product_interests i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.phone = ? AND i.status = 'pending' ORDER BY i.id
        """,
        (normalizar_telefone(telefone),),
    ).fetchall()
    return [linha["name"] for linha in linhas]
