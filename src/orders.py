import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.catalog import format_price
from src.dates import format_date
from src.phone import normalize_phone

PAYMENT_METHODS = {
    "pix": "PIX",
    "debit": "débito",
    "boleto": "boleto",
}


@dataclass(frozen=True)
class Customer:
    id: int
    name: str

    @property
    def first_name(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class OrderItem:
    name: str
    quantity: int


@dataclass_pydantic(frozen=True)
class Order:
    number: int
    order_date: str
    # The original code stays in the code only: the model receives only the status description.
    status: Annotated[str, Field(exclude=True)]
    status_description: str
    items: list[OrderItem]
    total: str
    payment: str
    rastreio: str | None
    estimated_delivery: str | None
    # Calculated in code; only present for an order shipped after the estimate (DQ-16).
    delay: str | None = None


def identify_customer(connection: sqlite3.Connection, phone: str | None) -> Customer | None:
    digits = normalize_phone(phone or "")
    if digits is None:
        return None
    row = connection.execute(
        "SELECT customer_id, name FROM customers WHERE phone = ?", (digits,)
    ).fetchone()
    return Customer(row["customer_id"], row["name"]) if row else None


CREDIT_INSTALLMENTS = {f"credit_{n}x": n for n in range(1, 13)}
# Fixed, literal translation (ADR-012): it adds no meaning that the data does not have.
ORDER_STATUS = {
    "pending": "pending",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def valid_payment(payment_code: str) -> bool:
    return payment_code in PAYMENT_METHODS or payment_code in CREDIT_INSTALLMENTS


def describe_payment(payment_code: str) -> str:
    if payment_code in CREDIT_INSTALLMENTS:
        return f"cartão de crédito em {CREDIT_INSTALLMENTS[payment_code]}x"
    return PAYMENT_METHODS[payment_code]


def get_items(connection: sqlite3.Connection, number: int) -> list[OrderItem]:
    rows = connection.execute(
        """
        SELECT p.name, i.quantity
        FROM order_items i JOIN products p ON p.product_id = i.product_id
        WHERE i.order_id = ?
        ORDER BY p.name
        """,
        (number,),
    ).fetchall()
    return [OrderItem(row["name"], row["quantity"]) for row in rows]


def describe_delay(row: sqlite3.Row, today: date | None) -> str | None:
    if today is None or row["status"] != "shipped" or not row["estimated_delivery"]:
        return None
    days = (today - date.fromisoformat(row["estimated_delivery"])).days
    if days <= 0:
        return None
    unit = "dia" if days == 1 else "dias"
    estimate = format_date(row["estimated_delivery"])
    return f"A entrega estimada era {estimate} e o pedido segue como enviado: {days} {unit} de atraso."


def get_orders(
    connection: sqlite3.Connection,
    customer_id: int,
    number: int | None = None,
    today: date | None = None,
) -> list[Order]:
    rows = connection.execute(
        """
        SELECT *
        FROM orders
        WHERE customer_id = ? AND (? IS NULL OR order_id = ?)
        ORDER BY order_id
        """,
        (customer_id, number, number),
    ).fetchall()
    return [
        Order(
            row["order_id"],
            format_date(row["order_date"]),
            row["status"],
            ORDER_STATUS[row["status"]],
            get_items(connection, row["order_id"]),
            # The recorded total prevails over the sum of the items (DQ-11 and DQ-12).
            format_price(row["total_cents"]),
            describe_payment(row["payment_method"]),
            row["tracking_code"],
            format_date(row["estimated_delivery"]),
            describe_delay(row, today),
        )
        for row in rows
    ]
