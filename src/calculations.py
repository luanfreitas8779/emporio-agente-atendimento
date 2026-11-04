"""Purchase calculations made in code, so the model passes the result on without calculating (ADR-013)."""

import sqlite3
from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass as dataclass_pydantic

from src import catalog

MAX_ID = 2**31 - 1
MAX_QUANTITY = 1000


@dataclass_pydantic(frozen=True)
class PurchaseItem:
    product_id: Annotated[int, Field(ge=1, le=MAX_ID)]
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)]


@dataclass_pydantic(frozen=True)
class PurchaseLine:
    name: str
    quantity: int
    unit_price: str
    subtotal: str


@dataclass_pydantic(frozen=True)
class PurchaseCalculation:
    items: list[PurchaseLine]
    total: str
    pix_total: str
    pix_savings: str
    # Only present when the calculation has exactly two items: the difference between the subtotals.
    difference: str | None = None
    # A product that cannot be sold now: the calculation is only a price reference.
    warning: str | None = None
    # A product on promotion: PIX does not stack with the discount, so there are no savings on it.
    pix_note: str | None = None
    shipping: str = ""


# data/politicas.md, entregas section: free above R$ 500,00 and a flat fee below that.
FREE_SHIPPING_THRESHOLD = 50_000
FLAT_SHIPPING_FEE = 3_500


def metro_area_shipping(total: int) -> str:
    """The policy's shipping for the total in cents; the exact limit amount is not defined."""
    if total > FREE_SHIPPING_THRESHOLD:
        return "Frete grátis na região metropolitana de Campo Grande."
    if total < FREE_SHIPPING_THRESHOLD:
        return f"Taxa fixa de {catalog.format_price(FLAT_SHIPPING_FEE)} na região metropolitana de Campo Grande."
    return (
        f"A política não define o frete para um pedido de exatamente {catalog.format_price(FREE_SHIPPING_THRESHOLD)}: "
        "confirme com a loja."
    )


AVAILABILITY_WARNINGS = {
    catalog.UNAVAILABLE: "sem estoque.",
    catalog.DISCONTINUED: "fora de catálogo.",
    catalog.NEW_RELEASE: "lançamento, ainda não está à venda.",
}


def calculate_purchase(
    connection: sqlite3.Connection, items: list[PurchaseItem]
) -> PurchaseCalculation | str:
    # The same product cited twice becomes a single line, with the quantity summed.
    quantities: dict[int, int] = {}
    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products = {}
    for product_id in quantities:
        product = catalog.pricing_data(connection, product_id)
        if product is None:
            return f"Produto {product_id} não encontrado: nenhuma conta foi feita."
        products[product_id] = product

    rows = []
    subtotals = []
    notices = []
    pix_notes = []
    total = 0
    pix_total = 0
    for product_id, quantity in quantities.items():
        product = products[product_id]
        subtotal = product.final_price * quantity
        subtotals.append(subtotal)
        total += subtotal
        pix_total += product.price_with_pix * quantity
        if product.availability in AVAILABILITY_WARNINGS:
            notices.append(f"{product.name}: {AVAILABILITY_WARNINGS[product.availability]}")
        elif product.stock < quantity:
            notices.append(f"{product.name}: o estoque não cobre {quantity} unidades.")
        if product.on_promotion:
            pix_notes.append(f"{product.name}: o PIX não soma ao desconto da promoção.")
        rows.append(
            PurchaseLine(
                product.name,
                quantity,
                catalog.format_price(product.final_price),
                catalog.format_price(subtotal),
            )
        )
    return PurchaseCalculation(
        rows,
        catalog.format_price(total),
        catalog.format_price(pix_total),
        catalog.format_price(total - pix_total),
        catalog.format_price(abs(subtotals[0] - subtotals[1])) if len(subtotals) == 2 else None,
        " ".join(notices) or None,
        " ".join(pix_notes) or None,
        metro_area_shipping(total),
    )
