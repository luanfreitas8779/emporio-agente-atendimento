import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Cliente:
    id: int
    nome: str


def identificar_cliente(conexao: sqlite3.Connection, telefone: str) -> Cliente | None:
    digitos = "".join(c for c in telefone if c.isdigit())
    linha = conexao.execute(
        "SELECT customer_id, name FROM customers WHERE phone = ?", (digitos,)
    ).fetchone()
    return Cliente(linha["customer_id"], linha["name"]) if linha else None
