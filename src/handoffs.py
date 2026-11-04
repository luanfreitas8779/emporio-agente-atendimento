import re
import sqlite3
from datetime import datetime, timedelta
from enum import StrEnum

from src.catalog import normalize
from src.memory import now_iso
from src.phone import normalize_phone


MAX_SUMMARY = 500
# The model rewrites the summary on each attempt; without the window the same case would become several records.
REPEAT_WINDOW = timedelta(hours=1)


# Words that appear in almost every summary and do not say what the subject is.
NON_SUBJECT_WORDS = {
    "cliente", "pedido", "reclama", "reclamou", "reclamacao", "reclamando", "relata", "informa",
    "afirma", "insatisfeito", "insatisfeita", "outro", "outra",
}


def _subject(summary: str) -> set[str]:
    """Words that identify the case: those with 5 letters or more, without the common ones, and the numbers."""
    words = re.findall(r"\w+", normalize(summary))
    return {p for p in words if (len(p) >= 5 or p.isdigit()) and p not in NON_SUBJECT_WORDS}


def _same_subject(previous: str, summary: str) -> bool:
    """Two complaint summaries deal with the same case when they cite the same order or, without
    orders cited in both, share a subject word."""
    previous_subject, subject = _subject(previous), _subject(summary)
    previous_orders = {p for p in previous_subject if p.isdigit()}
    order_list = {p for p in subject if p.isdigit()}
    if previous_orders and order_list:
        return bool(previous_orders & order_list)
    return bool(previous_subject & subject)


class Reason(StrEnum):
    COMPLAINT = "reclamacao"
    NO_SAFE_ANSWER = "sem_resposta_segura"
    AGENT_REQUESTED = "atendente_solicitado"


class Result(StrEnum):
    REGISTERED = "registrado"
    INVALID_SUMMARY = "resumo_invalido"
    ALREADY_REGISTERED = "ja_registrado"
    INVALID_PHONE = "telefone_invalido"


def register(connection: sqlite3.Connection, phone: str, reason: Reason, summary: str) -> Result:
    key = normalize_phone(phone)
    if key is None:
        return Result.INVALID_PHONE
    summary = summary.strip()[:MAX_SUMMARY].strip()
    if not summary:
        return Result.INVALID_SUMMARY
    cut = datetime.fromisoformat(now_iso()) - REPEAT_WINDOW
    previous_ones = connection.execute(
        "SELECT summary, created_at FROM handoffs WHERE phone = ? AND reason = ?", (key, reason)
    ).fetchall()
    # The same summary is a repeat at any time; another summary only within the window and, for a
    # complaint, only if it is about the same subject.
    repeated = any(
        previous == summary
        or (
            datetime.fromisoformat(created_at) >= cut
            and (reason != Reason.COMPLAINT or _same_subject(previous, summary))
        )
        for previous, created_at in previous_ones
    )
    if repeated:
        return Result.ALREADY_REGISTERED
    connection.execute(
        "INSERT INTO handoffs (phone, reason, summary, created_at) VALUES (?, ?, ?, ?)",
        (key, reason, summary, now_iso()),
    )
    connection.commit()
    return Result.REGISTERED
