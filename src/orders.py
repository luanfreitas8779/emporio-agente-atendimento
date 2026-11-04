import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.catalog import format_price
from src.dates import format_date
from src.phone import normalize_phone

FORMAS_DE_PAGAMENTO = {
    "pix": "PIX",
    "debit": "débito",
    "boleto": "boleto",
}


@dataclass(frozen=True)
class Cliente:
    id: int
    name: str

    @property
    def primeiro_nome(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class ItemPedido:
    name: str
    quantity: int


@dataclass_pydantic(frozen=True)
class Pedido:
    numero: int
    order_date: str
    # The original code stays in the code only: the model receives only the status description.
    status: Annotated[str, Field(exclude=True)]
    situacao: str
    itens: list[ItemPedido]
    total: str
    pagamento: str
    rastreio: str | None
    entrega_estimada: str | None
    # Calculated in code; only present for an order shipped after the estimate (DQ-16).
    atraso: str | None = None


def identificar_cliente(connection: sqlite3.Connection, phone: str | None) -> Cliente | None:
    digits = normalize_phone(phone or "")
    if digits is None:
        return None
    row = connection.execute(
        "SELECT customer_id, name FROM customers WHERE phone = ?", (digits,)
    ).fetchone()
    return Cliente(row["customer_id"], row["name"]) if row else None


PARCELAS_NO_CREDITO = {f"credit_{n}x": n for n in range(1, 13)}
# Fixed, literal translation (ADR-012): it adds no meaning that the data does not have.
STATUS_DE_PEDIDO = {
    "pending": "pendente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def pagamento_valido(codigo: str) -> bool:
    return codigo in FORMAS_DE_PAGAMENTO or codigo in PARCELAS_NO_CREDITO


def descrever_pagamento(codigo: str) -> str:
    if codigo in PARCELAS_NO_CREDITO:
        return f"cartão de crédito em {PARCELAS_NO_CREDITO[codigo]}x"
    return FORMAS_DE_PAGAMENTO[codigo]


def consultar_itens(connection: sqlite3.Connection, numero: int) -> list[ItemPedido]:
    rows = connection.execute(
        """
        SELECT p.name, i.quantity
        FROM order_items i JOIN products p ON p.product_id = i.product_id
        WHERE i.order_id = ?
        ORDER BY p.name
        """,
        (numero,),
    ).fetchall()
    return [ItemPedido(row["name"], row["quantity"]) for row in rows]


def descrever_atraso(row: sqlite3.Row, hoje: date | None) -> str | None:
    if hoje is None or row["status"] != "shipped" or not row["estimated_delivery"]:
        return None
    dias = (hoje - date.fromisoformat(row["estimated_delivery"])).days
    if dias <= 0:
        return None
    unidade = "dia" if dias == 1 else "dias"
    previsao = format_date(row["estimated_delivery"])
    return f"A entrega estimada era {previsao} e o pedido segue como enviado: {dias} {unidade} de atraso."


def consultar_pedidos(
    connection: sqlite3.Connection,
    cliente_id: int,
    numero: int | None = None,
    hoje: date | None = None,
) -> list[Pedido]:
    rows = connection.execute(
        """
        SELECT *
        FROM orders
        WHERE customer_id = ? AND (? IS NULL OR order_id = ?)
        ORDER BY order_id
        """,
        (cliente_id, numero, numero),
    ).fetchall()
    return [
        Pedido(
            row["order_id"],
            format_date(row["order_date"]),
            row["status"],
            STATUS_DE_PEDIDO[row["status"]],
            consultar_itens(connection, row["order_id"]),
            # The recorded total prevails over the sum of the items (DQ-11 and DQ-12).
            format_price(row["total_cents"]),
            descrever_pagamento(row["payment_method"]),
            row["tracking_code"],
            format_date(row["estimated_delivery"]),
            descrever_atraso(row, hoje),
        )
        for row in rows
    ]
