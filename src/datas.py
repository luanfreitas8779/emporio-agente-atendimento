from datetime import date


def formatar_data(data: date | str | None) -> str | None:
    """Datas apresentadas ao cliente saem em código, no formato brasileiro (ADR-012)."""
    if data is None:
        return None
    if isinstance(data, str):
        data = date.fromisoformat(data)
    return data.strftime("%d/%m/%Y")
