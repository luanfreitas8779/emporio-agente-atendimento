import sqlite3
from enum import StrEnum

from src.memory import _agora
from src.phone import normalizar_telefone


class Resultado(StrEnum):
    REGISTRADO = "registrado"


def registrar(conexao: sqlite3.Connection, telefone: str, product_id: int) -> Resultado:
    chave = normalizar_telefone(telefone)
    conexao.execute(
        "INSERT INTO product_interests (phone, product_id, created_at) VALUES (?, ?, ?)",
        (chave, product_id, _agora()),
    )
    conexao.commit()
    return Resultado.REGISTRADO


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
