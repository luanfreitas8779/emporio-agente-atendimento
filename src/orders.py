import sqlite3
from dataclasses import dataclass

from src.catalog import formatar_preco
from src.phone import normalizar_telefone

FORMAS_DE_PAGAMENTO = {
    "pix": "PIX",
    "debit": "débito",
    "boleto": "boleto",
}


@dataclass(frozen=True)
class Cliente:
    id: int
    nome: str


@dataclass(frozen=True)
class ItemPedido:
    nome: str
    quantidade: int


@dataclass(frozen=True)
class Pedido:
    numero: int
    data: str
    status: str
    itens: list[ItemPedido]
    total: str
    pagamento: str
    rastreio: str | None
    entrega_estimada: str | None


def identificar_cliente(conexao: sqlite3.Connection, telefone: str) -> Cliente | None:
    digitos = normalizar_telefone(telefone)
    if digitos is None:
        return None
    linha = conexao.execute(
        "SELECT customer_id, name FROM customers WHERE phone = ?", (digitos,)
    ).fetchone()
    return Cliente(linha["customer_id"], linha["name"]) if linha else None


PARCELAS_NO_CREDITO = {f"credit_{n}x": n for n in range(1, 13)}
STATUS_DE_PEDIDO = {"pending", "confirmed", "shipped", "delivered", "cancelled"}


def pagamento_valido(codigo: str) -> bool:
    return codigo in FORMAS_DE_PAGAMENTO or codigo in PARCELAS_NO_CREDITO


def descrever_pagamento(codigo: str) -> str:
    if codigo in PARCELAS_NO_CREDITO:
        return f"cartão de crédito em {PARCELAS_NO_CREDITO[codigo]}x"
    return FORMAS_DE_PAGAMENTO[codigo]


def consultar_itens(conexao: sqlite3.Connection, numero: int) -> list[ItemPedido]:
    linhas = conexao.execute(
        """
        SELECT p.name, i.quantity
        FROM order_items i JOIN products p ON p.product_id = i.product_id
        WHERE i.order_id = ?
        ORDER BY p.name
        """,
        (numero,),
    ).fetchall()
    return [ItemPedido(l["name"], l["quantity"]) for l in linhas]


def consultar_pedidos(
    conexao: sqlite3.Connection, cliente_id: int, numero: int | None = None
) -> list[Pedido]:
    linhas = conexao.execute(
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
            l["order_id"],
            l["order_date"],
            l["status"],
            consultar_itens(conexao, l["order_id"]),
            # O total registrado prevalece sobre a soma dos itens (DQ-11 e DQ-12).
            formatar_preco(l["total_cents"]),
            descrever_pagamento(l["payment_method"]),
            l["tracking_code"],
            l["estimated_delivery"],
        )
        for l in linhas
    ]
