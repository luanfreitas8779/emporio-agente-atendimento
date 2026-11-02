import re
import sqlite3
from datetime import datetime, timedelta
from enum import StrEnum

from src.catalog import normalizar
from src.memory import agora
from src.phone import normalizar_telefone


MAX_RESUMO = 500
# O modelo reescreve o resumo a cada tentativa; sem a janela o mesmo caso viraria vários registros.
JANELA_DE_REPETICAO = timedelta(hours=1)


# Palavras que aparecem em quase todo resumo e não dizem qual é o assunto.
PALAVRAS_SEM_ASSUNTO = {
    "cliente", "pedido", "reclama", "reclamou", "reclamacao", "reclamando", "relata", "informa",
    "afirma", "insatisfeito", "insatisfeita", "outro", "outra",
}


def _assunto(resumo: str) -> set[str]:
    """Palavras que identificam o caso: as de 5 letras ou mais, sem as comuns, e os números."""
    palavras = re.findall(r"\w+", normalizar(resumo))
    return {p for p in palavras if (len(p) >= 5 or p.isdigit()) and p not in PALAVRAS_SEM_ASSUNTO}


def _mesmo_assunto(anterior: str, resumo: str) -> bool:
    """Dois resumos de reclamação tratam do mesmo caso quando citam o mesmo pedido ou, sem
    pedidos citados nos dois, compartilham alguma palavra do assunto."""
    assunto_anterior, assunto = _assunto(anterior), _assunto(resumo)
    pedidos_anterior = {p for p in assunto_anterior if p.isdigit()}
    pedidos = {p for p in assunto if p.isdigit()}
    if pedidos_anterior and pedidos:
        return bool(pedidos_anterior & pedidos)
    return bool(assunto_anterior & assunto)


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
    corte = datetime.fromisoformat(agora()) - JANELA_DE_REPETICAO
    anteriores = conexao.execute(
        "SELECT summary, created_at FROM handoffs WHERE phone = ? AND reason = ?", (chave, motivo)
    ).fetchall()
    # O mesmo resumo é repetido a qualquer tempo; outro resumo só dentro da janela e, numa
    # reclamação, só se for sobre o mesmo assunto.
    repetido = any(
        anterior == resumo
        or (
            datetime.fromisoformat(criado_em) >= corte
            and (motivo != Motivo.RECLAMACAO or _mesmo_assunto(anterior, resumo))
        )
        for anterior, criado_em in anteriores
    )
    if repetido:
        return Resultado.JA_REGISTRADO
    conexao.execute(
        "INSERT INTO handoffs (phone, reason, summary, created_at) VALUES (?, ?, ?, ?)",
        (chave, motivo, resumo, agora()),
    )
    conexao.commit()
    return Resultado.REGISTRADO
