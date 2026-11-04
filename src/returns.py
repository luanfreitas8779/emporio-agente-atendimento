import sqlite3
from datetime import date, timedelta
from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.dates import format_date

PRAZO_DE_ARREPENDIMENTO_EM_DIAS = 7
PRAZO_DE_TROCA_POR_DEFEITO_EM_DIAS = 30
PRAZO_DE_TROCA_POR_PREFERENCIA_EM_DIAS = 7
PRAZO_DA_GARANTIA_LEGAL_EM_DIAS = 90

SEM_ENTREGA = {
    "pending": "O pedido ainda não foi enviado, então não há produto recebido para devolver.",
    "confirmed": "O pedido ainda não foi enviado, então não há produto recebido para devolver.",
    "cancelled": "O pedido foi cancelado, então não há produto para devolver.",
}

AVISO_DE_APROXIMACAO = (
    "A loja não registra a data real de recebimento: os prazos usam a entrega estimada "
    "como aproximação. Se o recebimento foi em outra data, a equipe confere."
)
AVISO_DE_ANALISE = (
    "O resultado vale para o prazo. A troca ou a devolução depende da análise do produto "
    "pela equipe, e não há aprovação garantida."
)

AVISO_SEM_ARREPENDIMENTO_PRESENCIAL = (
    "O direito de arrependimento vale para compras online. Em compra presencial, o cliente "
    "ainda pode pedir troca por defeito ou por preferência, dentro dos prazos da política."
)

AVISO_AINDA_NAO_CHEGOU = (
    "Pela entrega estimada, o pedido ainda não chegou. Os prazos contados do recebimento "
    "só começam quando o cliente receber o produto."
)


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
    name: str
    resultado: Resultado
    prazo_ate: str


@dataclass_pydantic(frozen=True)
class Veredito:
    resultado: Resultado
    regras: list[Regra]
    # What the model must ask the customer before there is a verdict.
    faltando: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    data_aproximada: bool = False
    data_de_recebimento: str | None = None
    reference_date: str | None = None


def avaliar_devolucao(
    connection: sqlite3.Connection,
    customer_id: int,
    number: int,
    motivo: Motivo,
    canal: Canal | None,
    today: date,
) -> Veredito:
    row = connection.execute(
        "SELECT order_date, status, estimated_delivery FROM orders WHERE order_id = ? AND customer_id = ?",
        (number, customer_id),
    ).fetchone()
    if row is None:
        return Veredito(Resultado.PEDIDO_NAO_ENCONTRADO, [])
    if row["status"] in SEM_ENTREGA:
        return Veredito(Resultado.NAO_SE_APLICA, [], notices=[SEM_ENTREGA[row["status"]]])
    # The channel only matters after confirming that the order exists and belongs to the customer.
    if motivo == Motivo.ARREPENDIMENTO and canal is None:
        return Veredito(Resultado.FALTAM_DADOS, [], ["canal_de_compra"])
    if motivo == Motivo.ARREPENDIMENTO and canal == Canal.PRESENCIAL:
        return Veredito(Resultado.NAO_SE_APLICA, [], notices=[AVISO_SEM_ARREPENDIMENTO_PRESENCIAL])
    compra = date.fromisoformat(row["order_date"])
    # Without an actual delivery date in the data (DQ-17), receipt is the estimated delivery.
    recebimento = date.fromisoformat(row["estimated_delivery"])
    if motivo == Motivo.DEFEITO:
        regras = [
            _regra("troca_por_defeito", compra, PRAZO_DE_TROCA_POR_DEFEITO_EM_DIAS, today),
            _regra("garantia_legal", recebimento, PRAZO_DA_GARANTIA_LEGAL_EM_DIAS, today),
        ]
    elif motivo == Motivo.PREFERENCIA:
        regras = [_regra("troca_por_preferencia", recebimento, PRAZO_DE_TROCA_POR_PREFERENCIA_EM_DIAS, today)]
    else:
        regras = [_regra("arrependimento", recebimento, PRAZO_DE_ARREPENDIMENTO_EM_DIAS, today)]
    notices = [AVISO_DE_APROXIMACAO, AVISO_DE_ANALISE]
    if recebimento > today:
        notices.insert(0, AVISO_AINDA_NAO_CHEGOU)
    dentro = any(r.resultado == Resultado.DENTRO_DO_PRAZO for r in regras)
    return Veredito(
        Resultado.DENTRO_DO_PRAZO if dentro else Resultado.FORA_DO_PRAZO,
        regras,
        notices=notices,
        data_aproximada=True,
        data_de_recebimento=format_date(recebimento),
        reference_date=format_date(today),
    )


def _regra(name: str, inicio: date, days: int, today: date) -> Regra:
    limite = inicio + timedelta(days=days)
    resultado = Resultado.DENTRO_DO_PRAZO if today <= limite else Resultado.FORA_DO_PRAZO
    return Regra(name, resultado, format_date(limite))
