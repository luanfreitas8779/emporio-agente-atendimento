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
    quantidade: Annotated[int, Field(ge=1, le=QUANTIDADE_MAXIMA)]


@dataclass_pydantic(frozen=True)
class LinhaDaCompra:
    nome: str
    quantidade: int
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
    observacao_pix: str | None = None
    frete: str = ""


# data/politicas.md, entregas section: free above R$ 500,00 and a flat fee below that.
LIMITE_DO_FRETE_GRATIS = 50_000
TAXA_DO_FRETE_FIXO = 3_500


def frete_na_regiao_metropolitana(total: int) -> str:
    """The policy's shipping for the total in cents; the exact limit amount is not defined."""
    if total > LIMITE_DO_FRETE_GRATIS:
        return "Frete grátis na região metropolitana de Campo Grande."
    if total < LIMITE_DO_FRETE_GRATIS:
        return f"Taxa fixa de {catalog.formatar_preco(TAXA_DO_FRETE_FIXO)} na região metropolitana de Campo Grande."
    return (
        f"A política não define o frete para um pedido de exatamente {catalog.formatar_preco(LIMITE_DO_FRETE_GRATIS)}: "
        "confirme com a loja."
    )


AVISO_DA_DISPONIBILIDADE = {
    catalog.INDISPONIVEL: "sem estoque.",
    catalog.FORA_DE_CATALOGO: "fora de catálogo.",
    catalog.LANCAMENTO: "lançamento, ainda não está à venda.",
}


def calcular_compra(
    connection: sqlite3.Connection, itens: list[ItemDaCompra]
) -> CalculoDaCompra | str:
    # The same product cited twice becomes a single line, with the quantity summed.
    quantidades: dict[int, int] = {}
    for item in itens:
        quantidades[item.product_id] = quantidades.get(item.product_id, 0) + item.quantidade

    produtos = {}
    for product_id in quantidades:
        produto = catalog.dados_para_conta(connection, product_id)
        if produto is None:
            return f"Produto {product_id} não encontrado: nenhuma conta foi feita."
        produtos[product_id] = produto

    linhas = []
    subtotais = []
    avisos = []
    observacoes_do_pix = []
    total = 0
    total_no_pix = 0
    for product_id, quantidade in quantidades.items():
        produto = produtos[product_id]
        subtotal = produto.preco_final * quantidade
        subtotais.append(subtotal)
        total += subtotal
        total_no_pix += produto.preco_no_pix * quantidade
        if produto.disponibilidade in AVISO_DA_DISPONIBILIDADE:
            avisos.append(f"{produto.nome}: {AVISO_DA_DISPONIBILIDADE[produto.disponibilidade]}")
        elif produto.estoque < quantidade:
            avisos.append(f"{produto.nome}: o estoque não cobre {quantidade} unidades.")
        if produto.em_promocao:
            observacoes_do_pix.append(f"{produto.nome}: o PIX não soma ao desconto da promoção.")
        linhas.append(
            LinhaDaCompra(
                produto.nome,
                quantidade,
                catalog.formatar_preco(produto.preco_final),
                catalog.formatar_preco(subtotal),
            )
        )
    return CalculoDaCompra(
        linhas,
        catalog.formatar_preco(total),
        catalog.formatar_preco(total_no_pix),
        catalog.formatar_preco(total - total_no_pix),
        catalog.formatar_preco(abs(subtotais[0] - subtotais[1])) if len(subtotais) == 2 else None,
        " ".join(avisos) or None,
        " ".join(observacoes_do_pix) or None,
        frete_na_regiao_metropolitana(total),
    )
