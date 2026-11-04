import sqlite3
from enum import StrEnum

from src.catalog import nome_do_produto
from src.memory import agora
from src.phone import normalize_phone


class Resultado(StrEnum):
    REGISTRADO = "registrado"
    JA_REGISTRADO = "ja_registrado"
    PRODUTO_INEXISTENTE = "produto_inexistente"
    TELEFONE_INVALIDO = "telefone_invalido"


def registrar(connection: sqlite3.Connection, phone: str, product_id: int) -> Resultado:
    chave = normalize_phone(phone)
    if chave is None:
        return Resultado.TELEFONE_INVALIDO
    if nome_do_produto(connection, product_id) is None:
        return Resultado.PRODUTO_INEXISTENTE
    cursor = connection.execute(
        "INSERT INTO product_interests (phone, product_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone, product_id) DO NOTHING",
        (chave, product_id, agora()),
    )
    connection.commit()
    return Resultado.REGISTRADO if cursor.rowcount else Resultado.JA_REGISTRADO


def listar_pendentes(connection: sqlite3.Connection, phone: str) -> list[str]:
    chave = normalize_phone(phone)
    if chave is None:
        return []
    linhas = connection.execute(
        """
        SELECT p.name FROM product_interests i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.phone = ? AND i.status = 'pending' ORDER BY i.id
        """,
        (chave,),
    ).fetchall()
    return [linha["name"] for linha in linhas]
