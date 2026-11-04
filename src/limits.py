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
    """First quota violation in the Gemini error body, or an empty dictionary."""
    return next(iter(_violacoes(corpo)), {})


def registrar_limite(erro: ModelAPIError, path: Path | None = None) -> None:
    """Appends a JSON line with the limit the provider reported; missing fields are null."""
    path = path or config.CAMINHO_LOG_DE_LIMITES
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
    with path.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")


def e_limite_diario(erro: ModelAPIError) -> bool:
    """The daily quota only comes back the next day, so waiting a few seconds does not help."""
    return any("PerDay" in (v.get("quotaId") or "") for v in _violacoes(erro.body))


def espera_indicada(erro: ModelAPIError) -> float | None:
    """Seconds of the `retryDelay` ("27s") in the error body, or None if missing or unreadable."""
    for detalhe in _detalhes(erro.body):
        atraso = detalhe.get("retryDelay")
        if isinstance(atraso, str) and atraso.endswith("s"):
            try:
                return float(atraso[:-1])
            except ValueError:
                return None
    return None
