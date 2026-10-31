import sqlite3
from datetime import date, timedelta
from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass as dataclass_pydantic

from src.datas import formatar_data

PRAZO_DE_ARREPENDIMENTO_EM_DIAS = 7


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
        "SELECT estimated_delivery FROM orders WHERE order_id = ? AND customer_id = ?",
        (numero, cliente_id),
    ).fetchone()
    # Sem data real de entrega nos dados (DQ-17), o recebimento é a entrega estimada.
    recebimento = date.fromisoformat(linha["estimated_delivery"])
    limite = recebimento + timedelta(days=PRAZO_DE_ARREPENDIMENTO_EM_DIAS)
    resultado = Resultado.DENTRO_DO_PRAZO if hoje <= limite else Resultado.FORA_DO_PRAZO
    return Veredito(resultado, [Regra("arrependimento", resultado, formatar_data(limite))])
