import sqlite3
from datetime import date, timedelta
from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.datas import formatar_data

PRAZO_DE_ARREPENDIMENTO_EM_DIAS = 7
PRAZO_DE_TROCA_POR_DEFEITO_EM_DIAS = 30
PRAZO_DA_GARANTIA_LEGAL_EM_DIAS = 90


class Motivo(StrEnum):
    ARREPENDIMENTO = "arrependimento"
    DEFEITO = "defeito"
    PREFERENCIA = "preferencia"


class Canal(StrEnum):
    ONLINE = "online"
    PRESENCIAL = "presencial"


class Resultado(StrEnum):
    DENTRO_DO_PRAZO = "dentro_do_prazo"
    FORA_DO_PRAZO = "fora_do_prazo"
    NAO_SE_APLICA = "nao_se_aplica"
    FALTAM_DADOS = "faltam_dados"
    PEDIDO_NAO_ENCONTRADO = "pedido_nao_encontrado"


@dataclass_pydantic(frozen=True)
class Regra:
    nome: str
    resultado: Resultado
    prazo_ate: str


@dataclass_pydantic(frozen=True)
class Veredito:
    resultado: Resultado
    regras: list[Regra]
    # O que o modelo deve perguntar ao cliente antes de haver veredito.
    faltando: list[str] = field(default_factory=list)


def avaliar_devolucao(
    conexao: sqlite3.Connection,
    cliente_id: int,
    numero: int,
    motivo: Motivo,
    canal: Canal | None,
    hoje: date,
) -> Veredito:
    if motivo == Motivo.ARREPENDIMENTO and canal is None:
        return Veredito(Resultado.FALTAM_DADOS, [], ["canal_de_compra"])
    if motivo == Motivo.ARREPENDIMENTO and canal == Canal.PRESENCIAL:
        return Veredito(Resultado.NAO_SE_APLICA, [])
    linha = conexao.execute(
        "SELECT order_date, estimated_delivery FROM orders WHERE order_id = ? AND customer_id = ?",
        (numero, cliente_id),
    ).fetchone()
    if linha is None:
        return Veredito(Resultado.PEDIDO_NAO_ENCONTRADO, [])
    compra = date.fromisoformat(linha["order_date"])
    # Sem data real de entrega nos dados (DQ-17), o recebimento é a entrega estimada.
    recebimento = date.fromisoformat(linha["estimated_delivery"])
    if motivo == Motivo.DEFEITO:
        regras = [
            _regra("troca_por_defeito", compra, PRAZO_DE_TROCA_POR_DEFEITO_EM_DIAS, hoje),
            _regra("garantia_legal", recebimento, PRAZO_DA_GARANTIA_LEGAL_EM_DIAS, hoje),
        ]
    else:
        regras = [_regra("arrependimento", recebimento, PRAZO_DE_ARREPENDIMENTO_EM_DIAS, hoje)]
    dentro = any(r.resultado == Resultado.DENTRO_DO_PRAZO for r in regras)
    return Veredito(Resultado.DENTRO_DO_PRAZO if dentro else Resultado.FORA_DO_PRAZO, regras)


def _regra(nome: str, inicio: date, dias: int, hoje: date) -> Regra:
    limite = inicio + timedelta(days=dias)
    resultado = Resultado.DENTRO_DO_PRAZO if hoje <= limite else Resultado.FORA_DO_PRAZO
    return Regra(nome, resultado, formatar_data(limite))
