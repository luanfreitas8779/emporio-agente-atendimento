"""Contas da compra feitas em código, para o modelo repassar o resultado sem calcular (ADR-013)."""

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
    # Só existe quando a conta tem exatamente dois itens: a diferença entre os subtotais.
    diferenca: str | None = None


def calcular_compra(
    conexao: sqlite3.Connection, itens: list[ItemDaCompra]
) -> CalculoDaCompra | str:
    for item in itens:
        if catalog.preco_final_em_centavos(conexao, item.product_id) is None:
            return f"Produto {item.product_id} não encontrado: nenhuma conta foi feita."
    linhas = []
    subtotais = []
    total = 0
    total_no_pix = 0
    for item in itens:
        unitario = catalog.preco_final_em_centavos(conexao, item.product_id)
        subtotal = unitario * item.quantidade
        subtotais.append(subtotal)
        total += subtotal
        total_no_pix += catalog.preco_no_pix_em_centavos(conexao, item.product_id) * item.quantidade
        linhas.append(
            LinhaDaCompra(
                catalog.nome_do_produto(conexao, item.product_id),
                item.quantidade,
                catalog.formatar_preco(unitario),
                catalog.formatar_preco(subtotal),
            )
        )
    return CalculoDaCompra(
        linhas,
        catalog.formatar_preco(total),
        catalog.formatar_preco(total_no_pix),
        catalog.formatar_preco(total - total_no_pix),
        catalog.formatar_preco(abs(subtotais[0] - subtotais[1])) if len(subtotais) == 2 else None,
    )
