import re
import sqlite3
from datetime import datetime, timedelta
from enum import StrEnum

from src.catalog import normalize
from src.memory import agora
from src.phone import normalize_phone


MAX_RESUMO = 500
# The model rewrites the summary on each attempt; without the window the same case would become several records.
JANELA_DE_REPETICAO = timedelta(hours=1)


# Words that appear in almost every summary and do not say what the subject is.
PALAVRAS_SEM_ASSUNTO = {
    "cliente", "pedido", "reclama", "reclamou", "reclamacao", "reclamando", "relata", "informa",
    "afirma", "insatisfeito", "insatisfeita", "outro", "outra",
}


def _assunto(resumo: str) -> set[str]:
    """Words that identify the case: those with 5 letters or more, without the common ones, and the numbers."""
    words = re.findall(r"\w+", normalize(resumo))
    return {p for p in words if (len(p) >= 5 or p.isdigit()) and p not in PALAVRAS_SEM_ASSUNTO}


def _mesmo_assunto(anterior: str, resumo: str) -> bool:
    """Two complaint summaries deal with the same case when they cite the same order or, without
    orders cited in both, share a subject word."""
    assunto_anterior, assunto = _assunto(anterior), _assunto(resumo)
    pedidos_anterior = {p for p in assunto_anterior if p.isdigit()}
    order_list = {p for p in assunto if p.isdigit()}
    if pedidos_anterior and order_list:
        return bool(pedidos_anterior & order_list)
    return bool(assunto_anterior & assunto)


class Reason(StrEnum):
    RECLAMACAO = "reclamacao"
    SEM_RESPOSTA_SEGURA = "sem_resposta_segura"
    ATENDENTE_SOLICITADO = "atendente_solicitado"


class Result(StrEnum):
    REGISTRADO = "registrado"
    RESUMO_INVALIDO = "resumo_invalido"
    JA_REGISTRADO = "ja_registrado"
    TELEFONE_INVALIDO = "telefone_invalido"


def registrar(connection: sqlite3.Connection, phone: str, reason: Reason, resumo: str) -> Result:
    key = normalize_phone(phone)
    if key is None:
        return Result.TELEFONE_INVALIDO
    resumo = resumo.strip()[:MAX_RESUMO].strip()
    if not resumo:
        return Result.RESUMO_INVALIDO
    corte = datetime.fromisoformat(agora()) - JANELA_DE_REPETICAO
    anteriores = connection.execute(
        "SELECT summary, created_at FROM handoffs WHERE phone = ? AND reason = ?", (key, reason)
    ).fetchall()
    # The same summary is a repeat at any time; another summary only within the window and, for a
    # complaint, only if it is about the same subject.
    repetido = any(
        anterior == resumo
        or (
            datetime.fromisoformat(criado_em) >= corte
            and (reason != Reason.RECLAMACAO or _mesmo_assunto(anterior, resumo))
        )
        for anterior, criado_em in anteriores
    )
    if repetido:
        return Result.JA_REGISTRADO
    connection.execute(
        "INSERT INTO handoffs (phone, reason, summary, created_at) VALUES (?, ?, ?, ?)",
        (key, reason, resumo, agora()),
    )
    connection.commit()
    return Result.REGISTRADO
