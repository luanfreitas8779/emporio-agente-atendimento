import sqlite3
from datetime import datetime, timedelta
from enum import StrEnum

from src.memory import agora
from src.phone import normalizar_telefone


MAX_RESUMO = 500
# O modelo reescreve o resumo a cada tentativa; sem a janela o mesmo caso viraria vários registros.
JANELA_DE_REPETICAO = timedelta(hours=1)


class Motivo(StrEnum):
    RECLAMACAO = "reclamacao"
    SEM_RESPOSTA_SEGURA = "sem_resposta_segura"
    ATENDENTE_SOLICITADO = "atendente_solicitado"


class Resultado(StrEnum):
    REGISTRADO = "registrado"
    RESUMO_INVALIDO = "resumo_invalido"
    JA_REGISTRADO = "ja_registrado"
    TELEFONE_INVALIDO = "telefone_invalido"


def registrar(conexao: sqlite3.Connection, telefone: str, motivo: Motivo, resumo: str) -> Resultado:
    chave = normalizar_telefone(telefone)
    if chave is None:
        return Resultado.TELEFONE_INVALIDO
    resumo = resumo.strip()[:MAX_RESUMO].strip()
    if not resumo:
        return Resultado.RESUMO_INVALIDO
    repetido = conexao.execute(
        "SELECT 1 FROM handoffs WHERE phone = ? AND reason = ? AND (summary = ? OR created_at >= ?)",
        (chave, motivo, resumo, (datetime.fromisoformat(agora()) - JANELA_DE_REPETICAO).isoformat()),
    ).fetchone()
    if repetido:
        return Resultado.JA_REGISTRADO
    conexao.execute(
        "INSERT INTO handoffs (phone, reason, summary, created_at) VALUES (?, ?, ?, ?)",
        (chave, motivo, resumo, agora()),
    )
    conexao.commit()
    return Resultado.REGISTRADO
