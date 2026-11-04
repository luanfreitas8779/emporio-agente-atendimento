"""Purchase calculations made in code, so the model passes the result on without calculating (ADR-013)."""

import sqlite3
from typing import Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass as dataclass_pydantic

from src import catalog

ID_MAXIMO = 2**31 - 1
QUANTIDADE_MAXIMA = 1000


@dataclass_pydantic(frozen=True)
class ItemDaCompra:
    product_id: Annotated[int, Field(ge=1, le=ID_MAXIMO)]
    quantity: Annotated[int, Field(ge=1, le=QUANTIDADE_MAXIMA)]


@dataclass_pydantic(frozen=True)
class LinhaDaCompra:
    name: str
    quantity: int
    preco_unitario: str
    subtotal: str


@dataclass_pydantic(frozen=True)
class CalculoDaCompra:
    itens: list[LinhaDaCompra]
    total: str
    total_no_pix: str
    economia_no_pix: str
    # Only present when the calculation has exactly two items: the difference between the subtotals.
    diferenca: str | None = None
    # A product that cannot be sold now: the calculation is only a price reference.
    aviso: str | None = None
    # A product on promotion: PIX does not stack with the discount, so there are no savings on it.
    pix_note: str | None = None
    frete: str = ""


# data/politicas.md, entregas section: free above R$ 500,00 and a flat fee below that.
LIMITE_DO_FRETE_GRATIS = 50_000
TAXA_DO_FRETE_FIXO = 3_500


def frete_na_regiao_metropolitana(total: int) -> str:
    """The policy's shipping for the total in cents; the exact limit amount is not defined."""
    if total > LIMITE_DO_FRETE_GRATIS:
        return "Frete grátis na região metropolitana de Campo Grande."
    if total < LIMITE_DO_FRETE_GRATIS:
        return f"Taxa fixa de {catalog.format_price(TAXA_DO_FRETE_FIXO)} na região metropolitana de Campo Grande."
    return (
        f"A política não define o frete para um pedido de exatamente {catalog.format_price(LIMITE_DO_FRETE_GRATIS)}: "
        "confirme com a loja."
    )


AVISO_DA_DISPONIBILIDADE = {
    catalog.UNAVAILABLE: "sem estoque.",
    catalog.DISCONTINUED: "fora de catálogo.",
    catalog.NEW_RELEASE: "lançamento, ainda não está à venda.",
}


def calcular_compra(
    connection: sqlite3.Connection, itens: list[ItemDaCompra]
) -> CalculoDaCompra | str:
    # The same product cited twice becomes a single line, with the quantity summed.
    quantidades: dict[int, int] = {}
    for item in itens:
        quantidades[item.product_id] = quantidades.get(item.product_id, 0) + item.quantity

    products = {}
    for product_id in quantidades:
        product = catalog.pricing_data(connection, product_id)
        if product is None:
            return f"Produto {product_id} não encontrado: nenhuma conta foi feita."
        products[product_id] = product

    rows = []
    subtotais = []
    avisos = []
    observacoes_do_pix = []
    total = 0
    total_no_pix = 0
    for product_id, quantity in quantidades.items():
        product = products[product_id]
        subtotal = product.final_price * quantity
        subtotais.append(subtotal)
        total += subtotal
        total_no_pix += product.price_with_pix * quantity
        if product.availability in AVISO_DA_DISPONIBILIDADE:
            avisos.append(f"{product.name}: {AVISO_DA_DISPONIBILIDADE[product.availability]}")
        elif product.stock < quantity:
            avisos.append(f"{product.name}: o estoque não cobre {quantity} unidades.")
        if product.on_promotion:
            observacoes_do_pix.append(f"{product.name}: o PIX não soma ao desconto da promoção.")
        rows.append(
            LinhaDaCompra(
                product.name,
                quantity,
                catalog.format_price(product.final_price),
                catalog.format_price(subtotal),
            )
        )
    return CalculoDaCompra(
        rows,
        catalog.format_price(total),
        catalog.format_price(total_no_pix),
        catalog.format_price(total - total_no_pix),
        catalog.format_price(abs(subtotais[0] - subtotais[1])) if len(subtotais) == 2 else None,
        " ".join(avisos) or None,
        " ".join(observacoes_do_pix) or None,
        frete_na_regiao_metropolitana(total),
    )
