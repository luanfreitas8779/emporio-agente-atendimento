import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.exceptions import ModelAPIError

from src import config


def _violacao(corpo: object) -> dict:
    """Primeira violação de cota do corpo do erro do Gemini, ou um dicionário vazio."""
    erro = corpo.get("error", {}) if isinstance(corpo, dict) else {}
    for detalhe in erro.get("details", []):
        for violacao in detalhe.get("violations", []):
            return violacao
    return {}


def registrar_limite(erro: ModelAPIError, caminho: Path | None = None) -> None:
    """Acrescenta uma linha JSON com o limite que o provedor informou; campos ausentes ficam nulos."""
    caminho = caminho or config.CAMINHO_LOG_DE_LIMITES
    violacao = _violacao(erro.body)
    evento = {
        "data": datetime.now(timezone.utc).isoformat(),
        "modelo": erro.model_name,
        "status": getattr(erro, "status_code", None),
        "retry_after": erro.retry_after,
        "metrica": violacao.get("quotaMetric"),
        "cota": violacao.get("quotaId"),
        "limite": violacao.get("quotaValue"),
    }
    with caminho.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")


def e_limite_diario(erro: ModelAPIError) -> bool:
    """A cota por dia só volta no dia seguinte, então esperar alguns segundos não resolve."""
    return "PerDay" in (_violacao(erro.body).get("quotaId") or "")


def espera_indicada(erro: ModelAPIError) -> float | None:
    """Segundos do `retryDelay` ("27s") no corpo do erro, ou None se ausente ou ilegível."""
    erro_do_corpo = erro.body.get("error", {}) if isinstance(erro.body, dict) else {}
    for detalhe in erro_do_corpo.get("details", []):
        atraso = detalhe.get("retryDelay")
        if isinstance(atraso, str) and atraso.endswith("s"):
            try:
                return float(atraso[:-1])
            except ValueError:
                return None
    return None
