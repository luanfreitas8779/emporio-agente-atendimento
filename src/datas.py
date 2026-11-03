from datetime import date


def formatar_data(data: date | str | None) -> str | None:
    """Dates shown to the customer are formatted in code, in the Brazilian format (ADR-012)."""
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
