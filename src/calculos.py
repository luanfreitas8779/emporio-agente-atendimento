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


def calcular_compra(conexao: sqlite3.Connection, itens: list[ItemDaCompra]) -> CalculoDaCompra:
    linhas = []
    total = 0
    for item in itens:
        unitario = catalog.preco_final_em_centavos(conexao, item.product_id)
        subtotal = unitario * item.quantidade
        total += subtotal
        linhas.append(
            LinhaDaCompra(
                catalog.nome_do_produto(conexao, item.product_id),
                item.quantidade,
                catalog.formatar_preco(unitario),
                catalog.formatar_preco(subtotal),
            )
        )
    return CalculoDaCompra(linhas, catalog.formatar_preco(total))
