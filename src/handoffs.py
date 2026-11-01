import sqlite3
from enum import StrEnum

from src.memory import agora
from src.phone import normalizar_telefone


class Motivo(StrEnum):
    RECLAMACAO = "reclamacao"
    SEM_RESPOSTA_SEGURA = "sem_resposta_segura"
    ATENDENTE_SOLICITADO = "atendente_solicitado"


class Resultado(StrEnum):
    REGISTRADO = "registrado"
    RESUMO_INVALIDO = "resumo_invalido"


def registrar(conexao: sqlite3.Connection, telefone: str, motivo: Motivo, resumo: str) -> Resultado:
    resumo = resumo.strip()
    if not resumo:
        return Resultado.RESUMO_INVALIDO
    conexao.execute(
        "INSERT INTO handoffs (phone, reason, summary, created_at) VALUES (?, ?, ?, ?)",
        (normalizar_telefone(telefone), motivo, resumo, agora()),
    )
    conexao.commit()
    return Resultado.REGISTRADO
