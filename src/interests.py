import sqlite3
from enum import StrEnum

from src.catalog import product_name
from src.memory import now_iso
from src.phone import normalize_phone


class Result(StrEnum):
    REGISTERED = "registrado"
    ALREADY_REGISTERED = "ja_registrado"
    PRODUCT_NOT_FOUND = "produto_inexistente"
    INVALID_PHONE = "telefone_invalido"


def register(connection: sqlite3.Connection, phone: str, product_id: int) -> Result:
    key = normalize_phone(phone)
    if key is None:
        return Result.INVALID_PHONE
    if product_name(connection, product_id) is None:
        return Result.PRODUCT_NOT_FOUND
    cursor = connection.execute(
        "INSERT INTO product_interests (phone, product_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT (phone, product_id) DO NOTHING",
        (key, product_id, now_iso()),
    )
    connection.commit()
    return Result.REGISTERED if cursor.rowcount else Result.ALREADY_REGISTERED


def list_pending(connection: sqlite3.Connection, phone: str) -> list[str]:
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
