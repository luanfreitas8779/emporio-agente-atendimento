import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.exceptions import ModelAPIError

from src import config


def _detalhes(corpo: object) -> list[dict]:
    erro = corpo.get("error", {}) if isinstance(corpo, dict) else {}
    return [d for d in erro.get("details", []) if isinstance(d, dict)]


def _violacoes(corpo: object) -> list[dict]:
    return [v for d in _detalhes(corpo) for v in d.get("violations", [])]


def _violacao(corpo: object) -> dict:
    """Primeira violação de cota do corpo do erro do Gemini, ou um dicionário vazio."""
    return next(iter(_violacoes(corpo)), {})


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
    return any("PerDay" in (v.get("quotaId") or "") for v in _violacoes(erro.body))


def espera_indicada(erro: ModelAPIError) -> float | None:
    """Segundos do `retryDelay` ("27s") no corpo do erro, ou None se ausente ou ilegível."""
    for detalhe in _detalhes(erro.body):
        atraso = detalhe.get("retryDelay")
        if isinstance(atraso, str) and atraso.endswith("s"):
            try:
                return float(atraso[:-1])
            except ValueError:
                return None
    return None
