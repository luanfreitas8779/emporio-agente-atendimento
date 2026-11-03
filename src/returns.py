import sqlite3
from datetime import date, timedelta
from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.datas import formatar_data

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
    nome: str
    resultado: Resultado
    prazo_ate: str


@dataclass_pydantic(frozen=True)
class Veredito:
    resultado: Resultado
    regras: list[Regra]
    # What the model must ask the customer before there is a verdict.
    faltando: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    data_aproximada: bool = False
    data_de_recebimento: str | None = None
    data_de_referencia: str | None = None


def avaliar_devolucao(
    conexao: sqlite3.Connection,
    cliente_id: int,
    numero: int,
    motivo: Motivo,
    canal: Canal | None,
    hoje: date,
) -> Veredito:
    linha = conexao.execute(
        "SELECT order_date, status, estimated_delivery FROM orders WHERE order_id = ? AND customer_id = ?",
        (numero, cliente_id),
    ).fetchone()
    if linha is None:
        return Veredito(Resultado.PEDIDO_NAO_ENCONTRADO, [])
    if linha["status"] in SEM_ENTREGA:
        return Veredito(Resultado.NAO_SE_APLICA, [], avisos=[SEM_ENTREGA[linha["status"]]])
    # The channel only matters after confirming that the order exists and belongs to the customer.
    if motivo == Motivo.ARREPENDIMENTO and canal is None:
        return Veredito(Resultado.FALTAM_DADOS, [], ["canal_de_compra"])
    if motivo == Motivo.ARREPENDIMENTO and canal == Canal.PRESENCIAL:
        return Veredito(Resultado.NAO_SE_APLICA, [], avisos=[AVISO_SEM_ARREPENDIMENTO_PRESENCIAL])
    compra = date.fromisoformat(linha["order_date"])
    # Without an actual delivery date in the data (DQ-17), receipt is the estimated delivery.
    recebimento = date.fromisoformat(linha["estimated_delivery"])
    if motivo == Motivo.DEFEITO:
        regras = [
            _regra("troca_por_defeito", compra, PRAZO_DE_TROCA_POR_DEFEITO_EM_DIAS, hoje),
            _regra("garantia_legal", recebimento, PRAZO_DA_GARANTIA_LEGAL_EM_DIAS, hoje),
        ]
    elif motivo == Motivo.PREFERENCIA:
        regras = [_regra("troca_por_preferencia", recebimento, PRAZO_DE_TROCA_POR_PREFERENCIA_EM_DIAS, hoje)]
    else:
        regras = [_regra("arrependimento", recebimento, PRAZO_DE_ARREPENDIMENTO_EM_DIAS, hoje)]
    avisos = [AVISO_DE_APROXIMACAO, AVISO_DE_ANALISE]
    if recebimento > hoje:
        avisos.insert(0, AVISO_AINDA_NAO_CHEGOU)
    dentro = any(r.resultado == Resultado.DENTRO_DO_PRAZO for r in regras)
    return Veredito(
        Resultado.DENTRO_DO_PRAZO if dentro else Resultado.FORA_DO_PRAZO,
        regras,
        avisos=avisos,
        data_aproximada=True,
        data_de_recebimento=formatar_data(recebimento),
        data_de_referencia=formatar_data(hoje),
    )


def _regra(nome: str, inicio: date, dias: int, hoje: date) -> Regra:
    limite = inicio + timedelta(days=dias)
    resultado = Resultado.DENTRO_DO_PRAZO if hoje <= limite else Resultado.FORA_DO_PRAZO
    return Regra(nome, resultado, formatar_data(limite))
