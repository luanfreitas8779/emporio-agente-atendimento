import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.exceptions import ModelAPIError

from src import config


def _details(body: object) -> list[dict]:
    error = body.get("error", {}) if isinstance(body, dict) else {}
    return [d for d in error.get("details", []) if isinstance(d, dict)]


def _violations(body: object) -> list[dict]:
    return [v for d in _details(body) for v in d.get("violations", [])]


def _violation(body: object) -> dict:
    """First quota violation in the Gemini error body, or an empty dictionary."""
    return next(iter(_violations(body)), {})


def log_limit(error: ModelAPIError, path: Path | None = None) -> None:
    """Appends a JSON line with the limit the provider reported; missing fields are null."""
    path = path or config.LIMITS_LOG_PATH
    violation = _violation(error.body)
    event = {
        "date": datetime.now(timezone.utc).isoformat(),
        "model": error.model_name,
        "status": getattr(error, "status_code", None),
        "retry_after": error.retry_after,
        "metric": violation.get("quotaMetric"),
        "quota": violation.get("quotaId"),
        "limit": violation.get("quotaValue"),
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def is_daily_limit(error: ModelAPIError) -> bool:
    """The daily quota only comes back the next day, so waiting a few seconds does not help."""
    return any("PerDay" in (v.get("quotaId") or "") for v in _violations(error.body))


def indicated_wait(error: ModelAPIError) -> float | None:
    """Seconds of the `retryDelay` ("27s") in the error body, or None if missing or unreadable."""
    for detail in _details(error.body):
        delay = detail.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None
