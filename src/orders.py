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


@dataclass(frozen=True)
class Pedido:
    numero: int
    status: str
    rastreio: str | None
    entrega_estimada: str | None


def consultar_pedidos(
    conexao: sqlite3.Connection, cliente_id: int, numero: int | None = None
) -> list[Pedido]:
    linhas = conexao.execute(
        """
        SELECT order_id, status, tracking_code, estimated_delivery
        FROM orders
        WHERE customer_id = ? AND (? IS NULL OR order_id = ?)
        ORDER BY order_id
        """,
        (cliente_id, numero, numero),
    ).fetchall()
    return [
        Pedido(l["order_id"], l["status"], l["tracking_code"], l["estimated_delivery"])
        for l in linhas
    ]
