from datetime import date


def formatar_data(data: date | str | None) -> str | None:
    """Datas apresentadas ao cliente saem em código, no formato brasileiro (ADR-012)."""
    if data is None:
        return None
    if isinstance(data, str):
        data = date.fromisoformat(data)
    return data.strftime("%d/%m/%Y")


DIAS_DA_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def dia_da_semana(data: date) -> str:
    return DIAS_DA_SEMANA[data.weekday()]
