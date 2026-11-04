import sqlite3
from datetime import date, timedelta
from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.dates import format_date

REGRET_DEADLINE_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30
PREFERENCE_EXCHANGE_DAYS = 7
LEGAL_WARRANTY_DAYS = 90

NOT_DELIVERED = {
    "pending": "O pedido ainda não foi enviado, então não há produto recebido para devolver.",
    "confirmed": "O pedido ainda não foi enviado, então não há produto recebido para devolver.",
    "cancelled": "O pedido foi cancelado, então não há produto para devolver.",
}

APPROXIMATION_NOTICE = (
    "A loja não registra a data real de recebimento: os prazos usam a entrega estimada "
    "como aproximação. Se o recebimento foi em outra data, a equipe confere."
)
ANALYSIS_NOTICE = (
    "O resultado vale para o prazo. A troca ou a devolução depende da análise do produto "
    "pela equipe, e não há aprovação garantida."
)

NO_IN_PERSON_REGRET_NOTICE = (
    "O direito de arrependimento vale para compras online. Em compra presencial, o cliente "
    "ainda pode pedir troca por defeito ou por preferência, dentro dos prazos da política."
)

NOT_ARRIVED_YET_NOTICE = (
    "Pela entrega estimada, o pedido ainda não chegou. Os prazos contados do recebimento "
    "só começam quando o cliente receber o produto."
)


class Reason(StrEnum):
    REGRET = "arrependimento"
    DEFECT = "defeito"
    PREFERENCE = "preferencia"


class Channel(StrEnum):
    ONLINE = "online"
    IN_PERSON = "presencial"


class Result(StrEnum):
    WITHIN_DEADLINE = "dentro_do_prazo"
    PAST_DEADLINE = "fora_do_prazo"
    NOT_APPLICABLE = "nao_se_aplica"
    MISSING_DATA = "faltam_dados"
    ORDER_NOT_FOUND = "pedido_nao_encontrado"


@dataclass_pydantic(frozen=True)
class Rule:
    name: str
    result: Result
    deadline: str


@dataclass_pydantic(frozen=True)
class Verdict:
    result: Result
    rules: list[Rule]
    # What the model must ask the customer before there is a verdict.
    missing: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    approximate_date: bool = False
    receipt_date: str | None = None
    reference_date: str | None = None


def assess_return(
    connection: sqlite3.Connection,
    customer_id: int,
    number: int,
    reason: Reason,
    channel: Channel | None,
    today: date,
) -> Verdict:
    row = connection.execute(
        "SELECT order_date, status, estimated_delivery FROM orders WHERE order_id = ? AND customer_id = ?",
        (number, customer_id),
    ).fetchone()
    if row is None:
        return Verdict(Result.ORDER_NOT_FOUND, [])
    if row["status"] in NOT_DELIVERED:
        return Verdict(Result.NOT_APPLICABLE, [], notices=[NOT_DELIVERED[row["status"]]])
    # The channel only matters after confirming that the order exists and belongs to the customer.
    if reason == Reason.REGRET and channel is None:
        return Verdict(Result.MISSING_DATA, [], ["canal_de_compra"])
    if reason == Reason.REGRET and channel == Channel.IN_PERSON:
        return Verdict(Result.NOT_APPLICABLE, [], notices=[NO_IN_PERSON_REGRET_NOTICE])
    purchase = date.fromisoformat(row["order_date"])
    # Without an actual delivery date in the data (DQ-17), receipt is the estimated delivery.
    receipt = date.fromisoformat(row["estimated_delivery"])
    if reason == Reason.DEFECT:
        rules = [
            _rule("troca_por_defeito", purchase, DEFECT_EXCHANGE_DAYS, today),
            _rule("garantia_legal", receipt, LEGAL_WARRANTY_DAYS, today),
        ]
    elif reason == Reason.PREFERENCE:
        rules = [_rule("troca_por_preferencia", receipt, PREFERENCE_EXCHANGE_DAYS, today)]
    else:
        rules = [_rule("arrependimento", receipt, REGRET_DEADLINE_DAYS, today)]
    notices = [APPROXIMATION_NOTICE, ANALYSIS_NOTICE]
    if receipt > today:
        notices.insert(0, NOT_ARRIVED_YET_NOTICE)
    within = any(r.result == Result.WITHIN_DEADLINE for r in rules)
    return Verdict(
        Result.WITHIN_DEADLINE if within else Result.PAST_DEADLINE,
        rules,
        notices=notices,
        approximate_date=True,
        receipt_date=format_date(receipt),
        reference_date=format_date(today),
    )


def _rule(name: str, start: date, days: int, today: date) -> Rule:
    limit = start + timedelta(days=days)
    result = Result.WITHIN_DEADLINE if today <= limit else Result.PAST_DEADLINE
    return Rule(name, result, format_date(limit))
