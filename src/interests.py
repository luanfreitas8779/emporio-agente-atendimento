import sqlite3
from enum import StrEnum

from src.catalog import product_name
from src.memory import agora
from src.phone import normalize_phone


class Result(StrEnum):
    REGISTRADO = "registrado"
    JA_REGISTRADO = "ja_registrado"
    PRODUTO_INEXISTENTE = "produto_inexistente"
    TELEFONE_INVALIDO = "telefone_invalido"


def registrar(connection: sqlite3.Connection, phone: str, product_id: int) -> Result:
    key = normalize_phone(phone)
    if key is None:
        return Result.TELEFONE_INVALIDO
    if product_name(connection, product_id) is None:
        return Result.PRODUTO_INEXISTENTE
    cursor = connection.execute(
        "INSERT INTO product_interests (phone, product_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone, product_id) DO NOTHING",
        (key, product_id, agora()),
    )
    connection.commit()
    return Result.REGISTRADO if cursor.rowcount else Result.JA_REGISTRADO


def listar_pendentes(connection: sqlite3.Connection, phone: str) -> list[str]:
    key = normalize_phone(phone)
    if key is None:
        return []
    rows = connection.execute(
        """
        SELECT p.name FROM product_interests i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.phone = ? AND i.status = 'pending' ORDER BY i.id
        """,
        (key,),
    ).fetchall()
    return [row["name"] for row in rows]
